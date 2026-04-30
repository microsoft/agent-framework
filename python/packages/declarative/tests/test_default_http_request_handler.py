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
            result = await handler.send(
                HttpRequestInfo(method="GET", url="https://api.example.test/x")
            )
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
        owned = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok"))
        )
        handler._owned_client = owned
        assert not owned.is_closed
        await handler.aclose()
        assert owned.is_closed

    @pytest.mark.asyncio
    async def test_caller_owned_client_is_not_closed(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok"))
        )
        handler = DefaultHttpRequestHandler(client=client)
        await handler.send(
            HttpRequestInfo(method="GET", url="https://api.example.test/x")
        )
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
                return original_ctor(
                    transport=httpx.MockTransport(
                        lambda r: httpx.Response(200, text="ok")
                    )
                )
            return original_ctor(*args, **kwargs)

        import agent_framework_declarative._workflows._http_handler as hh

        hh.httpx.AsyncClient = counting_ctor  # type: ignore[assignment]
        try:
            handler = DefaultHttpRequestHandler()
            try:
                await asyncio.gather(*[
                    handler.send(
                        HttpRequestInfo(method="GET", url="https://api.example.test/x")
                    )
                    for _ in range(8)
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
            result = await handler.send(
                HttpRequestInfo(method="GET", url="https://api.example.test/x")
            )
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
            result = await handler.send(
                HttpRequestInfo(method="GET", url="https://api.example.test/x")
            )
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
            owned = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok"))
            )
            handler._owned_client = owned
        assert owned.is_closed
