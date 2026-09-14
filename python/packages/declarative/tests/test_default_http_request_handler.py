# Copyright (c) Microsoft. All rights reserved.

"""Tests for ``DefaultHttpRequestHandler``.

These tests exercise the real handler against ``httpx.MockTransport`` (no real
network) to cover the parts of the handler not exercisable through the executor
stub: query-param URL composition, content-type forwarding, per-request
timeout overrides, multi-value response header preservation, and client
ownership semantics.
"""

from __future__ import annotations

import sys

import httpx
import pytest

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

# These tests don't actually need PowerFx, but the rest of the suite gates on
# Python versions and we keep behaviour consistent.
pytestmark = pytest.mark.skipif(
    sys.version_info >= (3, 14),
    reason="Skipped on Python 3.14+ to keep parity with rest of declarative suite",
)

from agent_framework_declarative._workflows._http_handler import (  # noqa: E402
    DefaultHttpRequestHandler,
    HttpRequestInfo,
)


def _make_handler(transport: httpx.MockTransport) -> DefaultHttpRequestHandler:
    """Return a handler with a MockTransport-backed caller-owned client."""
    client = httpx.AsyncClient(transport=transport)
    return DefaultHttpRequestHandler(client=client)


class TestRequestComposition:
    @pytest.mark.asyncio
    async def test_query_parameters_merged_into_url(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items",
                    query_parameters={"q": "alpha", "limit": "5"},
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        # httpx exposes the merged URL with QS appended
        assert req.url.params.get("q") == "alpha"
        assert req.url.params.get("limit") == "5"

    @pytest.mark.asyncio
    async def test_query_parameters_preserve_url_query_string(self) -> None:
        """query_parameters must be appended, not replace the URL's existing query string.

        Regression for https://github.com/microsoft/agent-framework/issues/7749:
        passing ``params=`` to httpx replaces the URL's existing query string, and the
        handler used to do exactly that — URL parameters (api-version, tenant, ...) were
        silently dropped. The .NET DefaultHttpRequestHandler.ResolveRequestUri preserves
        them; Python now matches that behavior.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items?api-version=2025-01-01&tenant=alpha",
                    query_parameters={"page": "2"},
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        # URL-supplied params are preserved and query_parameters are appended on top
        assert req.url.params.get("api-version") == "2025-01-01"
        assert req.url.params.get("tenant") == "alpha"
        assert req.url.params.get("page") == "2"

    @pytest.mark.asyncio
    async def test_query_parameters_append_before_fragment(self) -> None:
        """query_parameters must be inserted before any fragment, not appended after.

        Plain string concatenation would produce ``url#frag?key=val`` (an invalid URL
        — the query string must come before the fragment). The fix uses urlsplit so
        reassembly keeps the fragment last.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items?api-version=2025-01-01#section",
                    query_parameters={"page": "2"},
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        assert req.url.params.get("api-version") == "2025-01-01"
        assert req.url.params.get("page") == "2"
        # The fragment is preserved and stays last
        assert str(req.url).endswith("#section")
        assert req.url.fragment == "section"

    @pytest.mark.asyncio
    async def test_query_parameters_when_url_ends_with_question_mark(self) -> None:
        """query_parameters must append cleanly when the URL already ends with ``?``.

        urlsplit parses the trailing ``?`` as an empty query part, so the result is
        a clean ``?key=val`` rather than a malformed ``?&key=val`` that plain string
        concatenation would produce.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items?",
                    query_parameters={"page": "2"},
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        assert req.url.params.get("page") == "2"
        # Result is a clean query string, not && or && at the start
        assert str(req.url) == "https://api.example.test/items?page=2"

    @pytest.mark.asyncio
    async def test_query_parameters_preserve_client_level_params(self) -> None:
        """Client-level ``AsyncClient.params`` must survive alongside URL-embedded and
        ``query_parameters`` params.

        moonbox3 review on #7765: when a caller-supplied ``AsyncClient`` is built with
        ``params=``, letting httpx merge them drops the URL's own query outright. The
        handler composes the query itself and writes it over the built request's
        ``raw_path``, so every source survives.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        client = httpx.AsyncClient(
            params={"client-default": "v"},
            transport=httpx.MockTransport(respond),
        )
        handler = DefaultHttpRequestHandler(client=client)
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items?tenant=alpha&page=2",
                    query_parameters={"limit": "5"},
                )
            )
        finally:
            await handler.aclose()
            await client.aclose()

        req_url = str(captured["req"].url)
        for needle in ("client-default=v", "tenant=alpha", "page=2", "limit=5"):
            assert needle in req_url, f"missing {needle!r} in {req_url!r}"
        # Lower-precedence source's duplicate key is overridden (query_parameters win).
        assert "tenant=alpha" in req_url  # smoke: distinct keys all survive

    @pytest.mark.asyncio
    async def test_query_parameters_higher_precedence_than_client_params(self) -> None:
        """A client default is excluded by either request-level source, which both survive.

        ``query_parameters`` append to the URL query rather than replacing it, matching
        the .NET handler, so both request-level values are sent. The client-level param
        is a default and applies only for a key neither source mentions.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        client = httpx.AsyncClient(
            params={"key": "clientval"},
            transport=httpx.MockTransport(respond),
        )
        handler = DefaultHttpRequestHandler(client=client)
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items?key=urlval",
                    query_parameters={"key": "qpval"},
                )
            )
        finally:
            await handler.aclose()
            await client.aclose()

        assert captured["req"].url.raw_path == b"/items?key=urlval&key=qpval"

    @pytest.mark.asyncio
    async def test_query_parameters_empty_key_skipped(self) -> None:
        """Empty query-parameter keys are dropped (matches .NET ResolveRequestUri)."""
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/items",
                    query_parameters={"": "shouldbedropped", "page": "2"},
                )
            )
        finally:
            await handler.aclose()

        req_url = str(captured["req"].url)
        assert "shouldbedropped" not in req_url
        assert "page=2" in req_url

    @pytest.mark.asyncio
    async def test_body_content_type_forwarded(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(204)

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="POST",
                    url="https://api.example.test/items",
                    body='{"k":"v"}',
                    body_content_type="application/json",
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        assert req.headers.get("content-type") == "application/json"
        assert req.content == b'{"k":"v"}'

    @pytest.mark.asyncio
    async def test_existing_content_type_header_not_overwritten(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="POST",
                    url="https://api.example.test/items",
                    headers={"Content-Type": "application/xml"},  # caller wins
                    body="<x/>",
                    body_content_type="application/json",
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        assert req.headers.get("content-type") == "application/xml"

    @pytest.mark.asyncio
    async def test_body_without_content_type_defaults_to_text_plain(self) -> None:
        """Match .NET DefaultHttpRequestHandler: body without explicit content type → ``text/plain``."""
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(204)

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="POST",
                    url="https://api.example.test/items",
                    body="hello",
                    # No body_content_type and no Content-Type header.
                )
            )
        finally:
            await handler.aclose()

        req = captured["req"]
        assert req.headers.get("content-type") == "text/plain"
        assert req.content == b"hello"


class TestTimeout:
    @pytest.mark.asyncio
    async def test_per_request_timeout_surfaces_as_timeout_exception(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("simulated timeout", request=request)

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            with pytest.raises(httpx.TimeoutException):
                await handler.send(
                    HttpRequestInfo(
                        method="GET",
                        url="https://api.example.test/slow",
                        timeout_ms=50,
                    )
                )
        finally:
            await handler.aclose()


class TestResponseHeaders:
    @pytest.mark.asyncio
    async def test_multi_value_headers_preserved(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text="ok",
                headers=[
                    ("Content-Type", "application/json"),
                    ("Set-Cookie", "a=1"),
                    ("Set-Cookie", "b=2"),
                ],
            )

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            result = await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/x"))
        finally:
            await handler.aclose()

        assert result.is_success_status_code
        # The handler keeps multi-value headers as list[str].
        assert result.headers.get("set-cookie") == ["a=1", "b=2"]
        assert result.headers.get("content-type") == ["application/json"]


class TestClientOwnership:
    @pytest.mark.asyncio
    async def test_owned_client_is_closed_on_aclose(self) -> None:
        handler = DefaultHttpRequestHandler()
        # Inject a MockTransport-backed client into the owned slot and verify
        # aclose() releases it. Avoids real network access.
        owned = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
        handler._owned_client = owned
        assert not owned.is_closed
        await handler.aclose()
        assert owned.is_closed

    @pytest.mark.asyncio
    async def test_caller_owned_client_is_not_closed(self) -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
        handler = DefaultHttpRequestHandler(client=client)
        await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/x"))
        await handler.aclose()
        assert not client.is_closed
        await client.aclose()  # cleanup

    @pytest.mark.asyncio
    async def test_concurrent_first_send_creates_single_owned_client(self) -> None:
        """Concurrent first-send calls must not race-leak duplicate clients.

        Without the lock, two concurrent calls on a fresh handler would each
        observe ``_owned_client is None`` and create their own
        ``httpx.AsyncClient``, orphaning one. Verify that lazy initialization
        is serialized: all concurrent sends end up using the same client and
        ``aclose()`` cleanly closes it.
        """
        import asyncio

        # Patch httpx.AsyncClient to count constructions, but only when called
        # from inside _resolve_client (no transport=) so we don't break the
        # MockTransport-backed clients used elsewhere.
        original_ctor = httpx.AsyncClient
        construction_count = 0

        def counting_ctor(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal construction_count
            if not args and not kwargs:
                construction_count += 1
                return original_ctor(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
            return original_ctor(*args, **kwargs)

        import agent_framework_declarative._workflows._http_handler as hh

        hh.httpx.AsyncClient = counting_ctor  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
        try:
            handler = DefaultHttpRequestHandler()
            try:
                await asyncio.gather(*[
                    handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/x")) for _ in range(8)
                ])
            finally:
                await handler.aclose()
        finally:
            hh.httpx.AsyncClient = original_ctor  # type: ignore[assignment]

        assert construction_count == 1, (
            f"Expected exactly 1 owned client to be lazily created but got {construction_count}"
        )


class TestClientProvider:
    @pytest.mark.asyncio
    async def test_client_provider_overrides_default(self) -> None:
        captured: dict[str, str] = {}

        def primary(request: httpx.Request) -> httpx.Response:
            captured["transport"] = "primary"
            return httpx.Response(200, text="primary")

        def provided(request: httpx.Request) -> httpx.Response:
            captured["transport"] = "provided"
            return httpx.Response(200, text="provided")

        primary_client = httpx.AsyncClient(transport=httpx.MockTransport(primary))
        provided_client = httpx.AsyncClient(transport=httpx.MockTransport(provided))

        async def provider(info: HttpRequestInfo) -> httpx.AsyncClient:
            return provided_client

        handler = DefaultHttpRequestHandler(client=primary_client, client_provider=provider)
        try:
            result = await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/x"))
            assert result.body == "provided"
            assert captured["transport"] == "provided"
        finally:
            await handler.aclose()
            await primary_client.aclose()
            await provided_client.aclose()

    @pytest.mark.asyncio
    async def test_client_provider_returning_none_falls_back(self) -> None:
        captured: dict[str, str] = {}

        def primary(request: httpx.Request) -> httpx.Response:
            captured["transport"] = "primary"
            return httpx.Response(200, text="primary")

        async def provider(info: HttpRequestInfo) -> httpx.AsyncClient | None:
            return None

        primary_client = httpx.AsyncClient(transport=httpx.MockTransport(primary))
        handler = DefaultHttpRequestHandler(client=primary_client, client_provider=provider)
        try:
            result = await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/x"))
            assert result.body == "primary"
        finally:
            await handler.aclose()
            await primary_client.aclose()


class TestValidation:
    @pytest.mark.asyncio
    async def test_empty_url_raises(self) -> None:
        handler = DefaultHttpRequestHandler()
        with pytest.raises(ValueError):
            await handler.send(HttpRequestInfo(method="GET", url=""))

    @pytest.mark.asyncio
    async def test_empty_method_raises(self) -> None:
        handler = DefaultHttpRequestHandler()
        with pytest.raises(ValueError):
            await handler.send(HttpRequestInfo(method="", url="https://x.test/"))


class TestAsyncContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_closes_owned_client(self) -> None:
        async with DefaultHttpRequestHandler() as handler:
            owned = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
            handler._owned_client = owned
        assert owned.is_closed


class TestRawQueryPreservation:
    """The URL's query must reach the wire byte-for-byte.

    Routing it through ``httpx.QueryParams`` -- via ``params=`` or the client's own
    params merge -- decodes and re-encodes it, which rewrites ``%20`` as ``+``, expands
    a bare flag into ``key=`` and reorders interleaved duplicates. Any of those can
    invalidate a presigned URL or change how the server reads the request.
    """

    @pytest.mark.asyncio
    async def test_url_query_is_sent_verbatim(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    # percent-encoded space, a bare flag, and duplicates interleaved
                    # around another key
                    url="https://api.example.test/s?term=a%20b&download&x=1&y=2&x=3",
                )
            )
        finally:
            await handler.aclose()

        assert captured["req"].url.raw_path == b"/s?term=a%20b&download&x=1&y=2&x=3"

    @pytest.mark.asyncio
    async def test_url_query_is_verbatim_even_when_client_params_are_set(self) -> None:
        """A client params merge drops the URL query outright, so it must be bypassed."""
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        client = httpx.AsyncClient(
            params={"api-version": "2024-01-01"},
            transport=httpx.MockTransport(respond),
        )
        handler = DefaultHttpRequestHandler(client=client)
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/s?term=a%20b&download&x=1&y=2&x=3",
                )
            )
        finally:
            await handler.aclose()
            await client.aclose()

        # The URL's bytes are untouched and the client default is appended after them.
        assert captured["req"].url.raw_path == (b"/s?term=a%20b&download&x=1&y=2&x=3&api-version=2024-01-01")

    @pytest.mark.asyncio
    async def test_appended_parameters_encode_space_as_percent20(self) -> None:
        """Appended values are encoded the same way a preserved URL query is."""
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/s",
                    query_parameters={"q": "a b", "sym": "a&b=c"},
                )
            )
        finally:
            await handler.aclose()

        assert captured["req"].url.raw_path == b"/s?q=a%20b&sym=a%26b%3Dc"

    @pytest.mark.asyncio
    async def test_client_param_applies_only_when_key_absent_from_both_sources(self) -> None:
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        client = httpx.AsyncClient(
            params={"in-url": "dropped", "in-explicit": "dropped", "unique": "kept"},
            transport=httpx.MockTransport(respond),
        )
        handler = DefaultHttpRequestHandler(client=client)
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/s?in-url=fromurl",
                    query_parameters={"in-explicit": "fromexplicit"},
                )
            )
        finally:
            await handler.aclose()
            await client.aclose()

        assert captured["req"].url.raw_path == (b"/s?in-url=fromurl&in-explicit=fromexplicit&unique=kept")

    @pytest.mark.asyncio
    async def test_client_headers_cookies_auth_and_timeout_survive(self) -> None:
        """Building through the client keeps its configuration, params merge bypassed."""
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        client = httpx.AsyncClient(
            params={"api-version": "2024-01-01"},
            headers={"X-Client-Header": "client-value"},
            cookies={"session": "cookie-value"},
            auth=("user", "pass"),
            transport=httpx.MockTransport(respond),
        )
        handler = DefaultHttpRequestHandler(client=client)
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/s?keep=me",
                    timeout_ms=4500,
                )
            )
        finally:
            await handler.aclose()
            await client.aclose()

        request = captured["req"]
        assert request.headers["X-Client-Header"] == "client-value"
        assert request.headers["Cookie"] == "session=cookie-value"
        assert request.headers["Authorization"].startswith("Basic ")
        assert request.extensions["timeout"] == {
            "connect": 4.5,
            "read": 4.5,
            "write": 4.5,
            "pool": 4.5,
        }
        assert request.url.raw_path == b"/s?keep=me&api-version=2024-01-01"

    @pytest.mark.asyncio
    async def test_non_ascii_url_query_is_percent_encoded_not_rejected(self) -> None:
        """Composing raw bytes must still escape what cannot go on the wire.

        A caller can hand us a URL whose query holds literal non-ASCII text, which has
        no byte representation in a request target. Only those characters are escaped;
        an already-valid query stays byte-identical.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/s?q=café&keep=%20"))
        finally:
            await handler.aclose()

        assert captured["req"].url.raw_path == b"/s?q=caf%C3%A9&keep=%20"

    @pytest.mark.asyncio
    async def test_presigned_style_query_survives_untouched(self) -> None:
        """A signature-bearing query reaches the server byte-identical.

        Verified against a real Azure Blob SAS URL: base64 and ``%3A`` happen to
        round-trip through ``QueryParams`` unchanged, so this shape was already intact
        before the handler stopped re-encoding. It is pinned because a scheme that signs
        a value holding an encoded space is not so lucky -- see
        ``test_encoded_space_in_a_signed_value_is_not_rewritten``.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        signed = b"sig=abc%2Bdef%3D&se=2026-01-01T00%3A00%3A00Z&sp=r&sv=2024-11-04"
        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/blob?" + signed.decode()))
        finally:
            await handler.aclose()

        assert captured["req"].url.raw_path == b"/blob?" + signed

    @pytest.mark.asyncio
    async def test_appended_values_cannot_inject_additional_pairs(self) -> None:
        """Only the caller's own URL query is verbatim; everything appended is escaped.

        A value or key carrying ``&`` or ``=`` must not become a separate query
        parameter, for ``query_parameters`` or for client-level defaults.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        client = httpx.AsyncClient(
            params={"cd": "x&role=admin"},
            transport=httpx.MockTransport(respond),
        )
        handler = DefaultHttpRequestHandler(client=client)
        try:
            await handler.send(
                HttpRequestInfo(
                    method="GET",
                    url="https://api.example.test/s?a=1",
                    query_parameters={"q": "v&role=admin", "k&evil": "1"},
                )
            )
        finally:
            await handler.aclose()
            await client.aclose()

        assert captured["req"].url.raw_path == (b"/s?a=1&q=v%26role%3Dadmin&k%26evil=1&cd=x%26role%3Dadmin")

    @pytest.mark.asyncio
    async def test_encoded_space_in_a_signed_value_is_not_rewritten(self) -> None:
        """An encoded space in a query value must not become ``+``.

        This is the transformation that actually breaks a signature. Measured against
        httpx 0.28.1, routing the query through ``QueryParams`` rewrote
        ``filename%3D%22a%20b.txt%22`` as ``filename%3D%22a+b.txt%22``, which changes
        the bytes any scheme signing that parameter computed its HMAC over.
        """
        captured: dict[str, httpx.Request] = {}

        def respond(request: httpx.Request) -> httpx.Response:
            captured["req"] = request
            return httpx.Response(200, text="ok")

        signed = b"response-content-disposition=attachment%3B%20filename%3D%22a%20b.txt%22"
        handler = _make_handler(httpx.MockTransport(respond))
        try:
            await handler.send(HttpRequestInfo(method="GET", url="https://api.example.test/o?" + signed.decode()))
        finally:
            await handler.aclose()

        assert captured["req"].url.raw_path == b"/o?" + signed
