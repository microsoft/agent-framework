# Copyright (c) Microsoft. All rights reserved.

"""Tests for ``DefaultMCPToolHandler``.

Most tests exercise the real handler against a fake ``MCPStreamableHTTPTool``
(no real MCP server, no real network) to cover the parts of the handler not
exercisable through the executor stub: cache hit/miss/eviction, concurrent
connect via in-flight futures, header isolation across cache keys,
string-result normalisation, ``load_prompts=False`` verification, and
owned-vs-caller httpx close semantics, and provider-backed invocation lifetimes.

Two lifecycle cases use the real MCP SDK with an inert HTTPX mock transport.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from agent_framework import Content
from agent_framework.exceptions import ToolExecutionException

from agent_framework_declarative._workflows._mcp_handler import (
    DefaultMCPToolHandler,
    MCPToolInvocation,
)

pytestmark = pytest.mark.skipif(
    sys.version_info >= (3, 14),
    reason="Skipped on Python 3.14+ to keep parity with rest of declarative suite",
)


class FakeListToolsResult:  # noqa: B903 - mimics ``mcp.types.ListToolsResult`` shape, not a value type
    """Stand-in for ``mcp.types.ListToolsResult`` returned by ``session.list_tools()``."""

    def __init__(self, tools: list[Any], next_cursor: str | None = None) -> None:
        self.tools = tools
        self.nextCursor = next_cursor


class FakeMcpTool:
    """Stand-in for an MCP ``Tool`` (subset used by ``_invoke_list_tools``)."""

    def __init__(
        self,
        name: str,
        description: str | None = None,
        inputSchema: dict[str, Any] | None = None,
        outputSchema: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.inputSchema = inputSchema if inputSchema is not None else {"type": "object", "properties": {}}
        self.outputSchema = outputSchema


class FakeMcpSession:
    """Stand-in for ``mcp.ClientSession``.

    ``list_tools_pages`` lets a test enqueue multiple paginated responses;
    when None (default), an empty single-page result is returned. ``list_tools_error``
    raises a synthetic error on the next call when set.
    """

    def __init__(self) -> None:
        self.list_tools_pages: list[FakeListToolsResult] | None = None
        self.list_tools_calls: list[Any] = []
        self.list_tools_error: BaseException | None = None

    async def list_tools(self, params: Any = None) -> FakeListToolsResult:
        self.list_tools_calls.append(params)
        if self.list_tools_error is not None:
            raise self.list_tools_error
        if self.list_tools_pages is None:
            return FakeListToolsResult(tools=[])
        index = len(self.list_tools_calls) - 1
        if index >= len(self.list_tools_pages):
            return FakeListToolsResult(tools=[])
        return self.list_tools_pages[index]


class FakeTool:
    """Stand-in for ``MCPStreamableHTTPTool``.

    Records constructor kwargs, tracks connect/close lifecycle, and dispatches
    ``call_tool`` to a per-instance handler.
    """

    instances: list[FakeTool] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.connect_count = 0
        self.close_count = 0
        self.connect_delay: float = 0.0
        self.connect_error: BaseException | None = None
        self.call_handler: Any = lambda **_a: [Content.from_text("ok")]
        self._httpx_client: httpx.AsyncClient | None = kwargs.get("http_client")
        self.session: FakeMcpSession | None = None
        # Mimic MCPStreamableHTTPTool: when no caller client AND header_provider
        # is set, lazily allocate an owned httpx client during connect.
        FakeTool.instances.append(self)

    async def connect(self) -> None:
        if self.connect_delay:
            await asyncio.sleep(self.connect_delay)
        if self.connect_error is not None:
            raise self.connect_error
        self.connect_count += 1
        # Mimic lazy httpx allocation when no client provided AND header_provider set.
        if self.kwargs.get("http_client") is None and self.kwargs.get("header_provider") is not None:
            self._httpx_client = httpx.AsyncClient()
        # Mimic MCPStreamableHTTPTool: a live session becomes available after connect.
        if self.session is None:
            self.session = FakeMcpSession()

    async def close(self) -> None:
        self.close_count += 1

    async def call_tool(self, tool_name: str, **arguments: Any) -> Any:
        return self.call_handler(tool_name=tool_name, **arguments)


@pytest.fixture(autouse=True)
def _clear_fake_instances() -> None:
    FakeTool.instances.clear()


def _patch_tool() -> Any:
    """Patch the lazy import inside ``_create_entry`` to substitute FakeTool."""
    import agent_framework

    return patch.object(agent_framework, "MCPStreamableHTTPTool", FakeTool)


def _invocation(
    *, server_url: str = "https://mcp.example/api", tool_name: str = "search", **overrides: Any
) -> MCPToolInvocation:
    return MCPToolInvocation(
        server_url=server_url,
        tool_name=tool_name,
        **overrides,
    )


# ---------- Provider-backed invocation lifetimes --------------------------


class TestProviderLifetimes:
    @pytest.mark.parametrize("returns_none", [False, True])
    async def test_actual_sdk_lifecycle_and_hook_cleanup(
        self, returns_none: bool, caplog: pytest.LogCaptureFixture
    ) -> None:
        import agent_framework
        from agent_framework import MCPStreamableHTTPTool

        caplog.set_level("DEBUG", logger="agent_framework_declarative._workflows._mcp_handler")
        initialized: list[str] = []
        terminated: list[str] = []
        methods: list[str] = []
        tools: list[MCPStreamableHTTPTool] = []
        clients: list[RecordingClient] = []
        caller_hook = AsyncMock()

        async def respond(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Test"] == "lifecycle"
            if request.method == "GET":
                return httpx.Response(405)
            if request.method == "DELETE":
                terminated.append(request.headers["mcp-session-id"])
                return httpx.Response(200)

            body = json.loads(request.content)
            method = body["method"]
            methods.append(method)
            if "id" not in body:
                return httpx.Response(202)
            headers: dict[str, str] = {}
            if method == "initialize":
                session_id = f"lifecycle-{len(initialized) + 1}"
                initialized.append(session_id)
                headers["mcp-session-id"] = session_id
                result = {
                    "protocolVersion": body["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "lifecycle", "version": "1"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [{"name": "ok", "inputSchema": {"type": "object", "properties": {}}}],
                }
            elif method == "tools/call":
                result = {"content": [{"type": "text", "text": "ok"}]}
            else:
                assert method == "ping"
                result = {}
            return httpx.Response(200, headers=headers, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

        class RecordingClient(httpx.AsyncClient):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(
                    transport=httpx.MockTransport(respond), event_hooks={"request": [caller_hook]}, **kwargs
                )
                self.close_count = 0
                clients.append(self)

            async def aclose(self) -> None:
                self.close_count += 1
                await super().aclose()

        def create_tool(**kwargs: Any) -> MCPStreamableHTTPTool:
            tool = MCPStreamableHTTPTool(**kwargs)
            tools.append(tool)
            return tool

        caller_client = None if returns_none else RecordingClient()
        provider = AsyncMock(return_value=caller_client)
        try:
            with (
                patch.object(httpx, "AsyncClient", RecordingClient),
                patch.object(agent_framework, "MCPStreamableHTTPTool", side_effect=create_tool),
            ):
                async with DefaultMCPToolHandler(client_provider=provider) as handler:
                    for index, tool_name in enumerate(("ok", "tools/list", "ok", "tools/list"), start=1):
                        result = await handler.invoke_tool(
                            _invocation(tool_name=tool_name, headers={"X-Test": "lifecycle"})
                        )
                        assert not result.is_error
                        if tool_name == "ok":
                            assert result.outputs[0].text == "ok"
                        else:
                            assert result.outputs[0].text is not None
                            assert json.loads(result.outputs[0].text)["tools"][0]["name"] == "ok"
                        assert provider.await_count == index
                        assert len(tools) == index
                        assert len(initialized) == index
                        assert terminated == initialized
                        assert not handler._active_invocations
                        assert not handler._cache
                        tool = tools[-1]
                        assert tool.session is None
                        assert not tool.is_connected
                        assert tool._lifecycle_owner_task is None
                        assert tool._header_hook_client is None
                        assert all(client.event_hooks["request"] == [caller_hook] for client in clients)
                        if returns_none:
                            assert len(clients) == index
                            assert all(client.is_closed and client.close_count == 1 for client in clients)
                        else:
                            assert caller_client is not None
                            assert not caller_client.is_closed
                            assert caller_client.close_count == 0
            assert len({id(tool) for tool in tools}) == 4
            assert methods.count("tools/call") == 2
            assert methods.count("tools/list") == 6
            assert not any(
                "Could not cleanly close MCP exit stack" in record.getMessage()
                or "DefaultMCPToolHandler: error closing" in record.getMessage()
                for record in caplog.records
            )
        finally:
            for client in clients:
                if not client.is_closed:
                    await client.aclose()

    @pytest.mark.parametrize("returns_none", [False, True])
    async def test_sequential_invocations_get_fresh_tools(self, returns_none: bool) -> None:
        async with httpx.AsyncClient() as client:
            provider = AsyncMock(return_value=None if returns_none else client)
            with _patch_tool():
                async with DefaultMCPToolHandler(client_provider=provider, cache_max_size=1) as handler:
                    for index, tool_name in enumerate(("search", "tools/list", "search", "tools/list"), start=1):
                        invocation = _invocation(tool_name=tool_name, headers={"X-Test": "1"})
                        result = await handler.invoke_tool(invocation)
                        assert not result.is_error
                        assert result.outputs[0].text == ('{\n  "tools": []\n}' if tool_name == "tools/list" else "ok")
                        assert provider.await_count == index
                        assert provider.await_args is not None
                        assert provider.await_args.args[0] is invocation
                        assert len(FakeTool.instances) == index
                        tool = FakeTool.instances[-1]
                        assert tool.connect_count == 1
                        assert tool.close_count == 1
                        assert tool.kwargs["http_client"] is (None if returns_none else client)
                        if returns_none:
                            assert tool._httpx_client is not None
                            assert tool._httpx_client.is_closed
                        assert not client.is_closed
                        assert not handler._cache
                        assert not handler._inflight
                        assert not handler._active_invocations
            assert len({id(tool.session) for tool in FakeTool.instances}) == 4
            assert all(tool.close_count == 1 for tool in FakeTool.instances)
            assert not client.is_closed

    @pytest.mark.parametrize("returns_none", [False, True])
    async def test_concurrent_invocations_get_fresh_tools(self, returns_none: bool) -> None:
        all_connecting = asyncio.Event()
        release = asyncio.Event()
        original_connect = FakeTool.connect

        async def gated_connect(tool: FakeTool) -> None:
            await original_connect(tool)
            if len(FakeTool.instances) == 3:
                all_connecting.set()
            await release.wait()

        async with httpx.AsyncClient() as client:
            provider = AsyncMock(return_value=None if returns_none else client)
            with _patch_tool(), patch.object(FakeTool, "connect", gated_connect):
                async with DefaultMCPToolHandler(client_provider=provider) as handler:
                    tasks = [
                        asyncio.create_task(handler.invoke_tool(_invocation(tool_name=name, headers={"X-Test": "1"})))
                        for name in ("search", "tools/list", "search")
                    ]
                    try:
                        await asyncio.wait_for(all_connecting.wait(), timeout=5)
                        assert provider.await_count == 3
                        assert len({id(tool.session) for tool in FakeTool.instances}) == 3
                        assert all(tool.close_count == 0 for tool in FakeTool.instances)
                        assert not handler._cache
                        assert not handler._inflight
                    finally:
                        release.set()
                        results = await asyncio.gather(*tasks)
                    assert all(not result.is_error for result in results)
                    assert all(tool.close_count == 1 for tool in FakeTool.instances)
                    if returns_none:
                        assert all(tool._httpx_client and tool._httpx_client.is_closed for tool in FakeTool.instances)
                    assert not handler._active_invocations
            assert not client.is_closed

    @pytest.mark.timeout(10)
    @pytest.mark.parametrize("stage", ["provider", "connect", "search", "tools/list", "close"])
    @pytest.mark.parametrize("in_child_task", [False, True])
    async def test_reentrant_shutdown_is_rejected_without_closing_handler(
        self, stage: str, in_child_task: bool
    ) -> None:
        original_connect = FakeTool.connect
        original_close = FakeTool.close
        original_call = FakeTool.call_tool
        original_list = FakeMcpSession.list_tools
        rejected = 0

        async def check_shutdown(phase: str) -> None:
            nonlocal rejected
            if stage != phase:
                return
            with pytest.raises(RuntimeError, match="cannot be called from an active provider-backed invocation"):
                if in_child_task:
                    await asyncio.create_task(handler.aclose())
                else:
                    await handler.aclose()
            rejected += 1
            assert not handler._closed

        async def provider(_invocation: MCPToolInvocation) -> None:
            await check_shutdown("provider")

        async def connect(tool: FakeTool) -> None:
            await original_connect(tool)
            await check_shutdown("connect")

        async def close(tool: FakeTool) -> None:
            await check_shutdown("close")
            await original_close(tool)

        async def call(tool: FakeTool, tool_name: str, **arguments: Any) -> Any:
            await check_shutdown("search")
            return await original_call(tool, tool_name, **arguments)

        async def list_tools(session: FakeMcpSession, params: Any = None) -> FakeListToolsResult:
            await check_shutdown("tools/list")
            return await original_list(session, params)

        with (
            _patch_tool(),
            patch.object(FakeTool, "connect", connect),
            patch.object(FakeTool, "close", close),
            patch.object(FakeTool, "call_tool", call),
            patch.object(FakeMcpSession, "list_tools", list_tools),
        ):
            async with DefaultMCPToolHandler(client_provider=provider) as handler:
                for _ in range(2):
                    result = await handler.invoke_tool(
                        _invocation(tool_name="tools/list" if stage == "tools/list" else "search")
                    )
                    assert not result.is_error
                    assert handler._invocation_context.get() == ()
                    assert not handler._active_invocations
                    assert not handler._closed
        assert rejected == 2
        assert len(FakeTool.instances) == 2
        assert all(tool.close_count == 1 for tool in FakeTool.instances)

    @pytest.mark.timeout(10)
    async def test_nested_invocations_restore_context_and_keep_active_ancestry(self) -> None:
        release_child = asyncio.Event()
        children: list[asyncio.Task[None]] = []

        async def close_from_inherited_context() -> None:
            await release_child.wait()
            outer, inner = handler._invocation_context.get()
            assert not outer.done()
            assert inner.done()
            with pytest.raises(RuntimeError, match="cannot be called from an active provider-backed invocation"):
                await handler.aclose()
            assert not handler._closed

        async def provider(invocation: MCPToolInvocation) -> None:
            if invocation.tool_name == "inner":
                children.append(asyncio.create_task(close_from_inherited_context()))
                return
            outer_context = handler._invocation_context.get()
            assert len(outer_context) == 1
            nested_result = await handler.invoke_tool(_invocation(tool_name="inner"))
            assert not nested_result.is_error
            assert handler._invocation_context.get() is outer_context
            release_child.set()
            await children[-1]
            with pytest.raises(RuntimeError, match="cannot be called from an active provider-backed invocation"):
                await handler.aclose()

        with _patch_tool():
            async with DefaultMCPToolHandler(client_provider=provider) as handler:
                try:
                    result = await handler.invoke_tool(_invocation(tool_name="outer"))
                    assert not result.is_error
                    assert handler._invocation_context.get() == ()
                    assert not handler._active_invocations
                finally:
                    release_child.set()
                    await asyncio.gather(*children)
        assert len(FakeTool.instances) == 2
        assert all(tool.close_count == 1 for tool in FakeTool.instances)

    @pytest.mark.timeout(10)
    async def test_provider_can_invoke_and_close_another_handler(self) -> None:
        async def provider(_invocation: MCPToolInvocation) -> None:
            async with DefaultMCPToolHandler(client_provider=AsyncMock(return_value=None)) as other:
                result = await other.invoke_tool(_invocation)
                assert not result.is_error
                assert other._invocation_context.get() == ()
                assert handler._invocation_context.get()
            assert other._closed
            assert not handler._closed

        with _patch_tool():
            async with DefaultMCPToolHandler(client_provider=provider) as handler:
                result = await handler.invoke_tool(_invocation())
                assert not result.is_error
                assert handler._invocation_context.get() == ()
        assert len(FakeTool.instances) == 2
        assert all(tool.close_count == 1 for tool in FakeTool.instances)

    @pytest.mark.timeout(10)
    async def test_inherited_context_can_close_after_invocation_completes(self) -> None:
        release_child = asyncio.Event()
        children: list[asyncio.Task[None]] = []

        async def close_from_inherited_context() -> None:
            await release_child.wait()
            context = handler._invocation_context.get()
            assert len(context) == 1
            assert context[0].done()
            await handler.aclose()

        async def provider(_invocation: MCPToolInvocation) -> None:
            children.append(asyncio.create_task(close_from_inherited_context()))

        with _patch_tool():
            handler = DefaultMCPToolHandler(client_provider=provider)
            try:
                result = await handler.invoke_tool(_invocation())
                assert not result.is_error
                assert handler._invocation_context.get() == ()
                assert not handler._active_invocations
                assert not handler._closed
            finally:
                release_child.set()
                await asyncio.gather(*children)
                await handler.aclose()
        assert handler._closed
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].close_count == 1

    async def test_list_tools_paginates_within_each_invocation(self) -> None:
        original_connect = FakeTool.connect

        async def connect(tool: FakeTool) -> None:
            await original_connect(tool)
            assert tool.session is not None
            tool.session.list_tools_pages = [
                FakeListToolsResult([FakeMcpTool("first")], next_cursor="next"),
                FakeListToolsResult([FakeMcpTool("second")]),
            ]

        provider = AsyncMock(return_value=None)
        with (
            _patch_tool(),
            patch.object(FakeTool, "connect", connect),
            patch.object(FakeTool, "call_tool", new_callable=AsyncMock) as call_tool,
        ):
            async with DefaultMCPToolHandler(client_provider=provider) as handler:
                for _ in range(2):
                    result = await handler.invoke_tool(_invocation(tool_name="tools/list"))
                    assert not result.is_error
                    assert result.outputs[0].text is not None
                    payload = json.loads(result.outputs[0].text)
                    assert [tool["name"] for tool in payload["tools"]] == ["first", "second"]
            call_tool.assert_not_awaited()
        assert provider.await_count == 2
        assert len(FakeTool.instances) == 2
        for tool in FakeTool.instances:
            assert tool.close_count == 1
            assert tool.session is not None
            assert len(tool.session.list_tools_calls) == 2
            assert tool.session.list_tools_calls[0] is None
            assert tool.session.list_tools_calls[1].cursor == "next"

    @pytest.mark.parametrize("stage", ["provider", "connect", "search", "tools/list"])
    @pytest.mark.parametrize(
        "error_type", [httpx.ReadTimeout, ToolExecutionException, RuntimeError, asyncio.CancelledError]
    )
    @pytest.mark.parametrize("returns_none", [False, True])
    async def test_errors_clean_up_and_preserve_mapping(
        self, stage: str, error_type: type[BaseException], returns_none: bool
    ) -> None:
        error = error_type("operation stopped")
        original_connect = FakeTool.connect

        async def connect(tool: FakeTool) -> None:
            await original_connect(tool)
            if stage == "connect":
                raise error

        async with httpx.AsyncClient() as client:
            provider = AsyncMock(
                return_value=None if returns_none else client,
                side_effect=error if stage == "provider" else None,
            )
            with (
                _patch_tool(),
                patch.object(FakeTool, "connect", connect),
                patch.object(FakeTool, "call_tool", new_callable=AsyncMock, side_effect=error),
                patch.object(FakeMcpSession, "list_tools", new_callable=AsyncMock, side_effect=error),
            ):
                async with DefaultMCPToolHandler(client_provider=provider) as handler:
                    invocation = _invocation(
                        tool_name="tools/list" if stage == "tools/list" else "search", headers={"X-Test": "1"}
                    )
                    if error_type is asyncio.CancelledError or (
                        error_type is RuntimeError and stage in ("search", "tools/list")
                    ):
                        with pytest.raises(error_type, match="operation stopped"):
                            await handler.invoke_tool(invocation)
                    else:
                        result = await handler.invoke_tool(invocation)
                        assert result.is_error
                        assert "operation stopped" in (result.error_message or "")
                        assert result.outputs[0].text is not None
                        assert result.outputs[0].text.startswith("Error:")
                    assert handler._invocation_context.get() == ()
                    assert not handler._active_invocations
                    assert not handler._cache
                    assert not handler._inflight
            assert provider.await_count == 1
            assert len(FakeTool.instances) == (0 if stage == "provider" else 1)
            for tool in FakeTool.instances:
                assert tool.close_count == 1
                if returns_none:
                    assert tool._httpx_client is not None
                    assert tool._httpx_client.is_closed
            assert not client.is_closed

    @pytest.mark.parametrize("tool_name", ["search", "tools/list"])
    async def test_mcp_error_mapping_cleans_up(self, tool_name: str) -> None:
        from mcp.shared.exceptions import McpError
        from mcp.types import ErrorData

        error = McpError(ErrorData(code=-32603, message="operation stopped"))
        with (
            _patch_tool(),
            patch.object(FakeTool, "call_tool", new_callable=AsyncMock, side_effect=error),
            patch.object(FakeMcpSession, "list_tools", new_callable=AsyncMock, side_effect=error),
        ):
            async with DefaultMCPToolHandler(client_provider=AsyncMock(return_value=None)) as handler:
                result = await handler.invoke_tool(_invocation(tool_name=tool_name, headers={"X-Test": "1"}))
                assert result.is_error
                assert result.error_message == "operation stopped"
                assert not handler._active_invocations
        tool = FakeTool.instances[0]
        assert tool.close_count == 1
        assert tool._httpx_client is not None
        assert tool._httpx_client.is_closed

    async def test_tool_close_failure_still_closes_fallback_client(self) -> None:
        async def close(tool: FakeTool) -> None:
            tool.close_count += 1
            raise RuntimeError("close failed")

        with _patch_tool(), patch.object(FakeTool, "close", close):
            async with DefaultMCPToolHandler(client_provider=AsyncMock(return_value=None)) as handler:
                result = await handler.invoke_tool(_invocation(headers={"X-Test": "1"}))
                assert not result.is_error
                assert result.outputs[0].text == "ok"
                assert not handler._active_invocations
        tool = FakeTool.instances[0]
        assert tool.close_count == 1
        assert tool._httpx_client is not None
        assert tool._httpx_client.is_closed

    @pytest.mark.parametrize("connect_fails", [False, True])
    async def test_cleanup_cancellation_signals_completion(self, connect_fails: bool) -> None:
        original_connect = FakeTool.connect
        completions: list[asyncio.Future[None]] = []

        async def connect(tool: FakeTool) -> None:
            await original_connect(tool)
            if connect_fails:
                raise httpx.ConnectError("connect stopped")

        async def close(tool: FakeTool) -> None:
            tool.close_count += 1
            completions.extend(handler._active_invocations)
            raise asyncio.CancelledError("cleanup stopped")

        with (
            _patch_tool(),
            patch.object(FakeTool, "connect", connect),
            patch.object(FakeTool, "close", close),
        ):
            handler = DefaultMCPToolHandler(client_provider=AsyncMock(return_value=None))
            # Python 3.10 may drop the message when a cancelled task's result is retrieved again.
            with pytest.raises(asyncio.CancelledError):
                await handler.invoke_tool(_invocation(headers={"X-Test": "1"}))
            assert handler._invocation_context.get() == ()
            assert not handler._active_invocations
            assert len(completions) == 1
            assert completions[0].done()
            assert completions[0].result() is None
            await asyncio.wait_for(handler.aclose(), timeout=5)
        tool = FakeTool.instances[0]
        assert tool.close_count == 1
        assert tool._httpx_client is not None
        assert tool._httpx_client.is_closed

    @pytest.mark.parametrize("stage", ["provider", "connect", "search", "tools/list"])
    async def test_task_cancellation_cleans_up(self, stage: str) -> None:
        started = asyncio.Event()
        original_connect = FakeTool.connect

        async def wait(*_args: Any, **_kwargs: Any) -> None:
            started.set()
            await asyncio.Event().wait()

        async def provider(_invocation: MCPToolInvocation) -> None:
            if stage == "provider":
                await wait()

        async def connect(tool: FakeTool) -> None:
            await original_connect(tool)
            if stage == "connect":
                await wait()

        async def invoke_and_check_context() -> None:
            try:
                await handler.invoke_tool(
                    _invocation(tool_name="tools/list" if stage == "tools/list" else "search", headers={"X-Test": "1"})
                )
            finally:
                assert handler._invocation_context.get() == ()

        with (
            _patch_tool(),
            patch.object(FakeTool, "connect", connect),
            patch.object(FakeTool, "call_tool", new_callable=AsyncMock, side_effect=wait),
            patch.object(FakeMcpSession, "list_tools", new_callable=AsyncMock, side_effect=wait),
        ):
            async with DefaultMCPToolHandler(client_provider=provider) as handler:
                task = asyncio.create_task(invoke_and_check_context())
                await asyncio.wait_for(started.wait(), timeout=5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert not handler._active_invocations
        assert len(FakeTool.instances) == (0 if stage == "provider" else 1)
        for tool in FakeTool.instances:
            assert tool.close_count == 1
            assert tool._httpx_client is not None
            assert tool._httpx_client.is_closed

    async def test_repeated_cancellation_waits_for_cleanup(self) -> None:
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()
        original_close = FakeTool.close

        async def close(tool: FakeTool) -> None:
            cleanup_started.set()
            await release_cleanup.wait()
            await original_close(tool)

        with _patch_tool(), patch.object(FakeTool, "close", close):
            async with DefaultMCPToolHandler(client_provider=AsyncMock(return_value=None)) as handler:
                task = asyncio.create_task(handler.invoke_tool(_invocation(headers={"X-Test": "1"})))
                await asyncio.wait_for(cleanup_started.wait(), timeout=5)
                for _ in range(2):
                    task.cancel()
                    await asyncio.sleep(0)
                    assert not task.done()
                    assert handler._active_invocations
                release_cleanup.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert not handler._active_invocations
        tool = FakeTool.instances[0]
        assert tool.close_count == 1
        assert tool._httpx_client is not None
        assert tool._httpx_client.is_closed

    @pytest.mark.parametrize("stage", ["provider", "connect", "search", "tools/list", "close"])
    @pytest.mark.parametrize("cancel_shutdown", [False, True])
    async def test_shutdown_waits_for_invocation_cleanup(self, stage: str, cancel_shutdown: bool) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        original_connect = FakeTool.connect
        original_close = FakeTool.close
        original_call = FakeTool.call_tool
        original_list = FakeMcpSession.list_tools

        async def gate(phase: str) -> None:
            if stage == phase:
                started.set()
                await release.wait()

        async def provider(_invocation: MCPToolInvocation) -> None:
            await gate("provider")

        async def connect(tool: FakeTool) -> None:
            await original_connect(tool)
            await gate("connect")

        async def close(tool: FakeTool) -> None:
            await gate("close")
            await original_close(tool)

        async def call(tool: FakeTool, tool_name: str, **arguments: Any) -> Any:
            await gate("search")
            return await original_call(tool, tool_name, **arguments)

        async def list_tools(session: FakeMcpSession, params: Any = None) -> FakeListToolsResult:
            await gate("tools/list")
            return await original_list(session, params)

        provider_mock = AsyncMock(side_effect=provider)
        with (
            _patch_tool(),
            patch.object(FakeTool, "connect", connect),
            patch.object(FakeTool, "close", close),
            patch.object(FakeTool, "call_tool", call),
            patch.object(FakeMcpSession, "list_tools", list_tools),
        ):
            handler = DefaultMCPToolHandler(client_provider=provider_mock)
            invocation = _invocation(
                tool_name="tools/list" if stage == "tools/list" else "search", headers={"X-Test": "1"}
            )
            task = asyncio.create_task(handler.invoke_tool(invocation))
            await asyncio.wait_for(started.wait(), timeout=5)
            shutdown = asyncio.create_task(handler.aclose())
            await asyncio.sleep(0)
            assert handler._closed
            assert not shutdown.done()
            rejected = await handler.invoke_tool(invocation)
            assert rejected.is_error
            assert "closed" in (rejected.error_message or "")
            assert provider_mock.await_count == 1
            if cancel_shutdown:
                shutdown.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await shutdown
            second_shutdown = asyncio.create_task(handler.aclose())
            await asyncio.sleep(0)
            assert not second_shutdown.done()
            release.set()
            result = await task
            await second_shutdown
            if not cancel_shutdown:
                await shutdown
            await handler.aclose()
        assert result.is_error == (stage in ("provider", "connect"))
        if result.is_error:
            assert "closed" in (result.error_message or "")
        assert not handler._active_invocations
        assert not handler._cache
        assert not handler._inflight
        assert len(FakeTool.instances) == (0 if stage == "provider" else 1)
        for tool in FakeTool.instances:
            assert tool.close_count == 1
            assert tool._httpx_client is not None
            assert tool._httpx_client.is_closed

    async def test_invalid_list_arguments_skip_provider(self) -> None:
        provider = AsyncMock(return_value=None)
        with _patch_tool():
            async with DefaultMCPToolHandler(client_provider=provider) as handler:
                result = await handler.invoke_tool(_invocation(tool_name="tools/list", arguments={"q": "test"}))
        assert result.is_error
        assert "does not accept tool arguments" in (result.error_message or "")
        provider.assert_not_awaited()
        assert not FakeTool.instances


# ---------- Construction ---------------------------------------------------


class TestConstruction:
    def test_invalid_cache_size_raises(self) -> None:
        with pytest.raises(ValueError):
            DefaultMCPToolHandler(cache_max_size=0)
        with pytest.raises(ValueError):
            DefaultMCPToolHandler(cache_max_size=-3)


# ---------- Tool kwargs ----------------------------------------------------


class TestToolKwargs:
    @pytest.mark.asyncio
    async def test_load_prompts_false_passed_to_tool(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].kwargs["load_prompts"] is False

    @pytest.mark.asyncio
    async def test_server_label_used_as_tool_name(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_label="MyMcp"))
        assert FakeTool.instances[0].kwargs["name"] == "MyMcp"

    @pytest.mark.asyncio
    async def test_default_tool_name_when_no_label(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_label=None))
        assert FakeTool.instances[0].kwargs["name"] == "McpClient"

    @pytest.mark.asyncio
    async def test_no_header_provider_when_no_headers(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={}))
        assert FakeTool.instances[0].kwargs["header_provider"] is None

    @pytest.mark.asyncio
    async def test_header_provider_returns_captured_headers(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"Authorization": "Bearer T"}))
        provider = FakeTool.instances[0].kwargs["header_provider"]
        assert provider({}) == {"Authorization": "Bearer T"}
        # Even if runtime kwargs change, captured headers stay the same.
        assert provider({"foo": "bar"}) == {"Authorization": "Bearer T"}


# ---------- Cache behaviour ------------------------------------------------


class TestCache:
    @pytest.mark.asyncio
    async def test_same_url_and_headers_hit_cache(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"X": "1"}))
            await handler.invoke_tool(_invocation(headers={"X": "1"}))
        # One tool created, connect called once.
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].connect_count == 1

    @pytest.mark.asyncio
    async def test_different_headers_create_separate_entries(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"Authorization": "tk-A"}))
            await handler.invoke_tool(_invocation(headers={"Authorization": "tk-B"}))
        assert len(FakeTool.instances) == 2

    @pytest.mark.asyncio
    async def test_different_urls_create_separate_entries(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_url="https://mcp.a/api"))
            await handler.invoke_tool(_invocation(server_url="https://mcp.b/api"))
        assert len(FakeTool.instances) == 2

    @pytest.mark.asyncio
    async def test_lru_eviction_closes_old_entry(self) -> None:
        handler = DefaultMCPToolHandler(cache_max_size=2)
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_url="https://a/"))
            await handler.invoke_tool(_invocation(server_url="https://b/"))
            # Inserting a third evicts the LRU entry (the first one).
            await handler.invoke_tool(_invocation(server_url="https://c/"))
        assert len(FakeTool.instances) == 3
        # First instance (https://a/) was evicted → close() called.
        assert FakeTool.instances[0].kwargs["url"] == "https://a/"
        assert FakeTool.instances[0].close_count == 1
        # Other two remain in cache → not closed.
        assert FakeTool.instances[1].close_count == 0
        assert FakeTool.instances[2].close_count == 0

    @pytest.mark.asyncio
    async def test_repeated_use_keeps_lru_alive(self) -> None:
        handler = DefaultMCPToolHandler(cache_max_size=2)
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_url="https://a/"))
            await handler.invoke_tool(_invocation(server_url="https://b/"))
            # Touch a → b becomes LRU.
            await handler.invoke_tool(_invocation(server_url="https://a/"))
            # Insert c → b is evicted.
            await handler.invoke_tool(_invocation(server_url="https://c/"))
        # b was evicted.
        b = FakeTool.instances[1]
        assert b.kwargs["url"] == "https://b/"
        assert b.close_count == 1
        # a survived.
        a = FakeTool.instances[0]
        assert a.kwargs["url"] == "https://a/"
        assert a.close_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_connect_shares_one_entry(self) -> None:
        """Multiple concurrent invocations with the same key must share one tool."""
        handler = DefaultMCPToolHandler()

        # Slow down connect so concurrency window is observable.
        original_connect = FakeTool.connect

        async def slow_connect(self: FakeTool) -> None:
            self.connect_delay = 0.05
            await original_connect(self)

        with _patch_tool(), patch.object(FakeTool, "connect", slow_connect):
            results = await asyncio.gather(
                handler.invoke_tool(_invocation(headers={"X": "1"})),
                handler.invoke_tool(_invocation(headers={"X": "1"})),
                handler.invoke_tool(_invocation(headers={"X": "1"})),
                handler.invoke_tool(_invocation(headers={"X": "1"})),
            )
        assert all(not r.is_error for r in results)
        # Only one tool was created and connected, despite 4 concurrent calls.
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].connect_count == 1

    @pytest.mark.asyncio
    async def test_different_connection_names_create_separate_entries(self) -> None:
        """Same URL/headers but different ``connection_name`` must dispatch separately."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(connection_name="conn-A"))
            await handler.invoke_tool(_invocation(connection_name="conn-B"))
        assert len(FakeTool.instances) == 2

    @pytest.mark.asyncio
    async def test_different_server_labels_create_separate_entries(self) -> None:
        """Same URL/headers but different ``server_label`` must dispatch separately."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_label="LabelA"))
            await handler.invoke_tool(_invocation(server_label="LabelB"))
        assert len(FakeTool.instances) == 2

    @pytest.mark.asyncio
    async def test_full_identity_match_hits_cache(self) -> None:
        """All four identity components match → single cached entry."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(server_label="Lbl", connection_name="C", headers={"X": "1"}))
            await handler.invoke_tool(_invocation(server_label="Lbl", connection_name="C", headers={"X": "1"}))
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].connect_count == 1

    @pytest.mark.asyncio
    async def test_header_name_case_collapses_to_one_cache_entry(self) -> None:
        """Header name spelling differences (case-only) must share a cache entry."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"Authorization": "tk"}))
            await handler.invoke_tool(_invocation(headers={"authorization": "tk"}))
            await handler.invoke_tool(_invocation(headers={"AUTHORIZATION": "tk"}))
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].connect_count == 1

    @pytest.mark.asyncio
    async def test_header_value_case_does_not_collapse(self) -> None:
        """Header *values* remain case-sensitive (different tokens → different sessions)."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"Authorization": "Bearer-A"}))
            await handler.invoke_tool(_invocation(headers={"Authorization": "bearer-a"}))
        assert len(FakeTool.instances) == 2


# ---------- Aclose semantics ----------------------------------------------


class TestAclose:
    @pytest.mark.asyncio
    async def test_aclose_closes_owned_clients(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"X": "1"}))
            tool = FakeTool.instances[0]
            owned = tool._httpx_client
            assert owned is not None
            await handler.aclose()
        assert tool.close_count == 1
        assert owned.is_closed

    @pytest.mark.asyncio
    async def test_aclose_does_not_close_caller_supplied_client(self) -> None:
        caller_client = httpx.AsyncClient()

        async def provider(_inv: MCPToolInvocation) -> httpx.AsyncClient:
            return caller_client

        handler = DefaultMCPToolHandler(client_provider=provider)
        try:
            with _patch_tool():
                await handler.invoke_tool(_invocation(headers={"X": "1"}))
                await handler.aclose()
            assert FakeTool.instances[0].close_count == 1
            # Caller client must still be usable.
            assert not caller_client.is_closed
        finally:
            await caller_client.aclose()

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        with _patch_tool():
            async with DefaultMCPToolHandler() as handler:
                await handler.invoke_tool(_invocation())
            tool = FakeTool.instances[0]
        assert tool.close_count == 1

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self) -> None:
        """A second ``aclose`` is a no-op (no exception, no double-close)."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(headers={"X": "1"}))
            await handler.aclose()
            await handler.aclose()
        assert FakeTool.instances[0].close_count == 1

    @pytest.mark.asyncio
    async def test_invoke_after_close_returns_error_result(self) -> None:
        """Post-close ``invoke_tool`` surfaces a tool error rather than crashing."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.aclose()
            result = await handler.invoke_tool(_invocation())
        assert result.is_error is True
        assert "closed" in (result.error_message or "").lower()

    @pytest.mark.asyncio
    async def test_aclose_drains_inflight_creation(self) -> None:
        """An in-flight ``_create_entry`` must not leak when ``aclose`` races with it.

        Reproduces the race described in PR #5630 review-comment 3:
        task A claims an inflight future and starts a slow connect; task B
        runs ``aclose``; task A must self-clean (close its tool + httpx
        client) and surface a closed-handler error rather than orphaning
        the entry.
        """
        handler = DefaultMCPToolHandler()
        connect_started = asyncio.Event()
        release_connect = asyncio.Event()
        original_connect = FakeTool.connect

        async def gated_connect(self: FakeTool) -> None:
            connect_started.set()
            await release_connect.wait()
            await original_connect(self)

        with _patch_tool(), patch.object(FakeTool, "connect", gated_connect):
            invoke_task = asyncio.create_task(handler.invoke_tool(_invocation(headers={"X": "1"})))
            # Wait until task A is mid-connect.
            await connect_started.wait()
            # Race: kick off aclose. It must wait for the in-flight task.
            close_task = asyncio.create_task(handler.aclose())
            # Yield once to ensure aclose has set _closed and is awaiting.
            await asyncio.sleep(0)
            # Allow the connect to complete; phase 3 sees _closed and self-cleans.
            release_connect.set()
            result = await invoke_task
            await close_task

        # Entry was created and then closed by the in-flight task itself.
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].close_count == 1
        # The originating invocation surfaces a closed-handler error.
        assert result.is_error is True
        assert "closed" in (result.error_message or "").lower()


# ---------- Result normalisation ------------------------------------------


class TestResultNormalisation:
    @pytest.mark.asyncio
    async def test_string_result_wrapped_in_text_content(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            inv = _invocation()
            result = await handler.invoke_tool(inv)
            # The fake's default already returns a list; replace handler for this test.
            FakeTool.instances[0].call_handler = lambda **_a: "raw string body"
            result = await handler.invoke_tool(inv)
        assert result.is_error is False
        assert len(result.outputs) == 1
        assert result.outputs[0].text == "raw string body"  # type: ignore[reportAttributeAccessIssue]

    @pytest.mark.asyncio
    async def test_list_result_passed_through(self) -> None:
        handler = DefaultMCPToolHandler()
        custom = [Content.from_text("a"), Content.from_text("b")]
        with _patch_tool():
            inv = _invocation()
            await handler.invoke_tool(inv)
            FakeTool.instances[0].call_handler = lambda **_a: custom
            result = await handler.invoke_tool(inv)
        assert result.is_error is False
        assert len(result.outputs) == 2


# ---------- Error mapping --------------------------------------------------


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_tool_execution_exception_returns_error_result(self) -> None:
        handler = DefaultMCPToolHandler()

        def boom(**_a: Any) -> Any:
            raise ToolExecutionException("server says no")

        with _patch_tool():
            inv = _invocation()
            await handler.invoke_tool(inv)
            FakeTool.instances[0].call_handler = boom
            result = await handler.invoke_tool(inv)
        assert result.is_error is True
        assert result.error_message == "server says no"
        text = result.outputs[0].text  # type: ignore[reportAttributeAccessIssue]
        assert text is not None
        assert text.startswith("Error:")

    @pytest.mark.asyncio
    async def test_httpx_error_returns_error_result(self) -> None:
        handler = DefaultMCPToolHandler()

        def boom(**_a: Any) -> Any:
            raise httpx.ConnectError("dns failure")

        with _patch_tool():
            inv = _invocation()
            await handler.invoke_tool(inv)
            FakeTool.instances[0].call_handler = boom
            result = await handler.invoke_tool(inv)
        assert result.is_error is True
        assert "dns failure" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_unexpected_exception_propagates(self) -> None:
        """RuntimeError (not in the narrow catch list) must propagate."""
        handler = DefaultMCPToolHandler()

        def boom(**_a: Any) -> Any:
            raise RuntimeError("programmer error")

        with _patch_tool():
            inv = _invocation()
            await handler.invoke_tool(inv)
            FakeTool.instances[0].call_handler = boom
            with pytest.raises(RuntimeError, match="programmer error"):
                await handler.invoke_tool(inv)

    @pytest.mark.asyncio
    async def test_connect_failure_returns_error_result(self) -> None:
        handler = DefaultMCPToolHandler()
        with (
            _patch_tool(),
            patch.object(
                FakeTool,
                "connect",
                lambda self: (_ for _ in ()).throw(httpx.ConnectError("server down")),
            ),
        ):
            result = await handler.invoke_tool(_invocation())
        assert result.is_error is True
        text = result.outputs[0].text  # type: ignore[reportAttributeAccessIssue]
        assert text is not None
        assert text.startswith("Error:")
        # Failed connect must clear in-flight + cache entries.
        assert handler._inflight == {}
        assert len(handler._cache) == 0

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self) -> None:
        """asyncio.CancelledError is BaseException, must NOT be swallowed."""
        handler = DefaultMCPToolHandler()

        def boom(**_a: Any) -> Any:
            raise asyncio.CancelledError

        with _patch_tool():
            inv = _invocation()
            await handler.invoke_tool(inv)
            FakeTool.instances[0].call_handler = boom
            with pytest.raises(asyncio.CancelledError):
                await handler.invoke_tool(inv)


# ---------- Cache key isolation -------------------------------------------


class TestCacheKey:
    def test_key_order_independent(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"A": "1", "B": "2"})
        k2 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"B": "2", "A": "1"})
        assert k1 == k2

    def test_key_distinguishes_values(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"A": "1"})
        k2 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"A": "2"})
        assert k1 != k2

    def test_empty_headers_use_fixed_hash(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", None, None, None)
        k2 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {})
        assert k1 == k2

    def test_key_distinguishes_connection_name(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", None, "conn-A", None)
        k2 = DefaultMCPToolHandler._cache_key("https://x/", None, "conn-B", None)
        assert k1 != k2

    def test_key_distinguishes_server_label(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", "Lbl-A", None, None)
        k2 = DefaultMCPToolHandler._cache_key("https://x/", "Lbl-B", None, None)
        assert k1 != k2

    def test_key_collapses_header_name_case(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"Authorization": "tk"})
        k2 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"authorization": "tk"})
        assert k1 == k2

    def test_key_keeps_header_value_case(self) -> None:
        k1 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"X": "Bearer-A"})
        k2 = DefaultMCPToolHandler._cache_key("https://x/", None, None, {"X": "bearer-a"})
        assert k1 != k2


# ---------- tools/list reserved name --------------------------------------


class TestListTools:
    """Exercise the reserved :attr:`DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME` interception path."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_json_catalog(self) -> None:
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            # Prime the cache so the FakeTool session exists.
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].session.list_tools_pages = [  # type: ignore[union-attr]  # ty: ignore[invalid-assignment]
                FakeListToolsResult(
                    tools=[
                        FakeMcpTool(
                            name="search",
                            description="Search docs",
                            inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
                            outputSchema={"type": "object"},
                        ),
                        FakeMcpTool(name="echo", description=None, outputSchema=None),
                    ],
                ),
            ]
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        assert result.is_error is False
        assert len(result.outputs) == 1
        text = result.outputs[0].text  # type: ignore[reportAttributeAccessIssue]
        assert text is not None
        payload = json.loads(text)
        assert payload == {
            "tools": [
                {
                    "name": "search",
                    "description": "Search docs",
                    "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
                    "outputSchema": {"type": "object"},
                },
                {
                    "name": "echo",
                    "description": None,
                    "inputSchema": {"type": "object", "properties": {}},
                    "outputSchema": None,
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_list_tools_property_order_is_stable(self) -> None:
        """JSON property order is stable: name, description, inputSchema, outputSchema."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].session.list_tools_pages = [  # type: ignore[union-attr]  # ty: ignore[invalid-assignment]
                FakeListToolsResult(tools=[FakeMcpTool(name="t1", description="d")]),
            ]
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        text = result.outputs[0].text  # type: ignore[reportAttributeAccessIssue]
        assert text is not None
        name_idx = text.find('"name"')
        desc_idx = text.find('"description"')
        input_idx = text.find('"inputSchema"')
        output_idx = text.find('"outputSchema"')
        assert 0 <= name_idx < desc_idx < input_idx < output_idx

    @pytest.mark.asyncio
    async def test_list_tools_indented_output(self) -> None:
        """Output is JSON with a 2-space indent so the conversation log is human-readable."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].session.list_tools_pages = [  # type: ignore[union-attr]  # ty: ignore[invalid-assignment]
                FakeListToolsResult(tools=[FakeMcpTool(name="t1")]),
            ]
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        text = result.outputs[0].text  # type: ignore[reportAttributeAccessIssue]
        assert text is not None
        # Indented output contains newlines and a 2-space indented key.
        assert "\n  " in text

    @pytest.mark.asyncio
    async def test_list_tools_rejects_arguments(self) -> None:
        """Reserved name does NOT accept tool arguments. Fails fast before connect."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            result = await handler.invoke_tool(
                _invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME, arguments={"q": "test"}),
            )
        assert result.is_error is True
        assert "does not accept tool arguments" in (result.error_message or "")
        # Args validation runs before connect, so no tool was instantiated.
        assert FakeTool.instances == []

    @pytest.mark.asyncio
    async def test_list_tools_empty_args_dict_is_accepted(self) -> None:
        """An empty arguments dict is equivalent to no arguments."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
            result = await handler.invoke_tool(
                _invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME, arguments={}),
            )
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_list_tools_paginates(self) -> None:
        """Pagination loop calls list_tools repeatedly until nextCursor is empty."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].session.list_tools_pages = [  # type: ignore[union-attr]  # ty: ignore[invalid-assignment]
                FakeListToolsResult(tools=[FakeMcpTool(name="a")], next_cursor="cursor1"),
                FakeListToolsResult(tools=[FakeMcpTool(name="b")], next_cursor="cursor2"),
                FakeListToolsResult(tools=[FakeMcpTool(name="c")], next_cursor=None),
            ]
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        text = result.outputs[0].text  # type: ignore[reportAttributeAccessIssue]
        assert text is not None
        payload = json.loads(text)
        assert [t["name"] for t in payload["tools"]] == ["a", "b", "c"]
        session = FakeTool.instances[0].session
        assert session is not None
        assert len(session.list_tools_calls) == 3
        # First call has no cursor; second/third use the cursor from the prior page.
        assert session.list_tools_calls[0] is None
        assert getattr(session.list_tools_calls[1], "cursor", None) == "cursor1"
        assert getattr(session.list_tools_calls[2], "cursor", None) == "cursor2"

    @pytest.mark.asyncio
    async def test_list_tools_shares_cache_with_call_tool(self) -> None:
        """tools/list reuses the same cached MCP session as a regular call_tool."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation(tool_name="search"))
            await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        assert len(FakeTool.instances) == 1
        assert FakeTool.instances[0].connect_count == 1

    @pytest.mark.asyncio
    async def test_list_tools_propagates_session_errors_as_error_result(self) -> None:
        """Errors raised by session.list_tools become MCPToolResult(is_error=True), not crashes."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].session.list_tools_error = httpx.ReadTimeout("read timed out")  # type: ignore[union-attr]  # ty: ignore[invalid-assignment]
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        assert result.is_error is True
        assert "ReadTimeout" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_list_tools_returns_error_when_session_is_none(self) -> None:
        """If somehow the cached tool has no session, return a clear error rather than crashing."""
        handler = DefaultMCPToolHandler()
        with _patch_tool():
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].session = None
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        assert result.is_error is True
        assert "not connected" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_list_tools_does_not_call_call_tool(self) -> None:
        """The reserved name is intercepted; the inner call_tool path is bypassed."""
        handler = DefaultMCPToolHandler()
        call_tool_invoked = False

        def fail(**_a: Any) -> Any:
            nonlocal call_tool_invoked
            call_tool_invoked = True
            raise AssertionError("call_tool should not run for tools/list")

        with _patch_tool():
            await handler.invoke_tool(_invocation())
            FakeTool.instances[0].call_handler = fail
            FakeTool.instances[0].session.list_tools_pages = [  # type: ignore[union-attr]  # ty: ignore[invalid-assignment]
                FakeListToolsResult(tools=[]),
            ]
            result = await handler.invoke_tool(_invocation(tool_name=DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME))
        assert call_tool_invoked is False
        assert result.is_error is False

    def test_class_attribute_value(self) -> None:
        # Constant must equal the MCP protocol method name so a single
        # string travels unchanged through host code, YAML, and the wire.
        assert DefaultMCPToolHandler.LIST_TOOLS_TOOL_NAME == "tools/list"
