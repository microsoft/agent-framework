# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from typing import Any

from agent_framework import (
    Agent,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
)
from agent_framework_hosting import AgentState
from mcp import types
from pytest import raises

from agent_framework_hosting_mcp import MCPAgentTool


class RecordingClient(BaseChatClient[ChatOptions[None]]):
    """Record messages and return their latest text."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def get_response() -> ChatResponse:
            self.calls.append([message.text for message in messages])
            return ChatResponse(messages=Message("assistant", [f"response: {messages[-1].text}"]))

        return get_response()


async def test_agent_tool_generates_schema_from_agent_with_overrides() -> None:
    agent = Agent(
        client=RecordingClient(),
        name="Research Agent",
        description="Agent description",
    )
    tool: MCPAgentTool[Any] = MCPAgentTool(
        agent,
        name="research",
        description="Tool description",
        argument_name="prompt",
        argument_description="Research request",
        parameters={"audience": {"type": "string"}},
        required_parameters={"audience"},
        chat_option_parameters={
            "reasoning_effort": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            }
        },
    )

    definitions = await tool.list_tools()

    assert len(definitions) == 1
    definition = definitions[0]
    assert definition.name == "research"
    assert definition.description == "Tool description"
    assert definition.inputSchema == {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Research request"},
            "audience": {"type": "string"},
            "reasoning_effort": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
        },
        "required": ["prompt", "audience"],
        "additionalProperties": False,
    }

    run = tool.mcp_to_run({
        "prompt": "Investigate MCP",
        "audience": "developers",
        "reasoning_effort": "high",
    })
    messages = run["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], Message)
    assert messages[0].text == "Investigate MCP"
    assert run["options"] == {"reasoning_effort": "high"}


async def test_agent_tool_uses_agent_metadata_by_default() -> None:
    agent = Agent(client=RecordingClient(), name="Research Agent", description="Agent description")
    tool: MCPAgentTool[Any] = MCPAgentTool(agent)

    definition = (await tool.list_tools())[0]

    assert definition.name == "Research_Agent"
    assert definition.description == "Agent description"


async def test_agent_tool_runs_with_agent_state_session() -> None:
    client = RecordingClient()
    agent = Agent(
        client=client,
        name="session-agent",
        context_providers=[InMemoryHistoryProvider()],
    )
    state = AgentState(agent)
    tool: MCPAgentTool[Any] = MCPAgentTool(
        state,
        parameters={"session_id": {"type": "string"}},
        required_parameters={"session_id"},
        session_id_parameter="session_id",
    )

    first = await tool.call_tool("session-agent", {"task": "first", "session_id": "session-1"})
    second = await tool.call_tool("session-agent", {"task": "second", "session_id": "session-1"})

    assert isinstance(first[0], types.TextContent)
    assert first[0].text == "response: first"
    assert isinstance(second[0], types.TextContent)
    assert second[0].text == "response: second"
    assert client.calls[0] == ["first"]
    assert client.calls[1] == ["first", "response: first", "second"]
    assert await state.session_store.get("session-1") is not None


def test_agent_tool_rejects_undefined_session_parameter() -> None:
    agent = Agent(client=RecordingClient(), name="agent")

    with raises(ValueError, match="session_id_parameter"):
        MCPAgentTool(agent, session_id_parameter="session_id")


async def test_agent_tool_always_requires_session_parameter() -> None:
    agent = Agent(client=RecordingClient(), name="agent")
    tool: MCPAgentTool[Any] = MCPAgentTool(
        agent,
        parameters={"session_id": {"type": "string"}},
        session_id_parameter="session_id",
    )

    definition = (await tool.list_tools())[0]

    assert definition.inputSchema["required"] == ["task", "session_id"]
