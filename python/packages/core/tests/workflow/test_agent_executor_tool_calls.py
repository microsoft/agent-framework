# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentExecutor handling of tool calls and results in streaming mode."""

from collections.abc import AsyncIterable
from typing import Any

from agent_framework import (
    AgentExecutor,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    AgentThread,
    BaseAgent,
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    WorkflowBuilder,
)


class _ToolCallingAgent(BaseAgent):
    """Mock agent that simulates tool calls and results in streaming mode."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Non-streaming run - not used in this test."""
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="done")])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Simulate streaming with tool calls and results."""
        # First update: some text
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="Let me search for that...")],
            role=Role.ASSISTANT,
        )

        # Second update: tool call (no text!)
        yield AgentRunResponseUpdate(
            contents=[
                FunctionCallContent(
                    call_id="call_123",
                    name="search",
                    arguments={"query": "weather"},
                )
            ],
            role=Role.ASSISTANT,
        )

        # Third update: tool result (no text!)
        yield AgentRunResponseUpdate(
            contents=[
                FunctionResultContent(
                    call_id="call_123",
                    result={"temperature": 72, "condition": "sunny"},
                )
            ],
            role=Role.TOOL,
        )

        # Fourth update: final text response
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="The weather is sunny, 72°F.")],
            role=Role.ASSISTANT,
        )


async def test_agent_executor_emits_tool_calls_in_streaming_mode() -> None:
    """Test that AgentExecutor emits updates containing FunctionCallContent and FunctionResultContent."""
    # Arrange
    agent = _ToolCallingAgent(id="tool_agent", name="ToolAgent")
    agent_exec = AgentExecutor(agent, id="tool_exec")

    workflow = WorkflowBuilder().set_start_executor(agent_exec).build()

    # Act: run in streaming mode
    events: list[AgentRunUpdateEvent] = []
    async for event in workflow.run_stream("What's the weather?"):
        if isinstance(event, AgentRunUpdateEvent):
            events.append(event)

    # Assert: we should receive 4 events (text, function call, function result, text)
    assert len(events) == 4, f"Expected 4 events, got {len(events)}"

    # First event: text update
    assert events[0].data is not None
    assert isinstance(events[0].data.contents[0], TextContent)
    assert "Let me search" in events[0].data.contents[0].text

    # Second event: function call
    assert events[1].data is not None
    assert isinstance(events[1].data.contents[0], FunctionCallContent)
    func_call = events[1].data.contents[0]
    assert func_call.call_id == "call_123"
    assert func_call.name == "search"

    # Third event: function result
    assert events[2].data is not None
    assert isinstance(events[2].data.contents[0], FunctionResultContent)
    func_result = events[2].data.contents[0]
    assert func_result.call_id == "call_123"

    # Fourth event: final text
    assert events[3].data is not None
    assert isinstance(events[3].data.contents[0], TextContent)
    assert "sunny" in events[3].data.contents[0].text
