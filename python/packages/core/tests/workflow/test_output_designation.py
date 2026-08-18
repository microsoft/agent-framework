# Copyright (c) Microsoft. All rights reserved.

"""Tests for the ``OutputDesignation`` value type and the ``Workflow.is_terminal_executor``
public predicate that delegates to it.

The states the value type encodes:
- Omitted-selection compatibility: ``outputs=None`` -> every executor is terminal.
- Explicit: disjoint ``outputs`` and ``intermediates`` sets classify listed executors,
  and hide unlisted executors.
"""

from __future__ import annotations

import pytest
from typing_extensions import Never

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowValidationError,
    executor,
)
from agent_framework._workflows._runner_context import InProcRunnerContext
from agent_framework._workflows._workflow import OutputDesignation, Workflow

# ---------------------------------------------------------------------------
# OutputDesignation value type
# ---------------------------------------------------------------------------


def test_omitted_selection_designation_marks_every_executor_as_terminal() -> None:
    designation = OutputDesignation()  # designated defaults to None
    assert designation.outputs is None
    assert designation.is_terminal("anything")
    assert designation.is_terminal("else")
    assert designation.classify("anything") == "output"


def test_strict_empty_designation_marks_no_executor_as_terminal() -> None:
    designation = OutputDesignation(outputs=frozenset())
    assert designation.outputs == frozenset()
    assert not designation.is_terminal("anything")
    assert not designation.is_terminal("else")
    assert designation.classify("anything") is None


def test_strict_designated_set_only_terminal_for_members() -> None:
    designation = OutputDesignation(outputs=frozenset({"alpha", "beta"}), intermediates=frozenset({"gamma"}))
    assert designation.is_terminal("alpha")
    assert designation.is_terminal("beta")
    assert not designation.is_terminal("gamma")
    assert designation.is_intermediate("gamma")
    assert designation.classify("alpha") == "output"
    assert designation.classify("gamma") == "intermediate"
    assert designation.classify("delta") is None


def test_designation_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    designation = OutputDesignation(outputs=frozenset({"alpha"}))
    with pytest.raises(FrozenInstanceError):
        designation.outputs = frozenset({"beta"})  # type: ignore[misc]  # ty: ignore[invalid-assignment]


# ---------------------------------------------------------------------------
# Workflow.is_terminal_executor delegates to the designation
# ---------------------------------------------------------------------------


@executor
async def _emit_one(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
    await ctx.yield_output("hello")


@executor
async def _downstream(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
    await ctx.yield_output("downstream")


def test_is_terminal_executor_omitted_selection_returns_true_for_any_id() -> None:
    """Omitted-selection compatibility behavior: every executor is terminal."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        workflow = WorkflowBuilder(start_executor=_emit_one).build()
    assert workflow.is_terminal_executor(_emit_one.id)
    assert workflow.is_terminal_executor("anything-else")


def test_is_intermediate_executor_explicit_list_returns_true_only_for_designated() -> None:
    """Explicit mode tracks intermediate-designated executors separately."""
    workflow = WorkflowBuilder(start_executor=_emit_one, intermediate_output_from=[_emit_one]).build()
    assert not workflow.is_terminal_executor(_emit_one.id)
    assert not workflow.is_terminal_executor("nope")
    assert workflow.is_intermediate_executor(_emit_one.id)
    assert not workflow.is_intermediate_executor("nope")


def test_is_terminal_executor_strict_list_returns_true_only_for_designated() -> None:
    """Strict mode with a designated list: only listed executors are terminal."""
    workflow = (
        WorkflowBuilder(start_executor=_emit_one, output_from=[_emit_one]).add_edge(_emit_one, _downstream).build()
    )
    assert workflow.is_terminal_executor(_emit_one.id)
    assert not workflow.is_terminal_executor(_downstream.id)


def test_get_output_executors_throws_when_designation_references_missing_executor() -> None:
    workflow = Workflow(
        [],
        {_emit_one.id: _emit_one},
        _emit_one,
        InProcRunnerContext(),
        "test",
        output_from=["missing"],
    )

    with pytest.raises(WorkflowValidationError, match="Output executor 'missing' is not present"):
        workflow.get_output_executors()


def test_get_intermediate_executors_throws_when_designation_references_missing_executor() -> None:
    workflow = Workflow(
        [],
        {_emit_one.id: _emit_one},
        _emit_one,
        InProcRunnerContext(),
        "test",
        output_from=[],
        intermediate_output_from=["missing"],
    )

    with pytest.raises(WorkflowValidationError, match="Intermediate executor 'missing' is not present"):
        workflow.get_intermediate_executors()
