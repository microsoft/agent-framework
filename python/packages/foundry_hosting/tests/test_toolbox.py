# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

"""Unit tests for FoundryToolbox."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from agent_framework import SkillsProvider, SkillsSourceContext, SupportsAgentRun
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)

from agent_framework_foundry_hosting import FoundryToolbox
from agent_framework_foundry_hosting._toolbox import (  # pyright: ignore[reportPrivateUsage]
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


def test_auth_flow_injects_bearer_token() -> None:
    cred = _FakeCredential("abc123")
    auth = _ToolboxAuth(cred, "https://ai.azure.com/.default")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    flow = auth.auth_flow(request)
    prepared = next(flow)

    assert prepared.headers["Authorization"] == "Bearer abc123"
    assert cred.scopes == ["https://ai.azure.com/.default"]


def test_auth_flow_forwards_call_id_when_present() -> None:
    auth = _ToolboxAuth(_FakeCredential(), "scope")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    token = set_request_context(FoundryAgentRequestContext(call_id="call-xyz"))
    try:
        prepared = next(auth.auth_flow(request))
    finally:
        reset_request_context(token)

    assert prepared.headers["x-agent-foundry-call-id"] == "call-xyz"


def test_auth_flow_omits_call_id_when_absent() -> None:
    auth = _ToolboxAuth(_FakeCredential(), "scope")  # type: ignore
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = next(auth.auth_flow(request))

    assert "x-agent-foundry-call-id" not in prepared.headers


async def test_close_closes_owned_http_client() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore
        url="https://h/toolboxes/tb/mcp",
    )
    client = toolbox._httpx_client  # pyright: ignore[reportPrivateUsage]
    assert client is not None
    client.aclose = AsyncMock()  # type: ignore[method-assign]

    await toolbox.close()

    client.aclose.assert_awaited_once()
    # Idempotent: a second close does not re-close the client.
    await toolbox.close()
    client.aclose.assert_awaited_once()


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
    assert provider._disable_load_skill_approval is False  # pyright: ignore[reportPrivateUsage]
    assert provider._disable_read_skill_resource_approval is False  # pyright: ignore[reportPrivateUsage]
    assert provider._disable_run_skill_script_approval is False  # pyright: ignore[reportPrivateUsage]


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
    assert provider._disable_load_skill_approval is True  # pyright: ignore[reportPrivateUsage]
    assert provider._disable_read_skill_resource_approval is True  # pyright: ignore[reportPrivateUsage]
    assert provider._disable_run_skill_script_approval is True  # pyright: ignore[reportPrivateUsage]


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
    sentinel_session = object()
    toolbox.session = sentinel_session  # type: ignore

    captured: dict[str, object] = {}

    class _StubSkillsSource:
        def __init__(self, *, client: object) -> None:
            captured["client"] = client

        async def get_skills(self, context: SkillsSourceContext) -> list[str]:
            return ["skill-a"]

    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox.MCPSkillsSource", _StubSkillsSource)

    result = await _FoundryToolboxSkillsSource(toolbox).get_skills(_source_context())

    assert result == ["skill-a"]
    assert captured["client"] is sentinel_session


class TestFoundryToolboxReconnection:
    async def test_close_preserves_credential_for_reconnection(self) -> None:
        """After close(), get_mcp_client() should recreate an authenticated client."""
        cred = _FakeCredential("reconnect-token")
        toolbox = FoundryToolbox(
            cred,
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
        client.aclose = AsyncMock()
        await toolbox.close()

        client.aclose.assert_awaited_once()
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
            cred,
            url="https://h/toolboxes/idem/mcp",
        )

        await toolbox.close()
        await toolbox.close()

        toolbox.get_mcp_client()
        assert toolbox._httpx_client is not None
        assert isinstance(toolbox._httpx_client.auth, _ToolboxAuth)

        await toolbox.close()
