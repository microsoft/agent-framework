# Copyright (c) Microsoft. All rights reserved.

"""GitHub Copilot model client.

Provides :class:`GitHubCopilotModelClient`, a chat client that targets the
OpenAI-compatible inference endpoint exposed by GitHub Copilot
(``https://api.githubcopilot.com``).

The class wraps :class:`agent_framework_openai.OpenAIChatCompletionClient` and
adds the Copilot-specific concerns:

* Resolving a raw GitHub token from environment variables or the ``gh`` CLI,
  with optional interactive OAuth device-code login.
* Exchanging the raw token for the short-lived Copilot API token and
  refreshing it transparently on expiry.
* Attaching the editor-attribution headers the Copilot API expects.

This client is intended for prototyping and personal-use scenarios; the OAuth
client ID below is the public one shared by the Copilot CLI / opencode
project. Production integrations should register their own GitHub OAuth App.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_framework._middleware import ChatAndFunctionMiddlewareTypes
from agent_framework._tools import FunctionInvocationConfiguration
from agent_framework_openai import OpenAIChatCompletionClient

logger = logging.getLogger("agent_framework.github_copilot")


# region Constants

# OAuth device-code used by Copilot CLI.
OAUTH_CLIENT_ID = "Ov23li8tweQw6odWQebz"
OAUTH_SCOPE = "read:user"

# Token exchange endpoint (raw GitHub token -> short-lived Copilot API token).
TOKEN_EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"

# OpenAI-compatible inference endpoint.
COPILOT_BASE_URL = "https://api.githubcopilot.com"

# Model catalog endpoint.
COPILOT_MODELS_URL = f"{COPILOT_BASE_URL}/models"

# Editor attribution headers - the API validates these.
EDITOR_VERSION = "vscode/1.104.1"
COPILOT_INTEGRATION_ID = "vscode-chat"
USER_AGENT = "GitHubCopilotChat/0.26.7"

# Env vars checked in priority order (matches Copilot CLI behaviour).
TOKEN_ENV_VARS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")

_CLASSIC_PAT_PREFIX = "ghp_"

DEVICE_CODE_POLL_SAFETY_MARGIN = 3  # seconds added to server poll interval
EXCHANGE_CACHE_REFRESH_MARGIN = 120  # refresh 2 min before expiry

DEFAULT_MODEL = "gpt-5-mini"


# region Token resolution


def validate_token(token: str) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for whether ``token`` is usable with Copilot.

    Classic PATs (``ghp_*``) are explicitly unsupported - the token exchange
    endpoint rejects them. Accepted prefixes are ``gho_*``, ``github_pat_*``
    and ``ghu_*``.
    """
    token = token.strip()
    if not token:
        return False, "Empty token"
    if token.startswith(_CLASSIC_PAT_PREFIX):
        return False, (
            "Classic Personal Access Tokens (ghp_*) are not supported by the "
            "Copilot API. Use an OAuth token (gho_*) from `gh auth login`, a "
            "fine-grained PAT (github_pat_*) with the Copilot Requests "
            "permission, or this client's interactive device-code login."
        )
    return True, "OK"


def _gh_cli_candidates() -> list[str]:
    candidates: list[str] = []
    resolved = shutil.which("gh")
    if resolved:
        candidates.append(resolved)
    for path in (
        "/opt/homebrew/bin/gh",
        "/usr/local/bin/gh",
        str(Path.home() / ".local" / "bin" / "gh"),
    ):
        if path not in candidates and os.path.isfile(path) and os.access(path, os.X_OK):
            candidates.append(path)
    return candidates


def _try_gh_cli_token() -> str | None:
    """Read a token from ``gh auth token`` if the GitHub CLI is installed."""
    clean_env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
    gh_host = os.getenv("COPILOT_GH_HOST", "").strip()

    for gh_path in _gh_cli_candidates():
        cmd = [gh_path, "auth", "token"]
        if gh_host:
            cmd += ["--hostname", gh_host]
        try:
            result = subprocess.run(  # noqa: S603 - trusted gh binary
                cmd, capture_output=True, text=True, timeout=5, env=clean_env, check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def resolve_github_token() -> tuple[str, str]:
    """Find a usable GitHub token.

    Returns ``(token, source)``. ``token`` is empty when nothing was found.
    Unsupported classic PATs from env vars are skipped with a warning.
    """
    for var in TOKEN_ENV_VARS:
        val = os.getenv(var, "").strip()
        if val:
            ok, msg = validate_token(val)
            if not ok:
                logger.warning("Token from %s rejected: %s", var, msg)
                continue
            return val, var

    token = _try_gh_cli_token()
    if token:
        ok, msg = validate_token(token)
        if not ok:
            raise ValueError(f"Token from `gh auth token` is unsupported: {msg}")
        return token, "gh auth token"

    return "", ""


# region Device-code login


def device_code_login(
    *,
    host: str = "github.com",
    timeout_seconds: float = 300,
) -> str | None:
    """Run the GitHub OAuth device-code flow (RFC 8628).

    Prints a URL and one-time code, polls until the user authorizes, and
    returns the resulting OAuth access token (``gho_*``). Returns ``None``
    on failure, denial or timeout.
    """
    domain = host.rstrip("/")
    device_code_url = f"https://{domain}/login/device/code"
    access_token_url = f"https://{domain}/login/oauth/access_token"

    body = urllib.parse.urlencode({"client_id": OAUTH_CLIENT_ID, "scope": OAUTH_SCOPE}).encode()
    req = urllib.request.Request(  # noqa: S310 - https URL
        device_code_url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.error("Failed to start device authorization: %s", exc)
        return None

    verification_uri = data.get("verification_uri", f"https://{domain}/login/device")
    user_code = data.get("user_code", "")
    device_code = data.get("device_code", "")
    interval = max(int(data.get("interval", 5)), 1)

    if not device_code or not user_code:
        logger.error("GitHub did not return a device code.")
        return None

    print()
    print(f"  Open:  {verification_uri}")
    print(f"  Code:  {user_code}")
    print()
    print("  Waiting for authorization", end="", flush=True)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(interval + DEVICE_CODE_POLL_SAFETY_MARGIN)

        poll_body = urllib.parse.urlencode({
            "client_id": OAUTH_CLIENT_ID,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }).encode()
        poll_req = urllib.request.Request(  # noqa: S310
            access_token_url,
            data=poll_body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(poll_req, timeout=10) as resp:  # noqa: S310
                result = json.loads(resp.read().decode())
        except Exception:
            print(".", end="", flush=True)
            continue

        if result.get("access_token"):
            print(" ok")
            return str(result["access_token"])

        error = result.get("error", "")
        if error == "authorization_pending":
            print(".", end="", flush=True)
        elif error == "slow_down":
            server_interval = result.get("interval")
            interval = int(server_interval) if isinstance(server_interval, (int, float)) else interval + 5
            print(".", end="", flush=True)
        elif error == "expired_token":
            print("\n  Device code expired.")
            return None
        elif error == "access_denied":
            print("\n  Authorization denied.")
            return None
        else:
            print(f"\n  Unexpected error: {error}")
            return None

    print("\n  Timed out.")
    return None


# region Token exchange


@dataclass
class _ExchangeCache:
    entries: dict[str, tuple[str, float]] = field(default_factory=dict)


_cache = _ExchangeCache()


def _fingerprint(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()[:16]


def exchange_token(raw_token: str, *, timeout: float = 10.0) -> tuple[str, float]:
    """Exchange a raw GitHub token for a short-lived Copilot API token.

    Returns ``(api_token, expires_at_epoch)``. Results are cached in-process
    and reused until close to expiry.
    """
    fp = _fingerprint(raw_token)
    cached = _cache.entries.get(fp)
    if cached:
        api_token, expires_at = cached
        if time.time() < expires_at - EXCHANGE_CACHE_REFRESH_MARGIN:
            return api_token, expires_at

    req = urllib.request.Request(  # noqa: S310
        TOKEN_EXCHANGE_URL,
        method="GET",
        headers={
            "Authorization": f"token {raw_token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Editor-Version": EDITOR_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode(errors="ignore")
        except Exception:
            pass
        raise ValueError(f"Token exchange failed (HTTP {exc.code}): {body}") from exc
    except Exception as exc:
        raise ValueError(f"Token exchange failed: {exc}") from exc

    api_token = data.get("token", "")
    expires_at = data.get("expires_at", 0)
    if not api_token:
        raise ValueError("Token exchange returned an empty token")

    expires_at = float(expires_at) if expires_at else time.time() + 1800
    _cache.entries[fp] = (api_token, expires_at)
    return api_token, expires_at


# region Headers / catalog


def build_copilot_headers(*, is_agent_turn: bool = True) -> dict[str, str]:
    """Build the editor-attribution headers required by the Copilot API."""
    return {
        "Editor-Version": EDITOR_VERSION,
        "User-Agent": USER_AGENT,
        "Copilot-Integration-Id": COPILOT_INTEGRATION_ID,
        "Openai-Intent": "conversation-edits",
        "x-initiator": "agent" if is_agent_turn else "user",
    }


def fetch_copilot_model_catalog(api_token: str, *, timeout: float = 5.0) -> list[dict[str, Any]]:
    """Return the chat-capable models visible to the authenticated account."""
    headers = {**build_copilot_headers(), "Authorization": f"Bearer {api_token}"}
    req = urllib.request.Request(COPILOT_MODELS_URL, headers=headers)  # noqa: S310

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.error("Failed to fetch model catalog: %s", exc)
        return []

    items = data if isinstance(data, list) else data.get("data", [])
    models: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        if item.get("model_picker_enabled") is False:
            continue
        caps = item.get("capabilities") or {}
        model_type = str(caps.get("type") or "").lower()
        if model_type and model_type != "chat":
            continue
        endpoints = item.get("supported_endpoints")
        if isinstance(endpoints, list):
            normalized = {str(e).strip() for e in endpoints if str(e).strip()}
            if normalized and not normalized & {"/chat/completions", "/responses", "/v1/messages"}:
                continue
        seen.add(model_id)
        models.append(item)
    return models


# region Token acquisition (cache + fallback to device code)


_TOKEN_CACHE_PATH = Path.home() / ".agent_framework" / "github_copilot_token"


def _read_cached_raw_token() -> str:
    try:
        if _TOKEN_CACHE_PATH.is_file():
            token = _TOKEN_CACHE_PATH.read_text(encoding="utf-8").strip()
            ok, _ = validate_token(token)
            if ok:
                return token
    except OSError:
        pass
    return ""


def _write_cached_raw_token(token: str) -> None:
    try:
        _TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE_PATH.write_text(token, encoding="utf-8")
        try:
            os.chmod(_TOKEN_CACHE_PATH, 0o600)
        except OSError:
            pass
    except OSError as exc:
        logger.debug("Failed to cache GitHub token: %s", exc)


def _acquire_copilot_token(
    *,
    api_key: str | None,
    interactive: bool,
) -> tuple[str, str]:
    """Resolve a raw GitHub token for the Copilot API.

    Tries (in order): explicit ``api_key``, on-disk cache, env vars, ``gh`` CLI.
    Returns the first available token without requiring a successful exchange
    (the Copilot API accepts the raw ``gho_*`` token directly when the
    exchange endpoint is unavailable).

    If nothing is found and ``interactive`` is True, falls back to the
    device-code login flow and caches the resulting token.
    """
    explicit = (api_key or "").strip()
    if explicit:
        ok, msg = validate_token(explicit)
        if not ok:
            raise ValueError(f"Provided GitHub token is unsupported: {msg}")
        return explicit, "api_key argument"

    cached = _read_cached_raw_token()
    if cached:
        return cached, f"cache ({_TOKEN_CACHE_PATH})"

    resolved, src = resolve_github_token()
    if resolved:
        return resolved, src

    if not interactive:
        raise RuntimeError(
            "No GitHub token found. Pass `api_key=...`, set GITHUB_TOKEN / "
            "GH_TOKEN / COPILOT_GITHUB_TOKEN, or pass `interactive=True` to "
            "sign in via device-code."
        )

    print("No GitHub token found - starting interactive login...")
    obtained = device_code_login()
    if not obtained:
        raise RuntimeError("Interactive GitHub login failed or was cancelled.")
    _write_cached_raw_token(obtained)
    return obtained, "device-code login"


class _CopilotTokenProvider:
    """Callable that returns a current Copilot API token, refreshing as needed.

    The OpenAI Python SDK invokes the api_key callable per request, so this
    transparently handles the ~25-minute Copilot token lifetime.
    """

    def __init__(self, raw_token: str) -> None:
        self._raw_token = raw_token

    async def __call__(self) -> str:
        try:
            api_token, _ = await asyncio.to_thread(exchange_token, self._raw_token)
            return api_token
        except Exception as exc:
            logger.debug("Token exchange failed, using raw token: %s", exc)
            return self._raw_token


# region Client


class GitHubCopilotModelClient(OpenAIChatCompletionClient):
    """Chat client backed by the GitHub Copilot OpenAI-compatible API.

    Authentication is resolved automatically:

    1. ``api_key`` keyword argument (a raw GitHub OAuth or fine-grained PAT).
    2. ``COPILOT_GITHUB_TOKEN`` / ``GH_TOKEN`` / ``GITHUB_TOKEN`` env vars.
    3. ``gh auth token`` from the GitHub CLI.
    4. Interactive OAuth device-code login (when ``interactive=True``).

    The raw token is exchanged for a short-lived Copilot API token on each
    request via a callable api_key, so token refresh is automatic.

    Args:
        model: Copilot model id (e.g. ``"gpt-4o"``, ``"claude-sonnet-4"``).
            When omitted, falls back to the ``GITHUB_COPILOT_MODEL`` env var
            and finally to ``"gpt-4o"``.
        api_key: Optional raw GitHub token to use instead of the resolution
            chain above.
        interactive: When ``True`` (default) and no token can be resolved,
            launch the device-code login flow.
        default_headers: Extra HTTP headers merged on top of the Copilot
            attribution headers.
        middleware: Optional chat/function middleware.
        function_invocation_configuration: Optional function-invocation
            configuration forwarded to the base client.

    Example:
        >>> from agent_framework_github_copilot import GitHubCopilotModelClient
        >>> client = GitHubCopilotModelClient(model="gpt-4o")
        >>> # use as you would any agent_framework chat client
    """

    OTEL_PROVIDER_NAME = "github_copilot"

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        interactive: bool = True,
        default_headers: Mapping[str, str] | None = None,
        instruction_role: str | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        raw_token, source = _acquire_copilot_token(api_key=api_key, interactive=interactive)
        logger.info("GitHubCopilotModelClient using token from: %s", source)

        resolved_model = (
            model
            or os.getenv("GITHUB_COPILOT_MODEL", "").strip()
            or DEFAULT_MODEL
        )

        merged_headers: dict[str, str] = dict(build_copilot_headers())
        if default_headers:
            merged_headers.update(default_headers)

        # Construct AsyncOpenAI ourselves so the User-Agent header (which the
        # Copilot API validates) isn't prefixed with "agent-framework/...".
        from openai import AsyncOpenAI

        async_client = AsyncOpenAI(
            api_key=raw_token,  # initial value; refreshed per request via api_key callable
            base_url=COPILOT_BASE_URL,
            default_headers=merged_headers,
        )

        super().__init__(
            model=resolved_model,
            api_key=_CopilotTokenProvider(raw_token),
            async_client=async_client,
            instruction_role=instruction_role,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )

    def _parse_response_from_openai(self, response: Any, options: Mapping[str, Any]) -> Any:  # type: ignore[override]
        # Copilot's chat-completions response sometimes omits the `created`
        # timestamp; the base parser unconditionally calls
        # ``datetime.fromtimestamp(response.created)`` and crashes. Patch it.
        if getattr(response, "created", None) is None:
            try:
                response.created = int(time.time())
            except Exception:
                pass
        return super()._parse_response_from_openai(response, options)

    @classmethod
    def list_models(cls, *, api_key: str | None = None, interactive: bool = True) -> list[dict[str, Any]]:
        """Return the chat-capable models available to the authenticated account."""
        raw_token, _ = _acquire_copilot_token(api_key=api_key, interactive=interactive)
        try:
            api_token, _ = exchange_token(raw_token)
        except Exception as exc:
            logger.debug("Token exchange failed, using raw token: %s", exc)
            api_token = raw_token
        return fetch_copilot_model_catalog(api_token)

    def __repr__(self) -> str:
        return f"GitHubCopilotModelClient(model={self.model!r})"
