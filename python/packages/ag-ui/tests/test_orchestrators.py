# Copyright (c) Microsoft. All rights reserved.

"""Tests for AG-UI orchestrators."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

from agent_framework import AgentRunResponseUpdate, TextContent, ai_function
from agent_framework._tools import FunctionInvocationConfiguration

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._orchestrators import DefaultOrchestrator, ExecutionContext


@ai_function
def server_tool() -> str:
    """Server-executable tool."""
    return "server"


class DummyAgent:
    """Minimal agent stub to capture run_stream parameters."""

    def __init__(self) -> None:
        self.chat_options = SimpleNamespace(tools=[server_tool], response_format=None)
        self.tools = [server_tool]
        self.chat_client = SimpleNamespace(
            function_invocation_configuration=FunctionInvocationConfiguration(),
        )
        self.seen_tools: list[Any] | None = None

    async def run_stream(
        self,
        messages: list[Any],
        *,
        thread: Any,
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentRunResponseUpdate, None]:
        self.seen_tools = tools
        yield AgentRunResponseUpdate(contents=[TextContent(text="ok")], role="assistant")


class RecordingAgent:
    """Agent stub that captures messages passed to run_stream."""

    def __init__(self) -> None:
        self.chat_options = SimpleNamespace(tools=[], response_format=None)
        self.tools: list[Any] = []
        self.chat_client = SimpleNamespace(
            function_invocation_configuration=FunctionInvocationConfiguration(),
        )
        self.seen_messages: list[Any] | None = None

    async def run_stream(
        self,
        messages: list[Any],
        *,
        thread: Any,
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentRunResponseUpdate, None]:
        self.seen_messages = messages
        yield AgentRunResponseUpdate(contents=[TextContent(text="ok")], role="assistant")


async def test_default_orchestrator_merges_client_tools() -> None:
    """Client tool declarations are merged with server tools before running agent."""

    agent = DummyAgent()
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

    assert agent.seen_tools is not None
    tool_names = [getattr(tool, "name", "?") for tool in agent.seen_tools]
    assert "server_tool" in tool_names
    assert "get_weather" in tool_names
    assert agent.chat_client.function_invocation_configuration.additional_tools


async def test_default_orchestrator_with_camel_case_ids() -> None:
    """Client tool is able to extract camelCase IDs."""

    agent = DummyAgent()
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
    last_event = events[-1]
    assert last_event.run_id == "test-camelcase-runid"
    assert last_event.thread_id == "test-camelcase-threadid"


async def test_default_orchestrator_with_snake_case_ids() -> None:
    """Client tool is able to extract snake_case IDs."""

    agent = DummyAgent()
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

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # assert the last event has the expected run_id and thread_id
    last_event = events[-1]
    assert last_event.run_id == "test-snakecase-runid"
    assert last_event.thread_id == "test-snakecase-threadid"


async def test_state_context_injected_when_tool_call_state_mismatch() -> None:
    """State context should be injected when current state differs from tool call args."""

    agent = RecordingAgent()
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

    assert agent.seen_messages is not None
    state_messages = []
    for msg in agent.seen_messages:
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

    agent = RecordingAgent()
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

    assert agent.seen_messages is not None
    state_messages = []
    for msg in agent.seen_messages:
        role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        if role_value != "system":
            continue
        for content in msg.contents or []:
            if isinstance(content, TextContent) and content.text.startswith("Current state of the application:"):
                state_messages.append(content.text)
    assert not state_messages
