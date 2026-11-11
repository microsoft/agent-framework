# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, nullcontext
from copy import deepcopy
from types import MappingProxyType
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
from jsonschema import SchemaError
from mcp import Client, MCPError, types
from mcp.server import Server, ServerRequestContext
from pytest import raises

from agent_framework_hosting_mcp import AgentMCPTool

_VALID_TOOL_ARGUMENTS: dict[str, Any] = {
    "task": "hello",
    "audience": "developers",
    "model": "approved-model",
    "max_tokens": 8,
    "store": False,
}
_TOOL_PARAMETERS: dict[str, dict[str, Any]] = {
    "audience": {"type": "string", "minLength": 1},
    "metadata": {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
            "priority": {"$ref": "#/properties/metadata/$defs/priority"},
        },
        "required": ["tags", "priority"],
        "additionalProperties": False,
        "$defs": {"priority": {"enum": ["low", "high"]}},
    },
    "selection": {"oneOf": [{"type": "integer", "minimum": 1, "maximum": 3}, {"const": "auto"}]},
}
_CHAT_OPTION_PARAMETERS: dict[str, dict[str, Any]] = {
    "model": {"type": "string", "enum": ["approved-model"]},
    "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8},
    "store": {"type": "boolean", "const": False},
}


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
    client = RecordingClient()
    agent = Agent(client=client, name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(
        agent, parameters={"session_id": {"type": "string"}}, session_id_parameter="session_id", name="available_tool"
    )

    with (
        patch.object(agent, "run", wraps=agent.run) as run_agent,
        patch.object(tool.state.session_store, "get", wraps=tool.state.session_store.get) as get_session,
        patch.object(tool.state.session_store, "set", wraps=tool.state.session_store.set) as set_session,
        raises(MCPError, match="Unknown MCP tool") as exc_info,
    ):
        await tool.call_tool("made_up_tool", None)

    assert exc_info.value.code == types.INVALID_PARAMS
    run_agent.assert_not_called()
    get_session.assert_not_awaited()
    set_session.assert_not_awaited()
    assert not client.calls


@pytest.mark.parametrize("arguments", [{"task": "hello"}, {"task": "hello", "session_id": ""}])
async def test_agent_tool_rejects_invalid_runtime_session_id(arguments: dict[str, Any]) -> None:
    client = RecordingClient()
    agent = Agent(client=client, name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(
        agent,
        parameters={"session_id": {"type": "string"}},
        session_id_parameter="session_id",
    )

    with (
        patch.object(agent, "run", wraps=agent.run) as run_agent,
        patch.object(tool.state.session_store, "get", wraps=tool.state.session_store.get) as get_session,
        patch.object(tool.state.session_store, "set", wraps=tool.state.session_store.set) as set_session,
        raises(MCPError) as exc_info,
    ):
        await tool.call_tool("agent", arguments)

    assert exc_info.value.code == types.INVALID_PARAMS
    run_agent.assert_not_called()
    get_session.assert_not_awaited()
    set_session.assert_not_awaited()
    assert not client.calls


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
        ("direct", None),
        ("auto", "2026-07-28"),
        ("legacy", "2025-11-25"),
    ],
)
@pytest.mark.parametrize("session_mode", ["none", "new", "existing"])
@pytest.mark.parametrize(
    ("arguments", "valid"),
    [
        pytest.param(_VALID_TOOL_ARGUMENTS, True, id="valid-overrides"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": 1}, True, id="valid-minimum"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": 3.0}, True, id="valid-whole-number-float"),
        pytest.param(
            {
                **_VALID_TOOL_ARGUMENTS,
                "metadata": {"tags": ["first"], "priority": "low"},
                "selection": "auto",
            },
            True,
            id="valid-nested-arguments",
        ),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "selection": 2}, True, id="valid-composition"),
        pytest.param(None, False, id="no-arguments"),
        pytest.param({}, False, id="empty-arguments"),
        *(
            pytest.param(
                {key: value for key, value in _VALID_TOOL_ARGUMENTS.items() if key != missing},
                False,
                id=f"missing-{missing}",
            )
            for missing in ("task", "audience", "model", "max_tokens", "store")
        ),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "task": None}, False, id="null-task"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "task": 1}, False, id="non-string-task"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "audience": ""}, False, id="empty-audience"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "model": "other-model"}, False, id="invalid-enum"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": 0}, False, id="below-minimum"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": 9}, False, id="above-maximum"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": "8"}, False, id="numeric-string"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": True}, False, id="boolean-integer"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "max_tokens": 3.5}, False, id="fractional-integer"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "store": True}, False, id="invalid-const"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "store": 0}, False, id="non-boolean-store"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "undeclared": True}, False, id="unknown-property"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "metadata": {}}, False, id="nested-required"),
        pytest.param(
            {**_VALID_TOOL_ARGUMENTS, "metadata": {"tags": [], "priority": "low"}},
            False,
            id="nested-array-length",
        ),
        pytest.param(
            {**_VALID_TOOL_ARGUMENTS, "metadata": {"tags": [1], "priority": "low"}},
            False,
            id="nested-array-item-type",
        ),
        pytest.param(
            {**_VALID_TOOL_ARGUMENTS, "metadata": {"tags": ["first"], "priority": "other"}},
            False,
            id="local-reference",
        ),
        pytest.param(
            {**_VALID_TOOL_ARGUMENTS, "metadata": {"tags": ["first"], "priority": "low", "undeclared": True}},
            False,
            id="nested-unknown-property",
        ),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "selection": 0}, False, id="composition"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "session_id": None}, False, id="null-session-id"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "session_id": 1}, False, id="non-string-session-id"),
        pytest.param({**_VALID_TOOL_ARGUMENTS, "session_id": "other"}, False, id="session-id-pattern"),
    ],
)
async def test_agent_tool_validates_schema_before_execution(
    mode: str,
    expected_version: str | None,
    session_mode: str,
    arguments: dict[str, Any] | None,
    valid: bool,
) -> None:
    client = RecordingClient()
    default_options: ChatOptions[None] = {"model": "default-model", "max_tokens": 2, "store": True}
    agent = Agent(
        client=client,
        name="agent",
        default_options=default_options,
        context_providers=[InMemoryHistoryProvider()],
    )
    state = AgentState(agent)
    if session_mode == "existing":
        session = agent.create_session(session_id="session-1")
        session.state["marker"] = {"values": ["unchanged"]}
        await state.set_session("session-1", session)
    previous_session = await state.session_store.get("session-1")
    previous_snapshot = previous_session.to_dict() if previous_session is not None else None
    parameters = dict(_TOOL_PARAMETERS)
    if session_mode != "none":
        parameters["session_id"] = {"type": "string", "pattern": "^session-[0-9]+$"}
    agent_tool: AgentMCPTool[Any] = AgentMCPTool(
        state,
        parameters=parameters,
        required_parameters=("audience", "model", "max_tokens", "store"),
        chat_option_parameters=_CHAT_OPTION_PARAMETERS,
        session_id_parameter="session_id" if session_mode != "none" else None,
    )
    call_arguments = deepcopy(arguments)
    if session_mode != "none" and call_arguments is not None:
        call_arguments.setdefault("session_id", "session-1")
    arguments_snapshot = deepcopy(call_arguments)
    result: types.CallToolResult | None = None

    with (
        patch.object(agent, "run", wraps=agent.run) as run_agent,
        patch.object(client, "_inner_get_response", wraps=client._inner_get_response) as provider,
        patch.object(state.session_store, "get", wraps=state.session_store.get) as get_session,
        patch.object(state.session_store, "set", wraps=state.session_store.set) as set_session,
    ):
        async with AsyncExitStack() as stack:
            invoke: Callable[[str, dict[str, Any] | None], Awaitable[types.CallToolResult]] = agent_tool.call_tool
            if mode != "direct":

                async def list_tools(
                    _ctx: ServerRequestContext[dict[str, Any]], _params: types.PaginatedRequestParams | None
                ) -> types.ListToolsResult:
                    return await agent_tool.list_tools()

                async def call_tool(
                    _ctx: ServerRequestContext[dict[str, Any]], params: types.CallToolRequestParams
                ) -> types.CallToolResult:
                    return await agent_tool.call_tool(params.name, params.arguments)

                server = Server("test-server", on_list_tools=list_tools, on_call_tool=call_tool)
                mcp_client = await stack.enter_async_context(Client(server, mode=mode))
                tools = await mcp_client.list_tools()
                assert mcp_client.protocol_version == expected_version
                assert [tool.name for tool in tools.tools] == ["agent"]
                assert tools.tools[0].input_schema == (await agent_tool.list_tools()).tools[0].input_schema
                invoke = mcp_client.call_tool

            with nullcontext() if valid else raises(MCPError) as exc_info:
                result = await invoke("agent", call_arguments)

        if valid:
            assert result is not None
            assert result.result_type == "complete"
            assert not result.is_error
            assert result.content
            run_agent.assert_called_once()
            provider.assert_called_once()
            assert call_arguments is not None
            options = provider.call_args.kwargs["options"]
            for option in _CHAT_OPTION_PARAMETERS:
                assert options[option] == call_arguments[option]
                assert type(options[option]) is type(call_arguments[option])
            assert not {"audience", "metadata", "selection", "session_id"} & options.keys()
            if session_mode == "none":
                get_session.assert_not_awaited()
                set_session.assert_not_awaited()
            else:
                get_session.assert_awaited_once_with("session-1")
                assert set_session.await_count == (2 if session_mode == "new" else 1)
        else:
            assert exc_info is not None
            assert exc_info.value.code == types.INVALID_PARAMS
            run_agent.assert_not_called()
            provider.assert_not_called()
            get_session.assert_not_awaited()
            set_session.assert_not_awaited()
            assert not client.calls

    assert call_arguments == arguments_snapshot
    if not valid:
        stored_session = await state.session_store.get("session-1")
        assert (stored_session.to_dict() if stored_session is not None else None) == previous_snapshot


@pytest.mark.parametrize("argument_name", ["task", "prompt"])
async def test_agent_tool_accepts_mapping_arguments(argument_name: str) -> None:
    client = RecordingClient()
    agent = Agent(client=client, name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(agent, argument_name=argument_name)

    result = await tool.call_tool("agent", MappingProxyType({argument_name: "hello"}))

    assert not result.is_error
    assert client.calls == [["hello"]]


async def test_agent_tool_propagates_invalid_schema_configuration() -> None:
    client = RecordingClient()
    agent = Agent(client=client, name="agent")
    tool: AgentMCPTool[Any] = AgentMCPTool(
        agent,
        chat_option_parameters={"max_tokens": {"type": "unsupported"}},
    )

    with raises(SchemaError):
        await tool.call_tool("agent", {"task": "hello", "max_tokens": 1})

    assert not client.calls
