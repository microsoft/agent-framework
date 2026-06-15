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


@_requires_powerfx
class TestPowerFxStillWorks:
    def test_simple_powerfx_expression_evaluates(self, state: DeclarativeWorkflowState) -> None:
        state.set("Local.x", 6)
        state.set("Local.y", 7)
        assert state.eval("=Local.x * Local.y") == 42

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

    def test_message_text_eval_preserves_user_temp_value(self, state: DeclarativeWorkflowState) -> None:
        """User state at the temp key path survives a long MessageText eval."""
        long_text = "A" * 600
        state.set("Local._TempMessageText0", "user-important-value")
        state.set(
            "Local.Messages",
            [{"text": long_text, "contents": [{"type": "text", "text": long_text}]}],
        )

        result = state.eval("=Upper(MessageText(Local.Messages))")
        assert result == "A" * 600
        assert state.get("Local._TempMessageText0") == "user-important-value"

    def test_message_text_eval_cleans_up_on_powerfx_failure(
        self,
        state: DeclarativeWorkflowState,
        monkeypatch,
    ) -> None:
        """Temp key is removed even when PowerFx evaluation raises."""
        from agent_framework_declarative._workflows import _declarative_base as base

        class _FailingEngine:
            def eval(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

        monkeypatch.setattr(base, "Engine", _FailingEngine)

        long_text = "A" * 600
        state.set(
            "Local.Messages",
            [{"text": long_text, "contents": [{"type": "text", "text": long_text}]}],
        )

        with pytest.raises(RuntimeError, match="boom"):
            state.eval("=Upper(MessageText(Local.Messages))")

        local = state.get_state_data().get("Local", {})
        remaining = sorted(k for k in local if k.startswith("_TempMessageText"))
        assert not remaining, f"Temporary keys remain in Local after PowerFx failure: {remaining}"
