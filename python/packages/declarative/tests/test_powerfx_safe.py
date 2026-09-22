# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for ``_make_powerfx_safe``.

PowerFx (via pythonnet) only accepts plain primitives, dicts, and lists.
``Enum`` instances - especially ``str``- and ``int``-subclass enums like
MAF's ``MessageRole`` - silently pass ``isinstance(v, str)`` /
``isinstance(v, int)`` checks but blow up later inside pythonnet with
``'<EnumName>' value cannot be converted to System.<X>``. These tests
pin down the Enum coercion branch so we don't regress that interop fix.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, IntEnum
from typing import Any
from unittest.mock import MagicMock

import pytest
from agent_framework._workflows._state import State

from agent_framework_declarative._workflows import _declarative_base as base
from agent_framework_declarative._workflows import _powerfx_limits as limits
from agent_framework_declarative._workflows import _state as legacy
from agent_framework_declarative._workflows._declarative_base import _make_powerfx_safe


class _StrRole(str, Enum):
    USER = "user"
    SYSTEM = "system"


class _IntCode(IntEnum):
    ONE = 1
    TWO = 2


class _PlainEnum(Enum):
    X = "x"
    Y = 42


def test_str_subclass_enum_reduces_to_str():
    assert _make_powerfx_safe(_StrRole.USER) == "user"
    assert type(_make_powerfx_safe(_StrRole.USER)) is str


def test_int_subclass_enum_reduces_to_int():
    assert _make_powerfx_safe(_IntCode.ONE) == 1
    assert type(_make_powerfx_safe(_IntCode.ONE)) is int


def test_plain_enum_reduces_to_underlying_value():
    assert _make_powerfx_safe(_PlainEnum.X) == "x"
    assert _make_powerfx_safe(_PlainEnum.Y) == 42


def test_enum_inside_dict_is_coerced():
    safe = _make_powerfx_safe({"role": _StrRole.USER, "code": _IntCode.TWO})
    assert safe == {"role": "user", "code": 2}
    assert type(safe["role"]) is str
    assert type(safe["code"]) is int


def test_enum_inside_list_is_coerced():
    safe = _make_powerfx_safe([_StrRole.USER, _IntCode.ONE])
    assert safe == ["user", 1]
    assert type(safe[0]) is str
    assert type(safe[1]) is int


@pytest.mark.parametrize("committed", [False, True])
def test_state_depth_is_checked_before_copy_and_engine_dispatch(
    monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    """Even an expression without state references must respect the snapshot budget."""
    state = State()
    workflow_state = base.DeclarativeWorkflowState(state)
    workflow_state.initialize()
    data = workflow_state.get_state_data()
    nested: Any = "leaf"
    for _ in range(65):
        nested = [nested]
    data["Local"]["unused"] = nested
    state.set(base.DECLARATIVE_STATE_KEY, data)
    if committed:
        state.commit()

    engine = MagicMock()
    monkeypatch.setattr(base, "Engine", engine)
    deepcopy = MagicMock(side_effect=AssertionError("State was copied before validating its budget"))
    monkeypatch.setattr("agent_framework._workflows._state.copy.deepcopy", deepcopy)

    with pytest.raises(ValueError, match="PowerFx state.*depth"):
        workflow_state.eval("=1 + 1")

    deepcopy.assert_not_called()
    engine.assert_not_called()


@pytest.mark.parametrize(
    ("setting", "limit", "accepted", "rejected", "reason"),
    [
        ("_MAX_POWERFX_STATE_DEPTH", 2, [[0]], [[[0]]], "depth"),
        ("_MAX_POWERFX_STATE_NODES", 3, [0, 1], [0, 1, 2], "node"),
        ("_MAX_POWERFX_STATE_TEXT_SIZE", 4, {"ab": "cd"}, {"ab": "cde"}, "text size"),
    ],
)
def test_budget_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    limit: int,
    accepted: Any,
    rejected: Any,
    reason: str,
) -> None:
    monkeypatch.setattr(limits, setting, limit)
    assert _make_powerfx_safe(accepted) == accepted
    with pytest.raises(ValueError, match=f"PowerFx state.*{reason}"):
        _make_powerfx_safe(rejected)


def test_shared_values_count_at_each_emitted_occurrence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_NODES", 5)
    shared = [1]
    assert _make_powerfx_safe([shared, shared]) == [[1], [1]]
    with pytest.raises(ValueError, match="node budget"):
        _make_powerfx_safe([shared, shared, shared])


@pytest.mark.parametrize("kind", ["list", "dict", "object"])
def test_cycles_are_rejected(kind: str) -> None:
    if kind == "list":
        value: Any = []
        value.append(value)
    elif kind == "dict":
        value = {}
        value["self"] = value
    else:

        @dataclass
        class Record:
            child: Any = None

        value = Record()
        value.child = value
    with pytest.raises(ValueError, match="PowerFx state contains a cycle"):
        _make_powerfx_safe(value)


def test_conversion_preserves_normal_data() -> None:
    @dataclass
    class Record:
        role: _StrRole
        score: Decimal

    assert _make_powerfx_safe({"message": Record(_StrRole.USER, Decimal("1.25")), 7: [None, True]}) == {
        "message": {"role": "user", "score": Decimal("1.25")},
        "7": [None, True],
    }


def test_validated_snapshot_preserves_copy_isolation() -> None:
    store = State()
    state = base.DeclarativeWorkflowState(store)
    state.initialize({"question": "hello"})
    state.set("Local.items", [1, 2])
    store.commit()

    snapshot = state.get_state_data()
    snapshot["Local"]["items"].append(3)
    assert state.get("Local.items") == [1, 2]
    state.set_state_data(snapshot)
    assert state.get("Local.items") == [1, 2, 3]
    store.discard()
    assert state.get("Local.items") == [1, 2]


def test_budget_resets_between_conversions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_NODES", 2)
    assert _make_powerfx_safe([1]) == [1]
    assert _make_powerfx_safe([2]) == [2]


def test_configuration_is_checked_before_snapshotting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_TEXT_SIZE", 3)
    with pytest.raises(ValueError, match="text size budget"):
        base.DeclarativeEnvConfig(values={"name": "value"})


def test_symbol_logging_does_not_format_state_values() -> None:
    class Record:
        def __str__(self) -> str:
            raise AssertionError("Symbol logging must not format whole values")

    state = base.DeclarativeWorkflowState(State())
    state.initialize()
    state.set("Local.record", Record())

    assert state._to_powerfx_symbols()["Local"]["record"] == {}


def test_converted_strings_consume_one_aggregate_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[None] = []

    class Text:
        __slots__ = ()

        def __str__(self) -> str:
            calls.append(None)
            return "text"

    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_TEXT_SIZE", 7)
    with pytest.raises(ValueError, match="text size budget"):
        _make_powerfx_safe([Text(), Text(), Text()])
    assert len(calls) == 2


def test_state_write_rejection_preserves_previous_value(monkeypatch: pytest.MonkeyPatch) -> None:
    state = base.DeclarativeWorkflowState(State())
    state.initialize()
    state.set("Local.value", "before")
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_DEPTH", 5)

    with pytest.raises(ValueError, match="depth budget"):
        state.set("Local.value", [[[[0]]]])

    assert state.get("Local.value") == "before"


def test_symbol_aliases_share_the_output_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    state = base.DeclarativeWorkflowState(State())
    state.initialize({"value": "ordinary input"})
    data = state.get_state_data()
    size = limits._PowerFxStateBudget()
    # Capture the exact small fixture's text use without depending on generated IDs.
    original_consume = limits._PowerFxStateBudget.consume

    def consume(self: Any, item: Any, depth: int) -> None:
        original_consume(self, item, depth)
        size.text_size = self.text_size

    monkeypatch.setattr(limits._PowerFxStateBudget, "consume", consume)
    limits._validate_powerfx_state(data)
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_TEXT_SIZE", size.text_size)

    with pytest.raises(ValueError, match="text size budget"):
        state._to_powerfx_symbols()


def test_message_text_cleanup_after_symbol_budget_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    state = base.DeclarativeWorkflowState(State())
    state.initialize()
    state.set("Local._TempMessageText0", "original")
    before = state.get_state_data()
    monkeypatch.setattr(state, "_eval_and_replace_message_text", lambda expression: "hello")
    monkeypatch.setattr(state, "_to_powerfx_symbols", MagicMock(side_effect=limits._PowerFxStateLimitError("budget")))
    monkeypatch.setattr(base, "Engine", MagicMock())

    with pytest.raises(ValueError, match="budget"):
        state.eval("=Upper(MessageText(Local.Messages))")

    assert state.get_state_data() == before


def test_rejected_temporary_binding_preserves_state(monkeypatch: pytest.MonkeyPatch) -> None:
    state = base.DeclarativeWorkflowState(State())
    state.initialize()
    state.set("Local._TempMessageText0", "original")
    before = state.get_state_data()
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_TEXT_SIZE", 400)
    limits._validate_powerfx_state(before)
    monkeypatch.setattr(state, "_eval_and_replace_message_text", lambda expression: "x" * 401)
    engine = MagicMock()
    monkeypatch.setattr(base, "Engine", engine)

    with pytest.raises(ValueError, match="text size budget"):
        state.eval("=Upper(MessageText(Local.Messages))")

    assert state.get_state_data() == before
    engine.assert_not_called()


def test_legacy_budget_failure_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    state = legacy.WorkflowState()
    state.set("Local.values", [1, 2, 3])
    engine = MagicMock()
    fallback = MagicMock()
    monkeypatch.setattr(legacy, "_powerfx_engine", engine)
    monkeypatch.setattr(state, "_eval_simple", fallback)
    monkeypatch.setattr(limits, "_MAX_POWERFX_STATE_NODES", 3)

    with pytest.raises(ValueError, match="node budget"):
        state.eval("=1 + 1")

    engine.eval.assert_not_called()
    fallback.assert_not_called()
