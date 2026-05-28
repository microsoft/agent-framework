# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Entra (Azure AD) identity-linking sidecar channel.

Implements the OAuth 2.0 Authorization Code flow against Entra so users on
non-Entra channels (Telegram, Responses callers without a verified token,
etc.) can bind their per-channel id to a stable ``entra:<oid>`` isolation
key. Once the link is established, channel run-hooks can call
:meth:`EntraIdentityStore.lookup` and rewrite the request to use the Entra
key instead of the channel-native id.

Two credential modes are supported:

* ``client_secret`` — confidential-client secret.
* ``certificate_path`` — PEM bundle (private key + cert) for tenants that
  disallow secrets. The Teams channel uses the same PEM layout; see
  :mod:`agent_framework_hosting_teams` for the openssl recipe.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import msal
from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    logger,
)
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route


def entra_isolation_key(oid: str) -> str:
    """Canonical isolation key for a user identified by Entra object id."""
    return f"entra:{oid}"


class EntraIdentityStore:
    """Tiny JSON-backed mapping ``<channel>:<channel_id> → entra:<oid>``.

    Production deployments should swap this for a real KV store. Single-file
    JSON is fine for samples because writes are infrequent (only during the
    OAuth callback) and we serialize them under an asyncio lock.
    """

    def __init__(self, path: Path) -> None:
        """Open an identity store backed by ``path``.

        Loads any existing JSON document; an unreadable or corrupt file is
        logged and replaced with an empty in-memory map so callers always
        get a usable store.
        """
        self._path = path
        self._lock = asyncio.Lock()
        self._data: dict[str, str] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except Exception:
                logger.exception("identity store load failed; starting empty")

    def lookup(self, channel_key: str) -> str | None:
        """Return the linked ``entra:<oid>`` key for a per-channel id, or ``None``."""
        return self._data.get(channel_key)

    async def link(self, channel_key: str, oid: str) -> None:
        """Bind ``channel_key`` (e.g. ``telegram:123``) to the Entra ``oid`` and persist.

        Overwrites any existing mapping for ``channel_key`` and rewrites the
        backing JSON file under the lock so concurrent callers cannot race.
        """
        async with self._lock:
            self._data[channel_key] = entra_isolation_key(oid)
            self._path.write_text(json.dumps(self._data, indent=2, sort_keys=True))

    async def unlink(self, channel_key: str) -> None:
        """Remove the mapping for ``channel_key``; no-op if absent.

        The file is only rewritten when an entry actually existed so we
        don't churn disk on idempotent unlink calls.
        """
        async with self._lock:
            if self._data.pop(channel_key, None) is not None:
                self._path.write_text(json.dumps(self._data, indent=2, sort_keys=True))


@dataclass
class _PendingAuth:
    """In-memory record of an authorize redirect waiting for its OAuth callback."""

    channel: str
    channel_id: str
    expires_at: float
    return_to: str | None = None


def _link_html(body: str, *, status: int = 200) -> HTMLResponse:
    """Wrap ``body`` in a minimal HTML shell suitable for browser link UIs."""
    return HTMLResponse(
        f"<!doctype html><html><body style='font-family:system-ui;padding:2rem;max-width:40rem'>{body}</body></html>",
        status_code=status,
    )


def _load_certificate_credential(certificate_path: str | Path, certificate_password: bytes | None) -> dict[str, str]:
    """Build the ``msal`` certificate credential dict from a PEM bundle.

    Expects ``certificate_path`` to point at a single PEM containing the
    private key followed by the X.509 certificate (the layout produced by
    ``cat key.pem cert.pem > combined.pem``).
    """
    pem_bytes = Path(certificate_path).read_bytes()
    private_key = serialization.load_pem_private_key(pem_bytes, password=certificate_password)
    cert = x509.load_pem_x509_certificate(pem_bytes)

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    # SHA-1 thumbprint is required by the Entra ``client_assertion`` spec for cert auth — not a security choice.
    thumbprint = cert.fingerprint(hashes.SHA1()).hex()  # noqa: S303
    return {
        "private_key": private_key_pem,
        "thumbprint": thumbprint,
        "public_certificate": public_cert_pem,
    }


class EntraIdentityLinkChannel:
    """Sidecar Channel exposing ``GET /auth/start`` and ``GET /auth/callback``.

    Demonstrates that ``Channel`` is a general extensibility point — not just
    for chat surfaces. Owns the Entra OAuth Authorization Code flow used to
    bind a per-channel id (e.g. Telegram chat id) to the user's Entra object
    id.

    Two credential modes are supported (mutually exclusive):

    * ``client_secret`` — classic confidential-client secret.
    * ``certificate_path`` — PEM bundle (private key + certificate) for
      tenants that disallow secrets. See ``teams.py`` module docstring for
      an ``openssl`` recipe; the same PEM works here.

    Flow (OAuth 2.0 Authorization Code, confidential client):

    1. ``GET /auth/start?channel=<name>&id=<channel_id>`` mints a one-shot
       ``state`` token and 302s to the Entra ``authorize`` endpoint.
    2. User signs in; Entra calls ``GET /auth/callback?code=...&state=...``.
    3. We exchange the code for a token (via ``msal`` so secret + cert auth
       look identical at the call site), call Microsoft Graph ``/me`` to
       read ``id`` (oid), persist ``<channel>:<id> → entra:<oid>``, and
       respond with a friendly HTML page (or 302 to ``return_to``).

    Tokens never leave the host process; only the ``oid`` claim is stored.
    """

    name = "identity"
    path = "/auth"

    _AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant}"
    _GRAPH_ME = "https://graph.microsoft.com/v1.0/me"
    _PENDING_TTL_SECONDS = 600  # 10 minutes

    def __init__(
        self,
        *,
        store: EntraIdentityStore,
        tenant_id: str,
        client_id: str,
        public_base_url: str,
        client_secret: str | None = None,
        certificate_path: str | Path | None = None,
        certificate_password: bytes | None = None,
        scope: str = "openid profile User.Read",
        link_token_secret: str | None = None,
        link_token_ttl_seconds: int = 600,
    ) -> None:
        if bool(client_secret) == bool(certificate_path):
            raise ValueError("IdentityLinkChannel: pass exactly one of client_secret or certificate_path.")
        if certificate_path is not None:
            credential: str | dict[str, str] = _load_certificate_credential(certificate_path, certificate_password)
            self._auth_kind = "certificate"
        else:
            credential = client_secret  # type: ignore[assignment]
            self._auth_kind = "client_secret"

        self._store = store
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._public_base_url = public_base_url.rstrip("/")
        self._scopes = [s for s in scope.split() if s and s.lower() not in {"openid", "profile", "offline_access"}]
        # MSAL ConfidentialClientApplication is sync; we wrap blocking calls
        # in ``asyncio.to_thread`` because token endpoint calls do real I/O.
        self._msal_app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=self._AUTHORITY_TEMPLATE.format(tenant=tenant_id),
            client_credential=credential,
        )
        self._pending: dict[str, _PendingAuth] = {}
        self._http: httpx.AsyncClient | None = None
        # ``link_token_secret`` is the HMAC key that gates ``/auth/start``.
        # Without it any open-internet caller can mint a binding for an
        # arbitrary ``(channel, channel_id)`` pair and IDOR the victim's
        # isolation key (see PR review on 0026 for the threat model).
        # Optional only so dev-mode samples without the integration in
        # place don't have to scramble for a secret; unsigned mode logs
        # a loud warning at startup and wire-time.
        self._link_token_secret = link_token_secret.encode("utf-8") if link_token_secret else None
        self._link_token_ttl = link_token_ttl_seconds
        # Allowed redirect-back hosts: relative paths and same-origin only.
        # ``return_to`` from the unauthenticated /start query string is
        # otherwise an open redirect (auth-host phishing vector).
        parsed = urlparse(self._public_base_url)
        self._allowed_return_host = parsed.netloc.lower() if parsed.netloc else None

    @property
    def redirect_uri(self) -> str:
        """The fully-qualified OAuth redirect URI registered with Entra ID.

        Computed from ``public_base_url`` plus the channel's mount path so
        operators can copy it straight into the app registration's reply URLs.
        """
        return f"{self._public_base_url}{self.path}/callback"

    def contribute(self, context: "ChannelContext") -> "ChannelContribution":
        """Mount the ``/start`` and ``/callback`` routes plus lifecycle hooks."""
        return ChannelContribution(
            routes=[
                Route("/start", self._handle_start, methods=["GET"]),
                Route("/callback", self._handle_callback, methods=["GET"]),
            ],
            on_startup=[self._on_startup],
            on_shutdown=[self._on_shutdown],
        )

    async def _on_startup(self) -> None:
        """Open the shared HTTP client used for Microsoft Graph calls."""
        self._http = httpx.AsyncClient(timeout=15.0)
        if self._link_token_secret is None:
            logger.warning(
                "EntraIdentityLinkChannel running WITHOUT link_token_secret. "
                "GET /auth/start accepts unauthenticated (channel, id) pairs, "
                "which means any open-internet caller can bind their Entra "
                "account to a victim's per-channel id (IDOR on the identity "
                "store). Pass link_token_secret=<random>, mint URLs via "
                "mint_start_url(...), and gate /start in front of the "
                "channel that issues those URLs."
            )
        logger.info(
            "IdentityLinkChannel ready (auth=%s, signed_start=%s); redirect_uri=%s",
            self._auth_kind,
            self._link_token_secret is not None,
            self.redirect_uri,
        )

    async def _on_shutdown(self) -> None:
        """Close the Graph HTTP client; safe to call when never started."""
        if self._http is not None:
            await self._http.aclose()

    # -- link-token helpers ----------------------------------------------- #

    def _sign_link_token(self, channel: str, channel_id: str, expires_at: int) -> str:
        """Sign ``(channel, channel_id, expires_at)`` with HMAC-SHA256."""
        if self._link_token_secret is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("link_token_secret is required to mint link tokens")
        msg = f"{channel}|{channel_id}|{expires_at}".encode()
        return hmac.new(self._link_token_secret, msg, hashlib.sha256).hexdigest()

    def _verify_link_token(self, channel: str, channel_id: str, expires_at: int, signature: str) -> bool:
        """Constant-time verify the link-token signature and TTL."""
        if self._link_token_secret is None:  # pragma: no cover - guarded by callers
            return False
        if expires_at < int(time.time()):
            return False
        expected = self._sign_link_token(channel, channel_id, expires_at)
        return hmac.compare_digest(expected, signature)

    def mint_start_url(self, channel: str, channel_id: str, return_to: str | None = None) -> str:
        """Return a one-shot signed URL for ``GET /auth/start``.

        Required when ``link_token_secret`` is set. Channels that issue
        these URLs (e.g. a Telegram ``/link`` command after verifying the
        inbound webhook signature) call this helper so the resulting URL
        proves the caller authorised the ``(channel, channel_id)`` binding.

        Without this layer ``GET /auth/start`` is an IDOR vector: any
        anonymous caller can bind a victim's per-channel id to their own
        Entra ``oid``.
        """
        if self._link_token_secret is None:
            raise RuntimeError("mint_start_url requires link_token_secret in the constructor")
        if return_to is not None:
            self._validate_return_to(return_to)  # fail fast at mint time
        expires_at = int(time.time()) + self._link_token_ttl
        sig = self._sign_link_token(channel, str(channel_id), expires_at)
        params = {
            "channel": channel,
            "id": str(channel_id),
            "exp": str(expires_at),
            "sig": sig,
        }
        if return_to:
            params["return_to"] = return_to
        return f"{self._public_base_url}{self.path}/start?{urlencode(params)}"

    def _validate_return_to(self, return_to: str) -> None:
        """Reject open-redirect targets.

        Allows: relative paths starting with ``/``, or absolute URLs whose
        host equals the configured ``public_base_url``'s host. Rejects
        everything else with ``ValueError``.
        """
        if return_to.startswith("/") and not return_to.startswith("//"):
            return  # relative path, safe.
        parsed = urlparse(return_to)
        if not parsed.netloc:
            return
        if self._allowed_return_host and parsed.netloc.lower() == self._allowed_return_host:
            return
        raise ValueError(
            f"return_to must be a relative path or same-origin URL "
            f"(public_base_url host={self._allowed_return_host!r}); got {return_to!r}"
        )

    def authorize_url_for(self, channel: str, channel_id: str, return_to: str | None = None) -> str:
        """Mint a one-shot authorize URL the user can visit to bind their account."""
        state = secrets.token_urlsafe(24)
        self._gc_pending()
        self._pending[state] = _PendingAuth(
            channel=channel,
            channel_id=str(channel_id),
            expires_at=time.monotonic() + self._PENDING_TTL_SECONDS,
            return_to=return_to,
        )
        return str(
            self._msal_app.get_authorization_request_url(
                scopes=self._scopes,
                redirect_uri=self.redirect_uri,
                state=state,
                prompt="select_account",
            )
        )

    def _gc_pending(self) -> None:
        """Drop expired pending-auth entries so the in-memory map cannot grow unbounded."""
        now = time.monotonic()
        for key, entry in list(self._pending.items()):
            if entry.expires_at < now:
                self._pending.pop(key, None)

    async def _handle_start(self, request: Request) -> Response:
        """``GET /start?channel=&id=&return_to=&exp=&sig=`` — redirect to Entra to sign in.

        **Security model.** When ``link_token_secret`` is set the
        request must include ``exp`` + ``sig`` — an HMAC over
        ``(channel, channel_id, expires_at)`` minted by
        :meth:`mint_start_url`. Without that gate, any open-internet
        caller can bind a victim's per-channel id (e.g.
        ``telegram:<victim_chat>``) to their own Entra ``oid``: the
        callback would persist
        ``"telegram:<victim>" -> "entra:<attacker_oid>"`` and any
        future inbound message from the victim would resolve to the
        attacker's isolation key. We make the unsigned mode opt-in
        with a loud startup warning so the dev-mode default doesn't
        ship to production.

        ``return_to`` is validated against the configured
        ``public_base_url`` host (or restricted to relative paths) to
        prevent open-redirect phishing on a successful sign-in.
        """
        channel = request.query_params.get("channel")
        channel_id = request.query_params.get("id")
        return_to = request.query_params.get("return_to")
        if not channel or not channel_id:
            return _link_html("Missing 'channel' or 'id' query parameter.", status=400)

        if self._link_token_secret is not None:
            sig = request.query_params.get("sig")
            exp_raw = request.query_params.get("exp")
            try:
                exp = int(exp_raw) if exp_raw else 0
            except ValueError:
                exp = 0
            if not sig or not exp or not self._verify_link_token(channel, channel_id, exp, sig):
                logger.warning(
                    "EntraIdentityLinkChannel /start rejected: missing/invalid signed link-token (channel=%s, id=%s)",
                    channel,
                    channel_id,
                )
                return _link_html("Invalid or expired sign-in link.", status=403)
        else:
            # See _on_startup warning. Logged on every wire access so
            # operators can't miss the IDOR exposure in their access logs.
            logger.warning(
                "EntraIdentityLinkChannel /start accepted UNSIGNED request "
                "for (channel=%s, id=%s) — set link_token_secret to require "
                "HMAC-signed link tokens minted via mint_start_url().",
                channel,
                channel_id,
            )
        if return_to is not None:
            try:
                self._validate_return_to(return_to)
            except ValueError as exc:
                logger.warning("EntraIdentityLinkChannel /start invalid return_to: %s", exc)
                return _link_html("Invalid return_to URL.", status=400)
        url = self.authorize_url_for(channel, channel_id, return_to=return_to)
        return RedirectResponse(url, status_code=302)

    async def _handle_callback(self, request: Request) -> Response:
        """``GET /callback`` — finish the OAuth flow and persist the link.

        Exchanges the authorization code for a token, reads the user's
        ``id``/``userPrincipalName`` from Microsoft Graph, then stores the
        ``channel:channel_id -> entra:<oid>`` mapping in the identity store.
        Renders a small HTML page so a browser-based flow has something to
        show; if ``return_to`` was supplied (and validated at /start time
        against the same-origin allowlist) it appears as a deep link.

        All values that flow into HTML output (``error``, ``error_description``,
        ``channel_key``, ``upn``) are passed through :func:`html.escape` to
        avoid reflected XSS — both the OAuth-error path and the
        sign-in-success body would otherwise execute attacker-controlled
        markup on the auth host's origin.
        """
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("entra identity channel not started")
        if error := request.query_params.get("error"):
            description = request.query_params.get("error_description", "")
            return _link_html(
                f"Sign-in failed: {html.escape(error)}<br>{html.escape(description)}",
                status=400,
            )

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        pending = self._pending.pop(state or "", None)
        if not code or pending is None or pending.expires_at < time.monotonic():
            return _link_html("Invalid or expired sign-in state. Please retry.", status=400)

        # MSAL handles client_secret vs client_assertion (cert) under the hood.
        result: dict[str, Any] = await asyncio.to_thread(
            self._msal_app.acquire_token_by_authorization_code,
            code,
            scopes=self._scopes,
            redirect_uri=self.redirect_uri,
        )
        if "access_token" not in result:
            logger.warning("Entra token exchange failed: %s", result)
            err_text = result.get("error_description") or result.get("error") or "unknown error"
            return _link_html(
                f"Token exchange failed: {html.escape(str(err_text))}",
                status=502,
            )
        access_token = result["access_token"]

        me = await self._http.get(self._GRAPH_ME, headers={"Authorization": f"Bearer {access_token}"})
        if me.status_code != 200:
            return _link_html("Could not read user profile from Microsoft Graph.", status=502)
        profile = me.json()
        oid = profile.get("id")
        upn = profile.get("userPrincipalName") or profile.get("displayName") or oid
        if not oid:
            return _link_html("Profile response missing 'id'.", status=502)

        channel_key = f"{pending.channel}:{pending.channel_id}"
        await self._store.link(channel_key, oid)
        logger.info("Linked %s → entra:%s (%s)", channel_key, oid, upn)

        if pending.return_to:
            # ``return_to`` was already validated at /start time against
            # the allowlist (relative path or same-origin only). Re-check
            # defensively to harden against any future code path that
            # bypasses the /start gate.
            try:
                self._validate_return_to(pending.return_to)
                return RedirectResponse(pending.return_to, status_code=302)
            except ValueError:
                logger.warning(
                    "EntraIdentityLinkChannel /callback dropping invalid return_to: %s",
                    pending.return_to,
                )
        return _link_html(
            f"<h2>Linked</h2><p>{html.escape(channel_key)} is now bound to "
            f"<b>{html.escape(str(upn))}</b>.</p>"
            "<p>You can close this window and return to your chat.</p>"
        )
