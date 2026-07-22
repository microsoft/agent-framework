# Copyright (c) Microsoft. All rights reserved.

"""Tests for the explicit output/intermediate selection contract on WorkflowBuilder."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from typing_extensions import Never

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowValidationError,
    executor,
)


@executor
async def _emit_one(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
    await ctx.yield_output("hello")


@executor
async def _start(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
    await ctx.yield_output("from-start")
    await ctx.send_message("downstream")


@executor
async def _downstream(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
    await ctx.yield_output("from-downstream")


def test_designation_unset_emits_deprecation_warning() -> None:
    """State A: WorkflowBuilder built without explicit designation warns."""
    with pytest.warns(DeprecationWarning, match="output_from or intermediate_output_from") as warning_info:
        WorkflowBuilder(start_executor=_emit_one).build()
    assert str(warning_info[0].message) == (
        "WorkflowBuilder built without explicit output_from or intermediate_output_from; "
        "every yield_output produces type='output' for compatibility. Pass output_from='all', "
        "output_from=[...], or intermediate_output_from=[...] to opt into explicit designation - "
        "explicit designation will be required in a future version."
    )


@pytest.mark.asyncio
async def test_designation_unset_preserves_compatibility_all_output_behavior() -> None:
    """Omitted designation keeps compatibility all-output behavior while warning."""
    with pytest.warns(DeprecationWarning, match="output_from or intermediate_output_from"):
        workflow = WorkflowBuilder(start_executor=_start).add_edge(_start, _downstream).build()

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == ["from-start", "from-downstream"]
    assert result.get_intermediate_outputs() == []


@pytest.mark.asyncio
async def test_output_from_all_emits_all_outputs_without_omitted_selection_warning() -> None:
    """Explicit all-output designation emits every executor payload without omitted-selection warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        workflow = WorkflowBuilder(start_executor=_start, output_from="all").add_edge(_start, _downstream).build()

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == ["from-start", "from-downstream"]
    assert result.get_intermediate_outputs() == []


@pytest.mark.asyncio
async def test_output_from_all_with_empty_intermediate_list_is_valid() -> None:
    """Explicit all-output plus an empty intermediate list is a concrete no-intermediate selection."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        workflow = (
            WorkflowBuilder(start_executor=_start, output_from="all", intermediate_output_from=[])
            .add_edge(_start, _downstream)
            .build()
        )

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == ["from-start", "from-downstream"]
    assert result.get_intermediate_outputs() == []


@pytest.mark.asyncio
async def test_intermediate_output_from_all_other_marks_non_outputs_as_intermediate() -> None:
    """All-other intermediate designation classifies every non-output executor yield as intermediate."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            output_from=[_downstream],
            intermediate_output_from="all_other",
        )
        .add_edge(_start, _downstream)
        .build()
    )

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == ["from-downstream"]
    assert result.get_intermediate_outputs() == ["from-start"]


@pytest.mark.asyncio
async def test_all_other_streaming_events_mark_non_outputs_as_intermediate() -> None:
    """All-other emits intermediate events while streaming, not just in collected results."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            output_from=[_downstream],
            intermediate_output_from="all_other",
        )
        .add_edge(_start, _downstream)
        .build()
    )
    outputs: list[str] = []
    intermediates: list[str] = []

    async for event in workflow.run([Message(role="user", contents=["hi"])], stream=True):
        if event.type == "output":
            outputs.append(event.data)
        elif event.type == "intermediate":
            intermediates.append(event.data)

    assert outputs == ["from-downstream"]
    assert intermediates == ["from-start"]


def test_all_other_expands_to_concrete_intermediate_executor_selection_at_build_time() -> None:
    """The runner receives concrete executor IDs after all-other expansion."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            output_from=[_downstream],
            intermediate_output_from="all_other",
        )
        .add_edge(_start, _downstream)
        .build()
    )

    assert {executor.id for executor in workflow.get_output_executors()} == {_downstream.id}
    assert {executor.id for executor in workflow.get_intermediate_executors()} == {_start.id}
    assert workflow.is_intermediate_executor(_start.id)
    assert not workflow.is_intermediate_executor(_downstream.id)


@pytest.mark.asyncio
async def test_all_other_with_omitted_output_from_emits_only_intermediate_outputs() -> None:
    """All-other intermediate designation opts out of omitted-selection all-output behavior."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            intermediate_output_from="all_other",
        )
        .add_edge(_start, _downstream)
        .build()
    )

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == []
    assert result.get_intermediate_outputs() == ["from-start", "from-downstream"]


@pytest.mark.asyncio
async def test_all_other_with_empty_output_from_emits_only_intermediate_outputs() -> None:
    """All-other intermediate designation treats an empty output list as selecting no workflow outputs."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            output_from=[],
            intermediate_output_from="all_other",
        )
        .add_edge(_start, _downstream)
        .build()
    )

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == []
    assert result.get_intermediate_outputs() == ["from-start", "from-downstream"]


@pytest.mark.asyncio
async def test_all_other_with_output_from_all_expands_to_empty_intermediate_selection() -> None:
    """All-other is empty when every output-capable executor is already selected as workflow output."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            output_from="all",
            intermediate_output_from="all_other",
        )
        .add_edge(_start, _downstream)
        .build()
    )

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == ["from-start", "from-downstream"]
    assert result.get_intermediate_outputs() == []


@pytest.mark.asyncio
async def test_intermediate_output_from_all_routes_every_yield_to_intermediate() -> None:
    """``intermediate_output_from="all"`` designates every output-capable executor as intermediate."""
    workflow = (
        WorkflowBuilder(start_executor=_start, intermediate_output_from="all").add_edge(_start, _downstream).build()
    )

    result = await workflow.run([Message(role="user", contents=["hi"])])

    assert result.get_outputs() == []
    assert result.get_intermediate_outputs() == ["from-start", "from-downstream"]


def test_output_from_all_other_is_rejected() -> None:
    """The all-other literal is only valid for intermediate output selection."""
    with pytest.raises(ValueError, match="output_from.*all_other"):
        WorkflowBuilder(start_executor=_emit_one, output_from="all_other")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ("output_from", "intermediate_output_from"),
    [([_emit_one], None), (None, [_emit_one]), ([], [_emit_one])],
    ids=["output_list", "intermediate_list", "empty_output_with_intermediate"],
)
def test_explicit_designation_with_executor_does_not_warn(output_from, intermediate_output_from) -> None:
    """State B: any explicit designation with at least one executor opts into explicit mode without warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        WorkflowBuilder(
            start_executor=_emit_one,
            output_from=output_from,
            intermediate_output_from=intermediate_output_from,
        ).build()


@pytest.mark.parametrize(
    ("output_from", "intermediate_output_from"),
    [([], None), (None, []), ([], [])],
    ids=["empty_output", "empty_intermediate", "both_empty"],
)
def test_empty_explicit_designation_fails(output_from, intermediate_output_from) -> None:
    """State C: explicit mode needs at least one output or intermediate executor."""
    with pytest.raises(WorkflowValidationError, match="at least one output or intermediate executor"):
        WorkflowBuilder(
            start_executor=_emit_one,
            output_from=output_from,
            intermediate_output_from=intermediate_output_from,
        ).build()


def test_passing_both_output_executors_and_output_from_raises_type_error() -> None:
    """State D: supplying a deprecated alias and the canonical kwarg is unambiguous user error."""
    with pytest.raises(TypeError, match="Cannot pass multiple workflow output selection parameters"):
        WorkflowBuilder(
            start_executor=_emit_one,
            output_executors=[_emit_one],
            output_from=[_emit_one],
        )


def test_intermediate_executors_builder_parameter_is_not_public() -> None:
    """The branch-only intermediate_executors builder parameter is not supported."""
    builder_type: Any = WorkflowBuilder
    with pytest.raises(TypeError, match="unexpected keyword argument 'intermediate_executors'"):
        builder_type(
            start_executor=_emit_one,
            intermediate_executors=[_emit_one],
        )


def test_final_output_from_builder_parameter_is_not_public() -> None:
    """The branch-only final_output_from builder parameter is not supported."""
    builder_type: Any = WorkflowBuilder
    with pytest.raises(TypeError, match="unexpected keyword argument 'final_output_from'"):
        builder_type(
            start_executor=_emit_one,
            final_output_from=[_emit_one],
        )
