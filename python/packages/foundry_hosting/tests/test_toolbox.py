# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for FoundryToolbox."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
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

    captured: dict[str, Callable[[], object]] = {}
    captured_kwargs: dict[str, object] = {}

    class _StubSkillsSource:
        def __init__(self, *, session_provider: Callable[[], object], **kwargs: object) -> None:
            captured["session_provider"] = session_provider
            captured_kwargs.update(kwargs)

        async def get_skills(self, context: SkillsSourceContext) -> list[str]:
            return ["skill-a"]

    monkeypatch.setattr("agent_framework_foundry_hosting._toolbox.MCPSkillsSource", _StubSkillsSource)

    result = await _FoundryToolboxSkillsSource(toolbox).get_skills(_source_context())

    assert result == ["skill-a"]
    # The source hands MCPSkillsSource a provider (not a fixed session) that resolves
    # the toolbox's current session, so it survives a reconnect that swaps it.
    provider = captured["session_provider"]
    assert provider() is sentinel_session
    new_session = object()
    toolbox.session = new_session  # type: ignore
    assert provider() is new_session
    # No archive options set -> MCPSkillsSource is constructed with defaults.
    assert captured_kwargs == {}


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
    # Discovery captures the bound provider; a later reconnect gap (session is None)
    # surfaces the same clear error when the provider is resolved.
    toolbox.session = None  # type: ignore
    with pytest.raises(RuntimeError, match="not connected"):
        source._require_session()  # pyright: ignore[reportPrivateUsage]


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
        await provider._source.get_skills(context)  # pyright: ignore[reportPrivateUsage]

    # By default the toolbox index is read once and reused across agent runs.
    assert read_count[0] == 1


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
        await provider._source.get_skills(context)  # pyright: ignore[reportPrivateUsage]

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
        await provider._source.get_skills(context)  # pyright: ignore[reportPrivateUsage]

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
