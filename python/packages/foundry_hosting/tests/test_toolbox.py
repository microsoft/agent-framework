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
from unittest.mock import AsyncMock, patch

import httpx2 as httpx
import pytest
from agent_framework import MCPStreamableHTTPTool, SkillsProvider, SkillsSourceContext, SupportsAgentRun
from agent_framework.exceptions import ToolException, ToolExecutionException
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)
from mcp.client.session import ClientSession
from pydantic import AnyUrl

from agent_framework_foundry_hosting import FoundryToolbox
from agent_framework_foundry_hosting._feature_usage import FeatureIndex
from agent_framework_foundry_hosting._toolbox import (
    _FoundryToolboxSkillsSource,
    _resolve_toolbox_endpoint,
    _toolbox_name_from_endpoint,
    _ToolboxAuth,
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

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)

        self.requests.append(request)
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
                "capabilities": {"tools": {}, "resources": {}},
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
    await resource_session.read_resource(first_uri)
    sentinel_session.read_resource.assert_awaited_once_with(first_uri)

    new_session = AsyncMock()
    toolbox.session = new_session  # type: ignore
    second_uri = AnyUrl("skill://second")
    await resource_session.read_resource(second_uri)
    new_session.read_resource.assert_awaited_once_with(second_uri)
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
        await resource_session.read_resource(AnyUrl("skill://closed"))


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
