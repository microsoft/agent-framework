# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentFrameworkWorkflow wrapper behavior."""

from __future__ import annotations

from typing import Any, cast

import pytest
from agent_framework import Workflow, WorkflowBuilder, WorkflowContext, executor

from agent_framework_ag_ui import AgentFrameworkWorkflow


async def _run(agent: AgentFrameworkWorkflow, payload: dict[str, Any]) -> list[Any]:
    return [event async for event in agent.run(payload)]


async def test_workflow_wrapper_rejects_workflow_and_factory_at_once() -> None:
    """Workflow wrapper should reject ambiguous workflow source configuration."""

    @executor(id="start")
    async def start(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.yield_output("ok")

    workflow = WorkflowBuilder(start_executor=start).build()
    with pytest.raises(ValueError, match="workflow_factory"):
        AgentFrameworkWorkflow(workflow=workflow, workflow_factory=lambda _thread_id: workflow)


async def test_workflow_wrapper_factory_is_thread_scoped() -> None:
    """Thread-scoped workflow factories should isolate workflow instances by thread id."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info({"message": "Choose an option", "options": ["a", "b"]}, dict, request_id="choice")

    factory_calls: dict[str, int] = {}

    def workflow_factory(thread_id: str) -> Workflow:
        factory_calls[thread_id] = factory_calls.get(thread_id, 0) + 1
        return WorkflowBuilder(start_executor=requester).build()

    agent = AgentFrameworkWorkflow(workflow_factory=workflow_factory)

    first_events = await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [{"role": "user", "content": "start"}],
        },
    )
    first_finished = [event for event in first_events if event.type == "RUN_FINISHED"][0].model_dump()
    first_interrupt = first_finished.get("interrupt")
    assert isinstance(first_interrupt, list)
    assert first_interrupt[0]["id"] == "choice"
    assert factory_calls["thread-a"] == 1

    second_events = await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [],
            "resume": {"interrupts": [{"id": "choice", "value": {"selection": "a"}}]},
        },
    )
    second_types = [event.type for event in second_events]
    assert "RUN_ERROR" not in second_types
    second_finished = [event for event in second_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert "interrupt" not in second_finished
    assert factory_calls["thread-a"] == 1

    third_events = await _run(
        agent,
        {
            "thread_id": "thread-b",
            "messages": [{"role": "user", "content": "start"}],
        },
    )
    third_finished = [event for event in third_events if event.type == "RUN_FINISHED"][0].model_dump()
    third_interrupt = third_finished.get("interrupt")
    assert isinstance(third_interrupt, list)
    assert third_interrupt[0]["id"] == "choice"
    assert factory_calls["thread-b"] == 1

    agent.clear_thread_workflow("thread-a")
    await _run(
        agent,
        {
            "thread_id": "thread-a",
            "messages": [{"role": "user", "content": "restart"}],
        },
    )
    assert factory_calls["thread-a"] == 2


async def test_workflow_wrapper_without_workflow_raises_not_implemented() -> None:
    """Without workflow/workflow_factory, run should raise NotImplementedError."""
    agent = AgentFrameworkWorkflow()

    with pytest.raises(NotImplementedError, match="No workflow is attached"):
        _ = [event async for event in agent.run({"messages": [{"role": "user", "content": "start"}]})]


async def test_workflow_wrapper_factory_return_type_is_validated() -> None:
    """Factory outputs must be Workflow instances."""
    agent = AgentFrameworkWorkflow(workflow_factory=lambda _thread_id: cast(Any, object()))

    with pytest.raises(TypeError, match="workflow_factory must return a Workflow instance"):
        _ = [event async for event in agent.run({"thread_id": "thread-a", "messages": []})]
