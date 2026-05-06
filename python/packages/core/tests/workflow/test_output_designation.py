# Copyright (c) Microsoft. All rights reserved.

"""Tests for the ``OutputDesignation`` value type and the ``Workflow.is_terminal_executor``
public predicate that delegates to it.

The three states the value type encodes:
- Legacy: ``designated=None`` -> every executor is terminal.
- Strict-empty: ``designated=frozenset()`` -> no executor is terminal.
- Strict-list: ``designated=frozenset({...})`` -> only listed executors are terminal.
"""

from __future__ import annotations

import pytest
from typing_extensions import Never

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework._workflows._workflow import OutputDesignation

# ---------------------------------------------------------------------------
# OutputDesignation value type
# ---------------------------------------------------------------------------


def test_legacy_designation_marks_every_executor_as_terminal() -> None:
    designation = OutputDesignation()  # designated defaults to None
    assert designation.designated is None
    assert designation.is_terminal("anything")
    assert designation.is_terminal("else")


def test_strict_empty_designation_marks_no_executor_as_terminal() -> None:
    designation = OutputDesignation(designated=frozenset())
    assert designation.designated == frozenset()
    assert not designation.is_terminal("anything")
    assert not designation.is_terminal("else")


def test_strict_designated_set_only_terminal_for_members() -> None:
    designation = OutputDesignation(designated=frozenset({"alpha", "beta"}))
    assert designation.is_terminal("alpha")
    assert designation.is_terminal("beta")
    assert not designation.is_terminal("gamma")


def test_designation_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    designation = OutputDesignation(designated=frozenset({"alpha"}))
    with pytest.raises(FrozenInstanceError):
        designation.designated = frozenset({"beta"})  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Workflow.is_terminal_executor delegates to the designation
# ---------------------------------------------------------------------------


@executor
async def _emit_one(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output("hello")


@executor
async def _downstream(message: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output("downstream")


def test_is_terminal_executor_legacy_mode_returns_true_for_any_id() -> None:
    """Legacy mode (output_executors unset): every executor is terminal."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        workflow = WorkflowBuilder(start_executor=_emit_one).build()
    assert workflow.is_terminal_executor(_emit_one.id)
    assert workflow.is_terminal_executor("anything-else")


def test_is_terminal_executor_strict_empty_returns_false_for_every_id() -> None:
    """Strict mode with empty list: no executor is terminal."""
    workflow = WorkflowBuilder(start_executor=_emit_one, output_executors=[]).build()
    assert not workflow.is_terminal_executor(_emit_one.id)
    assert not workflow.is_terminal_executor("nope")


def test_is_terminal_executor_strict_list_returns_true_only_for_designated() -> None:
    """Strict mode with a designated list: only listed executors are terminal."""
    workflow = (
        WorkflowBuilder(start_executor=_emit_one, output_executors=[_emit_one]).add_edge(_emit_one, _downstream).build()
    )
    assert workflow.is_terminal_executor(_emit_one.id)
    assert not workflow.is_terminal_executor(_downstream.id)
