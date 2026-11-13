# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

"""Unit tests for FoundryToolbox."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import httpx as host_httpx
import httpx2 as httpx
import pytest
from agent_framework import (
    Agent,
    AgentSession,
    Content,
    FunctionInvocationContext,
    MCPStreamableHTTPTool,
    Message,
    SkillsProvider,
    SkillsSourceContext,
    SupportsAgentRun,
)
from agent_framework.exceptions import ToolException, ToolExecutionException
from agent_framework.openai import OpenAIChatClient
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)
from mcp.client.session import ClientSession
from mcp.types import Prompt, Tool
from pydantic import AnyUrl

from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from agent_framework_foundry_hosting._feature_usage import FeatureIndex
from agent_framework_foundry_hosting._toolbox import (
    _FoundryToolboxSkillsSource,
    _resolve_toolbox_endpoint,
    _toolbox_name_from_endpoint,
    _ToolboxAuth,
)

from .foundry_hosting.toolbox_approval_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    ToolboxApprovalClient,
    ToolboxApprovalServer,
    toolbox_connection,
    toolbox_tool,
)
from .foundry_hosting.web_search_test_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    _ToolResultServer,
)


class _StubAgent:
    """Minimal stand-in for a ``SupportsAgentRun`` used to build a source context."""

    name = "test-agent"


def _source_context() -> SkillsSourceContext:
    """Build a :class:`SkillsSourceContext` for exercising skill sources in tests."""
    return SkillsSourceContext(agent=cast(SupportsAgentRun, _StubAgent()))


class _FakeAccessToken:
    def __init__(self, token: str) -> None:
        self.token = token
        self.expires_on = int(datetime.now(timezone.utc).timestamp()) + 3600


class _FakeCredential:
    """Minimal stand-in for azure.core.credentials.TokenCredential."""

    def __init__(self, token: str = "fake-token") -> None:
        self._token = token
        self.scopes: list[str] = []

    def get_token(self, *scopes: str, **kwargs: object) -> _FakeAccessToken:
        self.scopes.extend(scopes)
        return _FakeAccessToken(self._token)


class _FakeAsyncCredential:
    """Minimal stand-in for azure.core.credentials_async.AsyncTokenCredential."""

    def __init__(self, token: str = "fake-token") -> None:
        self._token = token
        self.scopes: list[str] = []

    async def get_token(self, *scopes: str, **kwargs: object) -> _FakeAccessToken:
        self.scopes.extend(scopes)
        return _FakeAccessToken(self._token)


class _ToolboxLoopbackServer:
    """Minimal MCP server that records platform identity on every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._session_count = 0
        self.before_request: Callable[[httpx.Request], Awaitable[None]] | None = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)

        self.requests.append(request)
        if self.before_request is not None:
            await self.before_request(request)
        payload = json.loads(request.content)
        method = payload.get("method")
        call_id = request.headers.get("x-agent-foundry-call-id")
        headers: dict[str, str] = {}
        result: dict[str, Any]

        if method == "initialize":
            self._session_count += 1
            headers["mcp-session-id"] = f"session-{self._session_count}-{call_id or 'none'}"
            result = {
                "protocolVersion": payload["params"]["protocolVersion"],
                "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                "serverInfo": {"name": "toolbox-loopback", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "record",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"marker": {"type": "string"}},
                        },
                    }
                ]
            }
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": call_id or "none"}]}
        elif method == "prompts/list":
            result = {"prompts": [{"name": "request-prompt"}]}
        elif method == "prompts/get":
            result = {"messages": [{"role": "user", "content": {"type": "text", "text": call_id or "none"}}]}
        elif method == "resources/read":
            uri = payload["params"]["uri"]
            if uri == "skill://index.json":
                text = json.dumps({
                    "skills": [
                        {
                            "name": "loopback-skill",
                            "description": "Records the current Toolbox request identity.",
                            "type": "skill-md",
                            "url": "skill://loopback-skill/SKILL.md",
                        }
                    ]
                })
                mime_type = "application/json"
            else:
                text = f"# Loopback skill\n\nCall ID: {call_id or 'none'}"
                mime_type = "text/markdown"
            result = {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]}
        else:
            result = {}

        if "id" not in payload:
            return httpx.Response(202)
        return httpx.Response(
            200,
            headers=headers,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
        )

    def requests_for(self, method: str) -> list[httpx.Request]:
        return [request for request in self.requests if json.loads(request.content).get("method") == method]


async def _attach_loopback_transport(toolbox: FoundryToolbox, server: _ToolboxLoopbackServer) -> None:
    client = toolbox._httpx_client
    assert client is not None
    toolbox._httpx_client = httpx.AsyncClient(
        auth=client.auth,
        transport=httpx.MockTransport(server.handle),
        timeout=30,
    )
    await client.aclose()


async def _run_with_request_context(call_id: str, action: Callable[[], Awaitable[Any]]) -> Any:
    token = set_request_context(FoundryAgentRequestContext(call_id=call_id, user_id="same-user"))
    try:
        return await action()
    finally:
        reset_request_context(token)


async def test_same_call_id_overlaps_tool_and_skill_reads_without_freezing_bearer_tokens() -> None:
    server = _ToolboxLoopbackServer()
    arrivals: asyncio.Queue[httpx.Request] = asyncio.Queue()
    release = asyncio.Event()

    async def hold_response(request: httpx.Request) -> None:
        if json.loads(request.content).get("method") in ("tools/call", "resources/read"):
            arrivals.put_nowait(request)
            await release.wait()

    server.before_request = hold_response
    credential = _FakeCredential("before-refresh")
    toolbox = FoundryToolbox(credential, url="https://h/toolboxes/tb/mcp")  # type: ignore
    await _attach_loopback_transport(toolbox, server)
    try:
        await _run_with_request_context("parallel-call", toolbox.connect)
        first = asyncio.create_task(
            _run_with_request_context("parallel-call", lambda: toolbox.call_tool("record", marker="first"))
        )
        first_request = await asyncio.wait_for(arrivals.get(), timeout=5)
        credential._token = "after-refresh"
        second = asyncio.create_task(
            _run_with_request_context("parallel-call", lambda: toolbox.call_tool("record", marker="second"))
        )
        resource = asyncio.create_task(
            _run_with_request_context(
                "parallel-call", lambda: toolbox._read_resource(AnyUrl("skill://loopback-skill/SKILL.md"))
            )
        )
        try:
            next_requests = [await asyncio.wait_for(arrivals.get(), timeout=5) for _ in range(2)]
            assert not first.done() and not second.done() and not resource.done()
            assert first_request.headers["Authorization"] == "Bearer before-refresh"
            assert all(request.headers["Authorization"] == "Bearer after-refresh" for request in next_requests)
            assert all(
                request.headers["x-agent-foundry-call-id"] == "parallel-call"
                for request in [first_request, *next_requests]
            )
        finally:
            release.set()
            await asyncio.gather(first, second, resource)
        for task in (first, second):
            result = await task
            assert isinstance(result, list)
            assert result[0].text == "parallel-call"
        assert len(server.requests_for("initialize")) == 1
    finally:
        release.set()
        await toolbox.close()


async def test_cancelled_close_keeps_http_client_alive_until_owner_finishes() -> None:
    toolbox = FoundryToolbox(_FakeCredential(), url="https://h/toolboxes/tb/mcp")  # type: ignore
    await _attach_loopback_transport(toolbox, _ToolboxLoopbackServer())
    await _run_with_request_context("closing-call", toolbox.connect)
    client = toolbox._httpx_client
    assert client is not None
    closing = asyncio.Event()
    release = asyncio.Event()
    close_on_owner = toolbox._close_on_owner

    async def hold_teardown() -> None:
        closing.set()
        await release.wait()
        await close_on_owner()

    with patch.object(toolbox, "_close_on_owner", side_effect=hold_teardown):
        task = asyncio.create_task(toolbox.close())
        try:
            await asyncio.wait_for(closing.wait(), timeout=5)
            task.cancel()
            for _ in range(10):
                await asyncio.sleep(0)
            assert not task.done()
            assert not client.is_closed
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
    assert client.is_closed
    assert toolbox._httpx_client is None
    assert not toolbox.is_connected


async def test_toolbox_close_fences_recovery_before_waiting_for_its_barrier() -> None:
    from anyio import ClosedResourceError

    toolbox = FoundryToolbox(_FakeCredential(), url="https://h/toolboxes/tb/mcp")  # type: ignore
    server = _ToolboxLoopbackServer()
    await _attach_loopback_transport(toolbox, server)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fail_call(*args: Any, **kwargs: Any) -> None:
        started.set()
        await release.wait()
        raise ClosedResourceError

    tasks: list[asyncio.Task[Any]] = []
    try:
        async with asyncio.timeout(5):
            await _run_with_request_context("closing-call", toolbox.connect)
            connection = toolbox._require_connection()
            assert connection.client is not None
            with patch.object(connection.client, "call_tool", side_effect=fail_call):
                calling = asyncio.create_task(
                    _run_with_request_context("closing-call", lambda: toolbox.call_tool("record", marker="no-retry"))
                )
                tasks.append(calling)
                await started.wait()
                closing = asyncio.create_task(toolbox.close())
                tasks.append(closing)
                await asyncio.sleep(0)
                assert not closing.done()
                release.set()
                await closing
                with pytest.raises(ToolExecutionException, match="interrupted by close"):
                    await calling
            assert not toolbox.is_connected
            assert toolbox._httpx_client is None
            assert len(server.requests_for("initialize")) == 1
            assert not server.requests_for("tools/call")
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await toolbox.close()


def test_resolve_endpoint_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOLBOX_ENDPOINT", "https://host/toolboxes/tb/mcp?api-version=v1")
    assert _resolve_toolbox_endpoint() == "https://host/toolboxes/tb/mcp?api-version=v1"


def test_resolve_endpoint_builds_from_project_and_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOOLBOX_ENDPOINT", raising=False)
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://proj.example.com/")
    monkeypatch.setenv("TOOLBOX_NAME", "mybox")
    assert _resolve_toolbox_endpoint() == "https://proj.example.com/toolboxes/mybox/mcp?api-version=v1"


def test_resolve_endpoint_empty_explicit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOLBOX_ENDPOINT", "")
    with pytest.raises(ValueError, match="empty"):
        _resolve_toolbox_endpoint()


def test_resolve_endpoint_missing_inputs_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOOLBOX_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("TOOLBOX_NAME", raising=False)
    with pytest.raises(ValueError, match="TOOLBOX_ENDPOINT"):
        _resolve_toolbox_endpoint()


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://h/toolboxes/alpha/mcp?api-version=v1", "alpha"),
        ("https://h/toolboxes/beta/versions/3/mcp", "beta"),
        ("https://h/something/else", "toolbox"),
    ],
)
def test_toolbox_name_from_endpoint(endpoint: str, expected: str) -> None:
    assert _toolbox_name_from_endpoint(endpoint) == expected


def test_init_derives_name_and_defaults() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/sales/mcp?api-version=v1",
    )
    assert toolbox.name == "sales"
    assert toolbox.url == "https://h/toolboxes/sales/mcp?api-version=v1"
    # Toolboxes expose tools, not prompts.
    assert toolbox.load_prompts_flag is False


def test_init_forwards_additional_tool_arguments_and_parent_kwargs() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/sales/mcp?api-version=v1",
        description="Sales tools",
        additional_tool_argument_names={"*": ["tenant_id"], "search": ["thread"]},
    )

    assert toolbox.description == "Sales tools"
    assert toolbox._global_extra_arg_names == {"tenant_id"}
    assert toolbox._tool_extra_arg_names == {"search": {"thread"}}


@pytest.mark.parametrize(
    "metadata_location", ["structured", "block", "resource", "block_and_structured", "resource_and_structured"]
)
async def test_web_search_preserves_prose_and_citation_metadata(metadata_location: str) -> None:
    citation = {
        "type": "url_citation",
        "url": "https://example.test/source",
        "title": "Source",
        "start_index": 0,
        "end_index": 4,
    }
    resource: dict[str, Any] = {"uri": "about:web-search", "text": "Mars is red."}
    block: dict[str, Any] = {"type": "resource", "resource": resource}
    if metadata_location.startswith("block"):
        block["_meta"] = {"annotations": [citation]}
    elif metadata_location.startswith("resource"):
        resource["_meta"] = {"annotations": [citation]}
    structured: dict[str, Any] = {"query": "Mars"}
    if "structured" in metadata_location:
        structured["annotations"] = [citation]
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {"content": [block], "structuredContent": structured}
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert [item.text for item in result] == ["Mars is red.", json.dumps(structured)]
    expected: dict[str, Any] = {
        "type": "citation",
        "url": "https://example.test/source",
        "title": "Source",
    }
    if metadata_location != "structured":
        expected["annotated_regions"] = [{"type": "text_span", "start_index": 0, "end_index": 4}]
    citation_item = result[1] if metadata_location == "structured" else result[0]
    assert citation_item.annotations == [expected]


async def test_web_search_keeps_aggregate_citations_unbound_when_content_has_multiple_blocks() -> None:
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [{"type": "text", "text": "First"}, {"type": "text", "text": "Second"}],
        "structuredContent": {
            "annotations": [
                {
                    "type": "url_citation",
                    "url": "https://example.test/source",
                    "start_index": 0,
                    "end_index": 5,
                }
            ]
        },
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert [item.text for item in result] == ["First", "Second", json.dumps(server.call_result["structuredContent"])]
    assert result[0].annotations is None
    assert result[1].annotations is None
    assert result[2].annotations == [{"type": "citation", "url": "https://example.test/source"}]


async def test_web_search_keeps_block_citations_with_their_owning_text() -> None:
    first = {"type": "url_citation", "url": "https://example.test/first", "start_index": 0, "end_index": 5}
    second = {"type": "url_citation", "url": "https://example.test/second", "start_index": 0, "end_index": 6}
    unbound = {"type": "url_citation", "url": "https://example.test/other", "start_index": 0, "end_index": 5}
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [
            {"type": "text", "text": "First", "_meta": {"annotations": [first]}},
            {"type": "text", "text": "Second", "_meta": {"annotations": [second]}},
        ],
        "structuredContent": {"annotations": [first, second, unbound]},
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert [item.text for item in result] == ["First", "Second", json.dumps(server.call_result["structuredContent"])]
    assert result[0].annotations == [
        {
            "type": "citation",
            "url": "https://example.test/first",
            "annotated_regions": [{"type": "text_span", "start_index": 0, "end_index": 5}],
        }
    ]
    assert result[1].annotations == [
        {
            "type": "citation",
            "url": "https://example.test/second",
            "annotated_regions": [{"type": "text_span", "start_index": 0, "end_index": 6}],
        }
    ]
    assert result[2].annotations == [{"type": "citation", "url": "https://example.test/other"}]


async def test_web_search_keeps_repeated_aggregate_citations_not_matched_to_a_block() -> None:
    citation = {"type": "url_citation", "url": "https://example.test/source", "start_index": 0, "end_index": 5}
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [
            {"type": "text", "text": "First", "_meta": {"annotations": [citation]}},
            {"type": "text", "text": "Second"},
        ],
        "structuredContent": {"annotations": [citation, citation]},
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert result[0].annotations == [
        {
            "type": "citation",
            "url": "https://example.test/source",
            "annotated_regions": [{"type": "text_span", "start_index": 0, "end_index": 5}],
        }
    ]
    assert result[1].annotations is None
    assert result[2].annotations == [{"type": "citation", "url": "https://example.test/source"}]


async def test_web_search_keeps_citations_on_non_text_blocks_without_a_span() -> None:
    citation = {"type": "url_citation", "url": "https://example.test/image", "start_index": 0, "end_index": 5}
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [
            {"type": "image", "data": "eA==", "mimeType": "image/png", "_meta": {"annotations": [citation]}},
            {"type": "text", "text": "Search prose"},
        ],
        "structuredContent": {"annotations": [citation]},
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert result[0].type == "data"
    assert result[0].annotations == [{"type": "citation", "url": "https://example.test/image"}]
    assert result[1].text == "Search prose"
    assert result[2].text == json.dumps(server.call_result["structuredContent"])


@pytest.mark.parametrize(
    ("start", "end", "expected_region"),
    [
        (1, 3, {"type": "text_span", "start_index": 1, "end_index": 2}),
        (2, 3, None),
        (True, 3, None),
        (-1, 3, None),
        (1, 6, None),
    ],
)
async def test_web_search_ignores_invalid_utf16_citation_spans(
    start: Any, end: Any, expected_region: dict[str, Any] | None
) -> None:
    citation = {"type": "url_citation", "url": "https://example.test/source", "start_index": start, "end_index": end}
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [{"type": "text", "text": "A\U0001f30eBC", "_meta": {"annotations": [citation]}}],
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert result[0].annotations is not None
    assert result[0].annotations[0].get("annotated_regions") == (
        [expected_region] if expected_region is not None else None
    )
    if expected_region is not None:
        assert result[0].text is not None
        assert result[0].text[expected_region["start_index"] : expected_region["end_index"]] == "\U0001f30e"


async def test_web_search_preserves_unrecognized_structured_entries() -> None:
    unrecognized = [
        {"type": "url_citation", "title": "missing URL"},
        {"type": "url_citation", "url": "  "},
        {"type": "other", "value": 7},
        "invalid",
    ]
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [{"type": "text", "text": "Search prose"}],
        "structuredContent": {
            "annotations": [{"type": "url_citation", "url": "https://example.test"}, *unrecognized],
            "query": "Mars",
        },
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert result[0].text == "Search prose"
    assert result[1].text is not None
    assert result[1].annotations == [{"type": "citation", "url": "https://example.test"}]
    assert json.loads(result[1].text) == server.call_result["structuredContent"]


@pytest.mark.parametrize("content", [[], [{"type": "text", "text": ""}]])
async def test_web_search_without_prose_keeps_structured_result(content: list[dict[str, Any]]) -> None:
    structured = {"annotations": [{"type": "url_citation", "url": "https://example.test"}]}
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {"content": content, "structuredContent": structured}
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert result[0].text is not None
    assert json.loads(result[0].text) == structured
    assert result[0].annotations == [{"type": "citation", "url": "https://example.test"}]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("content_first", ["Search prose"]),
        ("content_only", ["Search prose"]),
        ("structured_only", ['{"annotations": [{"type": "url_citation", "url": "https://example.test"}]}']),
        ("both", ["Search prose", '{"annotations": [{"type": "url_citation", "url": "https://example.test"}]}']),
    ],
)
async def test_other_mcp_content_modes_replace_citation_handling(mode: str, expected: list[str]) -> None:
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [{"type": "text", "text": "Search prose"}],
        "structuredContent": {"annotations": [{"type": "url_citation", "url": "https://example.test"}]},
    }
    async with toolbox_connection(server, tool_result_content=mode) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert [item.text for item in result] == expected
    assert all(item.annotations is None for item in result)


async def test_custom_mcp_result_parser_overrides_toolbox_projection() -> None:
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [{"type": "text", "text": "Search prose"}],
        "structuredContent": {"annotations": [{"type": "url_citation", "url": "https://example.test"}]},
    }
    async with toolbox_connection(server, parse_tool_results=lambda _: "Custom result") as toolbox:
        assert await toolbox.call_tool("learn___microsoft_docs_search") == "Custom result"


async def test_non_web_search_result_keeps_default_mcp_selection() -> None:
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [{"type": "text", "text": "Summary"}],
        "structuredContent": {"value": 42},
    }
    async with toolbox_connection(server) as toolbox:
        result = await toolbox.call_tool("learn___microsoft_docs_search")

    assert isinstance(result, list)
    assert [item.text for item in result] == ['{"value": 42}']


@pytest.mark.parametrize("stream", [False, True])
async def test_web_search_provenance_survives_function_invocation(stream: bool) -> None:
    citation = {
        "type": "url_citation",
        "url": "https://example.test/source",
        "start_index": 0,
        "end_index": 4,
    }
    server = _ToolResultServer()
    server.tools = [toolbox_tool("never")]
    server.call_result = {
        "content": [
            {
                "type": "resource",
                "resource": {
                    "uri": "about:web-search",
                    "text": "Mars is red.",
                    "_meta": {"annotations": [citation]},
                },
            }
        ],
        "structuredContent": {"annotations": [citation]},
        "_meta": {"source": "server"},
    }
    client = ToolboxApprovalClient("learn___microsoft_docs_search")
    async with toolbox_connection(server) as toolbox:
        agent = Agent(client=client, tools=toolbox)
        session = agent.create_session()
        if stream:
            response_stream = agent.run("Search", session=session, stream=True)
            updates = [update async for update in response_stream]
            response = await response_stream.get_final_response()
            assert sum(content.type == "function_result" for update in updates for content in update.contents) == 1
        else:
            response = await agent.run("Search", session=session)

        restored_session = AgentSession.from_dict(json.loads(json.dumps(session.to_dict())))
        if stream:
            continued_stream = agent.run("Continue", session=restored_session, stream=True)
            _ = [update async for update in continued_stream]
            await continued_stream.get_final_response()
        else:
            await agent.run("Continue", session=restored_session)

    results = [
        content for message in response.messages for content in message.contents if content.type == "function_result"
    ]
    assert len(results) == 1
    assert results[0].call_id == "call-search"
    assert results[0].items is not None
    assert results[0].items[0].text == "Mars is red."
    assert results[0].items[0].annotations == [
        {
            "type": "citation",
            "url": "https://example.test/source",
            "annotated_regions": [{"type": "text_span", "start_index": 0, "end_index": 4}],
        }
    ]
    assert results[0].result == "Mars is red.\n" + json.dumps(server.call_result["structuredContent"])
    model_results = [
        content for message in client.calls[1] for content in message.contents if content.type == "function_result"
    ]
    assert len(model_results) == 1
    assert model_results[0].call_id == "call-search"
    assert model_results[0].items is not None
    assert model_results[0].items[0].annotations == results[0].items[0].annotations
    replayed = [content for message in client.calls[2] for content in message.contents]
    assert sum(content.type == "function_call" and content.call_id == "call-search" for content in replayed) == 1
    replayed_results = [content for content in replayed if content.type == "function_result"]
    assert len(replayed_results) == 1
    assert replayed_results[0].call_id == "call-search"
    assert replayed_results[0].items is not None
    assert replayed_results[0].items[0].annotations == results[0].items[0].annotations
    provider = OpenAIChatClient(model="test-model", api_key="test-key")
    try:
        assert provider._prepare_content_for_openai("tool", model_results[0]) == {
            "type": "function_call_output",
            "call_id": "call-search",
            "output": results[0].result,
        }
    finally:
        await provider.client.close()
    assert results[0].items[0].additional_properties["_meta"] == {"source": "server"}
    restored = Content.from_dict(results[0].to_dict())
    assert restored.items is not None
    assert restored.items[0].annotations == results[0].items[0].annotations
    host_payload = restored.additional_properties["_mcp_tool_result_host_payload"]
    assert host_payload["content"] == server.call_result["content"]
    assert host_payload["structuredContent"] == server.call_result["structuredContent"]
    assert host_payload["_meta"] == {"source": "server"}
    assert len(server.calls) == 1


def test_toolbox_owns_feature_index_53() -> None:
    assert FeatureIndex.FOUNDRY_TOOLBOX == 53


async def test_toolbox_marks_feature_on_successful_connect_not_construction() -> None:
    with (
        patch.object(MCPStreamableHTTPTool, "connect", new=AsyncMock()) as connect,
        patch("agent_framework_foundry_hosting._toolbox.mark_feature_used") as mark_used,
    ):
        toolbox = FoundryToolbox(
            _FakeCredential(),  # type: ignore
            url="https://h/toolboxes/sales/mcp?api-version=v1",
        )
        mark_used.assert_not_called()

        await toolbox.connect()

    connect.assert_awaited_once_with(reset=False)
    mark_used.assert_called_once_with(FeatureIndex.FOUNDRY_TOOLBOX)


async def test_auth_flow_injects_bearer_token() -> None:
    cred = _FakeCredential("abc123")
    auth = _ToolboxAuth(cred, "https://ai.azure.com/.default")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = await anext(auth.async_auth_flow(request))

    assert prepared.headers["Authorization"] == "Bearer abc123"
    assert cred.scopes == ["https://ai.azure.com/.default"]


async def test_auth_flow_injects_bearer_token_async_credential() -> None:
    cred = _FakeAsyncCredential("async123")
    auth = _ToolboxAuth(cred, "https://ai.azure.com/.default")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = await anext(auth.async_auth_flow(request))

    assert prepared.headers["Authorization"] == "Bearer async123"
    assert cred.scopes == ["https://ai.azure.com/.default"]


@pytest.mark.parametrize(
    ("additional_features", "expected"),
    [
        (None, "Toolboxes=V1Preview"),
        ("   ", "Toolboxes=V1Preview"),
        ("FeatureOne=Enabled,FeatureTwo=Enabled", "Toolboxes=V1Preview,FeatureOne=Enabled,FeatureTwo=Enabled"),
        ("FeatureOne=Enabled, toolboxes=v1preview ", "FeatureOne=Enabled, toolboxes=v1preview "),
    ],
)
async def test_auth_flow_injects_foundry_features_header(
    monkeypatch: pytest.MonkeyPatch,
    additional_features: str | None,
    expected: str,
) -> None:
    if additional_features is None:
        monkeypatch.delenv("FOUNDRY_AGENT_TOOLSET_FEATURES", raising=False)
    else:
        monkeypatch.setenv("FOUNDRY_AGENT_TOOLSET_FEATURES", additional_features)
    auth = _ToolboxAuth(_FakeCredential(), "scope")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = await anext(auth.async_auth_flow(request))

    assert prepared.headers["Foundry-Features"] == expected


def test_sync_auth_flow_injects_foundry_features_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_AGENT_TOOLSET_FEATURES", "FeatureOne=Enabled")
    auth = _ToolboxAuth(_FakeCredential(), "scope")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = next(auth.sync_auth_flow(request))

    assert prepared.headers["Foundry-Features"] == "Toolboxes=V1Preview,FeatureOne=Enabled"


def test_sync_auth_flow_injects_bearer_token() -> None:
    cred = _FakeCredential("sync123")
    auth = _ToolboxAuth(cred, "https://ai.azure.com/.default")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = next(auth.sync_auth_flow(request))

    assert prepared.headers["Authorization"] == "Bearer sync123"
    assert cred.scopes == ["https://ai.azure.com/.default"]


def test_sync_auth_flow_rejects_async_credential() -> None:
    auth = _ToolboxAuth(_FakeAsyncCredential(), "scope")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    with pytest.raises(RuntimeError, match="async credential"):
        next(auth.sync_auth_flow(request))


async def test_toolbox_header_provider_forwards_platform_headers_and_preserves_caller_headers() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
        header_provider=lambda kwargs: {
            "X-Custom-Header": kwargs["custom"],
            "x-agent-foundry-call-id": "untrusted-override",
        },
    )

    token = set_request_context(FoundryAgentRequestContext(call_id="call-xyz"))
    try:
        headers = toolbox._effective_headers({"custom": "custom-value"})
    finally:
        reset_request_context(token)
        await toolbox.close()

    assert headers["X-Custom-Header"] == "custom-value"
    assert headers["x-agent-foundry-call-id"] == "call-xyz"


async def test_toolbox_header_provider_does_not_retain_prior_platform_context() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )

    token = set_request_context(FoundryAgentRequestContext(call_id="canary-call-id"))
    try:
        headers = toolbox._effective_headers({})
        assert headers["x-agent-foundry-call-id"] == "canary-call-id"
    finally:
        reset_request_context(token)

    try:
        headers = toolbox._effective_headers({})
    finally:
        await toolbox.close()

    assert "x-agent-foundry-call-id" not in headers


@pytest.mark.parametrize("generated", [False, True])
async def test_prompt_in_detached_child_uses_current_platform_context(generated: bool) -> None:
    server = _ToolboxLoopbackServer()
    start_child = asyncio.Event()
    children: list[asyncio.Task[str]] = []
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
        load_prompts=True,
    )
    await _attach_loopback_transport(toolbox, server)

    async def call_prompt() -> str:
        await start_child.wait()
        token = set_request_context(FoundryAgentRequestContext(call_id="CALL-B", user_id="same-user"))
        try:
            if generated:
                prompt = next(function for function in toolbox.functions if function.name == "request-prompt")
                context = FunctionInvocationContext(function=prompt, arguments={}, kwargs={})
                contents = await prompt.invoke(arguments={}, context=context)
                assert len(contents) == 1
                assert contents[0].text is not None
                return contents[0].text
            return await toolbox.get_prompt("request-prompt")
        finally:
            reset_request_context(token)

    async def spawn_child(request: httpx.Request) -> None:
        if json.loads(request.content).get("method") == "tools/call":
            children.append(asyncio.create_task(call_prompt()))

    server.before_request = spawn_child
    try:
        async with asyncio.timeout(5):
            await _run_with_request_context("CALL-A", toolbox.connect)
            await _run_with_request_context("CALL-A", lambda: toolbox.call_tool("record", marker="parent"))
            assert len(children) == 1
            start_child.set()
            assert await children[0] == "CALL-B"
            request = server.requests_for("prompts/get")[-1]
            assert request.headers["x-agent-foundry-call-id"] == "CALL-B"
            assert request.headers["mcp-session-id"].endswith("-CALL-B")
            assert len(server.requests_for("initialize")) == 2
    finally:
        start_child.set()
        for child in children:
            child.cancel()
        await asyncio.gather(*children, return_exceptions=True)
        await toolbox.close()


async def test_custom_header_provider_key_error_does_not_drop_platform_headers() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
        header_provider=lambda kwargs: {"X-Custom-Header": kwargs["custom"]},
    )
    await _attach_loopback_transport(toolbox, server)

    try:
        await _run_with_request_context("CALL-X", toolbox.connect)
        await _run_with_request_context(
            "CALL-X",
            lambda: toolbox.call_tool("record", marker="with-custom", custom="custom-value"),
        )
        with pytest.raises(KeyError, match="custom"):
            await _run_with_request_context(
                "CALL-X",
                lambda: toolbox.call_tool("record", marker="missing-custom"),
            )
    finally:
        await toolbox.close()

    first_initialize = server.requests_for("initialize")[0]
    assert first_initialize.headers["x-agent-foundry-call-id"] == "CALL-X"
    assert "X-Custom-Header" not in first_initialize.headers

    call = server.requests_for("tools/call")[-1]
    assert call.headers["x-agent-foundry-call-id"] == "CALL-X"
    assert call.headers["X-Custom-Header"] == "custom-value"


async def test_custom_header_provider_missing_seeded_value_still_fails_connect() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
        header_provider=lambda kwargs: {"X-Custom-Header": kwargs["custom"]},
    )
    await _attach_loopback_transport(toolbox, server)

    token = set_request_context(FoundryAgentRequestContext(call_id="CALL-X"))
    try:
        await toolbox._prepare_for_run({})
        with pytest.raises(ToolException):
            await toolbox.connect()
    finally:
        reset_request_context(token)
        await toolbox.close()

    assert server.requests_for("initialize") == []


async def test_auth_flow_does_not_resolve_platform_context() -> None:
    auth = _ToolboxAuth(_FakeCredential(), "scope")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    token = set_request_context(FoundryAgentRequestContext(call_id="call-xyz"))
    try:
        prepared = await anext(auth.async_auth_flow(request))
    finally:
        reset_request_context(token)

    assert "x-agent-foundry-call-id" not in prepared.headers


async def test_toolbox_rebinds_after_connection_without_request_context() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
    )
    await _attach_loopback_transport(toolbox, server)

    try:
        await toolbox.connect()
        await _run_with_request_context(
            "CALL-B",
            lambda: toolbox.call_tool("record", marker="second-request"),
        )
    finally:
        await toolbox.close()

    initializes = server.requests_for("initialize")
    assert [request.headers.get("x-agent-foundry-call-id") for request in initializes] == [None, "CALL-B"]
    call = server.requests_for("tools/call")[-1]
    assert call.headers["x-agent-foundry-call-id"] == "CALL-B"
    assert call.headers["mcp-session-id"].endswith("-CALL-B")


async def test_toolbox_concurrent_callers_use_their_own_call_id() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
    )
    await _attach_loopback_transport(toolbox, server)

    try:
        await _run_with_request_context("CALL-A", toolbox.connect)
        await asyncio.gather(
            _run_with_request_context(
                "CALL-B",
                lambda: toolbox.call_tool("record", marker="request-b"),
            ),
            _run_with_request_context(
                "CALL-C",
                lambda: toolbox.call_tool("record", marker="request-c"),
            ),
        )
    finally:
        await toolbox.close()

    calls = server.requests_for("tools/call")
    calls_by_marker = {json.loads(request.content)["params"]["arguments"]["marker"]: request for request in calls}
    assert calls_by_marker["request-b"].headers["x-agent-foundry-call-id"] == "CALL-B"
    assert calls_by_marker["request-b"].headers["mcp-session-id"].endswith("-CALL-B")
    assert calls_by_marker["request-c"].headers["x-agent-foundry-call-id"] == "CALL-C"
    assert calls_by_marker["request-c"].headers["mcp-session-id"].endswith("-CALL-C")


async def test_toolbox_concurrent_skill_reads_use_their_own_call_id() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
        load_tools=False,
        header_provider=lambda _kwargs: {"X-Custom-Header": "resource-value"},
    )
    await _attach_loopback_transport(toolbox, server)
    source = toolbox.as_skills_provider()._source

    async def read_skill() -> tuple[str, str]:
        skills = await source.get_skills(_source_context())
        assert len(skills) == 1
        content = await skills[0].get_content()
        resource = await skills[0].get_resource("reference.md")
        assert resource is not None
        return content, await resource.read()

    try:
        await _run_with_request_context("CALL-A", toolbox.connect)
        results = await asyncio.gather(
            _run_with_request_context("CALL-B", read_skill),
            _run_with_request_context("CALL-C", read_skill),
        )
    finally:
        await toolbox.close()

    assert "CALL-B" in results[0][0]
    assert "CALL-B" in results[0][1]
    assert "CALL-C" in results[1][0]
    assert "CALL-C" in results[1][1]

    resource_requests = server.requests_for("resources/read")
    assert len(resource_requests) == 6
    assert [request.headers["x-agent-foundry-call-id"] for request in resource_requests].count("CALL-B") == 3
    assert [request.headers["x-agent-foundry-call-id"] for request in resource_requests].count("CALL-C") == 3
    assert all(
        request.headers["mcp-session-id"].endswith(f"-{request.headers['x-agent-foundry-call-id']}")
        for request in resource_requests
    )
    assert all(request.headers["X-Custom-Header"] == "resource-value" for request in resource_requests)


async def test_retained_skill_read_waits_for_replacement_initialization() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(_FakeCredential(), url="https://loopback.invalid/mcp")  # type: ignore
    await _attach_loopback_transport(toolbox, server)
    source = toolbox.as_skills_provider()._source
    initializing = asyncio.Event()
    release = asyncio.Event()
    tasks: list[asyncio.Task[Any]] = []

    async def block_replacement(request: httpx.Request) -> None:
        if (
            json.loads(request.content).get("method") == "initialize"
            and request.headers.get("x-agent-foundry-call-id") == "CALL-B"
        ):
            initializing.set()
            await release.wait()

    try:
        async with asyncio.timeout(10):
            await _run_with_request_context("CALL-A", toolbox.connect)
            skills = await _run_with_request_context("CALL-A", lambda: source.get_skills(_source_context()))
            assert len(skills) == 1
            server.before_request = block_replacement
            transition = asyncio.create_task(
                _run_with_request_context("CALL-B", lambda: toolbox.call_tool("record", marker="transition"))
            )
            tasks.append(transition)
            await initializing.wait()
            read = asyncio.create_task(_run_with_request_context("CALL-B", skills[0].get_content))
            tasks.append(read)
            await asyncio.sleep(0)
            assert not read.done()
            assert not any(
                request.headers.get("x-agent-foundry-call-id") == "CALL-B"
                for request in server.requests_for("resources/read")
            )
            release.set()
            result = await transition
            assert isinstance(result, list)
            assert len(result) == 1 and result[0].text == "CALL-B"
            assert "Call ID: CALL-B" in await read
            request = server.requests_for("resources/read")[-1]
            assert request.headers["x-agent-foundry-call-id"] == "CALL-B"
            assert request.headers["mcp-session-id"].endswith("-CALL-B")
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await toolbox.close()


async def test_toolbox_skills_reject_header_provider_that_requires_runtime_kwargs() -> None:
    server = _ToolboxLoopbackServer()
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://loopback.invalid/mcp",
        load_tools=False,
        header_provider=lambda kwargs: {"X-Custom-Header": kwargs["custom"]},
    )
    await _attach_loopback_transport(toolbox, server)
    source = toolbox.as_skills_provider()._source

    try:
        await _run_with_request_context("CALL-X", toolbox.connect)
        with pytest.raises(ToolExecutionException, match="cannot use a header_provider"):
            await _run_with_request_context("CALL-X", lambda: source.get_skills(_source_context()))
    finally:
        await toolbox.close()

    assert server.requests_for("resources/read") == []


async def test_close_closes_owned_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    client = toolbox._httpx_client
    assert client is not None
    aclose = AsyncMock()
    monkeypatch.setattr(client, "aclose", aclose)

    await toolbox.close()

    aclose.assert_awaited_once()
    # Idempotent: a second close does not re-close the client.
    await toolbox.close()
    aclose.assert_awaited_once()


def test_as_skills_provider_returns_provider() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    provider = toolbox.as_skills_provider(source_id="toolbox-skills")
    assert isinstance(provider, SkillsProvider)
    assert provider.source_id == "toolbox-skills"


def test_as_skills_provider_requires_approval_by_default() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    provider = toolbox.as_skills_provider()
    # By default every skill tool keeps its approval requirement.
    assert provider._disable_load_skill_approval is False
    assert provider._disable_read_skill_resource_approval is False
    assert provider._disable_run_skill_script_approval is False


def test_as_skills_provider_forwards_approval_overrides() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    provider = toolbox.as_skills_provider(
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
        disable_run_skill_script_approval=True,
    )
    # Overrides flow through to the underlying SkillsProvider so an unattended
    # host (no AgentSession) can load skills without an approval round-trip.
    assert provider._disable_load_skill_approval is True
    assert provider._disable_read_skill_resource_approval is True
    assert provider._disable_run_skill_script_approval is True


async def test_skills_source_requires_connection() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    # The toolbox has not been connected, so there is no MCP session yet.
    assert toolbox.session is None
    source = _FoundryToolboxSkillsSource(toolbox)
    with pytest.raises(RuntimeError, match="not connected"):
        await source.get_skills(_source_context())


async def test_skills_source_uses_connected_session(monkeypatch: pytest.MonkeyPatch) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    sentinel_session = AsyncMock()
    toolbox.session = sentinel_session  # type: ignore

    captured: dict[str, Callable[[], ClientSession]] = {}
    captured_kwargs: dict[str, object] = {}

    class _StubSkillsSource:
        def __init__(self, *, session_provider: Callable[[], ClientSession], **kwargs: object) -> None:
            captured["session_provider"] = session_provider
            captured_kwargs.update(kwargs)

        async def get_skills(self, context: SkillsSourceContext) -> list[str]:
            return ["skill-a"]

    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox.MCPSkillsSource", _StubSkillsSource)

    result = await _FoundryToolboxSkillsSource(toolbox).get_skills(_source_context())

    assert result == ["skill-a"]
    # The source hands MCPSkillsSource a stable adapter that resolves the toolbox's
    # current session for every identity-scoped resource read.
    provider = captured["session_provider"]
    resource_session = provider()
    assert provider() is resource_session
    first_uri = AnyUrl("skill://first")
    await resource_session.read_resource(cast(str, first_uri))
    sentinel_session.read_resource.assert_awaited_once_with(str(first_uri))

    new_session = AsyncMock()
    toolbox.session = new_session  # type: ignore
    second_uri = AnyUrl("skill://second")
    await resource_session.read_resource(cast(str, second_uri))
    new_session.read_resource.assert_awaited_once_with(str(second_uri))
    # No archive options set -> MCPSkillsSource is constructed with defaults.
    assert captured_kwargs == {}


async def test_skills_source_keeps_identity_adapter_when_high_level_client_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    sentinel_client = object()
    sentinel_session = object()
    current = {"connection": SimpleNamespace(client=sentinel_client, session=sentinel_session)}
    monkeypatch.setattr(toolbox, "_require_connection", lambda: current["connection"])

    captured: dict[str, Callable[[], object]] = {}

    class _StubSkillsSource:
        def __init__(self, *, session_provider: Callable[[], object]) -> None:
            captured["session_provider"] = session_provider

        async def get_skills(self, context: SkillsSourceContext) -> list[str]:
            return ["skill-a"]

    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox.MCPSkillsSource", _StubSkillsSource)

    result = await _FoundryToolboxSkillsSource(toolbox).get_skills(_source_context())

    assert result == ["skill-a"]
    provider = captured["session_provider"]
    resource_session = provider()
    assert resource_session is not sentinel_client
    assert provider() is resource_session

    replacement_client = object()
    current["connection"] = SimpleNamespace(client=replacement_client, session=object())
    assert provider() is resource_session


async def test_skills_source_forwards_archive_options(monkeypatch: pytest.MonkeyPatch) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    toolbox.session = object()  # type: ignore

    captured: dict[str, object] = {}

    class _StubSkillsSource:
        def __init__(self, *, session_provider: object, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        async def get_skills(self, context: SkillsSourceContext) -> list[str]:
            return []

    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox.MCPSkillsSource", _StubSkillsSource)

    source = _FoundryToolboxSkillsSource(
        toolbox,
        archive_options={"archive_resource_search_depth": 3, "archive_max_file_count": 5},
    )
    await source.get_skills(_source_context())

    # Only the explicitly-set archive options are forwarded to MCPSkillsSource.
    assert captured["kwargs"] == {"archive_resource_search_depth": 3, "archive_max_file_count": 5}


async def test_skills_source_requires_connection_via_provider() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    toolbox.session = object()  # type: ignore
    source = _FoundryToolboxSkillsSource(toolbox)
    resource_session = source._resource_session_provider()
    # A cached skill can retain the adapter across reconnects; if the Toolbox is
    # actually closed, the read still surfaces the same clear error.
    toolbox.session = None
    with pytest.raises(RuntimeError, match="not connected"):
        await resource_session.read_resource(cast(str, AnyUrl("skill://closed")))


class _FakeSkill:
    """Minimal stand-in for a :class:`~agent_framework.Skill` for caching tests."""

    def __init__(self, name: str) -> None:
        self.frontmatter = SimpleNamespace(name=name)


def _patch_counting_mcp_source(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch ``MCPSkillsSource`` with a stub that counts index reads.

    Returns a single-element list whose value tracks how many times
    ``get_skills`` (i.e. a ``skill://index.json`` read) has been invoked.
    """
    read_count = [0]

    class _CountingSkillsSource:
        def __init__(self, *, session_provider: object) -> None:
            self._session_provider = session_provider

        async def get_skills(self, context: SkillsSourceContext) -> list[_FakeSkill]:
            read_count[0] += 1
            return [_FakeSkill("skill-a")]

    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox.MCPSkillsSource", _CountingSkillsSource)
    return read_count


async def test_as_skills_provider_caches_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    toolbox.session = object()  # type: ignore
    read_count = _patch_counting_mcp_source(monkeypatch)

    provider = toolbox.as_skills_provider()
    context = _source_context()
    for _ in range(3):
        await provider._source.get_skills(context)

    # By default the toolbox index is read once and reused across agent runs.
    assert read_count[0] == 1


async def test_as_skills_provider_rebuilds_cache_when_platform_identity_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    toolbox.session = object()  # type: ignore
    read_count = _patch_counting_mcp_source(monkeypatch)
    source = toolbox.as_skills_provider()._source
    context = _source_context()

    await _run_with_request_context("CALL-A", lambda: source.get_skills(context))
    await _run_with_request_context("CALL-A", lambda: source.get_skills(context))
    await _run_with_request_context("CALL-B", lambda: source.get_skills(context))

    assert read_count[0] == 2


async def test_as_skills_provider_disable_caching_rereads_every_run(monkeypatch: pytest.MonkeyPatch) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    toolbox.session = object()  # type: ignore
    read_count = _patch_counting_mcp_source(monkeypatch)

    provider = toolbox.as_skills_provider(disable_caching=True)
    context = _source_context()
    for _ in range(3):
        await provider._source.get_skills(context)

    # With caching disabled the index is re-read on every agent run.
    assert read_count[0] == 3


async def test_as_skills_provider_cache_refresh_interval_rereads_after_staleness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    toolbox.session = object()  # type: ignore
    read_count = _patch_counting_mcp_source(monkeypatch)

    # A zero interval makes every cached result immediately stale, so each run
    # re-reads the index -- proving cache_refresh_interval is wired through.
    provider = toolbox.as_skills_provider(cache_refresh_interval=timedelta(0))
    context = _source_context()
    for _ in range(3):
        await provider._source.get_skills(context)

    assert read_count[0] == 3


def test_as_skills_provider_forwards_only_set_archive_options() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    # Unset archive kwargs are not forwarded (fall back to MCPSkillsSource defaults);
    # set ones are collected for forwarding. ``disable_caching=True`` keeps ``_source``
    # the bare ``_FoundryToolboxSkillsSource`` (no caching/dedup decorators wrapping it).
    default_source = cast(
        _FoundryToolboxSkillsSource,
        toolbox.as_skills_provider(disable_caching=True)._source,  # pyright: ignore[reportPrivateUsage]
    )
    assert default_source._archive_options == {}  # pyright: ignore[reportPrivateUsage]

    source = cast(
        _FoundryToolboxSkillsSource,
        toolbox.as_skills_provider(
            disable_caching=True,
            archive_max_size_bytes=2048,
            archive_resource_search_depth=1,
        )._source,  # pyright: ignore[reportPrivateUsage]
    )
    assert source._archive_options == {  # pyright: ignore[reportPrivateUsage]
        "archive_max_size_bytes": 2048,
        "archive_resource_search_depth": 1,
    }


class TestFoundryToolboxReconnection:
    async def test_close_preserves_credential_for_reconnection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After close(), get_mcp_client() should recreate an authenticated client."""
        cred = _FakeCredential("reconnect-token")
        toolbox = FoundryToolbox(
            cred,  # type: ignore
            url="https://h/toolboxes/recon/mcp",
            timeout=60.0,
        )

        assert toolbox._credential is cred
        assert toolbox._token_scope == "https://ai.azure.com/.default"
        assert toolbox._timeout == 60.0

        assert toolbox._httpx_client is not None
        assert isinstance(toolbox._httpx_client.auth, _ToolboxAuth)
        original_auth = toolbox._httpx_client.auth

        client = toolbox._httpx_client
        aclose = AsyncMock()
        monkeypatch.setattr(client, "aclose", aclose)
        await toolbox.close()

        aclose.assert_awaited_once()
        assert toolbox._httpx_client is None

        assert toolbox._credential is cred
        assert toolbox._timeout == 60.0

        ctx_manager = toolbox.get_mcp_client()
        assert toolbox._httpx_client is not None
        assert isinstance(toolbox._httpx_client.auth, _ToolboxAuth)

        new_auth = toolbox._httpx_client.auth
        assert new_auth is not original_auth
        assert new_auth._credential is cred

        assert hasattr(ctx_manager, "__aenter__")
        assert hasattr(ctx_manager, "__aexit__")

        await toolbox.close()

    async def test_close_idempotent_with_reconnection(self) -> None:
        """Multiple close() calls don't break reconnection."""
        cred = _FakeCredential()
        toolbox = FoundryToolbox(
            cred,  # type: ignore
            url="https://h/toolboxes/idem/mcp",
        )

        await toolbox.close()
        await toolbox.close()

        toolbox.get_mcp_client()
        assert toolbox._httpx_client is not None
        assert isinstance(toolbox._httpx_client.auth, _ToolboxAuth)

        await toolbox.close()


@pytest.mark.parametrize("prefix", [None, "guarded"])
@pytest.mark.parametrize(
    ("approval", "expected"),
    [
        ("always", "always_require"),
        ("never", "never_require"),
        ({"always": {"tool_names": ["microsoft_docs_search"]}}, "always_require"),
        ({"never": {"tool_names": ["microsoft_docs_search"]}}, "never_require"),
        ({"never": {"tool_names": ["learn___microsoft_docs_search"]}}, "never_require"),
        ({"never": {"tool_names": ["guarded_learn___microsoft_docs_search"]}}, "always_require"),
        ({"never": {"tool_names": ["other"]}}, "always_require"),
        ({"always": {"tool_names": ["other"]}}, "always_require"),
        ({"never": {"tool_names": []}}, "always_require"),
        ({"never": {}}, "never_require"),
        ({"always": {}, "never": {}}, "always_require"),
        (
            {"always": {"tool_names": ["microsoft_docs_search"]}, "never": {"tool_names": ["microsoft_docs_search"]}},
            "always_require",
        ),
    ],
)
async def test_discovered_tool_honors_metadata(approval: Any, expected: str, prefix: str | None) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(approval)]
    async with toolbox_connection(server, tool_name_prefix=prefix) as toolbox:
        assert toolbox.functions[0].approval_mode == expected


@pytest.mark.parametrize("read_only", [None, False, True])
@pytest.mark.parametrize("filter_read_only", [False, True])
@pytest.mark.parametrize("names", [None, ["microsoft_docs_search"], ["other"]])
async def test_metadata_filters_match_names_and_read_only(
    read_only: bool | None, filter_read_only: bool, names: list[str] | None
) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool({"never": {"read_only": filter_read_only, "tool_names": names}}, read_only=read_only)]
    async with toolbox_connection(server) as toolbox:
        matches = (names is None or names == ["microsoft_docs_search"]) and filter_read_only == (read_only is True)
        assert toolbox.functions[0].approval_mode == ("never_require" if matches else "always_require")


@pytest.mark.parametrize("metadata_policy", ["always", "never", None])
@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("never_require", "never_require"),
        ("always_require", "always_require"),
        ({"always_require_approval": ["learn___microsoft_docs_search"]}, "always_require"),
        (
            {"never_require_approval": ["guarded_learn___microsoft_docs_search"], "default": "always_require"},
            "never_require",
        ),
        ({"default": "never_require"}, "never_require"),
        ({}, "never_require"),
    ],
)
async def test_explicit_caller_policy_replaces_metadata(policy: Any, expected: str, metadata_policy: Any) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(metadata_policy)]
    async with toolbox_connection(server, tool_name_prefix="guarded", approval_mode=policy) as toolbox:
        assert toolbox.functions[0].approval_mode == expected


@pytest.mark.parametrize("meta", [None, {}, {"tool_configuration": {}}, {"unrelated": "always"}])
@pytest.mark.parametrize("default_mode", ["never_require", "always_require"])
async def test_missing_approval_metadata_preserves_default(
    meta: Any, default_mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox._DEFAULT_APPROVAL_MODE", default_mode)
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool()]
    server.tools[0]["_meta"] = meta
    server.prompts = [{"name": "summarize"}]
    async with toolbox_connection(server, load_prompts=True) as toolbox:
        assert len(toolbox.functions) == 2
        assert {function.approval_mode for function in toolbox.functions} == {default_mode}


async def test_explicit_none_approval_mode_selects_toolbox_metadata_policy() -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool("always")]
    async with toolbox_connection(server, approval_mode=None) as toolbox:
        assert toolbox.functions[0].approval_mode == "always_require"


@pytest.mark.parametrize(
    "approval",
    [
        None,
        False,
        1,
        [],
        "",
        "ALWAYS",
        "unknown",
        {},
        {"unexpected": {}},
        {"never": None},
        {"never": []},
        {"never": {"tool_names": "microsoft_docs_search"}},
        {"never": {"tool_names": [1]}},
        {"never": {"tool_names": [""]}},
        {"never": {"read_only": "true"}},
        {"never": {"unknown": True}},
        {"always": {}, "never": {"tool_names": False}},
    ],
)
async def test_malformed_approval_fails_discovery(approval: Any) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(approval)]
    async with toolbox_connection(server, connect=False) as toolbox:
        with pytest.raises(ToolExecutionException, match="Foundry Toolbox"):
            await toolbox.connect()
        assert toolbox.functions == []
        assert server.calls == []


@pytest.mark.parametrize("configuration", [None, [], "never", False])
async def test_malformed_tool_configuration_fails_discovery(configuration: Any) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool()]
    server.tools[0]["_meta"]["tool_configuration"] = configuration
    async with toolbox_connection(server, connect=False) as toolbox:
        with pytest.raises(ToolExecutionException, match="tool_configuration"):
            await toolbox.connect()


async def test_ordinary_mcp_does_not_interpret_foundry_metadata_or_replace_custom_approval() -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool()]
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as transport,
        MCPStreamableHTTPTool(
            name="ordinary", url="https://toolbox.invalid/mcp", http_client=transport, approval_mode=None
        ) as toolbox,
    ):
        function = toolbox.functions[0]
        assert function.approval_mode == "never_require"
        function.approval_mode = "always_require"
        await toolbox.load_tools()
        assert toolbox.functions[0] is function
        assert function.approval_mode == "always_require"


async def test_metadata_refresh_is_atomic_and_updates_retained_functions() -> None:
    server = ToolboxApprovalServer()
    server.page_size = 1
    server.tools = [toolbox_tool("never")]
    async with toolbox_connection(server) as toolbox:
        function = toolbox.functions[0]
        server.tools = [toolbox_tool("always"), toolbox_tool(None, name="learn___invalid")]
        with pytest.raises(ToolExecutionException, match="require_approval"):
            await toolbox.load_tools()
        assert toolbox.functions == [function]
        assert function.approval_mode == "never_require"
        server.tools = [toolbox_tool("always")]
        await toolbox.load_tools()
        assert toolbox.functions[0] is function
        assert function.approval_mode == "always_require"
        server.tools = [toolbox_tool("never")]
        await toolbox.connect(reset=True)
        assert toolbox.functions[0].approval_mode == "never_require"
        assert server.initializations == 2
        del server.tools[0]["_meta"]
        await toolbox.load_tools()
        assert toolbox.functions[0].approval_mode == "never_require"


@pytest.mark.parametrize(
    ("initial_policy", "refreshed_policy"),
    [("always", "never"), ("never", "always")],
)
async def test_reconnect_restores_approval_modes_when_prompt_discovery_fails(
    initial_policy: str, refreshed_policy: str
) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(initial_policy)]
    server.prompts = [{"name": "summarize"}]
    async with toolbox_connection(server, load_prompts=True) as toolbox:
        functions = list(toolbox.functions)
        original_modes = [function.approval_mode for function in functions]
        server.tools = [toolbox_tool(refreshed_policy)]
        server.prompts = [{"name": "summarize", "arguments": "invalid"}]

        with pytest.raises(ValueError, match="arguments"):
            await toolbox.connect(reset=True)

        assert server.initializations == 2
        assert not toolbox.is_connected
        assert all(current is previous for current, previous in zip(toolbox.functions, functions, strict=True))
        assert [function.approval_mode for function in toolbox.functions] == original_modes

        server.prompts = [{"name": "summarize"}]
        await toolbox.connect()
        assert toolbox.functions[0] is functions[0]
        assert toolbox.functions[0].approval_mode == f"{refreshed_policy}_require"


async def test_reconnect_restores_progressive_tools_when_prompt_discovery_fails() -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(name="learn___removed"), toolbox_tool(name="learn___kept")]
    server.prompts = [{"name": "summarize"}]
    async with toolbox_connection(server, load_prompts=True, use_progressive_disclosure=True) as toolbox:
        loader = next(function for function in toolbox.functions if function.name == "load_tool")
        arguments = {"tool": ["learn___removed", "learn___kept"]}
        context = FunctionInvocationContext(function=loader, arguments=arguments, tools=list(toolbox.functions))
        await loader.invoke(arguments=arguments, context=context)
        functions = list(toolbox.functions)
        assert {function.name for function in functions} >= {"learn___removed", "learn___kept"}

        server.tools = [toolbox_tool(name="learn___kept")]
        server.prompts = [{"name": "summarize", "arguments": "invalid"}]
        with pytest.raises(ValueError, match="arguments"):
            await toolbox.connect(reset=True)

        assert server.initializations == 2
        assert not toolbox.is_connected
        assert all(current is previous for current, previous in zip(toolbox.functions, functions, strict=True))
        assert toolbox._progressive_loaded_tool_names == {"learn___removed", "learn___kept"}

        server.prompts = [{"name": "summarize"}]
        await toolbox.connect()
        names = {function.name for function in toolbox.functions}
        assert "learn___kept" in names
        assert "learn___removed" not in names
        assert toolbox._progressive_loaded_tool_names == {"learn___kept"}


async def test_each_tool_uses_its_own_metadata_and_exact_server_prefix() -> None:
    server = ToolboxApprovalServer()
    server.tools = [
        toolbox_tool("always", name="learn___guarded"),
        toolbox_tool("never", name="learn___safe"),
        toolbox_tool({"never": {"tool_names": ["safe"]}}, name="other___safe"),
        toolbox_tool({"never": {"tool_names": ["learn___safe"]}}, name="learn___learn___safe"),
    ]
    async with toolbox_connection(
        server, tool_name_prefix="local", allowed_tools=["learn___guarded", "learn___safe"]
    ) as toolbox:
        assert {function.name: function.approval_mode for function in toolbox.functions} == {
            "local_learn___guarded": "always_require",
            "local_learn___safe": "never_require",
        }
        toolbox.allowed_tools = None
        assert {function.name: function.approval_mode for function in toolbox.functions} == {
            "local_learn___guarded": "always_require",
            "local_learn___safe": "never_require",
            "local_other___safe": "always_require",
            "local_learn___learn___safe": "never_require",
        }


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("approved", [False, True])
async def test_metadata_approval_pauses_and_resumes_once(stream: bool, approved: bool) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool()]
    client = ToolboxApprovalClient("guarded_learn___microsoft_docs_search")
    async with toolbox_connection(server, tool_name_prefix="guarded") as toolbox:
        agent = Agent(client=client, tools=toolbox)
        session = agent.create_session()
        if stream:
            paused_stream = agent.run("Search the docs", session=session, stream=True)
            paused_updates = [update async for update in paused_stream]
            paused = await paused_stream.get_final_response()
            assert any(
                content.type == "function_approval_request" for update in paused_updates for content in update.contents
            )
        else:
            paused = await agent.run("Search the docs", session=session)
        approvals = [
            content
            for message in paused.messages
            for content in message.contents
            if content.type == "function_approval_request"
        ]
        assert len(approvals) == 1
        assert not any(content.type == "function_result" for message in paused.messages for content in message.contents)
        assert server.calls == []
        assert len(client.calls) == 1
        decision = Message("user", [approvals[0].to_function_approval_response(approved=approved)])
        if stream:
            resumed_stream = agent.run(decision, session=session, stream=True)
            resumed_updates = [update async for update in resumed_stream]
            resumed = await resumed_stream.get_final_response()
            assert any(content.type == "function_result" for update in resumed_updates for content in update.contents)
        else:
            resumed = await agent.run(decision, session=session)
        assert resumed.text == "done"
        assert len(server.calls) == int(approved)
        returned = [content for message in resumed.messages for content in message.contents]
        assert sum(content.type == "function_result" for content in returned) == 1
        model_history = [content for message in client.calls[-1] for content in message.contents]
        assert sum(content.type == "function_call" for content in model_history) == 1
        assert sum(content.type == "function_result" for content in model_history) == 1
        assert not any(content.type.startswith("function_approval") for content in model_history)
        await agent.run("Continue", session=session)
        assert len(server.calls) == int(approved)


@pytest.mark.parametrize("stream", [False, True])
async def test_responses_host_returns_metadata_approval_before_tool_execution(stream: bool) -> None:
    mcp_server = ToolboxApprovalServer()
    mcp_server.tools = [toolbox_tool()]
    model = ToolboxApprovalClient("learn___microsoft_docs_search")
    async with toolbox_connection(mcp_server) as toolbox:
        host = ResponsesHostServer(agent=Agent(client=model, tools=toolbox))
        async with host_httpx.AsyncClient(
            transport=host_httpx.ASGITransport(app=host), base_url="http://test"
        ) as client:
            first = await client.post(
                "/responses", json={"model": "test-model", "input": "Search the docs", "stream": stream}
            )
            assert first.status_code == 200
            if stream:
                first_events = [
                    json.loads(line[6:])
                    for line in first.text.splitlines()
                    if line.startswith("data: ") and line != "data: [DONE]"
                ]
                first_body = next(event["response"] for event in first_events if event["type"] == "response.completed")
            else:
                first_body = first.json()
            approvals = [item for item in first_body["output"] if item["type"] == "mcp_approval_request"]
            assert len(approvals) == 1
            assert not any(item["type"] == "function_call_output" for item in first_body["output"])
            assert mcp_server.calls == []
            second = await client.post(
                "/responses",
                json={
                    "model": "test-model",
                    "input": [
                        {"type": "mcp_approval_response", "approval_request_id": approvals[0]["id"], "approve": True}
                    ],
                    "previous_response_id": first_body["id"],
                    "stream": stream,
                },
            )
            assert second.status_code == 200
            if stream:
                second_events = [
                    json.loads(line[6:])
                    for line in second.text.splitlines()
                    if line.startswith("data: ") and line != "data: [DONE]"
                ]
                second_body = next(
                    event["response"] for event in second_events if event["type"] == "response.completed"
                )
            else:
                second_body = second.json()
            assert sum(item["type"] == "function_call_output" for item in second_body["output"]) == 1
            assert len(mcp_server.calls) == 1


async def test_callable_approval_policy_is_composable_without_a_subclass() -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool()]
    server.prompts = [{"name": "summarize", "description": "Summarize the result"}]
    policy = Mock(return_value="always_require")
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as transport,
        MCPStreamableHTTPTool(
            name="ordinary",
            url="https://toolbox.invalid/mcp",
            http_client=transport,
            tool_name_prefix="local",
            approval_mode=policy,
        ) as toolbox,
    ):
        assert {function.approval_mode for function in toolbox.functions} == {"always_require"}
        items = [call.args[0] for call in policy.call_args_list]
        assert len(items) == 2
        assert any(isinstance(item, Tool) and item.name == "learn___microsoft_docs_search" for item in items)
        assert any(isinstance(item, Prompt) and item.name == "summarize" for item in items)
        functions = list(toolbox.functions)
        policy.return_value = "never_require"
        await toolbox.load_tools()
        await toolbox.load_prompts()
        assert toolbox.functions == functions
        assert all(current is previous for current, previous in zip(toolbox.functions, functions, strict=True))
        assert {function.approval_mode for function in toolbox.functions} == {"never_require"}
        assert policy.call_count == 4


@pytest.mark.parametrize("kind", ["tool", "prompt"])
async def test_callable_approval_requires_an_explicit_initial_decision(kind: str) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool()]
    server.prompts = [{"name": "summarize"}]
    with pytest.raises(ToolExecutionException, match="'always_require' or 'never_require'"):
        async with toolbox_connection(
            server,
            approval_mode=Mock(return_value=None),
            load_tools=kind == "tool",
            load_prompts=kind == "prompt",
        ):
            pytest.fail("A callback without an explicit decision must fail discovery.")


@pytest.mark.parametrize("kind", ["tool", "prompt"])
@pytest.mark.parametrize("invalid", [None, "always", "", True, False, 1, [], {}])
async def test_callable_approval_rejects_invalid_results_atomically(kind: str, invalid: Any) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(), toolbox_tool(name="learn___second")]
    server.prompts = [{"name": "summarize"}, {"name": "translate"}]
    policy = Mock(return_value="always_require")
    async with toolbox_connection(server, approval_mode=policy, load_prompts=True) as toolbox:
        functions = list(toolbox.functions)
        policy.side_effect = ["never_require", invalid]
        with pytest.raises(ToolExecutionException, match="approval_mode callable"):
            await (toolbox.load_tools() if kind == "tool" else toolbox.load_prompts())
        assert all(current is previous for current, previous in zip(toolbox.functions, functions, strict=True))
        assert {function.approval_mode for function in toolbox.functions} == {"always_require"}


@pytest.mark.parametrize("kind", ["tool", "prompt"])
async def test_callable_approval_errors_preserve_previous_snapshot(kind: str) -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool(), toolbox_tool(name="learn___second")]
    server.prompts = [{"name": "summarize"}, {"name": "translate"}]
    policy = Mock(return_value="never_require")
    async with toolbox_connection(server, approval_mode=policy, load_prompts=True) as toolbox:
        functions = list(toolbox.functions)
        policy.side_effect = ["always_require", ValueError("policy failed")]
        with pytest.raises(ValueError, match="policy failed"):
            await (toolbox.load_tools() if kind == "tool" else toolbox.load_prompts())
        assert toolbox.functions == functions
        assert {function.approval_mode for function in toolbox.functions} == {"never_require"}


async def test_caller_can_wrap_the_foundry_metadata_policy() -> None:
    server = ToolboxApprovalServer()
    server.tools = [toolbox_tool("never")]
    server.prompts = [{"name": "summarize"}]
    async with toolbox_connection(server, load_prompts=True) as toolbox:
        assert {function.approval_mode for function in toolbox.functions} == {"never_require"}
        metadata_policy = toolbox.approval_mode
        assert callable(metadata_policy)
        caller_policy = Mock(side_effect=metadata_policy)
        toolbox.approval_mode = caller_policy
        await toolbox.load_tools()
        assert toolbox.functions[0].approval_mode == "never_require"
        caller_policy.side_effect = None
        caller_policy.return_value = "always_require"
        await toolbox.load_tools()
        assert toolbox.functions[0].approval_mode == "always_require"
