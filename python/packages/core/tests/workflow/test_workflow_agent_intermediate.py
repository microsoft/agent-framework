# Copyright (c) Microsoft. All rights reserved.

"""Tests for WorkflowAgent translation of intermediate events to text_reasoning content.

Covers:
- type='intermediate' surfaces as AgentResponseUpdate with text_reasoning content
- type='data' (legacy via WorkflowEvent.emit) surfaces the same way (fixes F7)
- update.text returns terminal-only by virtue of the existing content-type filter
- Message.additional_properties survives the intermediate translation path
- Terminal yields keep using regular text content (backward compat)
"""

from __future__ import annotations

import warnings

import pytest
from typing_extensions import Never

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    executor,
)


@pytest.mark.asyncio
async def test_workflow_agent_forwards_intermediate_events_as_text_reasoning() -> None:
    """An intermediate yield from a non-designated executor surfaces through as_agent
    as an AgentResponseUpdate carrying text_reasoning content."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("intermediate progress")
        await ctx.send_message("downstream")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("FINAL")

    workflow = WorkflowBuilder(start_executor=emit, output_executors=[terminal]).add_edge(emit, terminal).build()
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    # Find the intermediate progress: it has text_reasoning content.
    intermediate_updates = [u for u in updates if any(c.type == "text_reasoning" for c in u.contents)]
    terminal_updates = [u for u in updates if any(c.type == "text" for c in u.contents)]

    intermediate_text = " ".join(c.text for u in intermediate_updates for c in u.contents if c.type == "text_reasoning")
    terminal_text = " ".join(u.text for u in terminal_updates)

    assert "intermediate progress" in intermediate_text
    assert "FINAL" in terminal_text


@pytest.mark.asyncio
async def test_workflow_agent_text_accessor_returns_terminal_only() -> None:
    """update.text excludes text_reasoning content automatically. The non-streaming
    AgentResponse.text returns only terminal text — intermediate progress is invisible
    to existing callers using .text."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("invisible-progress")
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("the-answer")

    workflow = WorkflowBuilder(start_executor=emit, output_executors=[terminal]).add_edge(emit, terminal).build()
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    assert isinstance(response, AgentResponse)
    # .text filters to content.type == "text" — intermediate text_reasoning is excluded.
    assert response.text == "the-answer"


@pytest.mark.asyncio
async def test_workflow_agent_legacy_data_event_emit_factory_still_forwarded() -> None:
    """Even the deprecated WorkflowEvent.emit() / type='data' path is forwarded as
    text_reasoning content (was previously dropped — F7 fix)."""

    @executor
    async def emit_legacy(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await ctx.add_event(WorkflowEvent.emit("emit_legacy", "legacy-payload"))
        await ctx.yield_output("DONE")

    workflow = WorkflowBuilder(start_executor=emit_legacy, output_executors=[emit_legacy]).build()
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    reasoning_text = " ".join(c.text for u in updates for c in u.contents if c.type == "text_reasoning")
    assert "legacy-payload" in reasoning_text


@pytest.mark.asyncio
async def test_workflow_agent_intermediate_message_preserves_additional_properties() -> None:
    """Message.additional_properties survives the intermediate translation path.

    Regression test for the omitted field in _mark_msg — without forwarding
    additional_properties, producer-attached metadata (tracking_id, conversation_id, etc.)
    silently disappears for messages flowing through non-designated executors.
    """

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, AgentResponse]) -> None:
        msg = Message(
            role="assistant",
            contents=[Content.from_text(text="hi")],
            additional_properties={"tracking_id": "abc-123"},
        )
        await ctx.yield_output(AgentResponse(messages=[msg]))
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("done")

    workflow = WorkflowBuilder(start_executor=emit, output_executors=[terminal]).add_edge(emit, terminal).build()
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    intermediate_msgs = [m for m in response.messages if any(c.type == "text_reasoning" for c in m.contents)]
    assert intermediate_msgs, "expected at least one intermediate message in the response"
    assert intermediate_msgs[0].additional_properties.get("tracking_id") == "abc-123"


@pytest.mark.asyncio
async def test_workflow_agent_terminal_text_stays_text_not_reasoning() -> None:
    """Backward compat — a designated executor's text yield surfaces as Content.text,
    not text_reasoning. Existing consumers reading .text on the response work unchanged."""

    @executor
    async def only(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("the-answer")

    workflow = WorkflowBuilder(start_executor=only, output_executors=[only]).build()
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    assert response.text == "the-answer"
    # No text_reasoning content because everything from `only` is terminal.
    assert all(c.type != "text_reasoning" for m in response.messages for c in m.contents)
