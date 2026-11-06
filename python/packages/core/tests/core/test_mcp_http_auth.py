# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from typing import Any, Literal, TypeAlias, cast
from unittest.mock import AsyncMock, Mock, patch

import httpx2 as httpx
import pytest
from mcp.client.session import ClientSession

from agent_framework import Agent, FunctionInvocationContext, MCPStreamableHTTPTool
from agent_framework.exceptions import ToolException, ToolExecutionException

from .mcp_http_helpers import MCPHTTPBarrier

MCPHTTPServer: TypeAlias = tuple[httpx.AsyncClient, list[httpx.Request], dict[str, list[str]]]
MCPHTTPClientFactory: TypeAlias = tuple[Callable[..., httpx.AsyncClient], list[httpx.Request], dict[str, list[str]]]


@pytest.fixture
async def mcp_http_client_factory() -> AsyncIterator[MCPHTTPClientFactory]:
    requests: list[httpx.Request] = []
    writes: dict[str, list[str]] = {"token-a": [], "token-A": [], "token-b": [], "token-c": []}

    async def record_request(request: httpx.Request) -> None:
        requests.append(request)

    async def handle(request: httpx.Request, protocol_version: str | None) -> httpx.Response:
        if request.url.path == "/unrelated":
            return httpx.Response(200)
        principal = request.headers.get("Authorization", "")
        if principal not in writes and principal != "rejected-token":
            return httpx.Response(401)
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        method = body.get("method")
        if principal == "rejected-token":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32001, "message": "rejected"}},
            )
        headers: dict[str, str] = {}
        result: dict[str, Any] = {}
        if method == "server/discover" and protocol_version == "2026-07-28":
            result = {"supportedVersions": [protocol_version], "capabilities": {"tools": {}, "prompts": {}}}
        elif method == "initialize":
            headers["mcp-session-id"] = f"session-{principal}"
            result = {
                "protocolVersion": protocol_version or body["params"]["protocolVersion"],
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "auth-test", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "record",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "marker": {"type": "string"},
                                **(
                                    {"credential": {"type": "string"}}
                                    if request.headers.get("X-Test-Declare-Credential") == "true"
                                    else {}
                                ),
                            },
                        },
                    },
                    {
                        "name": f"{principal}-only",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                ]
            }
        elif method == "tools/call":
            await asyncio.sleep(0)
            marker = body["params"].get("arguments", {}).get("marker")
            if marker is not None:
                writes[principal].append(marker)
            result = {"content": [{"type": "text", "text": principal}]}
        elif method == "prompts/list":
            result = (
                {
                    "prompts": [
                        {
                            "name": "principal-prompt",
                            "arguments": [{"name": "topic", "required": True}],
                        }
                    ]
                }
                if request.headers.get("X-Test-Prompts") == "enabled"
                else {"prompts": []}
            )
        elif method == "prompts/get":
            topic = body["params"].get("arguments", {}).get("topic", "")
            result = {
                "description": principal,
                "messages": [{"role": "user", "content": {"type": "text", "text": f"{principal}:{topic}"}}],
            }
        if protocol_version == "2026-07-28" and method in ("tools/list", "prompts/list"):
            result.update(resultType="complete", cacheScope="private", ttlMs=0)
        if protocol_version == "2026-07-28" and method in ("tools/call", "prompts/get"):
            result["resultType"] = "complete"
        if "id" not in body:
            return httpx.Response(202)
        return httpx.Response(200, headers=headers, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    async_client = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []

    def create_client(
        *,
        response_cookies: dict[str, str] | None = None,
        before_request: Callable[[httpx.Request], Awaitable[None]] | None = None,
        protocol_version: str | None = None,
        **kwargs: Any,
    ) -> httpx.AsyncClient:
        async def handle_with_cookies(request: httpx.Request) -> httpx.Response:
            if before_request is not None:
                await before_request(request)
            response = await handle(request, protocol_version)
            if response_cookies and request.method == "POST":
                method = json.loads(request.content).get("method")
                if method in response_cookies:
                    response.headers["Set-Cookie"] = response_cookies[method]
            return response

        client = async_client(transport=httpx.MockTransport(handle_with_cookies), **kwargs)
        client.event_hooks["request"].insert(0, record_request)
        clients.append(client)
        return client

    try:
        yield create_client, requests, writes
    finally:
        for client in clients:
            await client.aclose()


@pytest.fixture
async def mcp_http_server(mcp_http_client_factory: MCPHTTPClientFactory) -> AsyncIterator[MCPHTTPServer]:
    create_client, requests, writes = mcp_http_client_factory
    async with create_client() as client:
        yield client, requests, writes


def _tool(client: httpx.AsyncClient, principal: str, *, declare_credential: bool = False) -> MCPStreamableHTTPTool:
    return MCPStreamableHTTPTool(
        name=principal,
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        static_headers={"X-Test-Declare-Credential": "true"} if declare_credential else None,
        header_provider=lambda kwargs: {"Authorization": kwargs.get("credential", principal)},
    )


def _connected_client(tool: MCPStreamableHTTPTool) -> Any:
    connection = tool._require_connection()
    assert connection.client is not None
    return connection.client


def _calls(requests: list[httpx.Request]) -> list[httpx.Request]:
    return [
        request
        for request in requests
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/call"
    ]


def _requests_for_method(requests: list[httpx.Request], method: str) -> list[httpx.Request]:
    return [
        request
        for request in requests
        if request.method == "POST" and json.loads(request.content).get("method") == method
    ]


@pytest.mark.parametrize("protocol_version", ["2025-11-25", "2026-07-28"])
@pytest.mark.parametrize("header_source", ["dynamic", "static", "client"])
async def test_same_identity_http_requests_overlap(
    mcp_http_client_factory: MCPHTTPClientFactory, protocol_version: str, header_source: str
) -> None:
    create_client, requests, writes = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call", "prompts/get")
    headers = {"Authorization": "token-a", "X-Test-Prompts": "enabled"}
    client = create_client(
        before_request=barrier.before_request,
        protocol_version=protocol_version,
        headers=headers if header_source == "client" else None,
    )
    tool = MCPStreamableHTTPTool(
        name="parallel",
        url="https://mcp.example/mcp",
        http_client=client,
        static_headers=headers if header_source == "static" else None,
        header_provider=(lambda _: headers) if header_source == "dynamic" else None,
    )
    async with tool:
        first = asyncio.create_task(tool.call_tool("record", marker="first"))
        second = asyncio.create_task(tool.call_tool("record", marker="second"))
        prompt = asyncio.create_task(tool.get_prompt("principal-prompt", topic="parallel"))
        try:
            arrivals = [await barrier.next_request() for _ in range(3)]
            assert {json.loads(request.content)["method"] for request in arrivals} == {"tools/call", "prompts/get"}
            assert all(request.headers["Authorization"] == "token-a" for request in arrivals)
            assert all(not task.done() for task in (first, second, prompt))
            if protocol_version == "2025-11-25":
                assert {request.headers["mcp-session-id"] for request in arrivals} == {"session-token-a"}
        finally:
            barrier.release.set()
            await asyncio.gather(first, second, prompt)
        assert await prompt == "token-a:parallel"
    assert sorted(writes["token-a"]) == ["first", "second"]
    assert len(_requests_for_method(requests, "initialize")) == (1 if protocol_version == "2025-11-25" else 0)
    assert len(_requests_for_method(requests, "server/discover")) == 1


@pytest.mark.parametrize("transition", ["identity", "reset", "close", "tools", "prompts"])
@pytest.mark.parametrize("header_source", ["dynamic", "static", "client"])
async def test_http_transition_waits_for_active_requests(
    mcp_http_client_factory: MCPHTTPClientFactory, transition: str, header_source: str
) -> None:
    if transition == "identity" and header_source != "dynamic":
        pytest.skip("Fixed headers do not have a runtime identity transition.")
    create_client, requests, writes = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call")
    tool = MCPStreamableHTTPTool(
        name="transition",
        url="https://mcp.example/mcp",
        http_client=create_client(
            before_request=barrier.before_request,
            headers={"Authorization": "token-a"} if header_source == "client" else None,
        ),
        static_headers={"Authorization": "token-a"} if header_source == "static" else None,
        header_provider=(lambda kwargs: {"Authorization": kwargs.get("credential", "token-a")})
        if header_source == "dynamic"
        else None,
        load_prompts=False,
    )
    async with tool:
        active = asyncio.create_task(tool.call_tool("record", marker="active"))
        await barrier.next_request()
        waiting: asyncio.Task[object]
        if transition == "identity":
            waiting = asyncio.create_task(tool.call_tool("record", marker="new", credential="token-b"))
        elif transition == "reset":
            waiting = asyncio.create_task(tool.connect(reset=True))
        elif transition == "close":
            waiting = asyncio.create_task(tool.close())
        elif transition == "tools":
            waiting = asyncio.create_task(tool.load_tools())
        else:
            waiting = asyncio.create_task(tool.load_prompts())
        try:
            for _ in range(10):
                await asyncio.sleep(0)
            assert not waiting.done()
            assert len(_requests_for_method(requests, "initialize")) == 1
            assert len(_requests_for_method(requests, "tools/list")) == 1
            assert not any(request.method == "DELETE" for request in requests)
        finally:
            barrier.release.set()
            await asyncio.gather(active, waiting)
        if transition == "identity":
            assert writes["token-b"] == ["new"]
            assert all(function.name != "token-a-only" for function in tool.functions)
            assert any(function.name == "token-b-only" for function in tool.functions)
            assert any(
                request.method == "DELETE" and request.headers["Authorization"] == "token-a" for request in requests
            )
    assert writes["token-a"] == ["active"]


async def test_cancelled_identity_waiter_does_not_block_same_identity_calls(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    create_client, requests, _ = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call")
    tool = _tool(create_client(before_request=barrier.before_request), "token-a")
    async with tool:
        first = asyncio.create_task(tool.call_tool("record", marker="first"))
        await barrier.next_request()
        changing = asyncio.create_task(tool.call_tool("record", marker="changing", credential="token-b"))
        for _ in range(10):
            await asyncio.sleep(0)
        changing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await changing
        second = asyncio.create_task(tool.call_tool("record", marker="second"))
        try:
            request = await barrier.next_request()
            assert request.headers["Authorization"] == "token-a"
            assert not first.done()
            assert not second.done()
        finally:
            barrier.release.set()
            await asyncio.gather(first, second)
    assert len(_requests_for_method(requests, "initialize")) == 1


@pytest.mark.parametrize("stage", ["lock", "active", "reconcile", "lifecycle"])
async def test_header_admission_timeout_never_dispatches_the_waiting_call(
    mcp_http_client_factory: MCPHTTPClientFactory, stage: str
) -> None:
    create_client, requests, _ = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call" if stage == "active" else "initialize")
    client = create_client()
    tool = _tool(client, "token-a")
    async with tool, asyncio.timeout(5):
        client.event_hooks["request"].append(barrier.before_request)
        active = None
        if stage == "active":
            active = asyncio.create_task(tool.call_tool("record", marker="active"))
            await barrier.next_request()
        elif stage == "lifecycle":
            resetting = asyncio.create_task(tool.connect(reset=True))
            await barrier.next_request()
            resetting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await resetting
        try:
            with patch.object(tool, "request_timeout", 0.05):
                async with contextlib.AsyncExitStack() as stack:
                    if stage == "lock":
                        await stack.enter_async_context(tool._call_headers_lock)
                    with pytest.raises(ToolExecutionException, match="Timed out.*header admission") as error:
                        await tool.call_tool("record", credential="token-b", marker="must-not-send")
                    assert isinstance(error.value.__cause__, TimeoutError)
                assert tool._header_operations == (1 if stage == "active" else 0)
                assert not any(
                    json.loads(request.content)["params"]["arguments"].get("marker") == "must-not-send"
                    for request in _calls(requests)
                )
                if active is not None:
                    assert not active.done()
        finally:
            barrier.release.set()
            if active is not None:
                await active
            await tool._lifecycle_idle.wait()
        if not tool.is_connected:
            await tool.connect()
        await tool.call_tool("record", marker="after-timeout")
        assert _calls(requests)[-1].headers["Authorization"] == "token-a"


@pytest.mark.parametrize("prepare", [False, True])
async def test_header_admission_none_waits_until_identity_transition_can_finish(
    mcp_http_client_factory: MCPHTTPClientFactory, prepare: bool
) -> None:
    create_client, _, writes = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call")
    tool = _tool(create_client(before_request=barrier.before_request), "token-a")
    async with tool, asyncio.timeout(5):
        active = asyncio.create_task(tool.call_tool("record", marker="active"))
        await barrier.next_request()
        with patch.object(tool, "request_timeout", None):
            waiting = asyncio.create_task(
                tool._prepare_for_run({"credential": "token-b"})
                if prepare
                else tool.call_tool("record", credential="token-b", marker="waiting")
            )
            try:
                for _ in range(10):
                    await asyncio.sleep(0)
                assert not waiting.done()
            finally:
                barrier.release.set()
                await asyncio.gather(active, waiting)
        assert writes["token-a"] == ["active"]
        assert tool._header_operations == 0
        assert tool._session_header_identity == (("authorization", "token-b"),)


async def test_run_preparation_uses_the_header_admission_budget(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a")
    async with tool:
        async with tool._call_headers_lock:
            with (
                patch.object(tool, "request_timeout", 0.05),
                pytest.raises(ToolExecutionException, match="Timed out.*header admission"),
            ):
                await tool._prepare_for_run({"credential": "token-b"})
        assert len(_requests_for_method(requests, "initialize")) == 1
        await tool.call_tool("record", marker="after-timeout")


@pytest.mark.parametrize("stream", [False, True])
async def test_same_identity_agent_run_prepares_while_another_rpc_is_active(
    mcp_http_client_factory: MCPHTTPClientFactory, chat_client_base: Any, stream: bool
) -> None:
    create_client, requests, writes = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call")
    tool = _tool(create_client(before_request=barrier.before_request), "token-a")
    agent = Agent(client=chat_client_base, tools=tool)

    async def run_agent() -> str:
        if stream:
            return "".join([
                update.text
                async for update in agent.run(
                    "prepare", stream=True, function_invocation_kwargs={"credential": "token-a"}
                )
            ])
        return (await agent.run("prepare", function_invocation_kwargs={"credential": "token-a"})).text

    async with tool, asyncio.timeout(5):
        active = asyncio.create_task(tool.call_tool("record", marker="active"))
        await barrier.next_request()
        try:
            assert await asyncio.wait_for(run_agent(), timeout=1)
            assert not active.done()
            assert len(_requests_for_method(requests, "initialize")) == 1
        finally:
            barrier.release.set()
            await active
        assert writes["token-a"] == ["active"]


async def test_header_admission_budget_does_not_wrap_the_admitted_rpc(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    create_client, _, writes = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call")
    tool = _tool(create_client(before_request=barrier.before_request), "token-a")
    async with tool, asyncio.timeout(5):
        with patch.object(tool, "request_timeout", 0.05):
            calling = asyncio.create_task(tool.call_tool("record", marker="slow-rpc"))
            try:
                await barrier.next_request()
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(calling), timeout=0.1)
                assert not calling.done()
                assert tool._header_operations == 1
            finally:
                barrier.release.set()
                await calling
        assert writes["token-a"] == ["slow-rpc"]


@pytest.mark.parametrize("blocked_method", ["initialize", "tools/list"])
@pytest.mark.parametrize("dynamic_headers", [False, True])
async def test_close_interrupts_recovery_without_retry_and_explicit_reconnect_still_works(
    mcp_http_server: MCPHTTPServer, blocked_method: str, dynamic_headers: bool
) -> None:
    from anyio import ClosedResourceError

    client, requests, writes = mcp_http_server
    tool = (
        _tool(client, "token-a")
        if dynamic_headers
        else MCPStreamableHTTPTool(
            name="static",
            url="https://mcp.example/mcp",
            http_client=client,
            static_headers={"Authorization": "token-a"},
            load_prompts=False,
        )
    )
    barrier = MCPHTTPBarrier(blocked_method)
    tasks: list[asyncio.Task[Any]] = []
    try:
        async with asyncio.timeout(5):
            await tool.connect()
            client.event_hooks["request"].append(barrier.before_request)
            with patch.object(_connected_client(tool), "call_tool", side_effect=ClosedResourceError()):
                call = asyncio.create_task(tool.call_tool("record", marker="must-not-retry"))
                tasks.append(call)
                await barrier.next_request()
                closing = asyncio.create_task(tool.close())
                tasks.append(closing)
                await asyncio.sleep(0)
                barrier.release.set()
                with pytest.raises(ToolExecutionException, match="interrupted by close|Failed to reconnect"):
                    await call
                await closing
            assert not tool.is_connected
            assert tool._connection is None
            assert not tool._tools_loaded
            assert tool._header_operations == 0
            assert len(_requests_for_method(requests, "initialize")) == 2
            assert writes["token-a"] == []
            await tool.connect()
            await tool.call_tool("record", marker="explicit-reconnect")
            assert writes["token-a"] == ["explicit-reconnect"]
    finally:
        barrier.release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await tool.close()


async def test_close_queued_behind_a_failed_attempt_prevents_recovery(mcp_http_server: MCPHTTPServer) -> None:
    from anyio import ClosedResourceError

    client, requests, writes = mcp_http_server
    tool = _tool(client, "token-a")
    started = asyncio.Event()
    release = asyncio.Event()

    async def fail_call(*args: Any, **kwargs: Any) -> None:
        started.set()
        await release.wait()
        raise ClosedResourceError

    async with tool, asyncio.timeout(5):
        with patch.object(_connected_client(tool), "call_tool", side_effect=fail_call):
            call = asyncio.create_task(tool.call_tool("record", marker="must-not-retry"))
            await started.wait()
            closing = asyncio.create_task(tool.close())
            try:
                await asyncio.sleep(0)
                assert not closing.done()
            finally:
                release.set()
                await closing
            with pytest.raises(ToolExecutionException, match="interrupted by close"):
                await call
        assert len(_requests_for_method(requests, "initialize")) == 1
        assert not tool.is_connected
        assert writes["token-a"] == []


@pytest.mark.parametrize("timeout", [0.05, None])
@pytest.mark.parametrize("stage", ["reconnect", "discovery"])
async def test_recovery_budget_covers_reconnect_and_discovery(
    mcp_http_server: MCPHTTPServer, timeout: float | None, stage: str
) -> None:
    from anyio import ClosedResourceError

    client, _, writes = mcp_http_server
    tool = _tool(client, "token-a")
    started = asyncio.Event()
    release = asyncio.Event()
    method = "_reconnect_without_loading" if stage == "reconnect" else "_load_configured_discovery_locked"
    original = getattr(tool, method)

    async def block_recovery() -> None:
        started.set()
        await release.wait()
        await original()

    async with tool, asyncio.timeout(5):
        with (
            patch.object(_connected_client(tool), "call_tool", side_effect=ClosedResourceError()),
            patch.object(tool, method, side_effect=block_recovery),
            patch.object(tool, "request_timeout", timeout),
        ):
            call = asyncio.create_task(tool.call_tool("record", marker="retry"))
            try:
                await started.wait()
                if timeout is None:
                    for _ in range(10):
                        await asyncio.sleep(0)
                    assert not call.done()
                    release.set()
                    await call
                    assert writes["token-a"] == ["retry"]
                else:
                    with pytest.raises(ToolExecutionException, match="Timed out recovering") as error:
                        await call
                    assert isinstance(error.value.__cause__, TimeoutError)
                    assert writes["token-a"] == []
            finally:
                release.set()
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)
        assert tool._header_operations == 0


async def test_recovery_budget_includes_waiting_for_other_active_attempts(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    from anyio import ClosedResourceError

    create_client, _, writes = mcp_http_client_factory
    barrier = MCPHTTPBarrier("tools/call")
    tool = _tool(create_client(before_request=barrier.before_request), "token-a")
    async with tool, asyncio.timeout(5):
        active = asyncio.create_task(tool.call_tool("record", marker="active"))
        await barrier.next_request()
        try:
            with (
                patch.object(_connected_client(tool), "call_tool", side_effect=ClosedResourceError()),
                patch.object(tool, "request_timeout", 0.05),
                pytest.raises(ToolExecutionException, match="Timed out recovering"),
            ):
                await tool.call_tool("record", marker="must-not-retry")
            assert not active.done()
            assert tool._header_operations == 1
        finally:
            barrier.release.set()
            await active
        await tool.call_tool("record", marker="after-timeout")
        assert writes["token-a"] == ["active", "after-timeout"]


async def test_direct_prompt_resolves_current_identity_instead_of_reusing_previous_caller(
    mcp_http_server: MCPHTTPServer,
) -> None:
    client, requests, _ = mcp_http_server
    principal = ContextVar("prompt_principal", default="token-a")
    tool = MCPStreamableHTTPTool(
        name="prompt",
        url="https://mcp.example/mcp",
        http_client=client,
        header_provider=lambda _: {"Authorization": principal.get(), "X-Test-Prompts": "enabled"},
    )
    async with tool:
        token = principal.set("token-b")
        try:
            assert await tool.get_prompt("principal-prompt", topic="new-caller") == "token-b:new-caller"
        finally:
            principal.reset(token)
    assert _requests_for_method(requests, "prompts/get")[0].headers["Authorization"] == "token-b"
    assert len(_requests_for_method(requests, "initialize")) == 2


async def test_direct_prompt_in_detached_child_does_not_reuse_completed_invocation_headers(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    create_client, requests, _ = mcp_http_client_factory
    principal = ContextVar("child_prompt_principal", default="token-a")
    start_child = asyncio.Event()
    children: list[asyncio.Task[str]] = []

    async def call_prompt() -> str:
        await start_child.wait()
        token = principal.set("token-b")
        try:
            return await tool.get_prompt("principal-prompt", topic="child")
        finally:
            principal.reset(token)

    async def spawn_child(request: httpx.Request) -> None:
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/call":
            children.append(asyncio.create_task(call_prompt()))

    tool = MCPStreamableHTTPTool(
        name="child-prompt",
        url="https://mcp.example/mcp",
        http_client=create_client(before_request=spawn_child),
        header_provider=lambda _: {"Authorization": principal.get(), "X-Test-Prompts": "enabled"},
    )
    async with tool, asyncio.timeout(5):
        try:
            await tool.call_tool("record", marker="parent")
            assert len(children) == 1
            start_child.set()
            assert await children[0] == "token-b:child"
            assert _requests_for_method(requests, "prompts/get")[-1].headers["Authorization"] == "token-b"
            assert len(_requests_for_method(requests, "initialize")) == 2
        finally:
            start_child.set()
            for child in children:
                child.cancel()
            await asyncio.gather(*children, return_exceptions=True)


async def test_request_header_snapshot_cannot_be_reused_by_another_tool_owner(
    mcp_http_server: MCPHTTPServer,
) -> None:
    from agent_framework._mcp import _MCP_HEADER_OWNER_EXTENSION

    client, requests, _ = mcp_http_server
    first = MCPStreamableHTTPTool(
        name="first",
        url="https://mcp.example/mcp",
        http_client=client,
        static_headers={"X-First-Only": "first"},
        header_provider=lambda _: {"Authorization": "token-a"},
    )
    second = _tool(client, "token-b")
    async with first, second:
        original = _requests_for_method(requests, "tools/list")[0]
        reused = httpx.Request(
            "POST",
            original.url,
            headers=original.headers,
            content=original.content,
            extensions=original.extensions.copy(),
        )
        reused.extensions[_MCP_HEADER_OWNER_EXTENSION] = second._header_request_owner
        for hook in client.event_hooks["request"]:
            await hook(reused)
        assert reused.headers["Authorization"] == "token-b"
        assert "X-First-Only" not in reused.headers


async def test_nested_same_identity_call_can_finish_ahead_of_waiting_identity_change(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    create_client, requests, writes = mcp_http_client_factory
    outer_started = asyncio.Event()
    start_nested = asyncio.Event()

    async def invoke_nested(request: httpx.Request) -> None:
        if request.method != "POST":
            return
        body = json.loads(request.content)
        if body.get("method") == "tools/call" and body["params"]["arguments"].get("marker") == "outer":
            outer_started.set()
            await start_nested.wait()
            await tool.call_tool("record", marker="nested")

    tool = _tool(create_client(before_request=invoke_nested), "token-a")
    async with tool:
        outer = asyncio.create_task(tool.call_tool("record", marker="outer"))
        await asyncio.wait_for(outer_started.wait(), timeout=5)
        changing = asyncio.create_task(tool.call_tool("record", marker="changed", credential="token-b"))
        try:
            for _ in range(10):
                await asyncio.sleep(0)
            assert not changing.done()
        finally:
            start_nested.set()
            await asyncio.wait_for(asyncio.gather(outer, changing), timeout=5)
    assert writes["token-a"] == ["nested", "outer"]
    assert writes["token-b"] == ["changed"]
    assert len(_requests_for_method(requests, "initialize")) == 2


@pytest.mark.parametrize("operation", ["identity", "reset", "close", "tools", "prompts", "recovery"])
@pytest.mark.parametrize("dynamic_headers", [False, True])
async def test_nested_exclusive_operation_fails_instead_of_waiting_on_its_parent(
    mcp_http_client_factory: MCPHTTPClientFactory, operation: str, dynamic_headers: bool
) -> None:
    from anyio import ClosedResourceError

    if operation == "identity" and not dynamic_headers:
        pytest.skip("Fixed headers do not have a runtime identity transition.")
    create_client, _, writes = mcp_http_client_factory

    async def invoke_nested(request: httpx.Request) -> None:
        if request.method != "POST" or json.loads(request.content).get("method") != "tools/call":
            return
        close_generation = tool._close_generation
        with pytest.raises(ToolExecutionException, match="active HTTP operation"):
            if operation == "identity":
                await tool.call_tool("record", marker="nested", credential="token-b")
            elif operation == "reset":
                await tool.connect(reset=True)
            elif operation == "close":
                await tool.close()
            elif operation == "tools":
                await tool.load_tools()
            elif operation == "prompts":
                await tool.load_prompts()
            else:
                await tool._recover_connection_after_loss(
                    operation="tool call", inner_exception=ClosedResourceError(), load_configured=True
                )
        assert tool._close_generation == close_generation

    tool = (
        _tool(create_client(before_request=invoke_nested), "token-a")
        if dynamic_headers
        else MCPStreamableHTTPTool(
            name="static-nested",
            url="https://mcp.example/mcp",
            http_client=create_client(before_request=invoke_nested),
            static_headers={"Authorization": "token-a"},
            load_prompts=False,
        )
    )
    async with tool:
        await asyncio.wait_for(tool.call_tool("record", marker="outer"), timeout=5)
    assert writes["token-a"] == ["outer"]
    assert not writes["token-b"]


@pytest.mark.parametrize("dynamic_headers", [False, True])
async def test_simultaneous_connection_failures_share_one_recovery(
    mcp_http_server: MCPHTTPServer, dynamic_headers: bool
) -> None:
    from anyio import ClosedResourceError

    client, requests, writes = mcp_http_server
    tool = (
        _tool(client, "token-a")
        if dynamic_headers
        else MCPStreamableHTTPTool(
            name="static",
            url="https://mcp.example/mcp",
            http_client=client,
            static_headers={"Authorization": "token-a"},
            load_prompts=False,
        )
    )
    arrivals: asyncio.Queue[None] = asyncio.Queue()
    fail = asyncio.Event()

    async def fail_call(*args: Any, **kwargs: Any) -> None:
        arrivals.put_nowait(None)
        await fail.wait()
        raise ClosedResourceError

    async with tool:
        original_connection = tool._connection
        with patch.object(_connected_client(tool), "call_tool", side_effect=fail_call):
            first = asyncio.create_task(tool.call_tool("record", marker="first"))
            second = asyncio.create_task(tool.call_tool("record", marker="second"))
            try:
                await asyncio.wait_for(arrivals.get(), timeout=5)
                await asyncio.wait_for(arrivals.get(), timeout=5)
            finally:
                fail.set()
                await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
        assert tool._connection is not original_connection
        assert len(_requests_for_method(requests, "initialize")) == 2
        assert sorted(writes["token-a"]) == ["first", "second"]


async def test_liveness_failure_during_recovery_discovery_recovers_the_replacement_connection(
    mcp_http_server: MCPHTTPServer,
) -> None:
    from anyio import ClosedResourceError

    client, requests, writes = mcp_http_server
    tool = _tool(client, "token-a")
    async with tool, asyncio.timeout(5):
        original_connection = tool._connection
        original_check = tool._check_connection
        replacement_failed = False

        async def fail_replacement_once() -> None:
            nonlocal replacement_failed
            if tool._connection is not original_connection and not replacement_failed:
                replacement_failed = True
                raise ClosedResourceError
            await original_check()

        with (
            patch.object(_connected_client(tool), "call_tool", side_effect=ClosedResourceError()),
            patch.object(tool, "_check_connection", side_effect=fail_replacement_once),
        ):
            await tool.call_tool("record", marker="recovered")
        assert replacement_failed
        assert len(_requests_for_method(requests, "initialize")) == 3
        assert writes["token-a"] == ["recovered"]


async def test_cancelling_recovery_propagates_and_releases_the_exclusive_barrier(
    mcp_http_server: MCPHTTPServer,
) -> None:
    from anyio import ClosedResourceError

    client, _, writes = mcp_http_server
    tool = _tool(client, "token-a")
    started = asyncio.Event()

    async def block_recovery() -> None:
        started.set()
        await asyncio.Event().wait()

    async with tool, asyncio.timeout(5):
        with (
            patch.object(_connected_client(tool), "call_tool", side_effect=ClosedResourceError()),
            patch.object(tool, "_reconnect_without_loading", side_effect=block_recovery),
        ):
            calling = asyncio.create_task(tool.call_tool("record", marker="cancelled"))
            await started.wait()
            calling.cancel()
            with pytest.raises(asyncio.CancelledError):
                await calling
        assert tool._header_operations == 0
        assert tool._header_exclusive_owner is None
        await tool.call_tool("record", marker="after-cancel")
        assert writes["token-a"] == ["after-cancel"]


async def test_cancelled_close_waiter_still_blocks_new_http_operations_until_teardown(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    create_client, _, _ = mcp_http_client_factory
    closing = asyncio.Event()
    release_close = asyncio.Event()

    async def block_close(request: httpx.Request) -> None:
        if request.method == "DELETE":
            closing.set()
            await release_close.wait()

    tool = _tool(create_client(before_request=block_close), "token-a")
    await tool.connect()
    old_connection = tool._connection
    close = asyncio.create_task(tool.close())
    await asyncio.wait_for(closing.wait(), timeout=5)
    close.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close
    calling = asyncio.create_task(tool.call_tool("record", marker="after-close"))
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        assert not calling.done()
    finally:
        release_close.set()
        try:
            with pytest.raises(ToolExecutionException):
                await asyncio.wait_for(calling, timeout=5)
            assert tool._connection is not old_connection
        finally:
            await tool.close()


async def test_owned_client_does_not_replay_response_cookie_across_principals(
    mcp_http_client_factory: MCPHTTPClientFactory,
) -> None:
    create_client, requests, _ = mcp_http_client_factory
    principal = ContextVar("principal", default="token-a")
    response_cookies = {"tools/call": "regression_session=token-a; Path=/; Secure; HttpOnly"}

    def create_owned_client(**kwargs: Any) -> httpx.AsyncClient:
        return create_client(response_cookies=response_cookies, **kwargs)

    tool = MCPStreamableHTTPTool(
        name="owned",
        url="https://mcp.example/mcp",
        load_prompts=False,
        header_provider=lambda _: {"Authorization": principal.get()},
    )
    with patch("httpx2.AsyncClient", side_effect=create_owned_client):
        async with tool:
            await tool.call_tool("record")
            response_cookies.clear()
            token = principal.set("token-b")
            try:
                await tool.call_tool("record")
            finally:
                principal.reset(token)

    calls = _calls(requests)
    assert [request.headers["Authorization"] for request in calls] == ["token-a", "token-b"]
    assert "Cookie" not in calls[0].headers
    assert "regression_session=token-a" not in calls[1].headers.get("Cookie", "")


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

    error = asyncio.CancelledError if failure == "cancellation" else ToolException
    transport_patch = (
        contextlib.nullcontext()
        if failure == "initialize"
        else patch("agent_framework._mcp.streamable_http_client", side_effect=transport)
    )
    try:
        with transport_patch, patch("httpx2.AsyncClient", return_value=client), pytest.raises(error):
            await tool.connect()
        assert client.event_hooks["request"] == original_hooks
        assert client.is_closed is owned_client
    finally:
        await tool.close()


@pytest.mark.parametrize("header_source", ["none", "static", "provider"])
async def test_owned_client_is_closed_after_successful_session(
    mcp_http_client_factory: MCPHTTPClientFactory, header_source: str
) -> None:
    create_client, requests, _ = mcp_http_client_factory
    clients: list[httpx.AsyncClient] = []

    def create_owned_client(**kwargs: Any) -> httpx.AsyncClient:
        client = create_client(
            response_cookies={"tools/call": "implicit_session=previous; Path=/; Secure; HttpOnly"},
            **kwargs,
        )
        client.headers["Authorization"] = "token-a"
        clients.append(client)
        return client

    tool = MCPStreamableHTTPTool(
        name="owned",
        url="https://mcp.example/mcp",
        load_prompts=False,
        static_headers={"Cookie": "explicit_session=caller"} if header_source == "static" else None,
        header_provider=(lambda _: {"Authorization": "token-a", "Cookie": "explicit_session=caller"})
        if header_source == "provider"
        else None,
    )
    with patch("httpx2.AsyncClient", side_effect=create_owned_client):
        async with tool:
            await tool.call_tool("record")
            await tool.call_tool("record")
            assert len(clients) == 1
            assert tool._httpx_client is clients[0]
            await tool.connect(reset=True)
            assert len(clients) == 2
            assert clients[0].is_closed
            await tool.call_tool("record")
    assert len(_calls(requests)) == 3
    assert all(
        request.headers.get("Cookie") == ("explicit_session=caller" if header_source != "none" else None)
        for request in _calls(requests)
    )
    assert all(not client.cookies for client in clients)
    assert all(client.is_closed for client in clients)
    assert all(len(client.event_hooks["request"]) == 1 for client in clients)
    assert tool._httpx_client is None


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
        "session-token-c": "token-c",
        "session-token-b": "token-b",
    }
    assert writes == {"token-a": [], "token-A": [], "token-b": ["second"], "token-c": ["first"]}
    assert all("credential" not in json.loads(request.content)["params"]["arguments"] for request in calls)


async def test_dynamic_headers_reconnect_before_principal_change_and_bind_ambient_requests(
    mcp_http_server: MCPHTTPServer,
) -> None:
    client, requests, writes = mcp_http_server
    tool = _tool(client, "token-a")
    try:
        await tool.connect()
        await tool.call_tool("record", credential="token-a", marker="first")
        await tool.call_tool("record", credential="token-b", marker="second")
        await tool.load_tools()
        await tool._ensure_connected()
        assert {function.name for function in tool.functions} == {"record", "token-b-only"}

        assert [request.headers["Authorization"] for request in _requests_for_method(requests, "initialize")] == [
            "token-a",
            "token-b",
        ]
        calls = _calls(requests)
        assert [(request.headers["mcp-session-id"], request.headers["Authorization"]) for request in calls] == [
            ("session-token-a", "token-a"),
            ("session-token-b", "token-b"),
        ]
        second_initialize = _requests_for_method(requests, "initialize")[-1]
        switched_requests = requests[requests.index(second_initialize) :]
        ambient_requests = _requests_for_method(switched_requests, "tools/list") + _requests_for_method(
            switched_requests, "ping"
        )
        assert ambient_requests
        assert all(request.headers["Authorization"] == "token-b" for request in ambient_requests)
        assert all(request.headers["mcp-session-id"] == "session-token-b" for request in ambient_requests)
        assert writes["token-a"] == ["first"]
        assert writes["token-b"] == ["second"]
    finally:
        await tool.close()


async def test_identity_switch_waits_for_public_discovery_before_teardown(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    tool = _tool(client, "token-a")
    await tool.connect()
    load_started = asyncio.Event()
    release_load = asyncio.Event()
    reset_started = asyncio.Event()
    load_count = 0
    original_load_tools_locked = tool._load_tools_locked
    original_safe_close_exit_stack = tool._safe_close_exit_stack

    async def blocking_load_tools_locked() -> None:
        nonlocal load_count
        load_count += 1
        if load_count == 1:
            load_started.set()
            await release_load.wait()
            return
        await original_load_tools_locked()

    async def recording_safe_close_exit_stack() -> BaseException | None:
        reset_started.set()
        return await original_safe_close_exit_stack()

    with (
        patch.object(tool, "_load_tools_locked", new=blocking_load_tools_locked),
        patch.object(tool, "_safe_close_exit_stack", new=recording_safe_close_exit_stack),
    ):
        public_load = asyncio.create_task(tool.load_tools())
        try:
            await asyncio.wait_for(load_started.wait(), timeout=5)
            identity_switch = asyncio.create_task(tool._prepare_for_run({"credential": "token-b"}))
            await asyncio.sleep(0.05)
            assert not reset_started.is_set()
            release_load.set()
            await asyncio.wait_for(asyncio.gather(public_load, identity_switch), timeout=5)
            assert {function.name for function in tool.functions} == {"record", "token-b-only"}
        finally:
            release_load.set()
            public_load.cancel()
            await asyncio.gather(public_load, return_exceptions=True)
            await tool.close()


async def test_captured_prompt_reconciles_run_identity_at_invocation(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = MCPStreamableHTTPTool(
        name="prompts",
        url="https://mcp.example/mcp",
        http_client=client,
        load_tools=False,
        static_headers={"X-Test-Prompts": "enabled"},
        header_provider=lambda kwargs: {"Authorization": kwargs["credential"]},
    )
    tool._seed_connection_kwargs({"credential": "token-a"})
    try:
        await tool.connect()
        captured_prompt = next(function for function in tool.functions if function.name == "principal-prompt")

        await tool._prepare_for_run({"credential": "token-b"})
        assert _requests_for_method(requests, "initialize")[-1].headers["Authorization"] == "token-b"

        context = FunctionInvocationContext(
            function=captured_prompt,
            arguments={"topic": "identity"},
            kwargs={"credential": "token-a"},
        )
        await captured_prompt.invoke(arguments={"topic": "identity"}, context=context)

        prompt_request = _requests_for_method(requests, "prompts/get")[-1]
        assert prompt_request.headers["Authorization"] == "token-a"
        assert prompt_request.headers["mcp-session-id"] == "session-token-a"
        assert json.loads(prompt_request.content)["params"]["arguments"] == {"topic": "identity"}
    finally:
        await tool.close()


async def test_run_preparation_reconnects_before_exposing_principal_tools(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a")
    try:
        await tool.connect()

        await tool._prepare_for_run({"credential": "token-b"})

        assert {function.name for function in tool.functions} == {"record", "token-b-only"}
        assert [request.headers["Authorization"] for request in _requests_for_method(requests, "initialize")] == [
            "token-a",
            "token-b",
        ]
    finally:
        await tool.close()


async def test_concurrent_callers_use_sessions_bound_to_their_own_headers(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, writes = mcp_http_server
    tool = _tool(client, "token-a")
    try:
        await tool.connect()
        await asyncio.gather(
            tool.call_tool("record", credential="token-a", marker="first"),
            tool.call_tool("record", credential="token-b", marker="second"),
        )

        calls = _calls(requests)
        assert len(calls) == 2
        assert all(
            request.headers["mcp-session-id"] == f"session-{request.headers['Authorization']}" for request in calls
        )
        assert writes["token-a"] == ["first"]
        assert writes["token-b"] == ["second"]
    finally:
        await tool.close()


@pytest.mark.parametrize("model_credential", ["token-b", ""])
async def test_generated_tool_keeps_authentication_in_runtime_context(
    mcp_http_server: MCPHTTPServer, model_credential: str
) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a", declare_credential=True)
    try:
        await tool.connect()
        function = next(function for function in tool.functions if function.name == "record")
        arguments = {"marker": "model-value", "credential": model_credential}
        context = FunctionInvocationContext(
            function=function, arguments=arguments, kwargs={"credential": "token-a", "marker": "runtime-value"}
        )
        await function.invoke(arguments=arguments, context=context)

        call = _calls(requests)[-1]
        assert call.headers["Authorization"] == "token-a"
        assert call.headers["mcp-session-id"] == "session-token-a"
        assert json.loads(call.content)["params"]["arguments"]["marker"] == "model-value"
        assert json.loads(call.content)["params"]["arguments"]["credential"] == model_credential
        assert len(_requests_for_method(requests, "initialize")) == 1
        assert context.kwargs == {"credential": "token-a", "marker": "runtime-value"}
    finally:
        await tool.close()


async def test_generated_tool_does_not_supply_model_only_authentication(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a", declare_credential=True)
    try:
        await tool.connect()
        function = next(function for function in tool.functions if function.name == "record")
        arguments = {"marker": "model-value", "credential": "token-b"}
        context = FunctionInvocationContext(function=function, arguments=arguments, kwargs={})
        await function.invoke(arguments=arguments, context=context)
        assert _calls(requests)[-1].headers["Authorization"] == "token-a"

        # Direct calls remain host-controlled and must not inherit the generated invocation's context.
        await tool.call_tool("record", credential="token-b", marker="direct")
        assert _calls(requests)[-1].headers["Authorization"] == "token-b"
    finally:
        await tool.close()


@pytest.mark.parametrize("failure", [KeyError, asyncio.CancelledError])
async def test_generated_tool_auth_context_is_cleared_after_failure(
    mcp_http_server: MCPHTTPServer, failure: type[BaseException]
) -> None:
    client, requests, _ = mcp_http_server

    def headers(kwargs: dict[str, Any]) -> dict[str, str]:
        if "credential" not in kwargs:
            raise failure("credential")
        return {"Authorization": kwargs["credential"]}

    tool = MCPStreamableHTTPTool(
        name="runtime-auth",
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        header_provider=headers,
    )
    tool._seed_connection_kwargs({"credential": "token-a"})
    try:
        await tool.connect()
        function = next(function for function in tool.functions if function.name == "record")
        arguments = {"credential": "token-b"}
        context = FunctionInvocationContext(function=function, arguments=arguments, kwargs={})
        with pytest.raises(failure, match="credential"):
            await function.invoke(arguments=arguments, context=context)
        assert not _calls(requests)

        await tool.call_tool("record", credential="token-b")
        assert _calls(requests)[-1].headers["Authorization"] == "token-b"
    finally:
        await tool.close()


async def test_concurrent_generated_calls_keep_separate_auth_contexts(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a", declare_credential=True)
    try:
        await tool.connect()
        function = next(function for function in tool.functions if function.name == "record")

        async def invoke(principal: str, model_principal: str) -> None:
            arguments = {"marker": principal, "credential": model_principal}
            context = FunctionInvocationContext(
                function=function, arguments=arguments, kwargs={"credential": principal}
            )
            await function.invoke(arguments=arguments, context=context)

        await asyncio.gather(invoke("token-a", "token-b"), invoke("token-b", "token-a"))
        calls = _calls(requests)
        assert len(calls) == 2
        for request in calls:
            assert request.headers["Authorization"] == json.loads(request.content)["params"]["arguments"]["marker"]
            assert request.headers["mcp-session-id"] == f"session-{request.headers['Authorization']}"
    finally:
        await tool.close()


async def test_header_identity_normalizes_names_but_preserves_value_case(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, writes = mcp_http_server

    def provide_headers(kwargs: dict[str, Any]) -> dict[str, str]:
        return {
            kwargs.get("header_name", "Authorization"): kwargs.get("credential", "token-a"),
            kwargs.get("scope_header_name", "X-Scope"): kwargs.get("scope", "red"),
        }

    tool = MCPStreamableHTTPTool(
        name="normalized",
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        static_headers={"X-Static": "fixed"},
        header_provider=provide_headers,
    )
    tool._seed_connection_kwargs({
        "header_name": "Authorization",
        "credential": "token-a",
        "scope_header_name": "X-Scope",
        "scope": "red",
    })
    try:
        await tool.connect()
        await tool.call_tool(
            "record",
            header_name="authorization",
            credential="token-a",
            scope_header_name="x-scope",
            scope="red",
            marker="same",
        )
        assert len(_requests_for_method(requests, "initialize")) == 1

        await tool.call_tool("record", credential="token-a", scope="blue", marker="scope-change")
        await tool.call_tool("record", credential="token-A", scope="blue", marker="value-case-change")
        assert [request.headers["Authorization"] for request in _requests_for_method(requests, "initialize")] == [
            "token-a",
            "token-a",
            "token-A",
        ]
        assert writes["token-a"] == ["same", "scope-change"]
        assert writes["token-A"] == ["value-case-change"]
    finally:
        await tool.close()


async def test_failed_identity_reconnect_discards_the_previous_session(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a")
    try:
        await tool.connect()
        with pytest.raises((ToolException, ToolExecutionException)):
            await tool.call_tool("record", credential="rejected-token")

        assert tool.session is None
        assert not tool.is_connected
        assert tool.functions == []
        assert not any(
            request.headers.get("Authorization") == "rejected-token"
            and request.headers.get("mcp-session-id") == "session-token-a"
            for request in requests
        )
    finally:
        await tool.close()


async def test_cancelled_identity_switch_keeps_the_existing_session_bound(mcp_http_server: MCPHTTPServer) -> None:
    client, requests, _ = mcp_http_server
    tool = _tool(client, "token-a")
    try:
        await tool.connect()
        existing_session = tool.session
        existing_functions = list(tool.functions)
        existing_call_meta = dict(tool._tool_call_meta_by_name)
        existing_param_names = {name: set(params) for name, params in tool._tool_param_names_by_name.items()}

        async def cancel_reconnect() -> None:
            raise asyncio.CancelledError

        with (
            patch.object(tool, "_reconnect_for_identity_change", new=cancel_reconnect),
            pytest.raises(asyncio.CancelledError),
        ):
            await tool._prepare_for_run({"credential": "token-b"})

        assert tool.is_connected
        assert tool.session is existing_session
        assert tool.functions == existing_functions
        assert tool._tool_call_meta_by_name == existing_call_meta
        assert tool._tool_param_names_by_name == existing_param_names

        await tool.call_tool("record", credential="token-b")
        last_call = _calls(requests)[-1]
        assert last_call.headers["Authorization"] == "token-b"
        assert last_call.headers["mcp-session-id"] == "session-token-b"
    finally:
        await tool.close()


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
            patch("httpx2.AsyncClient", return_value=client),
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
                        "execution": {"taskSupport": "forbidden"},
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
    from mcp.shared.exceptions import MCPError

    try:
        with patch("httpx2.AsyncClient", side_effect=create_client):
            for _ in range(2):
                with pytest.raises(MCPError, match="discovery failed"):
                    await tool.connect()
                assert tool.session is None
                assert not tool.is_connected
                assert not tool._tools_loaded
                assert not tool._prompts_loaded
                assert tool.functions == []
                assert tool._tool_call_meta_by_name == {}
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

    with patch("httpx2.AsyncClient", return_value=client), patch.object(tool, "_close_on_owner", record_cleanup):
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

    async def cancel_before_delivery(
        *, reset: bool = False, load_configured: bool = True, reset_discovery: bool = False
    ) -> None:
        await connect_on_owner(
            reset=reset,
            load_configured=load_configured,
            reset_discovery=reset_discovery,
        )
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
        abandoned_connection = tool._connection
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        retry = asyncio.create_task(tool.connect())
        release_setup.set()
        await asyncio.wait_for(retry, timeout=5)
        assert tool.is_connected
        assert tool._connection is not abandoned_connection
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
        supplied_session = cast(ClientSession, _connected_client(source).session)
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


async def test_caller_supplied_session_rejects_header_identity_changes(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    async with _tool(client, "token-a") as source:
        supplied_session = cast(ClientSession, _connected_client(source).session)
        borrowed = MCPStreamableHTTPTool(
            name="borrowed",
            url="https://must-not-connect.example/mcp",
            session=supplied_session,
            load_prompts=False,
            header_provider=lambda kwargs: {"Authorization": kwargs["credential"]},
        )
        try:
            await borrowed.connect()
            with pytest.raises(ToolExecutionException, match="caller-supplied session"):
                await borrowed._prepare_for_run({"credential": "token-b"})
            with pytest.raises(ToolExecutionException, match="caller-supplied session"):
                await borrowed.call_tool("record", credential="token-b")
            assert borrowed.is_connected
            assert borrowed.session is supplied_session

            await borrowed.close()
            assert not borrowed.is_connected
            assert borrowed.session is supplied_session
            with pytest.raises(ToolExecutionException, match="caller-supplied session"):
                await borrowed.call_tool("record", credential="token-a")
            await borrowed.connect()

            with pytest.raises(ToolExecutionException, match="caller-supplied session"):
                await borrowed._prepare_for_run({"credential": "token-a"})
            with pytest.raises(ToolExecutionException, match="caller-supplied session"):
                await borrowed.call_tool("record", credential="token-a")
        finally:
            await borrowed.close()

        await supplied_session.send_ping()


async def test_replacing_supplied_session_invalidates_bound_header_identity() -> None:
    """A recorded header identity is valid only for the session that established it."""
    original_session = Mock(spec=ClientSession)
    replacement_session = Mock(spec=ClientSession)
    tool = MCPStreamableHTTPTool(
        name="borrowed",
        url="https://must-not-connect.example/mcp",
        session=original_session,
        header_provider=lambda _kwargs: {"Authorization": "A"},
    )
    tool._bind_session_headers({"Authorization": "A"})

    with pytest.warns(DeprecationWarning, match=r"MCPTool\.session.*removed in vNext"):
        tool.session = replacement_session

    with pytest.raises(ToolExecutionException, match="identity is unknown"):
        await tool._ensure_session_identity({"Authorization": "A"}, {})


async def test_cancelled_redundant_connect_keeps_existing_session(mcp_http_server: MCPHTTPServer) -> None:
    client, _, _ = mcp_http_server
    async with _tool(client, "token-a") as tool:
        existing_session = tool.session
        original_hooks = list(client.event_hooks["request"])
        connect_on_owner = tool._connect_on_owner

        async def cancel_before_delivery(
            *, reset: bool = False, load_configured: bool = True, reset_discovery: bool = False
        ) -> None:
            await connect_on_owner(
                reset=reset,
                load_configured=load_configured,
                reset_discovery=reset_discovery,
            )
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
        supplied_session = cast(ClientSession, _connected_client(source).session)
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


def _kwargs_dependent_tool(client: httpx.AsyncClient) -> MCPStreamableHTTPTool:
    """A tool whose header_provider can only authenticate when connection kwargs are seeded."""
    return MCPStreamableHTTPTool(
        name="seeded",
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        header_provider=lambda kwargs: {"Authorization": kwargs["credential"]},
    )


@pytest.mark.parametrize("seeded", [True, False])
async def test_seeded_connection_kwargs_authenticate_the_handshake(
    mcp_http_server: MCPHTTPServer, seeded: bool
) -> None:
    client, requests, _ = mcp_http_server
    tool = _kwargs_dependent_tool(client)
    if seeded:
        tool._seed_connection_kwargs({"credential": "token-a"})
    try:
        if not seeded:
            with pytest.raises(ToolException):
                await tool.connect()
            return
        async with tool:
            await tool.call_tool("record", credential="token-a")
        initializes = [
            request
            for request in requests
            if request.method == "POST" and json.loads(request.content).get("method") == "initialize"
        ]
        assert [request.headers.get("Authorization") for request in initializes] == ["token-a"]
    finally:
        await tool.close()


async def test_connected_run_defers_missing_per_call_header_until_invocation(
    mcp_http_server: MCPHTTPServer,
) -> None:
    client, requests, _ = mcp_http_server
    tool = _kwargs_dependent_tool(client)
    tool._seed_connection_kwargs({"credential": "token-a"})
    try:
        await tool.connect()
        existing_session = tool.session

        await tool._prepare_for_run({"unrelated": "value"})

        assert tool.is_connected
        assert tool.session is existing_session

        await tool.call_tool("record", credential="token-b")
        assert [request.headers["Authorization"] for request in _requests_for_method(requests, "initialize")] == [
            "token-a",
            "token-b",
        ]
        call_request = _calls(requests)[-1]
        assert call_request.headers["Authorization"] == "token-b"
        assert call_request.headers["mcp-session-id"] == "session-token-b"
    finally:
        await tool.close()


async def test_connection_rebinds_to_changed_call_headers_and_clears_kwargs_on_close(
    mcp_http_server: MCPHTTPServer,
) -> None:
    client, requests, _ = mcp_http_server
    tool = _kwargs_dependent_tool(client)
    tool._seed_connection_kwargs({"credential": "token-a"})
    try:
        async with tool:
            # A later run must not re-authenticate an already-established connection.
            tool._seed_connection_kwargs({"credential": "token-b"})
            assert tool._connection_kwargs == {"credential": "token-a"}
            # A call with another effective header identity establishes a matching session.
            await tool.call_tool("record", credential="token-c")
        initializes = [
            request
            for request in requests
            if request.method == "POST" and json.loads(request.content).get("method") == "initialize"
        ]
        assert [request.headers.get("Authorization") for request in initializes] == ["token-a", "token-c"]
        assert [
            (request.headers.get("mcp-session-id"), request.headers.get("Authorization"))
            for request in _calls(requests)
        ] == [("session-token-c", "token-c")]
        assert tool._connection_kwargs is None
        # The credential was released on close, so an unseeded reconnect is rejected.
        with pytest.raises(ToolException):
            await tool.connect()
    finally:
        await tool.close()


async def test_standalone_static_header_provider_authenticates_without_a_run(mcp_http_server: MCPHTTPServer) -> None:
    """A provider that ignores kwargs authenticates the handshake outside any agent run.

    Pins the boundary of the connection-kwargs seeding: standalone use has no per-call kwargs
    to seed from, so a closure/token-provider style provider is the supported shape there.
    """
    client, requests, _ = mcp_http_server
    tool = MCPStreamableHTTPTool(
        name="standalone",
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        header_provider=lambda _kwargs: {"Authorization": "token-a"},
    )
    try:
        async with tool:
            await tool.call_tool("record")
        authenticated = [
            request
            for request in requests
            if request.method == "POST"
            and json.loads(request.content).get("method") in {"initialize", "tools/list", "tools/call"}
        ]
        assert authenticated
        assert all(request.headers.get("Authorization") == "token-a" for request in authenticated)
    finally:
        await tool.close()


async def test_seeded_kwargs_missing_the_providers_key_fails_the_handshake(
    mcp_http_server: MCPHTTPServer,
) -> None:
    """A key absent from seeded connection kwargs is a misconfiguration, not a tolerated ambient miss.

    An unseeded connection legitimately has no per-call values, so a KeyError there is tolerated.
    Once a run supplies kwargs, a provider asking for an absent key must fail loudly instead of
    letting the handshake go out unauthenticated.
    """
    client, _, _ = mcp_http_server
    tool = MCPStreamableHTTPTool(
        name="mismatch",
        url="https://mcp.example/mcp",
        http_client=client,
        load_prompts=False,
        header_provider=lambda kwargs: {"Authorization": kwargs["credential"]},
    )
    tool._seed_connection_kwargs({"typo_credential": "token-a"})
    try:
        with pytest.raises(ToolException) as error:
            await tool.connect()
        assert "'credential'" in str(error.value)
    finally:
        await tool.close()


async def test_run_supplying_no_kwargs_still_fails_a_kwargs_dependent_provider(
    mcp_http_server: MCPHTTPServer,
) -> None:
    """Seeding an empty mapping is still seeding, so the provider's missing key must not be tolerated.

    An empty mapping cannot distinguish a run that supplied no kwargs from a connection no run
    ever seeded; only the latter has no way to carry the key and may proceed unauthenticated.
    """
    client, _, _ = mcp_http_server
    tool = _kwargs_dependent_tool(client)
    tool._seed_connection_kwargs({})
    try:
        with pytest.raises(ToolException) as error:
            await tool.connect()
        assert "'credential'" in str(error.value)
    finally:
        await tool.close()


async def test_failed_connect_releases_the_seeded_credential(mcp_http_server: MCPHTTPServer) -> None:
    """An abandoned connection attempt must not leave its credential for a later unseeded connect.

    A rejected handshake unwinds without going through close(), so the release has to happen on
    the failure path too; otherwise a standalone reconnect re-sends the failed run's credential.
    """
    client, requests, _ = mcp_http_server
    tool = _kwargs_dependent_tool(client)
    tool._seed_connection_kwargs({"credential": "token-rejected"})
    try:
        with pytest.raises(ToolException):
            await tool.connect()
        assert tool._connection_kwargs is None
        with pytest.raises(ToolException):
            await tool.connect()
        initializes = [
            request
            for request in requests
            if request.method == "POST" and json.loads(request.content).get("method") == "initialize"
        ]
        assert [request.headers.get("Authorization") for request in initializes] == ["token-rejected", None]
    finally:
        await tool.close()


async def test_a_second_run_cannot_replace_an_unconnected_claim(mcp_http_server: MCPHTTPServer) -> None:
    """The first run to seed owns the connection, even before its handshake completes.

    is_connected only turns true after initialize returns, so it cannot by itself stop a
    concurrent run from swapping the credential mid-handshake and authenticating the shared
    connection as the wrong caller.
    """
    client, requests, _ = mcp_http_server
    tool = _kwargs_dependent_tool(client)
    tool._seed_connection_kwargs({"credential": "token-a"})
    tool._seed_connection_kwargs({"credential": "token-b"})
    try:
        async with tool:
            pass
        initializes = [
            request
            for request in requests
            if request.method == "POST" and json.loads(request.content).get("method") == "initialize"
        ]
        assert [request.headers.get("Authorization") for request in initializes] == ["token-a"]
    finally:
        await tool.close()
