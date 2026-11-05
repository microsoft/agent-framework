# Copyright (c) Microsoft. All rights reserved.

"""Test invocation ownership, protocol isolation, and MCP result compatibility."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx2 as httpx
import pytest
from agent_framework import Content, InMemoryCheckpointStorage
from agent_framework.exceptions import ToolException, ToolExecutionException
from mcp import types
from mcp.server import Server
from mcp.shared.exceptions import MCPError

from agent_framework_declarative._workflows import ToolApprovalResponse, WorkflowFactory
from agent_framework_declarative._workflows._mcp_handler import DefaultMCPToolHandler, MCPToolInvocation

pytestmark = pytest.mark.skipif(sys.version_info >= (3, 14), reason="PowerFx does not support Python 3.14+")


@pytest.mark.parametrize("concurrent", [False, True])
@pytest.mark.parametrize("provider_mode", ["none", "fallback", "borrowed"])
async def test_invocations_own_separate_clients(
    mcp_tool_factory: Callable[[], MagicMock],
    mcp_tool_constructor: MagicMock,
    concurrent: bool,
    provider_mode: str,
) -> None:
    tools = [mcp_tool_factory(), mcp_tool_factory()]
    mcp_tool_constructor.side_effect = tools
    async with httpx.AsyncClient() as client:
        provider = AsyncMock(return_value=client if provider_mode == "borrowed" else None)
        handler = DefaultMCPToolHandler(client_provider=None if provider_mode == "none" else provider)
        invocation = MCPToolInvocation("https://mcp.example/api", "remember", headers={"X-Test": "same-config"})
        if concurrent:
            results = await asyncio.gather(handler.invoke_tool(invocation), handler.invoke_tool(invocation))
        else:
            results = (await handler.invoke_tool(invocation), await handler.invoke_tool(invocation))
        assert all(not result.is_error for result in results)
        assert mcp_tool_constructor.call_count == 2
        assert provider.await_count == (0 if provider_mode == "none" else 2)
        assert not client.is_closed
        for tool in tools:
            tool.connect.assert_awaited_once()
            tool.close.assert_awaited_once()


@pytest.mark.parametrize("provider_mode", ["none", "fallback", "borrowed"])
@pytest.mark.parametrize("concurrent", [False, True])
async def test_real_protocol_sessions_are_terminated_before_return(
    stateful_mcp_server: tuple[Server[Any], dict[str, list[str]], list[httpx.AsyncClient]],
    provider_mode: str,
    concurrent: bool,
) -> None:
    server, histories, clients = stateful_mcp_server
    caller_client = httpx.AsyncClient() if provider_mode == "borrowed" else None
    provider = AsyncMock(return_value=caller_client)
    handler = DefaultMCPToolHandler(client_provider=None if provider_mode == "none" else provider)
    invocation = MCPToolInvocation("http://127.0.0.1:8000/mcp", "remember", headers={"X-Test": "same-config"})
    try:
        async with server.session_manager.run():
            if concurrent:
                results = await asyncio.gather(handler.invoke_tool(invocation), handler.invoke_tool(invocation))
            else:
                results = (await handler.invoke_tool(invocation), await handler.invoke_tool(invocation))
            assert [result.outputs[0].text for result in results] == ["1", "1"]
            assert len(histories) == 2
            assert not server.session_manager._server_instances
            assert all(client.is_closed for client in clients if client is not caller_client)
            if caller_client is not None:
                assert not caller_client.is_closed
                assert not caller_client.event_hooks["request"]
            result = await handler.invoke_tool(
                MCPToolInvocation(invocation.server_url, "tools/list", headers=dict(invocation.headers))
            )
            assert not result.is_error
            assert len(histories) == 3
            assert not server.session_manager._server_instances
    finally:
        if caller_client is not None:
            await caller_client.aclose()
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("streaming", [False, True])
async def test_shared_handler_isolates_independent_workflows(
    stateful_mcp_server: tuple[Server[Any], dict[str, list[str]], list[httpx.AsyncClient]], streaming: bool
) -> None:
    server, histories, clients = stateful_mcp_server
    factory = WorkflowFactory(mcp_tool_handler=DefaultMCPToolHandler())
    definition = {
        "name": "isolation",
        "actions": [
            {
                "kind": "InvokeMcpTool",
                "id": "remember",
                "serverUrl": "http://127.0.0.1:8000/mcp",
                "toolName": "remember",
                "headers": {"X-Test": "same-config"},
            }
        ],
    }
    workflows = [factory.create_workflow_from_definition(definition) for _ in range(2)]
    async with server.session_manager.run():
        if streaming:
            await asyncio.gather(*(workflow.run({}, stream=True).get_final_response() for workflow in workflows))
        else:
            await asyncio.gather(*(workflow.run({}) for workflow in workflows))
        assert sorted(map(len, histories.values())) == [1, 1]
        assert not server.session_manager._server_instances
    assert all(client.is_closed for client in clients)


async def test_approval_checkpoint_resume_uses_fresh_protocol_session(
    stateful_mcp_server: tuple[Server[Any], dict[str, list[str]], list[httpx.AsyncClient]],
) -> None:
    server, histories, clients = stateful_mcp_server
    factory = WorkflowFactory(mcp_tool_handler=DefaultMCPToolHandler())
    definition = {
        "name": "approval-resume",
        "actions": [
            {
                "kind": "InvokeMcpTool",
                "id": action_id,
                "serverUrl": "http://127.0.0.1:8000/mcp",
                "toolName": "remember",
                "requireApproval": approval,
            }
            for action_id, approval in (("before_pause", False), ("after_pause", True))
        ],
    }
    storage = InMemoryCheckpointStorage()
    async with server.session_manager.run():
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({}, checkpoint_storage=storage)
        assert sorted(map(len, histories.values())) == [1]
        assert not server.session_manager._server_instances
        [request] = (await workflow._runner_context.get_pending_request_info_events()).values()
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None
        resumed = factory.create_workflow_from_definition(definition)
        await resumed.run(
            checkpoint_id=checkpoint_id,
            checkpoint_storage=storage,
            responses={request.request_id: ToolApprovalResponse(approved=True)},
        )
        assert sorted(map(len, histories.values())) == [1, 1]
        assert not server.session_manager._server_instances
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(
    "error",
    [
        ToolException("connection failed"),
        ToolExecutionException("tool error"),
        httpx.ReadTimeout("timeout"),
        MCPError(-32603, "MCP error"),
        ValueError("invalid configuration"),
    ],
)
async def test_connection_errors_clean_up_and_propagate(
    mcp_tool: MagicMock, mcp_tool_constructor: MagicMock, error: Exception
) -> None:
    mcp_tool.connect.side_effect = error
    with pytest.raises(type(error)) as excinfo:
        await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    assert excinfo.value is error
    mcp_tool.call_tool.assert_not_awaited()
    mcp_tool.close.assert_awaited_once()


async def test_remote_tool_error_returns_error_result(mcp_tool: MagicMock, mcp_tool_constructor: MagicMock) -> None:
    mcp_tool.call_tool.side_effect = ToolExecutionException("tool error")
    result = await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    assert result.is_error
    assert result.error_message == "tool error"
    assert result.outputs[0].text is not None
    assert result.outputs[0].text.startswith("Error:")
    mcp_tool.close.assert_awaited_once()


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("error", [httpx.ReadTimeout("timeout"), MCPError(-32603, "MCP error")])
async def test_call_transport_errors_clean_up_and_propagate(
    mcp_tool: MagicMock, mcp_tool_constructor: MagicMock, error: Exception, wrapped: bool
) -> None:
    failure = ToolExecutionException("Failed to call tool", inner_exception=error) if wrapped else error
    if wrapped:
        failure.__cause__ = error
    mcp_tool.call_tool.side_effect = failure
    with pytest.raises(type(failure)) as excinfo:
        await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    assert excinfo.value is failure
    if wrapped:
        assert excinfo.value.__cause__ is error
    mcp_tool.close.assert_awaited_once()


@pytest.mark.parametrize("stage", ["connect", "call_tool"])
async def test_cancellation_cleans_up_and_propagates(
    mcp_tool: MagicMock, mcp_tool_constructor: MagicMock, stage: str
) -> None:
    getattr(mcp_tool, stage).side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    mcp_tool.close.assert_awaited_once()


async def test_repeated_cancellation_waits_for_cleanup(mcp_tool: MagicMock, mcp_tool_constructor: MagicMock) -> None:
    release = asyncio.Event()
    mcp_tool.close.side_effect = release.wait
    task = asyncio.create_task(
        DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    )
    try:
        for _ in range(10):
            await asyncio.sleep(0)
            if mcp_tool.close.await_count:
                break
        assert mcp_tool.close.await_count == 1
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_unexpected_call_error_propagates(mcp_tool: MagicMock, mcp_tool_constructor: MagicMock) -> None:
    mcp_tool.call_tool.side_effect = RuntimeError("programming error")
    with pytest.raises(RuntimeError, match="programming error"):
        await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    mcp_tool.close.assert_awaited_once()


@pytest.mark.parametrize("call_fails", [False, True])
async def test_cleanup_error_does_not_replace_invocation_outcome(
    mcp_tool: MagicMock, mcp_tool_constructor: MagicMock, caplog: pytest.LogCaptureFixture, call_fails: bool
) -> None:
    mcp_tool.close.side_effect = RuntimeError("cleanup failed")
    handler = DefaultMCPToolHandler()
    invocation = MCPToolInvocation("https://mcp.example/api", "remember")
    if call_fails:
        mcp_tool.call_tool.side_effect = RuntimeError("call failed")
        with pytest.raises(RuntimeError, match="call failed"):
            await handler.invoke_tool(invocation)
    else:
        result = await handler.invoke_tool(invocation)
        assert not result.is_error
    assert "error closing invocation MCP client" in caplog.text


@pytest.mark.parametrize("error", [RuntimeError("provider failed"), httpx.ConnectError("connection failed")])
async def test_provider_failure_propagates_without_constructing_tool(
    mcp_tool_constructor: MagicMock, error: Exception
) -> None:
    provider = AsyncMock(side_effect=error)
    with pytest.raises(type(error)) as excinfo:
        await DefaultMCPToolHandler(client_provider=provider).invoke_tool(
            MCPToolInvocation("https://mcp.example/api", "remember")
        )
    assert excinfo.value is error
    mcp_tool_constructor.assert_not_called()


@pytest.mark.parametrize("raw", ["plain text", [Content.from_text("first"), Content.from_text("second")]])
async def test_result_normalisation(mcp_tool: MagicMock, mcp_tool_constructor: MagicMock, raw: Any) -> None:
    mcp_tool.call_tool.return_value = raw
    result = await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "remember"))
    assert [content.text for content in result.outputs] == (
        ["plain text"] if isinstance(raw, str) else ["first", "second"]
    )


async def test_constructor_passes_invocation_and_discovery_options(mcp_tool_constructor: MagicMock) -> None:
    invocation = MCPToolInvocation(
        "https://mcp.example/api", "remember", server_label="label", headers={"X-Test": "value"}
    )
    await DefaultMCPToolHandler(max_discovery_pages=12, max_discovery_items=345).invoke_tool(invocation)
    assert mcp_tool_constructor.call_args.kwargs == {
        "name": "label",
        "url": invocation.server_url,
        "load_prompts": False,
        "http_client": None,
        "static_headers": {"X-Test": "value"},
        "max_discovery_pages": 12,
        "max_discovery_items": 345,
    }
    assert mcp_tool_constructor.call_args.kwargs["static_headers"] is not invocation.headers


@pytest.mark.parametrize("option", ["max_discovery_pages", "max_discovery_items"])
@pytest.mark.parametrize("value", [0, -1])
def test_invalid_discovery_limit_raises(option: str, value: int) -> None:
    with pytest.raises(ValueError, match=f"{option} must be positive or None"):
        if option == "max_discovery_pages":
            DefaultMCPToolHandler(max_discovery_pages=value)
        else:
            DefaultMCPToolHandler(max_discovery_items=value)


async def test_list_tools_rejects_arguments_before_provider(mcp_tool_constructor: MagicMock) -> None:
    provider = AsyncMock()
    with pytest.raises(ValueError, match="The reserved MCP 'tools/list' operation does not accept tool arguments"):
        await DefaultMCPToolHandler(client_provider=provider).invoke_tool(
            MCPToolInvocation("https://mcp.example/api", "tools/list", arguments={"unexpected": True})
        )
    provider.assert_not_awaited()
    mcp_tool_constructor.assert_not_called()


async def test_list_tools_preserves_catalog_and_pagination(
    mcp_tool: MagicMock, mcp_tool_constructor: MagicMock
) -> None:
    list_page = mcp_tool._require_connection.return_value.list_tools_page
    list_page.side_effect = [
        types.ListToolsResult(
            tools=[
                types.Tool(
                    name="first",
                    description="description",
                    input_schema={"type": "object"},
                    output_schema={"type": "string"},
                )
            ],
            next_cursor="next",
        ),
        types.ListToolsResult(tools=[types.Tool(name="second", input_schema={"type": "object"})]),
    ]
    result = await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "tools/list"))
    text = result.outputs[0].text
    assert text is not None
    assert json.loads(text) == {
        "tools": [
            {
                "name": "first",
                "description": "description",
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "string"},
            },
            {"name": "second", "description": None, "inputSchema": {"type": "object"}, "outputSchema": None},
        ]
    }
    assert list(json.loads(text)["tools"][0]) == ["name", "description", "inputSchema", "outputSchema"]
    assert "\n  " in text
    assert list_page.await_args_list[0].args == (None,)
    assert list_page.await_args_list[1].args[0].cursor == "next"
    mcp_tool.call_tool.assert_not_awaited()
    mcp_tool.close.assert_awaited_once()


async def test_list_tools_disconnected_error(mcp_tool: MagicMock, mcp_tool_constructor: MagicMock) -> None:
    mcp_tool._require_connection.side_effect = RuntimeError("disconnected")
    with pytest.raises(RuntimeError, match="disconnected"):
        await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "tools/list"))
    mcp_tool.close.assert_awaited_once()


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("timeout"), MCPError(-32603, "MCP error"), ToolExecutionException("discovery failed")]
)
async def test_list_tools_transport_error(
    mcp_tool: MagicMock, mcp_tool_constructor: MagicMock, error: Exception
) -> None:
    mcp_tool._require_connection.return_value.list_tools_page.side_effect = error
    with pytest.raises(type(error)) as excinfo:
        await DefaultMCPToolHandler().invoke_tool(MCPToolInvocation("https://mcp.example/api", "tools/list"))
    assert excinfo.value is error
    mcp_tool.close.assert_awaited_once()
