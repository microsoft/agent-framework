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
import sys
import zlib
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, Protocol, runtime_checkable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

import httpx
from httpx._client import ACCEPT_ENCODING

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
       on first ``send()`` without response-cookie persistence. Closed by :meth:`aclose`.
    2. ``DefaultHttpRequestHandler(client=existing)`` — caller-owned client.
       Retains its cookie behavior and is not closed by :meth:`aclose`.
    3. ``DefaultHttpRequestHandler(client_provider=cb)`` — per-request client
       lookup (parity with .NET's ``httpClientProvider`` callback). The
       provider's clients retain their cookie behavior and are not closed by :meth:`aclose`.
       Returning ``None`` falls back to ``client``, if supplied, then to the owned client.

    The provider receives a new :class:`HttpRequestInfo` with an absolute HTTP(S) URL
    normalized by ``httpx`` and ``query_parameters`` already appended to ``url``.
    The snapshot's ``query_parameters`` is empty; the original request is not modified.
    Client-level query defaults are applied after selection, and supplied clients retain
    their redirect behavior. The provider is not called again for automatic redirects.

    Applications requiring persistent cookies must supply a client through ``client``
    or ``client_provider`` scoped to one authenticated principal and manage its lifetime.
    Explicit outbound ``Cookie`` headers and response ``Set-Cookie`` headers are preserved;
    the owned-client policy only prevents automatic cookie persistence.

    Response bodies are limited to ``max_response_body_bytes`` (10 MiB by default),
    both on the wire and after each gzip/deflate decoding stage. Other content encodings
    are rejected. The limit also applies to redirect and authentication responses.
    Caller-supplied response hooks must not eagerly read response bodies.

    Keyword Args:
        client: Optional caller-owned HTTP client.
        client_provider: Optional per-request client provider.
        max_response_body_bytes: Positive wire and decoded response-body limit in bytes.

    .. warning::

       This handler performs **no** URL filtering or SSRF protection. Wrap or
       replace it with a custom handler in production.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        client_provider: ClientProvider | None = None,
        max_response_body_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        if isinstance(max_response_body_bytes, bool) or not isinstance(max_response_body_bytes, int):
            raise ValueError("max_response_body_bytes must be a positive integer.")
        if max_response_body_bytes <= 0:
            raise ValueError("max_response_body_bytes must be a positive integer.")
        self._max_response_body_bytes = max_response_body_bytes
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

        url = httpx.URL(info.url)
        if not url.is_absolute_url or url.scheme not in {"http", "https"}:
            raise ValueError("HttpRequestInfo.url must be an absolute HTTP or HTTPS URL.")

        # Preserve the authored query bytes, appending rather than replacing duplicate
        # keys. QueryParams would rewrite escapes, bare flags and duplicate ordering.
        query = urlsplit(info.url).query
        explicit_pairs = [(key, value) for key, value in info.query_parameters.items() if key]
        if explicit_pairs:
            query += ("&" if query else "") + urlencode(explicit_pairs, quote_via=quote)
        raw_path = url.raw_path.split(b"?", 1)[0]
        if query:
            raw_path += b"?" + _encode_query(query)
        url = url.copy_with(raw_path=raw_path)

        info = replace(info, url=str(url), headers=dict(info.headers), query_parameters={})
        client = await self._resolve_client(info)

        timeout: httpx.Timeout | object
        if info.timeout_ms is not None and info.timeout_ms > 0:
            timeout = httpx.Timeout(info.timeout_ms / 1000.0)
        else:
            timeout = httpx.USE_CLIENT_DEFAULT

        headers = dict(info.headers)
        if not _has_header(headers, "accept-encoding") and client.headers.get("accept-encoding") == ACCEPT_ENCODING:
            headers["Accept-Encoding"] = "gzip, deflate"
        content: bytes | str | None = None
        if info.body is not None:
            content = info.body
            if not _has_header(headers, "content-type"):
                # Match .NET DefaultHttpRequestHandler: when a body is sent
                # without an explicit content type, default to ``text/plain``
                # so the request is interpretable by servers and direct
                # callers (not just the YAML executor) get sensible defaults.
                headers["Content-Type"] = info.body_content_type or "text/plain"

        # Selected-client params remain defaults for keys absent from the workflow's
        # composed query. They are host configuration, unavailable before selection.
        request_keys = {key for key, _ in parse_qsl(url.query.decode("ascii"), keep_blank_values=True)}
        client_defaults = [(key, value) for key, value in client.params.multi_items() if key not in request_keys]
        if client_defaults:
            encoded_query = url.query + (b"&" if url.query else b"")
            encoded_query += urlencode(client_defaults, quote_via=quote).encode("ascii")
            url = url.copy_with(query=encoded_query)

        # Build without the query so the client's params merge has nothing to clobber --
        # it drops the URL's query outright -- then overwrite the query httpx composed
        # with ours. The fragment stays on the built URL; httpx does not send it.
        request = client.build_request(
            method=info.method,
            url=url.copy_with(query=None),
            headers=headers or None,
            content=content,
            timeout=timeout,
        )
        request.url = url

        auth = client.auth
        if auth is None:
            auth = httpx.BasicAuth(url.username, url.password) if url.username or url.password else httpx.Auth()
        response = await client.send(
            request,
            stream=True,
            follow_redirects=False,
            auth=_ResponseLimitAuth(
                auth,
                limit=self._max_response_body_bytes,
                follow_redirects=client.follow_redirects,
            ),
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
                    self._owned_client = httpx.AsyncClient(
                        cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
                    )
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


class _ResponseLimitAuth(httpx.Auth):
    """Read every response within bounds before HTTPX can buffer intermediate bodies."""

    def __init__(self, auth: httpx.Auth, *, limit: int, follow_redirects: bool) -> None:
        self._auth = auth
        self._limit = limit
        self._follow_redirects = follow_redirects

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        flow = self._auth.async_auth_flow(request)
        try:
            request = await flow.__anext__()
            while True:
                response = yield request
                await _read_bounded_response(response, self._limit)
                if self._follow_redirects and response.next_request is not None:
                    request = response.next_request
                    continue
                try:
                    request = await flow.asend(response)
                except StopAsyncIteration:
                    return
        finally:
            await flow.aclose()


async def _read_bounded_response(response: httpx.Response, limit: int) -> None:
    """Cache only bounded decoded content, preserving HTTPX text and auth behavior."""
    try:
        if response.is_stream_consumed:
            if len(response.content) > limit:
                raise httpx.StreamError("HTTP response body exceeds the configured limit.")
            return

        encodings = [
            encoding.strip().lower()
            for encoding in response.headers.get("content-encoding", "").split(",")
            if encoding.strip().lower() != "identity" and encoding.strip()
        ]
        if (
            response.request.method == "HEAD"
            or 100 <= response.status_code < 200
            or response.status_code in {204, 205, 304}
            or (response.request.method == "CONNECT" and 200 <= response.status_code < 300)
        ):
            encodings = []
        if len(encodings) > 4:
            raise httpx.DecodingError("HTTP response has too many content encoding stages.", request=response.request)
        decoders = [_BoundedContentDecoder(encoding, limit) for encoding in reversed(encodings)]
        body = bytearray()
        received = 0
        async for chunk in response.aiter_raw():
            received += len(chunk)
            if received > limit:
                raise httpx.StreamError("HTTP response body exceeds the configured limit.")
            for decoder in decoders:
                chunk = decoder.decode(chunk)
            if len(body) + len(chunk) > limit:
                raise httpx.StreamError("HTTP response body exceeds the configured limit.")
            body.extend(chunk)
        for index, decoder in enumerate(decoders):
            chunk = decoder.finish()
            for downstream in decoders[index + 1 :]:
                chunk = downstream.decode(chunk)
            if len(body) + len(chunk) > limit:
                raise httpx.StreamError("HTTP response body exceeds the configured limit.")
            body.extend(chunk)
        # HTTPX rereads intermediate responses during auth/redirect handling. Populate
        # its content cache so those reads cannot trigger automatic decoding again.
        response._content = bytes(body)  # pyright: ignore[reportPrivateUsage]
    finally:
        await response.aclose()


class _BoundedContentDecoder:
    def __init__(self, encoding: str, limit: int) -> None:
        if encoding not in {"gzip", "deflate"}:
            raise httpx.DecodingError(f"Unsupported HTTP response content encoding: {encoding}.")
        self._limit = limit
        self._decoded = 0
        self._input = bytearray()
        self._decoder = zlib.decompressobj(zlib.MAX_WBITS | 16) if encoding == "gzip" else None

    def decode(self, data: bytes) -> bytes:
        if self._decoder is None:
            # Raw deflate can share a wrapped stream's prefix. Retain bounded input
            # until finalization so a failed candidate never reaches downstream stages.
            if len(self._input) + len(data) > self._limit:
                raise httpx.StreamError("HTTP response body exceeds the configured limit.")
            self._input.extend(data)
            return b""
        try:
            decoded = self._decoder.decompress(data, min(self._limit - self._decoded + 1, sys.maxsize))
        except zlib.error as exc:
            raise httpx.DecodingError(str(exc)) from exc
        self._decoded += len(decoded)
        if self._decoded > self._limit:
            raise httpx.StreamError("HTTP response body exceeds the configured limit.")
        if self._decoder.unused_data:
            raise httpx.DecodingError("Unexpected data after HTTP response content encoding.")
        return decoded

    def finish(self) -> bytes:
        if self._decoder is not None:
            if not self._decoder.eof:
                raise httpx.DecodingError("Incomplete HTTP response content encoding.")
            return b""

        data = bytes(self._input)
        self._input.clear()
        failures: list[httpx.DecodingError | httpx.StreamError] = []
        for mode in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            self._decoder = zlib.decompressobj(mode)
            self._decoded = 0
            try:
                decoded = self.decode(data)
                if not self._decoder.eof:
                    raise httpx.DecodingError("Incomplete HTTP response content encoding.")
                return decoded
            except (httpx.DecodingError, httpx.StreamError) as exc:
                failures.append(exc)
        for error in failures:
            if isinstance(error, httpx.StreamError):
                raise error
        raise failures[-1]
