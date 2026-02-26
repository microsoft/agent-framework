# Copyright (c) Microsoft. All rights reserved.

"""Tests for WorkflowAgent session history persistence (GitHub issue #4248).

Validates that WorkflowAgent correctly saves both user input and assistant
response messages to session history via the InMemoryHistoryProvider.
"""

import uuid

import pytest
from typing_extensions import Never

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    Message,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)


@executor
async def simple_response_executor(
    messages: list[Message], ctx: WorkflowContext[Never, AgentResponse]
) -> None:
    """Executor that emits a simple assistant response."""
    input_text = messages[-1].text if messages else "no input"
    response = AgentResponse(
        messages=[
            Message(
                role="assistant",
                contents=[Content.from_text(text=f"Response to: {input_text}")],
                author_name="test-agent",
            )
        ],
    )
    await ctx.yield_output(response)


@executor
async def streaming_response_executor(
    messages: list[Message], ctx: WorkflowContext[Never, AgentResponseUpdate]
) -> None:
    """Executor that emits a streaming assistant response."""
    input_text = messages[-1].text if messages else "no input"
    update = AgentResponseUpdate(
        contents=[Content.from_text(text=f"Streamed response to: {input_text}")],
        role="assistant",
        author_name="test-agent",
        message_id=str(uuid.uuid4()),
    )
    await ctx.yield_output(update)


class TestWorkflowAgentSessionHistory:
    """Test that WorkflowAgent persists responses to session history.

    Reproduces and validates the fix for GitHub issue #4248:
    WorkflowAgent was not saving workflow responses to session history
    because session_context._response was never set before calling
    _run_after_providers.
    """

    async def test_non_streaming_saves_response_to_session(self):
        """Non-streaming run should save both user and assistant messages to session history."""
        workflow = WorkflowBuilder(start_executor=simple_response_executor).build()
        agent = workflow.as_agent("test-agent")
        session = agent.create_session()

        await agent.run("Hello", session=session)

        # The InMemoryHistoryProvider stores messages in session.state["in_memory"]["messages"]
        stored_messages = session.state.get("in_memory", {}).get("messages", [])

        # Should have both user input and assistant response
        assert len(stored_messages) >= 2, (
            f"Expected at least 2 messages (user + assistant), got {len(stored_messages)}: "
            f"{[(m.role, m.text) for m in stored_messages]}"
        )

        roles = [m.role for m in stored_messages]
        assert "user" in roles, "User message should be in session history"
        assert "assistant" in roles, "Assistant message should be in session history"

        # Verify the assistant message content
        assistant_msgs = [m for m in stored_messages if m.role == "assistant"]
        assert any("Response to: Hello" in (m.text or "") for m in assistant_msgs)

    async def test_streaming_saves_response_to_session(self):
        """Streaming run should save both user and assistant messages to session history."""
        workflow = WorkflowBuilder(start_executor=streaming_response_executor).build()
        agent = workflow.as_agent("test-agent")
        session = agent.create_session()

        # Consume the stream fully
        async for _ in agent.run("Hello", stream=True, session=session):
            pass

        stored_messages = session.state.get("in_memory", {}).get("messages", [])

        assert len(stored_messages) >= 2, (
            f"Expected at least 2 messages (user + assistant), got {len(stored_messages)}: "
            f"{[(m.role, m.text) for m in stored_messages]}"
        )

        roles = [m.role for m in stored_messages]
        assert "user" in roles, "User message should be in session history"
        assert "assistant" in roles, "Assistant message should be in session history"

        assistant_msgs = [m for m in stored_messages if m.role == "assistant"]
        assert any("Streamed response to: Hello" in (m.text or "") for m in assistant_msgs)

    async def test_multi_turn_saves_all_messages(self):
        """Multiple turns should accumulate all messages in session history."""
        workflow = WorkflowBuilder(start_executor=simple_response_executor).build()
        agent = workflow.as_agent("test-agent")
        session = agent.create_session()

        # Turn 1
        await agent.run("First question", session=session)

        # Turn 2
        await agent.run("Second question", session=session)

        stored_messages = session.state.get("in_memory", {}).get("messages", [])

        # Should have 4 messages: user1, assistant1, user2, assistant2
        assert len(stored_messages) >= 4, (
            f"Expected at least 4 messages (2 user + 2 assistant), got {len(stored_messages)}: "
            f"{[(m.role, m.text) for m in stored_messages]}"
        )

        user_msgs = [m for m in stored_messages if m.role == "user"]
        assistant_msgs = [m for m in stored_messages if m.role == "assistant"]

        assert len(user_msgs) >= 2, f"Expected at least 2 user messages, got {len(user_msgs)}"
        assert len(assistant_msgs) >= 2, f"Expected at least 2 assistant messages, got {len(assistant_msgs)}"

        # Verify content of second turn references the input
        assert any("Second question" in (m.text or "") for m in user_msgs)
        assert any("Response to: Second question" in (m.text or "") for m in assistant_msgs)
