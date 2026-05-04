# Copyright (c) Microsoft. All rights reserved.

"""Tests for ``DefaultMCPToolHandler``.

These tests exercise the real handler against a fake ``MCPStreamableHTTPTool``
(no real MCP server, no real network) to cover the parts of the handler not
exercisable through the executor stub: cache hit/miss/eviction, concurrent
connect via in-flight futures, header isolation across cache keys,
string-result normalisation, ``load_prompts=False`` verification, and
owned-vs-caller httpx close semantics.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import patch

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
        self._httpx_client: httpx.AsyncClient | None = None
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
        assert result.outputs[0].text.startswith("Error:")  # type: ignore[reportAttributeAccessIssue]

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
        assert result.outputs[0].text.startswith("Error:")  # type: ignore[reportAttributeAccessIssue]
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
