# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, Literal, TypeAlias
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from agent_framework import MCPStreamableHTTPTool
from agent_framework.exceptions import ToolException, ToolExecutionException

MCPHTTPServer: TypeAlias = tuple[httpx.AsyncClient, list[httpx.Request], dict[str, list[str]]]


@pytest.fixture
async def mcp_http_server() -> AsyncIterator[MCPHTTPServer]:
    requests: list[httpx.Request] = []
    writes: dict[str, list[str]] = {"token-a": [], "token-b": [], "token-c": []}

    async def record_request(request: httpx.Request) -> None:
        requests.append(request)

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/unrelated":
            return httpx.Response(200)
        principal = request.headers.get("Authorization", "")
        if principal not in writes:
            return httpx.Response(401)
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        method = body.get("method")
        headers: dict[str, str] = {}
        result: dict[str, Any] = {}
        if method == "initialize":
            headers["mcp-session-id"] = f"session-{principal}"
            result = {
                "protocolVersion": body["params"]["protocolVersion"],
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "auth-test", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "record",
                        "inputSchema": {"type": "object", "properties": {"marker": {"type": "string"}}},
                    }
                ]
            }
        elif method == "tools/call":
            await asyncio.sleep(0)
            marker = body["params"].get("arguments", {}).get("marker")
            if marker is not None:
                writes[principal].append(marker)
            result = {"content": [{"type": "text", "text": principal}]}
        elif method == "prompts/list":
            result = {"prompts": []}
        if "id" not in body:
            return httpx.Response(202)
        return httpx.Response(200, headers=headers, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), event_hooks={"request": [record_request]}
    ) as client:
        yield client, requests, writes


def _tool(client: httpx.AsyncClient, principal: str) -> MCPStreamableHTTPTool:
    return MCPStreamableHTTPTool(
        name=principal,
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        header_provider=lambda kwargs: {"Authorization": kwargs.get("credential", principal)},
    )


def _calls(requests: list[httpx.Request]) -> list[httpx.Request]:
    return [
        request
        for request in requests
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/call"
    ]


@pytest.mark.parametrize("principals", [("token-a", "token-b"), ("token-b", "token-a")])
async def test_shared_client_keeps_tools_and_caller_requests_isolated(
    mcp_http_server: MCPHTTPServer, principals: tuple[str, str]
) -> None:
    client, requests, writes = mcp_http_server
    original_hooks = list(client.event_hooks["request"])
    first, second = (_tool(client, principal) for principal in principals)

    async with first:
        await first.call_tool("record")
        async with second:
            await second.call_tool("record")
            await first.call_tool("record", marker="first-only")
            await client.get("https://mcp.example/unrelated")
            assert "Authorization" not in requests[-1].headers
        await first.call_tool("record")
        await first.connect(reset=True)
        await first.call_tool("record")
        assert len(client.event_hooks["request"]) == len(original_hooks) + 1

    calls = _calls(requests)
    assert [request.headers["Authorization"] for request in calls] == [
        principals[0],
        principals[1],
        principals[0],
        principals[0],
        principals[0],
    ]
    assert calls[2].headers["mcp-session-id"] == f"session-{principals[0]}"
    assert all(
        request.headers["mcp-session-id"] == f"session-{request.headers['Authorization']}"
        for request in requests
        if "mcp-session-id" in request.headers
    )
    assert writes[principals[0]] == ["first-only"]
    assert writes[principals[1]] == []
    assert client.event_hooks["request"] == original_hooks
    assert not client.is_closed
    await client.get("https://mcp.example/unrelated")
    assert "Authorization" not in requests[-1].headers


async def test_closing_another_tool_does_not_skip_inflight_request_hooks(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    started = asyncio.Event()
    release = asyncio.Event()

    async def pause_call(request: httpx.Request) -> None:
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/call":
            started.set()
            await release.wait()

    async with _tool(client, "token-a") as first:
        client.event_hooks["request"].append(pause_call)
        async with _tool(client, "token-b") as second:
            call = asyncio.create_task(second.call_tool("record"))
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                await first.close()
            finally:
                release.set()
                result = await call
    assert isinstance(result, list)
    assert result[0].text == "token-b"
    assert _calls(requests)[-1].headers["Authorization"] == "token-b"
    assert pause_call in client.event_hooks["request"]


@pytest.mark.parametrize("failure", ["entry", "cancellation", "initialize"])
@pytest.mark.parametrize("owned_client", [False, True])
async def test_transport_failure_cleans_up_hooks_and_owned_client(
    mcp_http_server: MCPHTTPServer, failure: str, owned_client: bool
) -> None:
    client, _, _ = mcp_http_server
    original_hooks = list(client.event_hooks["request"])
    tool = _tool(client, "token-a")
    if owned_client:
        tool = MCPStreamableHTTPTool(
            name="owned", url="https://mcp.example/mcp", header_provider=lambda _: {"Authorization": "token-a"}
        )
    if failure == "initialize":
        tool = MCPStreamableHTTPTool(
            name="invalid",
            url="https://mcp.example/mcp",
            http_client=None if owned_client else client,
            header_provider=lambda _: {"Authorization": "invalid-token"},
        )

    @contextlib.asynccontextmanager
    async def transport(**kwargs: Any) -> AsyncGenerator[tuple[()]]:
        if failure == "cancellation":
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
            await asyncio.sleep(0)
        raise RuntimeError("transport entry failed")
        yield ()

    error = asyncio.CancelledError if failure == "cancellation" and sys.version_info >= (3, 11) else ToolException
    transport_patch = (
        contextlib.nullcontext()
        if failure == "initialize"
        else patch("agent_framework._mcp.streamable_http_client", side_effect=transport)
    )
    try:
        with transport_patch, patch("httpx.AsyncClient", return_value=client), pytest.raises(error):
            await tool.connect()
        assert client.event_hooks["request"] == original_hooks
        assert client.is_closed is owned_client
    finally:
        await tool.close()


async def test_owned_client_is_closed_after_successful_session(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    original_hooks = list(client.event_hooks["request"])
    tool = MCPStreamableHTTPTool(
        name="owned",
        url="https://mcp.example/mcp",
        load_prompts=False,
        header_provider=lambda _: {"Authorization": "token-a"},
    )
    with patch("httpx.AsyncClient", return_value=client):
        async with tool:
            await tool.call_tool("record")
    assert client.is_closed
    assert client.event_hooks["request"] == original_hooks


async def test_connecting_another_tool_during_a_call_does_not_capture_its_headers(
    mcp_http_server: MCPHTTPServer,
) -> None:
    client, requests, _ = mcp_http_server
    second = _tool(client, "token-b")
    connected = False

    async def connect_second(request: httpx.Request) -> None:
        nonlocal connected
        if not connected and request.method == "POST" and json.loads(request.content).get("method") == "tools/call":
            connected = True
            await second.connect()

    client.event_hooks["request"].append(connect_second)
    try:
        async with _tool(client, "token-a") as first:
            await first.call_tool("record", credential="token-c")
            await second.call_tool("record")
            assert [request.headers["Authorization"] for request in _calls(requests)] == ["token-c", "token-b"]
            second_initializes = [
                request
                for request in requests
                if request.method == "POST"
                and json.loads(request.content).get("method") == "initialize"
                and request.headers["Authorization"] == "token-b"
            ]
            assert len(second_initializes) == 1
    finally:
        await second.close()
    assert not client.is_closed
    await client.get("https://mcp.example/unrelated")
    assert "Authorization" not in requests[-1].headers


async def test_shared_client_concurrent_calls_keep_dynamic_headers_isolated(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, writes = mcp_http_server
    async with _tool(client, "token-a") as first, _tool(client, "token-b") as second:
        await asyncio.gather(
            first.call_tool("record", credential="token-c", marker="first"),
            second.call_tool("record", credential="token-b", marker="second"),
        )
    calls = _calls(requests)
    assert {request.headers["mcp-session-id"]: request.headers["Authorization"] for request in calls} == {
        "session-token-a": "token-c",
        "session-token-b": "token-b",
    }
    assert writes == {"token-a": [], "token-b": ["second"], "token-c": ["first"]}
    assert all("credential" not in json.loads(request.content)["params"]["arguments"] for request in calls)


async def test_headerless_transport_does_not_inherit_another_transports_credentials(
    mcp_http_server: MCPHTTPServer,
) -> None:
    client, requests, _ = mcp_http_server
    second = MCPStreamableHTTPTool(
        name="unauthenticated", url="https://mcp.example/mcp", http_client=client, load_prompts=False
    )
    attempted = False

    async def connect_second(request: httpx.Request) -> None:
        nonlocal attempted
        if not attempted and request.method == "POST" and json.loads(request.content).get("method") == "tools/call":
            attempted = True
            with pytest.raises(ToolException):
                await second.connect()

    client.event_hooks["request"].append(connect_second)
    try:
        async with _tool(client, "token-a") as first:
            await first.call_tool("record")
            assert attempted
            assert _calls(requests)[-1].headers["Authorization"] == "token-a"
            assert any(
                request.method == "POST"
                and json.loads(request.content).get("method") == "initialize"
                and "Authorization" not in request.headers
                for request in requests
            )
    finally:
        await second.close()


async def test_failed_connect_removes_only_its_own_authentication_hook(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    async with _tool(client, "token-a") as first:
        original_hooks = list(client.event_hooks["request"])
        failed = _tool(client, "invalid-token")
        try:
            with pytest.raises(ToolException):
                await failed.connect()
            assert client.event_hooks["request"] == original_hooks
            await first.call_tool("record")
            assert _calls(requests)[-1].headers["Authorization"] == "token-a"
        finally:
            await failed.close()
    assert not client.is_closed


async def test_prepared_transport_hook_is_removed_on_close(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    original_hooks = list(client.event_hooks["request"])
    tool = _tool(client, "token-a")
    tool.get_mcp_client()
    tool.get_mcp_client()
    await tool.close()
    assert client.event_hooks["request"] == original_hooks


@pytest.mark.parametrize("discovery_method", ["load_tools", "load_prompts"])
@pytest.mark.parametrize("entry_method", ["connect", "context_manager"])
@pytest.mark.parametrize("owned_client", [False, True])
@pytest.mark.parametrize("failure_type", [ToolExecutionException, asyncio.CancelledError])
async def test_discovery_failure_cleans_up_resources(
    mcp_http_server: MCPHTTPServer,
    discovery_method: str,
    entry_method: str,
    owned_client: bool,
    failure_type: type[ToolExecutionException] | type[asyncio.CancelledError],
) -> None:
    client, _, _ = mcp_http_server
    original_hooks = list(client.event_hooks["request"])
    tool = MCPStreamableHTTPTool(
        name="discovery",
        url="https://mcp.example/mcp",
        http_client=None if owned_client else client,
        header_provider=lambda _: {"Authorization": "token-a"},
    )
    failure = failure_type("discovery failed")
    try:
        with (
            patch("httpx.AsyncClient", return_value=client),
            patch.object(tool, discovery_method, new=AsyncMock(side_effect=failure)),
            pytest.raises(failure_type, match="discovery failed") as error,
        ):
            if entry_method == "connect":
                await tool.connect()
            else:
                async with tool:
                    pytest.fail("Failed discovery must not enter the context manager")
        assert error.value is failure
        assert client.event_hooks["request"] == original_hooks
        assert client.is_closed is owned_client
        assert tool.session is None
        assert not tool.is_connected
        assert not tool._tools_loaded
        assert not tool._prompts_loaded
    finally:
        await tool.close()


@pytest.mark.parametrize("discovery_method", ["tools/list", "prompts/list"])
@pytest.mark.parametrize("owned_client", [False, True])
async def test_discovery_failure_retry_starts_a_fresh_session(
    discovery_method: Literal["tools/list", "prompts/list"], owned_client: bool
) -> None:
    initialize_count = 0
    failure_count = 0
    clients: list[httpx.AsyncClient] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal initialize_count, failure_count
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        method = body.get("method")
        if method == discovery_method and body.get("params", {}).get("cursor") and failure_count < 2:
            failure_count += 1
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32603, "message": "discovery failed"}}
            )
        result: dict[str, Any] = {}
        headers: dict[str, str] = {}
        if method == "initialize":
            initialize_count += 1
            headers["mcp-session-id"] = f"session-{initialize_count}"
            result = {
                "protocolVersion": body["params"]["protocolVersion"],
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "discovery-test", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "record" if failure_count == 2 else "partial_record",
                        "inputSchema": {"type": "object", "properties": {"marker": {"type": "string"}}},
                        "_meta": {"source": "discovery"},
                        "execution": {"taskSupport": "optional"},
                    }
                ]
            }
        elif method == "prompts/list":
            result = {"prompts": [{"name": "partial_prompt"}] if failure_count < 2 else []}
        if method == discovery_method and failure_count < 2:
            result["nextCursor"] = "next-page"
        if "id" not in body:
            return httpx.Response(202)
        return httpx.Response(200, headers=headers, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    async_client = httpx.AsyncClient

    def create_client(**kwargs: Any) -> httpx.AsyncClient:
        client = async_client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    tool = MCPStreamableHTTPTool(
        name="discovery",
        url="https://mcp.example/mcp",
        http_client=None if owned_client else create_client(),
        header_provider=lambda _: {"Authorization": "token-a"},
    )
    from mcp.shared.exceptions import McpError

    try:
        with patch("httpx.AsyncClient", side_effect=create_client):
            for _ in range(2):
                with pytest.raises(McpError, match="discovery failed"):
                    await tool.connect()
                assert tool.session is None
                assert not tool.is_connected
                assert not tool._tools_loaded
                assert not tool._prompts_loaded
                assert tool.functions == []
                assert tool._tool_call_meta_by_name == {}
                assert tool._tool_task_support_by_name == {}
                assert tool._tool_param_names_by_name == {}
                assert all(not client.event_hooks["request"] for client in clients)
                assert all(client.is_closed is owned_client for client in clients)
            await tool.connect()
            assert tool.is_connected
            assert [function.name for function in tool.functions] == ["record"]
            assert initialize_count == 3
            assert len(clients) == (3 if owned_client else 1)
            await tool.close()
            assert all(not client.event_hooks["request"] for client in clients)
            assert all(client.is_closed is owned_client for client in clients)
    finally:
        await tool.close()
        for client in clients:
            await client.aclose()


@pytest.mark.parametrize("blocked_method", ["initialize", "tools/list", "prompts/list"])
@pytest.mark.parametrize("entry_method", ["connect", "context_manager"])
@pytest.mark.parametrize("owned_client", [False, True])
async def test_cancelled_connect_caller_releases_abandoned_resources(
    mcp_http_server: MCPHTTPServer, blocked_method: str, entry_method: str, owned_client: bool
) -> None:
    client, requests, _ = mcp_http_server
    setup_started = asyncio.Event()
    release_setup = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def block_setup(request: httpx.Request) -> None:
        if request.method == "POST" and json.loads(request.content).get("method") == blocked_method:
            setup_started.set()
            await release_setup.wait()

    client.event_hooks["request"].append(block_setup)
    original_hooks = list(client.event_hooks["request"])
    tool = MCPStreamableHTTPTool(
        name="cancelled-caller",
        url="https://mcp.example/mcp",
        http_client=None if owned_client else client,
        header_provider=lambda _: {"Authorization": "token-a"},
    )
    close_on_owner = tool._close_on_owner

    async def record_cleanup() -> None:
        await close_on_owner()
        cleanup_finished.set()

    async def enter() -> None:
        if entry_method == "connect":
            await tool.connect()
        else:
            async with tool:
                pytest.fail("Cancelled setup must not enter the context manager")

    with patch("httpx.AsyncClient", return_value=client), patch.object(tool, "_close_on_owner", record_cleanup):
        caller = asyncio.create_task(enter())
        try:
            await asyncio.wait_for(setup_started.wait(), timeout=5)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            assert not client.is_closed
            assert tool._lifecycle_owner_task is not None
            assert not tool._lifecycle_owner_task.done()

            release_setup.set()
            await asyncio.wait_for(cleanup_finished.wait(), timeout=5)
            assert not tool.is_connected
            assert tool.session is None
            assert tool._lifecycle_owner_task is None
            assert client.event_hooks["request"] == original_hooks
            assert client.is_closed is owned_client
            assert any(
                request.method == "DELETE" and request.headers.get("Authorization") == "token-a" for request in requests
            )
        finally:
            release_setup.set()
            await tool.close()


async def test_cancelled_queued_connect_does_not_start_transport(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a")
    caller = asyncio.create_task(tool.connect())
    # This runs before the lifecycle owner created by connect() gets its first turn.
    asyncio.get_running_loop().call_soon(caller.cancel, None)
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert tool._lifecycle_owner_task is None
    await tool.close()
    assert requests == []


async def test_connect_cancelled_during_result_delivery_releases_session(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    original_hooks = list(client.event_hooks["request"])
    tool = _tool(client, "token-a")
    cleanup_finished = asyncio.Event()
    connect_on_owner = tool._connect_on_owner
    close_on_owner = tool._close_on_owner

    async def cancel_before_delivery(*, reset: bool = False, load_configured: bool = True) -> None:
        await connect_on_owner(reset=reset, load_configured=load_configured)
        # Setup succeeds, then the caller is cancelled before consuming the completed future.
        asyncio.get_running_loop().call_soon(caller.cancel, None)

    async def record_cleanup() -> None:
        await close_on_owner()
        cleanup_finished.set()

    with (
        patch.object(tool, "_connect_on_owner", cancel_before_delivery),
        patch.object(tool, "_close_on_owner", record_cleanup),
    ):
        caller = asyncio.create_task(tool.connect())
        try:
            with pytest.raises(asyncio.CancelledError):
                await caller
            await asyncio.wait_for(cleanup_finished.wait(), timeout=5)
            assert tool.session is None
            assert not tool.is_connected
            assert tool._lifecycle_owner_task is None
            assert client.event_hooks["request"] == original_hooks
        finally:
            await tool.close()


async def test_abandoned_connect_is_cleaned_before_next_caller(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    setup_started = asyncio.Event()
    release_setup = asyncio.Event()

    async def block_setup(request: httpx.Request) -> None:
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/list":
            setup_started.set()
            await release_setup.wait()

    client.event_hooks["request"].append(block_setup)
    original_hooks = list(client.event_hooks["request"])
    tool = _tool(client, "token-a")
    caller = asyncio.create_task(tool.connect())
    try:
        await asyncio.wait_for(setup_started.wait(), timeout=5)
        abandoned_session = tool.session
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        retry = asyncio.create_task(tool.connect())
        release_setup.set()
        await asyncio.wait_for(retry, timeout=5)
        assert tool.is_connected
        assert tool.session is not abandoned_session
        assert (
            sum(
                request.method == "POST" and json.loads(request.content).get("method") == "initialize"
                for request in requests
            )
            == 2
        )
        assert len(client.event_hooks["request"]) == len(original_hooks) + 1
    finally:
        release_setup.set()
        await tool.close()


@pytest.mark.parametrize("discovery_method", ["load_tools", "load_prompts"])
@pytest.mark.parametrize("entry_method", ["connect", "context_manager"])
@pytest.mark.parametrize("failure_type", [ToolExecutionException, RuntimeError, asyncio.CancelledError])
async def test_failed_discovery_preserves_caller_supplied_session(
    mcp_http_server: MCPHTTPServer,
    discovery_method: str,
    entry_method: str,
    failure_type: type[Exception] | type[asyncio.CancelledError],
) -> None:
    client, _, _ = mcp_http_server
    async with _tool(client, "token-a") as source:
        supplied_session = source.session
        assert supplied_session is not None
        original_hooks = list(client.event_hooks["request"])
        borrowed = MCPStreamableHTTPTool(
            name="borrowed", url="https://must-not-connect.example/mcp", session=supplied_session
        )
        failure = failure_type("discovery failed")
        expected_error = (
            ToolExecutionException
            if entry_method == "context_manager" and failure_type is RuntimeError
            else failure_type
        )
        with patch.object(
            borrowed, "get_mcp_client", Mock(side_effect=AssertionError("Unexpected transport"))
        ) as transport:
            try:
                with (
                    patch.object(borrowed, discovery_method, AsyncMock(side_effect=failure)),
                    pytest.raises(expected_error),
                ):
                    if entry_method == "connect":
                        await borrowed.connect()
                    else:
                        async with borrowed:
                            pytest.fail("Failed discovery must not enter the context manager")
                assert borrowed.session is supplied_session
                assert not borrowed.is_connected
                assert client.event_hooks["request"] == original_hooks
                assert not client.is_closed
                await supplied_session.send_ping()

                await borrowed.connect()
                assert borrowed.is_connected
                assert borrowed.session is supplied_session
                await borrowed.connect(reset=True)
                assert borrowed.session is supplied_session
                transport.assert_not_called()
            finally:
                await borrowed.close()
        assert borrowed.session is supplied_session
        await supplied_session.send_ping()


async def test_cancelled_redundant_connect_keeps_existing_session(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    async with _tool(client, "token-a") as tool:
        existing_session = tool.session
        original_hooks = list(client.event_hooks["request"])
        connect_on_owner = tool._connect_on_owner

        async def cancel_before_delivery(*, reset: bool = False, load_configured: bool = True) -> None:
            await connect_on_owner(reset=reset, load_configured=load_configured)
            asyncio.get_running_loop().call_soon(caller.cancel, None)

        with patch.object(tool, "_connect_on_owner", cancel_before_delivery):
            caller = asyncio.create_task(tool.connect())
            with pytest.raises(asyncio.CancelledError):
                await caller
        # A subsequent request also confirms that the abandoned action finished processing.
        await tool.connect()
        assert tool.is_connected
        assert tool.session is existing_session
        assert client.event_hooks["request"] == original_hooks
        result = await tool.call_tool("record")
        assert isinstance(result, list)
        assert result[0].text == "token-a"


async def test_cancelled_borrowed_session_caller_can_retry(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    async with _tool(client, "token-a") as source:
        supplied_session = source.session
        assert supplied_session is not None
        borrowed = MCPStreamableHTTPTool(
            name="borrowed", url="https://must-not-connect.example/mcp", session=supplied_session
        )
        setup_started = asyncio.Event()
        release_setup = asyncio.Event()
        load_tools = borrowed.load_tools

        async def block_discovery() -> None:
            setup_started.set()
            await release_setup.wait()
            await load_tools()

        with (
            patch.object(borrowed, "load_tools", block_discovery),
            patch.object(
                borrowed, "get_mcp_client", Mock(side_effect=AssertionError("Unexpected transport"))
            ) as transport,
        ):
            caller = asyncio.create_task(borrowed.connect())
            try:
                await asyncio.wait_for(setup_started.wait(), timeout=5)
                caller.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await caller
                release_setup.set()
                await borrowed.connect()
                assert borrowed.is_connected
                assert borrowed.session is supplied_session
                transport.assert_not_called()
                await supplied_session.send_ping()
            finally:
                release_setup.set()
                await borrowed.close()
