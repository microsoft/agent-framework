# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
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
from mcp import Client, MCPError, types
from mcp.server import Server, ServerRequestContext
from pytest import raises

from agent_framework_hosting_mcp import AgentMCPTool


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
    tool: AgentMCPTool[Any] = AgentMCPTool(
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

    list_tools_result = await tool.list_tools()
    result_tools = list_tools_result.tools

    assert list_tools_result.result_type == "complete"
    assert len(result_tools) == 1
    result_tool = result_tools[0]
    assert result_tool.name == "research"
    assert result_tool.description == "Tool description"
    assert result_tool.input_schema == {
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
    tool: AgentMCPTool[Any] = AgentMCPTool(agent)

    result_tool = (await tool.list_tools()).tools[0]

    assert result_tool.name == "Research_Agent"
    assert result_tool.description == "Agent description"


async def test_agent_tool_runs_with_agent_state_session() -> None:
    client = RecordingClient()
    agent = Agent(
        client=client,
        name="session-agent",
        context_providers=[InMemoryHistoryProvider()],
    )
    state = AgentState(agent)
    tool: AgentMCPTool[Any] = AgentMCPTool(
        state,
        parameters={"session_id": {"type": "string"}},
        required_parameters={"session_id"},
        session_id_parameter="session_id",
    )

    first = await tool.call_tool("session-agent", {"task": "first", "session_id": "session-1"})
    second = await tool.call_tool("session-agent", {"task": "second", "session_id": "session-1"})

    assert first.result_type == "complete"
    assert not first.is_error
    assert isinstance(first.content[0], types.TextContent)
    assert first.content[0].text == "response: first"

    assert second.result_type == "complete"
    assert not second.is_error
    assert isinstance(second.content[0], types.TextContent)
    assert second.content[0].text == "response: second"

    assert client.calls[0] == ["first"]
    assert client.calls[1] == ["first", "response: first", "second"]
    assert await state.session_store.get("session-1") is not None


def test_agent_tool_rejects_undefined_session_parameter() -> None:
    agent = Agent(client=RecordingClient(), name="agent")

    with raises(ValueError, match="session_id_parameter"):
        AgentMCPTool(agent, session_id_parameter="session_id")


async def test_agent_tool_always_requires_session_parameter() -> None:
    agent = Agent(client=RecordingClient(), name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(
        agent,
        parameters={"session_id": {"type": "string"}},
        session_id_parameter="session_id",
    )

    definition = (await tool.list_tools()).tools[0]

    assert definition.input_schema["required"] == ["task", "session_id"]


async def test_agent_tool_unknown_tool_name() -> None:
    agent = Agent(client=RecordingClient(), name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(
        agent, parameters={"session_id": {"type": "string"}}, session_id_parameter="session_id", name="available_tool"
    )

    with raises(MCPError, match="Unknown MCP tool") as exc_info:
        await tool.call_tool("made_up_tool", None)

    assert exc_info.value.code == types.INVALID_PARAMS


async def test_agent_tool_rejects_missing_runtime_session_id() -> None:
    agent = Agent(client=RecordingClient(), name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(
        agent,
        parameters={"session_id": {"type": "string"}},
        session_id_parameter="session_id",
    )

    with raises(MCPError) as exc_info:
        await tool.call_tool("agent", {"task": "hello"})

    assert exc_info.value.code == types.INVALID_PARAMS


async def test_agent_tool_propagates_agent_execution_failure() -> None:
    agent = Agent(client=RecordingClient(), name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(agent)

    with (
        patch.object(agent, "run", AsyncMock(side_effect=RuntimeError("agent execution failed"))),
        raises(RuntimeError, match="agent execution failed"),
    ):
        await tool.call_tool("agent", {"task": "hello"})


@pytest.mark.parametrize(
    ("mode", "expected_version"),
    [
        ("auto", "2026-07-28"),
        ("legacy", "2025-11-25"),
    ],
)
async def test_agent_tool_serves_both_protocol_eras(
    mode: str,
    expected_version: str,
) -> None:
    agent = Agent(client=RecordingClient(), name="agent")
    agent_tool: AgentMCPTool[Any] = AgentMCPTool(agent)

    async def list_tools(
        _ctx: ServerRequestContext[dict[str, Any]], _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return await agent_tool.list_tools()

    async def call_tool(
        _ctx: ServerRequestContext[dict[str, Any]], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        return await agent_tool.call_tool(params.name, params.arguments or {})

    server = Server(
        "test-server",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )

    async with Client(server, mode=mode) as mcp_client:
        tools = await mcp_client.list_tools()
        result = await mcp_client.call_tool("agent", {"task": "hello"})

        assert mcp_client.protocol_version == expected_version
        assert [tool.name for tool in tools.tools] == ["agent"]
        assert result.result_type == "complete"
        assert not result.is_error
        assert result.content
