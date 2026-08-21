# Copyright (c) Microsoft. All rights reserved.

"""Tests for WorkflowAgent forwarding of intermediate workflow events.

Covers:
- type='intermediate' surfaces as AgentResponseUpdate without content-type rewriting
- type='data' (compatibility alias via WorkflowEvent.emit) is forwarded
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
from agent_framework.exceptions import AgentInvalidRequestException


@pytest.mark.asyncio
async def test_workflow_agent_forwards_intermediate_events_without_content_rewrite() -> None:
    """An intermediate yield from an intermediate-designated executor surfaces through as_agent
    as an AgentResponseUpdate carrying its original content type."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("intermediate progress")
        await ctx.send_message("downstream")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("FINAL")

    workflow = (
        WorkflowBuilder(
            start_executor=emit,
            output_from=[terminal],
            intermediate_output_from=[emit],
        )
        .add_edge(emit, terminal)
        .build()
    )
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    text = " ".join(c.text for u in updates for c in u.contents if c.type == "text")  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]
    reasoning_text = " ".join(c.text for u in updates for c in u.contents if c.type == "text_reasoning")  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]

    assert "intermediate progress" in text
    assert "FINAL" in text
    assert reasoning_text == ""


@pytest.mark.asyncio
async def test_workflow_agent_text_accessor_includes_forwarded_intermediate_text() -> None:
    """Intermediate text is forwarded as text until issue 5885 defines the final mapping."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("invisible-progress")
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("the-answer")

    workflow = (
        WorkflowBuilder(
            start_executor=emit,
            output_from=[terminal],
            intermediate_output_from=[emit],
        )
        .add_edge(emit, terminal)
        .build()
    )
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    assert isinstance(response, AgentResponse)
    assert "invisible-progress" in response.text
    assert "the-answer" in response.text


@pytest.mark.asyncio
async def test_workflow_agent_hidden_yields_do_not_surface_non_streaming() -> None:
    """In explicit designation mode, unlisted executor yields stay out of agent responses."""

    @executor
    async def hidden(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("hidden-progress")
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("visible-answer")

    workflow = WorkflowBuilder(start_executor=hidden, output_from=[terminal]).add_edge(hidden, terminal).build()
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    all_text = " ".join(c.text for m in response.messages for c in m.contents if hasattr(c, "text"))  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]

    assert response.text == "visible-answer"
    assert "hidden-progress" not in all_text


@pytest.mark.asyncio
async def test_workflow_agent_hidden_yields_do_not_surface_streaming() -> None:
    """In explicit designation mode, unlisted executor yields stay out of agent updates."""

    @executor
    async def hidden(messages: list[Message], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output("hidden-progress")
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("visible-answer")

    workflow = WorkflowBuilder(start_executor=hidden, output_from=[terminal]).add_edge(hidden, terminal).build()
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    all_text = " ".join(c.text for u in updates for c in u.contents if hasattr(c, "text"))  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]

    assert "visible-answer" in all_text
    assert "hidden-progress" not in all_text


@pytest.mark.asyncio
async def test_workflow_agent_data_event_emit_factory_still_forwarded() -> None:
    """Even the deprecated WorkflowEvent.emit() / type='data' path is forwarded."""

    @executor
    async def emit_data_alias(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await ctx.add_event(WorkflowEvent.emit("emit_data_alias", "data-alias-payload"))
        await ctx.yield_output("DONE")

    workflow = WorkflowBuilder(start_executor=emit_data_alias, output_from=[emit_data_alias]).build()
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    text = " ".join(c.text for u in updates for c in u.contents if c.type == "text")  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]
    assert "data-alias-payload" in text


@pytest.mark.asyncio
async def test_workflow_agent_intermediate_message_preserves_additional_properties() -> None:
    """Message.additional_properties survives intermediate forwarding.

    Producer-attached metadata (tracking_id, conversation_id, etc.) must not disappear
    for messages flowing through intermediate-designated executors.
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
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("done")

    workflow = (
        WorkflowBuilder(
            start_executor=emit,
            output_from=[terminal],
            intermediate_output_from=[emit],
        )
        .add_edge(emit, terminal)
        .build()
    )
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    intermediate_msgs = [m for m in response.messages if any(c.type == "text" and c.text == "hi" for c in m.contents)]
    assert intermediate_msgs, "expected at least one intermediate message in the response"
    assert intermediate_msgs[0].additional_properties.get("tracking_id") == "abc-123"


@pytest.mark.asyncio
async def test_workflow_agent_terminal_text_stays_text_not_reasoning() -> None:
    """A designated executor's text yield surfaces as Content.text."""

    @executor
    async def only(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("the-answer")

    workflow = WorkflowBuilder(start_executor=only, output_from=[only]).build()
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    assert response.text == "the-answer"
    # No text_reasoning content because everything from `only` is terminal.
    assert all(c.type != "text_reasoning" for m in response.messages for c in m.contents)


@pytest.mark.asyncio
async def test_workflow_agent_non_streaming_rejects_terminal_update() -> None:
    """A terminal event carrying AgentResponseUpdate is streaming-only and invalid in run()."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[Never, AgentResponseUpdate]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output(AgentResponseUpdate(contents=[Content.from_text(text="partial")], role="assistant"))

    workflow = WorkflowBuilder(start_executor=emit, output_from=[emit]).build()
    agent = workflow.as_agent("test")

    with pytest.raises(AgentInvalidRequestException, match="AgentResponseUpdate"):
        await agent.run("hi")


@pytest.mark.asyncio
async def test_workflow_agent_non_streaming_rejects_intermediate_update() -> None:
    """An intermediate event carrying AgentResponseUpdate is streaming-only and invalid in run()."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, AgentResponseUpdate]) -> None:
        await ctx.yield_output(AgentResponseUpdate(contents=[Content.from_text(text="partial")], role="assistant"))
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output("FINAL")

    workflow = (
        WorkflowBuilder(
            start_executor=emit,
            output_from=[terminal],
            intermediate_output_from=[emit],
        )
        .add_edge(emit, terminal)
        .build()
    )
    agent = workflow.as_agent("test")

    with pytest.raises(AgentInvalidRequestException, match="AgentResponseUpdate"):
        await agent.run("hi")


@pytest.mark.asyncio
async def test_workflow_agent_streaming_update_payloads_preserve_classification() -> None:
    """Streaming AgentResponseUpdate payloads preserve original content types."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[str, AgentResponseUpdate]) -> None:
        await ctx.yield_output(
            AgentResponseUpdate(contents=[Content.from_text(text="intermediate-chunk")], role="assistant")
        )
        await ctx.send_message("forward")

    @executor
    async def terminal(message: str, ctx: WorkflowContext[Never, AgentResponseUpdate]) -> None:  # type: ignore[valid-type]
        await ctx.yield_output(
            AgentResponseUpdate(contents=[Content.from_text(text="terminal-chunk")], role="assistant")
        )

    workflow = (
        WorkflowBuilder(
            start_executor=emit,
            output_from=[terminal],
            intermediate_output_from=[emit],
        )
        .add_edge(emit, terminal)
        .build()
    )
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    text = " ".join(c.text for u in updates for c in u.contents if c.type == "text")  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]
    reasoning_text = " ".join(c.text for u in updates for c in u.contents if c.type == "text_reasoning")  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]

    assert "intermediate-chunk" in text
    assert "terminal-chunk" in text
    assert reasoning_text == ""


@pytest.mark.asyncio
async def test_workflow_agent_drops_orchestration_internal_events() -> None:
    """Orchestration-internal event types (group_chat / handoff_sent / magentic_orchestrator)
    must not surface through workflow.as_agent(). Their dataclass payloads would otherwise
    be stringified by the generic fallback path and leak into response history."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        # Construct typed orchestration-internal events directly to assert they get
        # dropped at the agent boundary regardless of payload.
        await ctx.add_event(WorkflowEvent("group_chat", data={"orchestrator": "details"}))  # type: ignore[arg-type]
        await ctx.add_event(WorkflowEvent("handoff_sent", data={"target": "agent_b"}))  # type: ignore[arg-type]
        await ctx.add_event(WorkflowEvent("magentic_orchestrator", data={"plan": "..."}))  # type: ignore[arg-type]
        await ctx.yield_output("FINAL")

    workflow = WorkflowBuilder(start_executor=emit, output_from=[emit]).build()
    agent = workflow.as_agent("test")

    response = await agent.run("hi")
    all_text = " ".join(c.text for m in response.messages for c in m.contents if hasattr(c, "text"))  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]
    assert "orchestrator" not in all_text
    assert "agent_b" not in all_text
    assert "plan" not in all_text
    assert response.text == "FINAL"


@pytest.mark.asyncio
async def test_workflow_agent_drops_orchestration_internal_events_streaming() -> None:
    """Streaming counterpart — orchestration-internal events stay inside the workflow."""

    @executor
    async def emit(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
        await ctx.add_event(WorkflowEvent("group_chat", data={"orchestrator": "details"}))  # type: ignore[arg-type]
        await ctx.yield_output("FINAL")

    workflow = WorkflowBuilder(start_executor=emit, output_from=[emit]).build()
    agent = workflow.as_agent("test")

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("hi", stream=True):
        updates.append(update)

    all_text = " ".join(c.text for u in updates for c in u.contents if hasattr(c, "text"))  # type: ignore[misc]  # pyrefly: ignore[no-matching-overload]  # ty: ignore[no-matching-overload]
    assert "orchestrator" not in all_text
    assert "FINAL" in all_text
