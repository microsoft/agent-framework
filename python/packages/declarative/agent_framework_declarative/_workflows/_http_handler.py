# Copyright (c) Microsoft. All rights reserved.

"""HTTP request handler abstraction for declarative workflows.

Mirrors the .NET ``IHttpRequestHandler`` / ``DefaultHttpRequestHandler`` pair from
``Microsoft.Agents.AI.Workflows.Declarative``. Provides:

- :class:`HttpRequestInfo` — request input data passed from the executor.
- :class:`HttpRequestResult` — response data returned to the executor.
- :class:`HttpRequestHandler` — :class:`typing.Protocol` callers implement to plug
  in custom transports (e.g. with allowlisting, mTLS, retries, etc.).
- :class:`DefaultHttpRequestHandler` — production-grade default backed by
  ``httpx.AsyncClient``.

Security note: :class:`DefaultHttpRequestHandler` performs **no** URL filtering
or SSRF protection. Production deployments should supply a custom handler that
enforces an allowlist or DNS-rebinding-resistant policy. This split mirrors the
.NET design.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

__all__ = [
    "DefaultHttpRequestHandler",
    "HttpRequestHandler",
    "HttpRequestInfo",
    "HttpRequestResult",
]


@dataclass
class HttpRequestInfo:
    """Description of an HTTP request to be dispatched by a :class:`HttpRequestHandler`.

    Mirrors the .NET ``HttpRequestInfo`` record. Field semantics:

    - ``method``: HTTP method (``GET``, ``POST``, etc.). Already upper-cased by the executor.
    - ``url``: Absolute URL. Already evaluated from the YAML expression.
    - ``headers``: Single-value header map (case-insensitive keys per HTTP semantics
      but stored as authored). Empty values are skipped by the executor.
    - ``query_parameters``: String key/value pairs appended to the URL.
    - ``body``: Request body bytes/text, or ``None`` for no body.
    - ``body_content_type``: Content type to send (e.g. ``application/json``).
      Ignored when ``body`` is ``None``.
    - ``timeout_ms``: Per-request timeout in milliseconds. ``None`` => use the
      handler's default.
    - ``connection_name``: Optional Foundry connection name for handlers that
      resolve auth/credentials by connection.
    """

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    query_parameters: dict[str, str] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    body: str | None = None
    body_content_type: str | None = None
    timeout_ms: int | None = None
    connection_name: str | None = None


@dataclass
class HttpRequestResult:
    """Response returned by a :class:`HttpRequestHandler`.

    Mirrors the .NET ``HttpRequestResult`` record. ``headers`` preserves
    multi-value response headers (e.g. multiple ``Set-Cookie`` headers) as a
    ``dict[str, list[str]]``. The executor folds duplicates into a single
    comma-joined string only at the point it assigns ``responseHeaders`` to
    workflow state.

    Header keys are normalized to lowercase so that lookups are consistent
    regardless of the server's transmitted casing (HTTP headers are
    case-insensitive per RFC 7230 §3.2). Custom :class:`HttpRequestHandler`
    implementations should follow the same convention.
    """

    status_code: int
    is_success_status_code: bool
    body: str
    headers: dict[str, list[str]] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]


@runtime_checkable
class HttpRequestHandler(Protocol):
    """Protocol for HTTP request handlers used by ``HttpRequestAction``.

    Implementations must be safe to call concurrently from multiple workflow
    runs. Implementations are responsible for any URL allowlisting, SSRF
    guards, retry policies, auth resolution, and other policies that the
    workflow author wants applied.
    """

    async def send(self, info: HttpRequestInfo) -> HttpRequestResult:
        """Dispatch ``info`` and return the response result.

        Args:
            info: Description of the request to send.

        Returns:
            The response. Implementations should NOT raise on non-2xx status
            codes; instead, set ``is_success_status_code`` accordingly. They
            SHOULD raise on transport-level failures (connection refused,
            DNS errors, timeouts).
        """
        ...


ClientProvider = Callable[[HttpRequestInfo], Awaitable["httpx.AsyncClient | None"]]


class DefaultHttpRequestHandler:
    """Default :class:`HttpRequestHandler` backed by :class:`httpx.AsyncClient`.

    Construction modes:

    1. ``DefaultHttpRequestHandler()`` — owns an internal client created lazily
       on first ``send()``. Closed by :meth:`aclose`.
    2. ``DefaultHttpRequestHandler(client=existing)`` — caller-owned client.
       Not closed by :meth:`aclose`.
    3. ``DefaultHttpRequestHandler(client_provider=cb)`` — per-request client
       lookup (parity with .NET's ``httpClientProvider`` callback). The
       provider may return ``None`` to fall back to the owned/default client.

    .. warning::

       This handler performs **no** URL filtering or SSRF protection. Wrap or
       replace it with a custom handler in production.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        client_provider: ClientProvider | None = None,
    ) -> None:
        self._owned_client: httpx.AsyncClient | None = None
        self._caller_client = client
        self._client_provider = client_provider
        # Guards lazy creation of ``_owned_client`` against concurrent first
        # ``send()`` calls leaking duplicate clients.
        self._owned_client_lock = asyncio.Lock()

    async def send(self, info: HttpRequestInfo) -> HttpRequestResult:
        """Dispatch the request and return the parsed result."""
        if not info.url:
            raise ValueError("HttpRequestInfo.url must be a non-empty string.")
        if not info.method:
            raise ValueError("HttpRequestInfo.method must be a non-empty string.")

        client = await self._resolve_client(info)

        timeout: httpx.Timeout | object
        if info.timeout_ms is not None and info.timeout_ms > 0:
            timeout = httpx.Timeout(info.timeout_ms / 1000.0)
        else:
            timeout = httpx.USE_CLIENT_DEFAULT

        headers = dict(info.headers)
        content: bytes | str | None = None
        if info.body is not None:
            content = info.body
            if not _has_header(headers, "content-type"):
                # Match .NET DefaultHttpRequestHandler: when a body is sent
                # without an explicit content type, default to ``text/plain``
                # so the request is interpretable by servers and direct
                # callers (not just the YAML executor) get sensible defaults.
                headers["Content-Type"] = info.body_content_type or "text/plain"

        params: Mapping[str, str] | None = info.query_parameters or None

        response = await client.request(
            method=info.method,
            url=info.url,
            params=params,
            headers=headers or None,
            content=content,
            timeout=timeout,  # type: ignore[arg-type]
        )

        # Preserve multi-value headers (e.g. multiple Set-Cookie) as list[str].
        # Normalize names to lowercase so lookups are consistent and case
        # variations from the transport do not create duplicate logical keys
        # (HTTP headers are case-insensitive per RFC 7230 §3.2).
        result_headers: dict[str, list[str]] = {}
        for key, value in response.headers.multi_items():
            result_headers.setdefault(key.lower(), []).append(value)

        body_text = response.text

        return HttpRequestResult(
            status_code=response.status_code,
            is_success_status_code=200 <= response.status_code < 300,
            body=body_text,
            headers=result_headers,
        )

    async def aclose(self) -> None:
        """Release the owned client, if any. Caller-owned clients are NOT closed."""
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def _resolve_client(self, info: HttpRequestInfo) -> httpx.AsyncClient:
        """Pick a client for this request: provider → caller → lazily-owned."""
        if self._client_provider is not None:
            provided = await self._client_provider(info)
            if provided is not None:
                return provided
        if self._caller_client is not None:
            return self._caller_client
        if self._owned_client is None:
            # Double-checked locking under asyncio.Lock so concurrent first
            # callers don't each create a fresh httpx.AsyncClient and orphan
            # one of them.
            async with self._owned_client_lock:
                if self._owned_client is None:
                    self._owned_client = httpx.AsyncClient()
        return self._owned_client

    async def __aenter__(self) -> DefaultHttpRequestHandler:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    """Case-insensitive header presence check."""
    needle = name.lower()
    return any(key.lower() == needle for key in headers)
