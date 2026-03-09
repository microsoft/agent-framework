# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the generative UI (workflow-as-agent) scenario."""

from __future__ import annotations

from typing import Any

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from event_stream import EventStream
from typing_extensions import Never

from agent_framework_ag_ui import AgentFrameworkWorkflow


async def _run(wrapper: AgentFrameworkWorkflow, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in wrapper.run(payload)])


PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-gen-ui-agent",
    "run_id": "run-gen-ui-agent",
    "messages": [{"role": "user", "content": "Generate a UI"}],
}


# ── Golden stream tests ──


async def test_workflow_agent_golden_sequence() -> None:
    """Workflow-as-agent: emits step events and text content."""

    @executor(id="generator")
    async def generator(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("Here is your generated UI content!")

    workflow = WorkflowBuilder(start_executor=generator).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, PAYLOAD)

    stream.assert_bookends()
    stream.assert_no_run_error()
    stream.assert_text_messages_balanced()

    # Should have step events for the executor
    stream.assert_has_type("STEP_STARTED")
    stream.assert_has_type("STEP_FINISHED")

    # Should have text message content
    stream.assert_has_type("TEXT_MESSAGE_CONTENT")


async def test_workflow_agent_step_names_match() -> None:
    """Step started/finished events reference the executor name."""

    @executor(id="my_executor")
    async def my_executor(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("Done!")

    workflow = WorkflowBuilder(start_executor=my_executor).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, PAYLOAD)

    started = [e for e in stream.get("STEP_STARTED") if getattr(e, "step_name", "") == "my_executor"]
    finished = [e for e in stream.get("STEP_FINISHED") if getattr(e, "step_name", "") == "my_executor"]
    assert started, "Expected STEP_STARTED for 'my_executor'"
    assert finished, "Expected STEP_FINISHED for 'my_executor'"


async def test_workflow_agent_ordered_events() -> None:
    """Workflow events follow expected ordering: RUN_STARTED → STEP_STARTED → content → STEP_FINISHED → RUN_FINISHED."""

    @executor(id="my_step")
    async def my_step(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("Generated content")

    workflow = WorkflowBuilder(start_executor=my_step).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, PAYLOAD)

    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "STEP_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "STEP_FINISHED",
            "TEXT_MESSAGE_END",
            "RUN_FINISHED",
        ]
    )
