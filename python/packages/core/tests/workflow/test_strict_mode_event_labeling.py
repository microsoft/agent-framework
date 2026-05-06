# Copyright (c) Microsoft. All rights reserved.

"""Tests for the runner's strict-mode event labeling.

Strict mode = WorkflowBuilder built with explicit output_executors=[...].
- Yields from designated executors -> type='output'.
- Yields from non-designated executors -> type='intermediate'.

Legacy mode (output_executors unset) preserves today's behavior:
every yield -> type='output'.
"""

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
async def _downstream(message: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output("from-downstream")


def _input_msg() -> list[Message]:
    return [Message(role="user", contents=["hi"])]


@pytest.mark.asyncio
async def test_strict_mode_designated_executor_emits_output_events() -> None:
    """In strict mode, the designated executor's yields produce type='output' events."""
    workflow = WorkflowBuilder(start_executor=_start, output_executors=[_start]).add_edge(_start, _downstream).build()
    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run(_input_msg(), stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    assert any(ev.data == "from-start" for ev in output_events), "designated executor's yield is type='output'"
    assert any(ev.data == "from-downstream" for ev in intermediate_events), (
        "non-designated executor's yield is relabeled to type='intermediate'"
    )


@pytest.mark.asyncio
async def test_strict_mode_empty_list_means_no_terminals() -> None:
    """Strict mode with output_executors=[] produces zero type='output' events; everything is intermediate."""
    workflow = WorkflowBuilder(start_executor=_start, output_executors=[]).add_edge(_start, _downstream).build()
    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run(_input_msg(), stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    assert len(output_events) == 0
    assert {ev.data for ev in intermediate_events} == {"from-start", "from-downstream"}


@pytest.mark.asyncio
async def test_legacy_mode_unset_keeps_all_yields_as_output() -> None:
    """Legacy mode (output_executors unset) preserves today's behavior — all yields are type='output'."""
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
    """WorkflowRunResult.get_outputs() returns only designated outputs in strict mode."""
    workflow = (
        WorkflowBuilder(start_executor=_start, output_executors=[_downstream]).add_edge(_start, _downstream).build()
    )
    result = await workflow.run(_input_msg())
    outputs = result.get_outputs()
    assert outputs == ["from-downstream"]


@pytest.mark.asyncio
async def test_strict_mode_get_outputs_empty_with_no_terminals() -> None:
    """output_executors=[] yields no terminal outputs."""
    workflow = WorkflowBuilder(start_executor=_start, output_executors=[]).add_edge(_start, _downstream).build()
    result = await workflow.run(_input_msg())
    assert result.get_outputs() == []
