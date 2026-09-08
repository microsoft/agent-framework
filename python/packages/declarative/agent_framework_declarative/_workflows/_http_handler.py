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
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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

        # Compose the query as raw bytes rather than routing it through ``params=``.
        # Anything that reaches ``httpx.QueryParams`` -- ``params=`` or the client's own
        # ``AsyncClient.params`` merge -- is decoded and re-encoded. Measured against
        # httpx 0.28.1, that rewrites ``%20`` in a value as ``+``, expands a bare
        # ``download`` into ``download=``, and reorders interleaved duplicates
        # (``x=1&y=2&x=3`` becomes ``x=1&x=3&y=2``), all of it even when nothing needed
        # merging. Base64 and ``%3A`` round-trip unchanged, so a signature is not
        # rewritten by itself, but any scheme that signs a value holding an encoded
        # space is, and a server that distinguishes ``download`` from ``download=`` or
        # reads repeated keys positionally sees a different request either way.
        # Building the query here and writing it back over the request's ``raw_path``
        # keeps the caller's bytes exactly as given.
        raw = urlsplit(info.url)

        # ``query_parameters`` append rather than replace, so a URL carrying
        # ``filter=region&filter=status`` plus ``{"filter": "tenant"}`` sends all three,
        # matching the .NET handler. Client-level params are defaults only: they apply
        # for a key absent from both request-level sources.
        explicit_pairs = [(key, value) for key, value in info.query_parameters.items() if key]
        request_keys = {key for key, _ in parse_qsl(raw.query, keep_blank_values=True)}
        request_keys.update(key for key, _ in explicit_pairs)
        client_defaults = [(key, value) for key, value in client.params.multi_items() if key not in request_keys]

        query_segments: list[str] = []
        if raw.query:
            query_segments.append(raw.query)
        # ``quote_via=quote`` keeps spaces as ``%20`` instead of ``+``, so appended
        # parameters are encoded the same way the preserved URL query is.
        for pairs in (explicit_pairs, client_defaults):
            if pairs:
                query_segments.append(urlencode(pairs, quote_via=quote))
        query = "&".join(segment for segment in query_segments if segment)

        # Build without the query so the client's params merge has nothing to clobber --
        # it drops the URL's query outright -- then overwrite the query httpx composed
        # with ours. The fragment stays on the built URL; httpx does not send it.
        request = client.build_request(
            method=info.method,
            url=urlunsplit((raw.scheme, raw.netloc, raw.path, "", raw.fragment)),
            headers=headers or None,
            content=content,
            timeout=timeout,
        )
        # Reuse httpx's own path encoding and replace only the query part of ``raw_path``.
        raw_path = request.url.raw_path.split(b"?", 1)[0]
        if query:
            raw_path += b"?" + _encode_query(query)
        request.url = request.url.copy_with(raw_path=raw_path)

        response = await client.send(request)

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


#: Characters a query string may carry literally: RFC 3986 sub-delims plus ``:@/?``, the
#: square brackets many APIs use in key names, and ``%`` so escapes already in the
#: caller's URL are left alone instead of being double-encoded. Everything legal stays
#: as authored and only bytes that cannot appear in a URL get escaped.
_QUERY_SAFE = "!$&'()*+,;=:@/?%[]~"


def _encode_query(query: str) -> bytes:
    """Return *query* as URL-safe bytes without disturbing what is already valid.

    A caller can hand us a URL whose query holds non-ASCII text -- ``?q=café`` -- which
    cannot go on the wire as-is. Percent-encoding only the characters that need it keeps
    an already-valid query byte-identical, which is the point of composing it by hand.
    """
    return quote(query, safe=_QUERY_SAFE).encode("ascii")


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    """Case-insensitive header presence check."""
    needle = name.lower()
    return any(key.lower() == needle for key in headers)
