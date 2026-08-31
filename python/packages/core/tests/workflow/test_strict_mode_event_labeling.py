# Copyright (c) Microsoft. All rights reserved.

"""Tests for the runner's explicit output selection event labeling."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from typing_extensions import Never

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)


@executor
async def _start(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
    await ctx.yield_output("from-start")
    await ctx.send_message("downstream")


@executor
async def _downstream(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
    await ctx.yield_output("from-downstream")


def _input_msg() -> list[Message]:
    return [Message(role="user", contents=["hi"])]


@pytest.mark.asyncio
async def test_strict_mode_designated_executor_emits_output_events() -> None:
    """Output-designated executor yields produce type='output' events."""
    workflow = WorkflowBuilder(start_executor=_start, output_from=[_start]).add_edge(_start, _downstream).build()
    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run(_input_msg(), stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    assert any(ev.data == "from-start" for ev in output_events), "designated executor's yield is type='output'"
    assert intermediate_events == []
    assert all(ev.data != "from-downstream" for ev in output_events), "unlisted executor yield is hidden"


@pytest.mark.asyncio
async def test_intermediate_designated_executor_emits_intermediate_events() -> None:
    """Intermediate-designated executor yields produce type='intermediate' events."""
    workflow = (
        WorkflowBuilder(start_executor=_start, intermediate_output_from=[_downstream])
        .add_edge(_start, _downstream)
        .build()
    )
    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run(_input_msg(), stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    assert len(output_events) == 0
    assert {ev.data for ev in intermediate_events} == {"from-downstream"}


@pytest.mark.asyncio
async def test_omitted_selection_keeps_all_yields_as_output() -> None:
    """Omitted output selection preserves today's behavior: all yields are type='output'."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        workflow = WorkflowBuilder(start_executor=_start).add_edge(_start, _downstream).build()
    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run(_input_msg(), stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    assert {ev.data for ev in output_events} == {"from-start", "from-downstream"}
    assert len(intermediate_events) == 0


@pytest.mark.asyncio
async def test_strict_mode_get_outputs_returns_only_designated() -> None:
    """WorkflowRunResult.get_outputs() returns only output-designated payloads."""
    workflow = (
        WorkflowBuilder(
            start_executor=_start,
            output_from=[_downstream],
            intermediate_output_from=[_start],
        )
        .add_edge(_start, _downstream)
        .build()
    )
    result = await workflow.run(_input_msg())
    assert result.get_outputs() == ["from-downstream"]
    assert result.get_intermediate_outputs() == ["from-start"]


@pytest.mark.asyncio
async def test_hidden_yields_remain_in_executor_completion_events() -> None:
    """Hidden yield_output payloads stay available through executor_completed observability."""
    workflow = WorkflowBuilder(start_executor=_start, output_from=[_downstream]).add_edge(_start, _downstream).build()
    result = await workflow.run(_input_msg())
    assert result.get_outputs() == ["from-downstream"]
    assert result.get_intermediate_outputs() == []
    assert not any(event.type in {"output", "intermediate"} and event.data == "from-start" for event in result)
    completed = [event for event in result if event.type == "executor_completed" and event.executor_id == _start.id]
    assert completed
    assert completed[0].data == ["downstream", "from-start"]
