# Copyright (c) Microsoft. All rights reserved.

"""Tests for AG-UI orchestrators."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

from ag_ui.core import BaseEvent, RunFinishedEvent
from agent_framework import (
    AgentResponseUpdate,
    AgentThread,
    BaseChatClient,
    ChatAgent,
    ChatResponseUpdate,
    FunctionInvocationConfiguration,
    TextContent,
    ai_function,
)

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._orchestrators import DefaultOrchestrator, ExecutionContext


@ai_function
def server_tool() -> str:
    """Server-executable tool."""
    return "server"


def _create_mock_chat_agent(
    tools: list[Any] | None = None,
    response_format: Any = None,
    capture_tools: list[Any] | None = None,
    capture_messages: list[Any] | None = None,
) -> ChatAgent:
    """Create a ChatAgent with mocked chat client for testing.

    Args:
        tools: Tools to configure on the agent.
        response_format: Response format to configure.
        capture_tools: If provided, tools passed to run_stream will be appended here.
        capture_messages: If provided, messages passed to run_stream will be appended here.
    """
    mock_chat_client = MagicMock(spec=BaseChatClient)
    mock_chat_client.function_invocation_configuration = FunctionInvocationConfiguration()

    agent = ChatAgent(
        chat_client=mock_chat_client,
        tools=tools or [server_tool],
        response_format=response_format,
    )

    # Create a mock run_stream that captures parameters and yields a simple response
    async def mock_run_stream(
        messages: list[Any],
        *,
        #     thread: AgentThread,
        #     tools: list[Any] | None = None,
        #     **kwargs: Any,
        # ) -> AsyncGenerator[AgentRunResponseUpdate, None]:
        #     self.seen_tools = tools
        #     yield AgentRunResponseUpdate(
        #         contents=[TextContent(text="ok")],
        #         role="assistant",
        #         response_id=thread.metadata.get("ag_ui_run_id"),  # type: ignore[attr-defined] (metadata always created in orchestrator)
        #         raw_representation=ChatResponseUpdate(
        #             contents=[TextContent(text="ok")],
        #             conversation_id=thread.metadata.get("ag_ui_thread_id"),  # type: ignore[attr-defined] (metadata always created in orchestrator)
        #             response_id=thread.metadata.get("ag_ui_run_id"),  # type: ignore[attr-defined] (metadata always created in orchestrator)
        #         ),
        #     )
        thread: AgentThread,
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentResponseUpdate, None]:
        if capture_tools is not None and tools is not None:
            capture_tools.extend(tools)
        if capture_messages is not None:
            capture_messages.extend(messages)
        yield AgentResponseUpdate(
            contents=[TextContent(text="ok")],
            role="assistant",
            response_id=thread.metadata.get("ag_ui_run_id"),  # type: ignore[attr-defined] (metadata always created in orchestrator)
            raw_representation=ChatResponseUpdate(
                contents=[TextContent(text="ok")],
                conversation_id=thread.metadata.get("ag_ui_thread_id"),  # type: ignore[attr-defined] (metadata always created in orchestrator)
                response_id=thread.metadata.get("ag_ui_run_id"),  # type: ignore[attr-defined] (metadata always created in orchestrator)
            ),
        )

    # Patch the run_stream method
    agent.run_stream = mock_run_stream  # type: ignore[method-assign]

    return agent


async def test_default_orchestrator_merges_client_tools() -> None:
    """Client tool declarations are merged with server tools before running agent."""
    captured_tools: list[Any] = []
    agent = _create_mock_chat_agent(tools=[server_tool], capture_tools=captured_tools)
    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            }
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Client weather lookup.",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            }
        ],
    }

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    assert len(captured_tools) > 0
    tool_names = [getattr(tool, "name", "?") for tool in captured_tools]
    assert "server_tool" in tool_names
    assert "get_weather" in tool_names
    assert agent.chat_client.function_invocation_configuration.additional_tools


async def test_default_orchestrator_with_camel_case_ids() -> None:
    """Client tool is able to extract camelCase IDs."""
    agent = _create_mock_chat_agent()
    orchestrator = DefaultOrchestrator()

    input_data = {
        "runId": "test-camelcase-runid",
        "threadId": "test-camelcase-threadid",
        "messages": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            }
        ],
        "tools": [],
    }

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # assert the last event has the expected run_id and thread_id
    assert isinstance(events[-1], RunFinishedEvent)
    last_event = events[-1]
    assert last_event.run_id == "test-camelcase-runid"
    assert last_event.thread_id == "test-camelcase-threadid"


async def test_default_orchestrator_with_snake_case_ids() -> None:
    """Client tool is able to extract snake_case IDs."""
    agent = _create_mock_chat_agent()
    orchestrator = DefaultOrchestrator()

    input_data = {
        "run_id": "test-snakecase-runid",
        "thread_id": "test-snakecase-threadid",
        "messages": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            }
        ],
        "tools": [],
    }

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events: list[BaseEvent] = []
    async for event in orchestrator.run(context):
        events.append(event)

    # assert the last event has the expected run_id and thread_id
    assert isinstance(events[-1], RunFinishedEvent)
    last_event = events[-1]
    assert last_event.run_id == "test-snakecase-runid"
    assert last_event.thread_id == "test-snakecase-threadid"


async def test_state_context_injected_when_tool_call_state_mismatch() -> None:
    """State context should be injected when current state differs from tool call args."""
    captured_messages: list[Any] = []
    agent = _create_mock_chat_agent(tools=[], capture_messages=captured_messages)
    orchestrator = DefaultOrchestrator()

    tool_recipe = {"title": "Salad", "special_preferences": []}
    current_recipe = {"title": "Salad", "special_preferences": ["Vegetarian"]}

    input_data = {
        "state": {"recipe": current_recipe},
        "messages": [
            {"role": "system", "content": "Instructions"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "update_recipe", "arguments": {"recipe": tool_recipe}},
                    }
                ],
            },
            {"role": "user", "content": "What are the dietary preferences?"},
        ],
    }

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(
            state_schema={"recipe": {"type": "object"}},
            predict_state_config={"recipe": {"tool": "update_recipe", "tool_argument": "recipe"}},
            require_confirmation=False,
        ),
    )

    async for _event in orchestrator.run(context):
        pass

    assert len(captured_messages) > 0
    state_messages = []
    for msg in captured_messages:
        role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        if role_value != "system":
            continue
        for content in msg.contents or []:
            if isinstance(content, TextContent) and content.text.startswith("Current state of the application:"):
                state_messages.append(content.text)
    assert state_messages
    assert "Vegetarian" in state_messages[0]


async def test_state_context_not_injected_when_tool_call_matches_state() -> None:
    """State context should be skipped when tool call args match current state."""
    captured_messages: list[Any] = []
    agent = _create_mock_chat_agent(tools=[], capture_messages=captured_messages)
    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {"role": "system", "content": "Instructions"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "update_recipe", "arguments": {"recipe": {}}},
                    }
                ],
            },
            {"role": "user", "content": "What are the dietary preferences?"},
        ],
    }

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(
            state_schema={"recipe": {"type": "object"}},
            predict_state_config={"recipe": {"tool": "update_recipe", "tool_argument": "recipe"}},
            require_confirmation=False,
        ),
    )

    async for _event in orchestrator.run(context):
        pass

    assert len(captured_messages) > 0
    state_messages = []
    for msg in captured_messages:
        role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        if role_value != "system":
            continue
        for content in msg.contents or []:
            if isinstance(content, TextContent) and content.text.startswith("Current state of the application:"):
                state_messages.append(content.text)
    assert not state_messages
