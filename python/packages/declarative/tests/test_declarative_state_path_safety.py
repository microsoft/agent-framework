# Copyright (c) Microsoft. All rights reserved.
# pyright: reportUnknownParameterType=false, reportUnknownArgumentType=false
# pyright: reportMissingParameterType=false, reportUnknownMemberType=false
# pyright: reportPrivateUsage=false, reportUnknownVariableType=false
# pyright: reportGeneralTypeIssues=false

"""Path-segment validation tests for DeclarativeWorkflowState.

Path segments handed to ``get``/``set``/``append`` and ``{Variable.Path}``
placeholders in ``interpolate_string`` are subject to three distinct rules
that this module pins:

- **Empty segments** (e.g. ``""``, ``"Local."``, ``"Local..foo"``) are rejected
  by all of ``get``/``set``/``append`` and ``interpolate_string``. ``get`` and
  ``interpolate_string`` return their default / leave the placeholder literal;
  ``set`` and ``append`` raise ``ValueError``.
- **Object-attribute segments** — segments that ``get`` would resolve via
  ``getattr`` because the parent is a non-dict object — must match the safe
  identifier shape ``[A-Za-z][A-Za-z0-9_]*``. Other shapes are rejected with a
  warning log and the default is returned.
- **Dict-keyed segments** — segments that resolve via dict lookup because the
  parent is a ``dict`` — may use arbitrary non-empty string keys (e.g. UUIDs
  or hyphenated identifiers like ``System.conversations.<uuid>.messages``).
"""

import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_framework_declarative._workflows import DeclarativeWorkflowState

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

_requires_powerfx = pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")


@pytest.fixture
def mock_state() -> MagicMock:
    """In-memory mock for the underlying State."""
    ms = MagicMock()
    ms._data = {}

    def get(key: str, default: Any = None) -> Any:
        return ms._data.get(key, default)

    def set_(key: str, value: Any) -> None:
        ms._data[key] = value

    def has(key: str) -> bool:
        return key in ms._data

    def delete(key: str) -> None:
        ms._data.pop(key, None)

    ms.get = MagicMock(side_effect=get)
    ms.set = MagicMock(side_effect=set_)
    ms.has = MagicMock(side_effect=has)
    ms.delete = MagicMock(side_effect=delete)
    return ms


@pytest.fixture
def state(mock_state: MagicMock) -> DeclarativeWorkflowState:
    s = DeclarativeWorkflowState(mock_state)
    s.initialize()
    return s


@dataclass
class _PlainObj:
    """Non-dict object so ``get`` falls through to attribute access."""

    text: str = "hi"


# ---------------------------------------------------------------------------
# get(): invalid paths return default
# ---------------------------------------------------------------------------


class TestGetRejectsInvalidPaths:
    def test_rejects_dunder_segment_via_attribute_access(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.obj", _PlainObj())
        assert state.get("Local.obj.__class__") is None
        assert state.get("Local.obj.__class__", default="DEF") == "DEF"

    def test_rejects_full_env_exfil_chain(self, state: DeclarativeWorkflowState, monkeypatch) -> None:
        sentinel = "agent-framework-path-safety-sentinel"
        monkeypatch.setenv("AF_PATH_SAFETY_SENTINEL", sentinel)
        state.set("Local.obj", _PlainObj())

        result = state.get("Local.obj.__class__.__init__.__globals__.os.environ")

        assert result is None
        assert sentinel not in str(result)

    def test_rejects_leading_underscore_via_attribute_access(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.obj", _PlainObj())
        assert state.get("Local.obj._private") is None

    def test_rejects_invalid_chars_via_attribute_access(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.obj", _PlainObj())
        assert state.get("Local.obj.text bar") is None
        assert state.get("Local.obj.text-bar") is None

    def test_rejects_empty_path_and_empty_segments(self, state: DeclarativeWorkflowState) -> None:
        assert state.get("") is None
        assert state.get(".") is None
        assert state.get("Local.") is None
        assert state.get(".Local") is None

    def test_warning_logged_on_rejected_attribute_segment(
        self,
        state: DeclarativeWorkflowState,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        state.set("Local.obj", _PlainObj())
        with caplog.at_level(logging.WARNING, logger="agent_framework_declarative._workflows._declarative_base"):
            state.get("Local.obj.__class__")
        assert any("rejecting attribute segment" in r.message for r in caplog.records)

    def test_dict_keyed_dunder_is_not_attribute_access(self, state: DeclarativeWorkflowState) -> None:
        """A literal dunder dict key is harmless because dict lookup never reaches getattr."""
        state.set("Local.bag", {"__class__": "harmless-string"})
        assert state.get("Local.bag.__class__") == "harmless-string"


# ---------------------------------------------------------------------------
# get(): legitimate paths continue to work
# ---------------------------------------------------------------------------


class TestGetAllowsValidPaths:
    def test_underscore_inside_identifier(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.user_input", "ok")
        assert state.get("Local.user_input") == "ok"

    def test_mixed_case_identifiers(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.UserInput", "u1")
        state.set("Local.userInput", "u2")
        assert state.get("Local.UserInput") == "u1"
        assert state.get("Local.userInput") == "u2"

    def test_object_attribute_traversal_still_works(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.msg", _PlainObj(text="hello"))
        assert state.get("Local.msg.text") == "hello"

    def test_nested_dict_traversal_still_works(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.params", {"team": {"name": "alpha"}})
        assert state.get("Local.params.team.name") == "alpha"

    def test_uuid_and_hyphenated_dict_keys_are_allowed(self, state: DeclarativeWorkflowState) -> None:
        """Conversation-id style paths use arbitrary dict keys (UUIDs / hyphens)."""
        conv_id = "eb815014-06f1-4db6-b7c1-304ea135424f"
        state.set(f"System.conversations.{conv_id}.messages", ["m1", "m2"])
        assert state.get(f"System.conversations.{conv_id}.messages") == ["m1", "m2"]


# ---------------------------------------------------------------------------
# set() / append(): dict-keyed operations accept arbitrary string keys
# ---------------------------------------------------------------------------


class TestSetAndAppend:
    def test_set_allows_underscore_inside_identifier(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.user_input", "ok")
        assert state.get("Local.user_input") == "ok"

    def test_set_allows_uuid_and_hyphenated_dict_keys(self, state: DeclarativeWorkflowState) -> None:
        conv_id = "conv-test-1"
        state.set(f"System.conversations.{conv_id}.messages", [])
        assert state.get(f"System.conversations.{conv_id}.messages") == []

    def test_append_allows_uuid_and_hyphenated_dict_keys(self, state: DeclarativeWorkflowState) -> None:
        conv_id = "conv-42"
        state.append(f"System.conversations.{conv_id}.messages", {"role": "user", "text": "hi"})
        msgs = state.get(f"System.conversations.{conv_id}.messages")
        assert msgs == [{"role": "user", "text": "hi"}]

    def test_workflow_inputs_still_read_only(self, state: DeclarativeWorkflowState) -> None:
        with pytest.raises(ValueError, match="read-only"):
            state.set("Workflow.Inputs.x", 1)


# ---------------------------------------------------------------------------
# set() / append(): malformed paths (empty segments) raise ValueError
# ---------------------------------------------------------------------------


class TestSetRejectsInvalidPaths:
    @pytest.mark.parametrize("bad_path", ["", "Local.", "Local..foo", ".Local"])
    def test_set_rejects_empty_segment(self, state: DeclarativeWorkflowState, bad_path: str) -> None:
        with pytest.raises(ValueError, match="empty segments are not allowed"):
            state.set(bad_path, "x")

    @pytest.mark.parametrize("bad_path", ["", "Local.", "Local..foo", ".Local"])
    def test_append_rejects_empty_segment(self, state: DeclarativeWorkflowState, bad_path: str) -> None:
        with pytest.raises(ValueError, match="empty segments are not allowed"):
            state.append(bad_path, "x")

    def test_set_rejection_makes_no_partial_write(self, state: DeclarativeWorkflowState) -> None:
        """Rejected set() must not create an unreachable entry in the state."""
        state.set("Local.user_input", "pre")
        with pytest.raises(ValueError):
            state.set("Local.", "value")
        local = state.get_state_data().get("Local", {})
        assert "" not in local
        assert local == {"user_input": "pre"}
        assert state.get("Local.") is None
        assert state.get("Local.user_input") == "pre"

    def test_append_rejection_makes_no_partial_write(self, state: DeclarativeWorkflowState) -> None:
        """Rejected append() must not create an unreachable entry in the state."""
        state.set("Local.items", ["a"])
        with pytest.raises(ValueError):
            state.append("Local.", "value")
        local = state.get_state_data().get("Local", {})
        assert "" not in local
        assert local == {"items": ["a"]}


# ---------------------------------------------------------------------------
# interpolate_string(): permissive matcher; get() enforces safety
# ---------------------------------------------------------------------------


class TestInterpolateString:
    def test_ignores_dunder_payload(self, state: DeclarativeWorkflowState, monkeypatch) -> None:
        sentinel = "agent-framework-interp-sentinel"
        monkeypatch.setenv("AF_INTERP_SENTINEL", sentinel)
        state.set("Local.obj", _PlainObj())

        out = state.interpolate_string("X={Local.obj.__class__.__init__.__globals__.os.environ}")

        assert sentinel not in out
        assert out == "X="

    def test_unknown_path_reduces_to_empty(self, state: DeclarativeWorkflowState) -> None:
        assert state.interpolate_string("v={Local._private}") == "v="

    @pytest.mark.parametrize(
        "literal",
        ["{foo-bar}", "{Ctrl+C}", "{not:a:path}", "{Local.}", "{}"],
    )
    def test_non_state_braced_tokens_left_literal(self, state: DeclarativeWorkflowState, literal: str) -> None:
        assert state.interpolate_string(f"v={literal}") == f"v={literal}"

    def test_allows_underscore_inside_identifier(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.user_input", "hello")
        assert state.interpolate_string("v={Local.user_input}") == "v=hello"

    def test_resolves_nested_dict_path(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.params", {"team": "alpha"})
        assert state.interpolate_string("team={Local.params.team}") == "team=alpha"

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("_id", "abc123"),
            ("1", "one"),
            ("2025", "year-bucket"),
        ],
    )
    def test_resolves_dict_keyed_segments(self, state: DeclarativeWorkflowState, key: str, value: str) -> None:
        state.set("Local.bag", {key: value})
        assert state.interpolate_string(f"v={{Local.bag.{key}}}") == f"v={value}"

    def test_resolves_uuid_conversation_key(self, state: DeclarativeWorkflowState) -> None:
        conv_id = "eb815014-06f1-4db6-b7c1-304ea135424f"
        state.set(f"System.conversations.{conv_id}.messages", ["hello"])
        out = state.interpolate_string(f"m={{System.conversations.{conv_id}.messages}}")
        assert out == "m=['hello']"

    def test_end_to_end_send_activity_payload_neutralized(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch,
    ) -> None:
        sentinel = "agent-framework-e2e-sentinel"
        monkeypatch.setenv("AF_E2E_SENTINEL", sentinel)
        state.set("Local.toolResult", _PlainObj())

        payload = "{Local.toolResult.__class__.__init__.__globals__.os.environ}"
        evaluated = state.eval_if_expression(payload)
        rendered = state.interpolate_string(evaluated) if isinstance(evaluated, str) else str(evaluated)

        assert sentinel not in rendered
        assert rendered == ""


# ---------------------------------------------------------------------------
# Regressions: PowerFx and internal temp-variable handling still work
# ---------------------------------------------------------------------------


class TestMessageTextPreprocessing:
    def test_replacement_text_is_not_rescanned_as_formula(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []

        def replace_message_text(inner_expr: str) -> str:
            calls.append(inner_expr)
            if inner_expr == "Local.Messages":
                return "MessageText(Local.Secret)"
            pytest.fail(f"Replacement text was re-scanned: {inner_expr}")

        monkeypatch.setattr(state, "_eval_and_replace_message_text", replace_message_text)
        temp_writes: list[tuple[str, Any]] = []

        formula = state._preprocess_custom_functions("Upper(MessageText(Local.Messages))", temp_writes)

        assert formula == "Upper(Local._TempMessageText0)"
        assert calls == ["Local.Messages"]
        assert state.get("Local._TempMessageText0") == "MessageText(Local.Secret)"

    def test_interpolation_preprocesses_only_original_expression_sections(
        self, state: DeclarativeWorkflowState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        message_text = '$"MessageText(Local.Secret) {MessageText(Local.Secret)}"'

        def replace_message_text(inner_expr: str) -> str:
            calls.append(inner_expr)
            return message_text

        monkeypatch.setattr(state, "_eval_and_replace_message_text", replace_message_text)
        temp_writes: list[tuple[str, Any]] = []
        formula = '$"Literal MessageText(Local.Messages) {{MessageText(Local.Messages)}} {MessageText(Local.Messages)}"'

        result = state._preprocess_custom_functions(formula, temp_writes)

        assert result == (
            '$"Literal MessageText(Local.Messages) {{MessageText(Local.Messages)}} {Local._TempMessageText0}"'
        )
        assert calls == ["Local.Messages"]
        assert state.get("Local._TempMessageText0") == message_text
        assert temp_writes == [("Local._TempMessageText0", state._MISSING)]

    def test_message_text_inside_string_literal_is_not_preprocessed(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []

        def replace_message_text(inner_expr: str) -> str:
            calls.append(inner_expr)
            return "hello"

        monkeypatch.setattr(state, "_eval_and_replace_message_text", replace_message_text)

        formula = state._preprocess_custom_functions(
            'Concatenate("MessageText(Local.Secret)", MessageText(Local.Messages))',
            [],
        )

        assert formula == 'Concatenate("MessageText(Local.Secret)", Local._TempMessageText0)'
        assert calls == ["Local.Messages"]

    @pytest.mark.parametrize(
        "formula",
        [
            'Upper("Say ""MessageText(ignored)""")',
            "Upper(Local.'MessageText(ignored)')",
            "Upper(Local.'Archived'' MessageText(ignored)')",
            "1 // MessageText(ignored)",
            "1 // MessageText(ignored)\n + 2",
            "1 // MessageText(ignored)\r + 2",
            "1 // MessageText(ignored)\r\n + 2",
            "/* MessageText(ignored) */ 1",
            "1 /* unmatched ) ' \" MessageText(ignored) */",
        ],
    )
    def test_quoted_tokens_and_comments_are_not_preprocessed(
        self, state: DeclarativeWorkflowState, monkeypatch: pytest.MonkeyPatch, formula: str
    ) -> None:
        def unexpected_call(inner_expr: str) -> str:
            pytest.fail(f"Processed a call inside a quoted token or comment: {inner_expr}")

        monkeypatch.setattr(state, "_eval_and_replace_message_text", unexpected_call)
        temp_writes: list[tuple[str, Any]] = []

        assert state._preprocess_custom_functions(formula, temp_writes) == formula
        assert temp_writes == []

    @pytest.mark.parametrize(
        "inner_expr",
        [
            "Local.'Messages) archive'",
            "Local.'Messages'' ) archive'",
            'If(")""(" = ")""(", Local.Messages, Local.Messages)',
            "Local.Messages /* ) ' \" MessageText(ignored) */",
            "Local.Messages // ) MessageText(ignored)\n",
            "Local.Messages // ) MessageText(ignored)\r",
            "Local.Messages // ) MessageText(ignored)\r\n",
        ],
    )
    def test_call_boundaries_ignore_quoted_tokens_and_comments(
        self, state: DeclarativeWorkflowState, monkeypatch: pytest.MonkeyPatch, inner_expr: str
    ) -> None:
        calls: list[str] = []

        def replace_message_text(expression: str) -> str:
            calls.append(expression)
            return "hello"

        monkeypatch.setattr(state, "_eval_and_replace_message_text", replace_message_text)

        formula = state._preprocess_custom_functions(f"Upper(MessageText({inner_expr}))", [])

        assert formula == "Upper(Local._TempMessageText0)"
        assert calls == [inner_expr]

    @pytest.mark.parametrize(
        ("existing_name", "existing_value"),
        [("_TempMessageText0", None), ("_tempmessagetext0", "user-value")],
    )
    def test_temporary_binding_avoids_existing_names(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch: pytest.MonkeyPatch,
        existing_name: str,
        existing_value: str | None,
    ) -> None:
        state.set(f"Local.{existing_name}", existing_value)
        monkeypatch.setattr(state, "_eval_and_replace_message_text", lambda inner_expr: "hello")
        temp_writes: list[tuple[str, Any]] = []

        formula = state._preprocess_custom_functions("Upper(MessageText(Local.Messages))", temp_writes)

        assert formula == "Upper(Local._TempMessageText1)"
        assert state.get_state_data()["Local"] == {existing_name: existing_value, "_TempMessageText1": "hello"}
        assert temp_writes == [("Local._TempMessageText1", state._MISSING)]

    @pytest.mark.parametrize(
        "reference", ["Local._TempMessageText0", "Local.'_TempMessageText0'", "Local._tempmessagetext0"]
    )
    def test_temporary_binding_avoids_formula_references(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch: pytest.MonkeyPatch,
        reference: str,
    ) -> None:
        monkeypatch.setattr(state, "_eval_and_replace_message_text", lambda inner_expr: "hello")

        formula = state._preprocess_custom_functions(f"Upper(MessageText(Local.Messages) & {reference})", [])

        assert formula == f"Upper(Local._TempMessageText1 & {reference})"
        assert "_TempMessageText0" not in state.get_state_data()["Local"]


@_requires_powerfx
class TestPowerFxStillWorks:
    def test_simple_powerfx_expression_evaluates(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.x", 6)
        state.set("Local.y", 7)
        assert state.eval("=Local.x * Local.y") == 42

    @pytest.mark.parametrize("name", ["Messages) archive", "Messages' ) archive"])
    def test_message_text_argument_with_quoted_identifier(self, state: DeclarativeWorkflowState, name: str) -> None:
        state.set(f"Local.{name}", [{"text": "hello", "contents": [{"type": "text", "text": "hello"}]}])
        quoted_name = name.replace("'", "''")
        original_local = state.get_state_data()["Local"].copy()

        assert state.eval(f"=Upper(MessageText(Local.'{quoted_name}'))") == "HELLO"
        assert state.get_state_data()["Local"] == original_local

    @pytest.mark.parametrize(
        ("formula", "expected"),
        [
            ('$"Message: {MessageText(Local.Messages)}"', "Message: hello"),
            (
                '$"Literal MessageText(ignored) ""{{{MessageText(Local.Messages)}}}"""',
                'Literal MessageText(ignored) "{hello}"',
            ),
            (
                '$"{With({nested: {text: $"Inner {MessageText(Local.Messages)}"}}, nested.text)}"',
                "Inner hello",
            ),
            ('$"{MessageText(Local.Messages)}:{Upper(MessageText(Local.Other))}"', "hello:OTHER"),
            ('$"{/* } MessageText(Local.Secret) */ MessageText(Local.Messages)}"', "hello"),
            (
                (
                    'Upper(MessageText(If($"Literal ) {MessageText(Local.Messages)}" = "Literal ) hello", '
                    "Local.Messages, Local.Other)))"
                ),
                "HELLO",
            ),
        ],
        ids=[
            "basic",
            "literal-text-and-escapes",
            "nested-records-and-interpolation",
            "multiple-expressions",
            "commented-interpolation-delimiter",
            "interpolation-in-function-argument",
        ],
    )
    def test_expression_sections_evaluate_with_powerfx(
        self, state: DeclarativeWorkflowState, formula: str, expected: str
    ) -> None:
        """Only expression sections of interpolated strings may evaluate MessageText calls."""
        state.set("Local.Messages", [{"text": "hello", "contents": [{"type": "text", "text": "hello"}]}])
        state.set("Local.Other", [{"text": "other", "contents": [{"type": "text", "text": "other"}]}])
        original_local = state.get_state_data()["Local"].copy()

        assert state.eval(f"={formula}") == expected
        assert state.get_state_data()["Local"] == original_local

    @pytest.mark.parametrize("name", ["MessageText(ignored)", "Archived' MessageText(ignored)"])
    def test_quoted_identifier_with_function_like_text(self, state: DeclarativeWorkflowState, name: str) -> None:
        state.set(f"Local.{name}", "hello")
        quoted_name = name.replace("'", "''")
        original_local = state.get_state_data()["Local"].copy()

        assert state.eval(f"=Upper(Local.'{quoted_name}')") == "HELLO"
        assert state.get_state_data()["Local"] == original_local

    @pytest.mark.parametrize(
        ("formula", "expected"),
        [
            ("1 // MessageText(1 / 0)", 1),
            ("1 /* MessageText(1 / 0) */", 1),
            ("/* MessageText(1 / 0) */ Upper(MessageText(Local.Messages))", "HELLO"),
            ("// MessageText(1 / 0)\n Upper(MessageText(Local.Messages))", "HELLO"),
            ("Upper(MessageText(Local.Messages /* ) MessageText(1 / 0) */))", "HELLO"),
            ("Upper(MessageText(Local.Messages // ) MessageText(1 / 0)\n))", "HELLO"),
        ],
    )
    def test_message_text_in_comments_is_not_evaluated(
        self, state: DeclarativeWorkflowState, formula: str, expected: str | int
    ) -> None:
        state.set("Local.Messages", [{"text": "hello", "contents": [{"type": "text", "text": "hello"}]}])
        original_local = state.get_state_data()["Local"].copy()

        assert state.eval(f"={formula}") == expected
        assert state.get_state_data()["Local"] == original_local

    def test_internal_temp_message_text_still_works(self, state: DeclarativeWorkflowState) -> None:
        """Long MessageText() results round-trip and the temp key is removed after eval."""
        long_text = "A" * 600
        state.set(
            "Local.Messages",
            [{"text": long_text, "contents": [{"type": "text", "text": long_text}]}],
        )

        result = state.eval("=Upper(MessageText(Local.Messages))")
        assert result == "A" * 600

        local = state.get_state_data().get("Local", {})
        remaining = sorted(k for k in local if k.startswith("_TempMessageText"))
        assert not remaining, f"Temporary keys remain in Local: {remaining}"

    @pytest.mark.parametrize("text", ["hello", "A" * 600], ids=["short", "long"])
    def test_message_text_eval_preserves_user_temp_value(self, state: DeclarativeWorkflowState, text: str) -> None:
        """Existing symbols retain their values during evaluation, not just after cleanup."""
        state.set("Local._TempMessageText0", "user-important-value")
        state.set(
            "Local.Messages",
            [{"text": text, "contents": [{"type": "text", "text": text}]}],
        )
        original_local = state.get_state_data()["Local"].copy()

        result = state.eval("=Upper(Local._TempMessageText0 & MessageText(Local.Messages))")

        assert result == f"USER-IMPORTANT-VALUE{text.upper()}"
        assert state.get_state_data()["Local"] == original_local

    def test_message_text_eval_does_not_define_missing_symbol(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.Messages", [{"text": "hello", "contents": [{"type": "text", "text": "hello"}]}])
        original_local = state.get_state_data()["Local"].copy()

        result = state.eval("=Upper(MessageText(Local.Messages) & Local._TempMessageText0)")

        assert result is None
        assert state.get_state_data()["Local"] == original_local

    @pytest.mark.parametrize(
        "second_argument",
        ["Local.Second", 'If(Upper(MessageText(Local.First)) = "HELLO", Local.Second, Local.First)'],
    )
    def test_multiple_message_text_calls_use_distinct_bindings(
        self, state: DeclarativeWorkflowState, second_argument: str
    ) -> None:
        state.set("Local._TempMessageText0", "prefix")
        state.set("Local._TempMessageText1", "suffix")
        state.set("Local.First", [{"text": "hello", "contents": [{"type": "text", "text": "hello"}]}])
        state.set("Local.Second", [{"text": "world", "contents": [{"type": "text", "text": "world"}]}])
        original_local = state.get_state_data()["Local"].copy()

        result = state.eval(
            "=Upper(Local._TempMessageText0 & MessageText(Local.First) & "
            f"MessageText({second_argument}) & Local._TempMessageText1)"
        )

        assert result == "PREFIXHELLOWORLDSUFFIX"
        assert state.get_state_data()["Local"] == original_local

    @pytest.mark.parametrize("text", ["hello", "A" * 600], ids=["short", "long"])
    def test_message_text_eval_cleans_up_on_powerfx_failure(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch: pytest.MonkeyPatch,
        text: str,
    ) -> None:
        """New temp keys are removed and existing state survives evaluation errors."""
        from agent_framework_declarative._workflows import _declarative_base as base

        class _FailingEngine:
            def eval(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

        monkeypatch.setattr(base, "Engine", _FailingEngine)

        state.set("Local._TempMessageText0", "user-important-value")
        state.set("Local._TempMessageText1", None)
        state.set(
            "Local.Messages",
            [{"text": text, "contents": [{"type": "text", "text": text}]}],
        )
        monkeypatch.setattr(state, "_eval_and_replace_message_text", lambda inner_expr: text)
        original_local = state.get_state_data()["Local"].copy()

        with pytest.raises(RuntimeError, match="boom"):
            state.eval("=Upper(MessageText(Local.Messages))")

        assert state.get_state_data()["Local"] == original_local
