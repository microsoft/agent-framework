# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for FoundryToolbox."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)

from agent_framework_foundry_hosting import FoundryToolbox
from agent_framework_foundry_hosting._toolbox import (  # pyright: ignore[reportPrivateUsage]
    _resolve_toolbox_endpoint,
    _toolbox_name_from_endpoint,
    _ToolboxAuth,
)


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


def test_init_rejects_http_client() -> None:
    with pytest.raises(TypeError, match="http_client"):
        FoundryToolbox(
            _FakeCredential(),  # type: ignore[arg-type]
            url="https://h/toolboxes/tb/mcp",
            http_client=httpx.AsyncClient(),
        )


def test_init_derives_name_and_defaults() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore[arg-type]
        url="https://h/toolboxes/sales/mcp?api-version=v1",
    )
    assert toolbox.name == "sales"
    assert toolbox.url == "https://h/toolboxes/sales/mcp?api-version=v1"
    # Toolboxes expose tools, not prompts.
    assert toolbox.load_prompts_flag is False


def test_auth_flow_injects_bearer_token() -> None:
    cred = _FakeCredential("abc123")
    auth = _ToolboxAuth(cred, "https://ai.azure.com/.default")
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    flow = auth.auth_flow(request)
    prepared = next(flow)

    assert prepared.headers["Authorization"] == "Bearer abc123"
    assert cred.scopes == ["https://ai.azure.com/.default"]


def test_auth_flow_forwards_call_id_when_present() -> None:
    auth = _ToolboxAuth(_FakeCredential(), "scope")
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    token = set_request_context(FoundryAgentRequestContext(call_id="call-xyz"))
    try:
        prepared = next(auth.auth_flow(request))
    finally:
        reset_request_context(token)

    assert prepared.headers["x-agent-foundry-call-id"] == "call-xyz"


def test_auth_flow_omits_call_id_when_absent() -> None:
    auth = _ToolboxAuth(_FakeCredential(), "scope")
    request = httpx.Request("POST", "https://h/toolboxes/tb/mcp")

    prepared = next(auth.auth_flow(request))

    assert "x-agent-foundry-call-id" not in prepared.headers


async def test_close_closes_owned_http_client() -> None:
    toolbox = FoundryToolbox(
        _FakeCredential(),  # type: ignore[arg-type]
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
