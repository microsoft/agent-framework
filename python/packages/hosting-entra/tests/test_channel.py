# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :mod:`agent_framework_hosting_entra`.

The MSAL ``ConfidentialClientApplication`` and Microsoft Graph calls are
mocked out so no network access is required. Live OAuth, certificate auth,
and full webhook flow are out of scope here.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from agent_framework_hosting_entra import (
    EntraIdentityLinkChannel,
    EntraIdentityStore,
    entra_isolation_key,
)


def test_entra_isolation_key_format() -> None:
    assert entra_isolation_key("abc123") == "entra:abc123"


class TestEntraIdentityStore:
    @pytest.mark.asyncio
    async def test_link_writes_entra_namespaced_value(self, tmp_path: Path) -> None:
        store = EntraIdentityStore(tmp_path / "links.json")
        await store.link("telegram:42", "oid-xyz")
        assert store.lookup("telegram:42") == "entra:oid-xyz"
        # Persisted to disk.
        saved = json.loads((tmp_path / "links.json").read_text())
        assert saved == {"telegram:42": "entra:oid-xyz"}

    @pytest.mark.asyncio
    async def test_unlink_removes_entry(self, tmp_path: Path) -> None:
        store = EntraIdentityStore(tmp_path / "links.json")
        await store.link("telegram:42", "oid")
        await store.unlink("telegram:42")
        assert store.lookup("telegram:42") is None
        assert json.loads((tmp_path / "links.json").read_text()) == {}

    @pytest.mark.asyncio
    async def test_unlink_unknown_is_noop(self, tmp_path: Path) -> None:
        store = EntraIdentityStore(tmp_path / "links.json")
        await store.unlink("telegram:never")  # must not raise
        assert not (tmp_path / "links.json").exists()

    def test_loads_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "links.json"
        path.write_text(json.dumps({"telegram:1": "entra:abc"}))
        store = EntraIdentityStore(path)
        assert store.lookup("telegram:1") == "entra:abc"

    def test_corrupt_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "links.json"
        path.write_text("not-json")
        store = EntraIdentityStore(path)
        assert store.lookup("anything") is None


class TestEntraIdentityLinkChannelConfig:
    def test_rejects_neither_credential(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            EntraIdentityLinkChannel(
                store=EntraIdentityStore(tmp_path / "x.json"),
                tenant_id="t",
                client_id="c",
                public_base_url="https://example.com",
            )

    def test_rejects_both_credentials(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            EntraIdentityLinkChannel(
                store=EntraIdentityStore(tmp_path / "x.json"),
                tenant_id="t",
                client_id="c",
                public_base_url="https://example.com",
                client_secret="s",
                certificate_path="/tmp/does-not-exist.pem",
            )

    def test_redirect_uri_strips_trailing_slash(self, tmp_path: Path) -> None:
        with patch(
            "agent_framework_hosting_entra._channel.msal.ConfidentialClientApplication",
            MagicMock(),
        ):
            ch = EntraIdentityLinkChannel(
                store=EntraIdentityStore(tmp_path / "x.json"),
                tenant_id="t",
                client_id="c",
                public_base_url="https://example.com/",
                client_secret="s",
            )
            assert ch.redirect_uri == "https://example.com/auth/callback"


class TestEntraIdentityLinkChannelRoutes:
    def _make_channel(self, tmp_path: Path, msal_app: MagicMock) -> tuple[EntraIdentityLinkChannel, EntraIdentityStore]:
        store = EntraIdentityStore(tmp_path / "links.json")
        with patch(
            "agent_framework_hosting_entra._channel.msal.ConfidentialClientApplication",
            return_value=msal_app,
        ):
            ch = EntraIdentityLinkChannel(
                store=store,
                tenant_id="tenant-1",
                client_id="client-1",
                public_base_url="https://example.com",
                client_secret="s",
            )
        return ch, store

    def _mount_app(self, ch: EntraIdentityLinkChannel) -> Starlette:
        # We don't depend on AgentFrameworkHost here — wire the routes
        # directly so we can exercise the channel in isolation.
        from starlette.routing import Mount

        contribution = ch.contribute(MagicMock())
        return Starlette(routes=[Mount(ch.path, routes=contribution.routes)])

    def test_start_missing_params_returns_400(self, tmp_path: Path) -> None:
        msal_app = MagicMock()
        ch, _ = self._make_channel(tmp_path, msal_app)
        with TestClient(self._mount_app(ch)) as client:
            r = client.get("/auth/start", follow_redirects=False)
        assert r.status_code == 400

    def test_start_redirects_to_authorize_url(self, tmp_path: Path) -> None:
        msal_app = MagicMock()
        msal_app.get_authorization_request_url.return_value = (
            "https://login.microsoftonline.com/tenant-1/oauth2/v2.0/authorize?state=X"
        )
        ch, _ = self._make_channel(tmp_path, msal_app)
        with TestClient(self._mount_app(ch)) as client:
            r = client.get(
                "/auth/start",
                params={"channel": "telegram", "id": "42"},
                follow_redirects=False,
            )
        assert r.status_code == 302
        assert "login.microsoftonline.com" in r.headers["location"]

    def test_callback_invalid_state_returns_400(self, tmp_path: Path) -> None:
        msal_app = MagicMock()
        ch, _ = self._make_channel(tmp_path, msal_app)
        ch._http = MagicMock(aclose=AsyncMock())
        with TestClient(self._mount_app(ch)) as client:
            r = client.get("/auth/callback", params={"code": "c", "state": "unknown"})
        assert r.status_code == 400

    def test_callback_links_oid_on_success(self, tmp_path: Path) -> None:
        msal_app = MagicMock()
        msal_app.get_authorization_request_url.return_value = (
            "https://login.microsoftonline.com/tenant-1/authorize?state=X"
        )
        msal_app.acquire_token_by_authorization_code.return_value = {"access_token": "t"}
        ch, store = self._make_channel(tmp_path, msal_app)

        # Fake the Graph /me call.
        graph_response = MagicMock()
        graph_response.status_code = 200
        graph_response.json = MagicMock(return_value={"id": "oid-xyz", "userPrincipalName": "user@x"})
        ch._http = MagicMock()
        ch._http.get = AsyncMock(return_value=graph_response)
        ch._http.aclose = AsyncMock()

        # Mint a real state via the public API so the pending dict is populated.
        ch.authorize_url_for("telegram", "42")
        state = next(iter(ch._pending.keys()))

        with TestClient(self._mount_app(ch)) as client:
            r = client.get("/auth/callback", params={"code": "abc", "state": state})
        assert r.status_code == 200
        assert store.lookup("telegram:42") == "entra:oid-xyz"

    def test_callback_token_failure_returns_502(self, tmp_path: Path) -> None:
        msal_app = MagicMock()
        msal_app.get_authorization_request_url.return_value = "https://x"
        msal_app.acquire_token_by_authorization_code.return_value = {
            "error": "invalid_grant",
            "error_description": "expired",
        }
        ch, store = self._make_channel(tmp_path, msal_app)
        ch._http = MagicMock(aclose=AsyncMock())
        ch.authorize_url_for("telegram", "42")
        state = next(iter(ch._pending.keys()))
        with TestClient(self._mount_app(ch)) as client:
            r = client.get("/auth/callback", params={"code": "c", "state": state})
        assert r.status_code == 502
        assert store.lookup("telegram:42") is None
