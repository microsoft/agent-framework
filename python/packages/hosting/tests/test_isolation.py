# Copyright (c) Microsoft. All rights reserved.

"""Tests for the per-request isolation contextvar surface in
:mod:`agent_framework_hosting._isolation`.

The isolation keys are the ONLY seam Foundry-aware providers use to
find partition keys, and the host's ASGI middleware lifts them off the
two well-known headers on every inbound HTTP request. A regression
that drops the lookup, mistypes a header name, or fails to reset the
contextvar would silently misroute writes / leak per-request state
across requests, with zero unit-test signal — so cover the surface
fully here.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route
from starlette.testclient import TestClient

from agent_framework_hosting import (
    Channel,
    ChannelContext,
    ChannelContribution,
    IsolationKeys,
    get_current_isolation_keys,
    reset_current_isolation_keys,
    set_current_isolation_keys,
)
from agent_framework_hosting._isolation import (  # pyright: ignore[reportPrivateUsage]
    ISOLATION_HEADER_CHAT,
    ISOLATION_HEADER_USER,
    current_isolation_keys,
)


class TestIsolationKeys:
    def test_defaults_to_none_pair(self) -> None:
        keys = IsolationKeys()
        assert keys.user_key is None
        assert keys.chat_key is None
        assert keys.is_empty is True

    def test_partial_with_only_user_is_not_empty(self) -> None:
        keys = IsolationKeys(user_key="alice")
        assert keys.user_key == "alice"
        assert keys.chat_key is None
        assert keys.is_empty is False

    def test_partial_with_only_chat_is_not_empty(self) -> None:
        keys = IsolationKeys(chat_key="general")
        assert keys.is_empty is False

    def test_full_pair_is_not_empty(self) -> None:
        keys = IsolationKeys(user_key="alice", chat_key="general")
        assert keys.is_empty is False


class TestContextVarHelpers:
    def test_default_is_none(self) -> None:
        # Each test gets a fresh contextvar value because pytest runs
        # tests in fresh contexts. ``get`` returns the default.
        assert get_current_isolation_keys() is None

    def test_set_and_get_round_trip(self) -> None:
        token = set_current_isolation_keys(IsolationKeys(user_key="alice", chat_key="general"))
        try:
            current = get_current_isolation_keys()
            assert current is not None
            assert current.user_key == "alice"
            assert current.chat_key == "general"
        finally:
            reset_current_isolation_keys(token)
        # Reset restores prior value (None in the default context).
        assert get_current_isolation_keys() is None

    def test_set_with_none_clears(self) -> None:
        outer = set_current_isolation_keys(IsolationKeys(user_key="alice"))
        try:
            inner = set_current_isolation_keys(None)
            try:
                assert get_current_isolation_keys() is None
            finally:
                reset_current_isolation_keys(inner)
            # Reset surfaces the outer value again.
            current = get_current_isolation_keys()
            assert current is not None
            assert current.user_key == "alice"
        finally:
            reset_current_isolation_keys(outer)

    def test_module_level_contextvar_is_the_same_instance(self) -> None:
        """Direct contextvar access (used by the ASGI middleware) and the
        public `get_current_isolation_keys()` helper read from the SAME
        underlying contextvar. A regression that introduced a second
        contextvar would silently break the middleware → provider hop."""
        token = current_isolation_keys.set(IsolationKeys(user_key="bob"))
        try:
            via_helper = get_current_isolation_keys()
            assert via_helper is not None
            assert via_helper.user_key == "bob"
        finally:
            current_isolation_keys.reset(token)


class TestHeaderConstants:
    """The two header names are part of the public contract — they
    match the ones the Foundry Hosted Agents runtime stamps on every
    inbound request. A typo here would silently misroute partition
    writes."""

    def test_user_header_value(self) -> None:
        assert ISOLATION_HEADER_USER == "x-agent-user-isolation-key"

    def test_chat_header_value(self) -> None:
        assert ISOLATION_HEADER_CHAT == "x-agent-chat-isolation-key"


# --------------------------------------------------------------------------- #
# End-to-end: ASGI middleware lifts the headers into the contextvar.
# --------------------------------------------------------------------------- #


class _IsolationProbeChannel:
    """A minimal Channel that exposes a single GET route which captures
    the contextvar value INSIDE the request and returns it as JSON.

    Tests use this to exercise the full middleware → contextvar →
    handler hop end-to-end.
    """

    name = "probe"
    path = ""

    def __init__(self) -> None:
        self.captured: list[IsolationKeys | None] = []

        async def _handler(_request: Request) -> JSONResponse:
            keys = get_current_isolation_keys()
            self.captured.append(keys)
            payload = (
                {"user": keys.user_key, "chat": keys.chat_key}
                if keys is not None
                else {"user": None, "chat": None, "_present": False}
            )
            return JSONResponse(payload)

        self._routes: list[BaseRoute] = [Route("/probe", _handler)]

    def contribute(self, _context: ChannelContext) -> ChannelContribution:
        return ChannelContribution(routes=self._routes)


def _make_host_with_probe() -> tuple[object, _IsolationProbeChannel]:
    from agent_framework_hosting import AgentFrameworkHost

    class _NoopAgent:
        async def run(self, *_args: object, **_kwargs: object) -> object:  # pragma: no cover - never called
            raise RuntimeError("not invoked")

    probe = _IsolationProbeChannel()
    assert isinstance(probe, Channel)
    host = AgentFrameworkHost(target=_NoopAgent(), channels=[probe])  # type: ignore[arg-type]
    return host, probe


class TestIsolationMiddlewareEndToEnd:
    def test_both_headers_lifted_into_contextvar(self) -> None:
        host, probe = _make_host_with_probe()
        with TestClient(host.app) as client:  # type: ignore[attr-defined]
            r = client.get(
                "/probe",
                headers={
                    ISOLATION_HEADER_USER: "alice-uid",
                    ISOLATION_HEADER_CHAT: "general-cid",
                },
            )
        assert r.status_code == 200
        assert r.json() == {"user": "alice-uid", "chat": "general-cid"}
        assert len(probe.captured) == 1
        captured = probe.captured[0]
        assert captured is not None
        assert captured.user_key == "alice-uid"
        assert captured.chat_key == "general-cid"

    def test_only_user_header_lifted(self) -> None:
        """One-header-only branch: the middleware still binds (chat=None)."""
        host, probe = _make_host_with_probe()
        with TestClient(host.app) as client:  # type: ignore[attr-defined]
            r = client.get("/probe", headers={ISOLATION_HEADER_USER: "alice-uid"})
        assert r.status_code == 200
        assert r.json() == {"user": "alice-uid", "chat": None}

    def test_only_chat_header_lifted(self) -> None:
        host, probe = _make_host_with_probe()
        with TestClient(host.app) as client:  # type: ignore[attr-defined]
            r = client.get("/probe", headers={ISOLATION_HEADER_CHAT: "general-cid"})
        assert r.status_code == 200
        assert r.json() == {"user": None, "chat": "general-cid"}

    def test_no_headers_keeps_contextvar_none(self) -> None:
        """Local-dev path: with neither header present the middleware is
        a no-op and the contextvar stays at its default ``None`` —
        providers see "no isolation" and route to the in-memory
        fallback rather than picking up stale per-request state."""
        host, probe = _make_host_with_probe()
        with TestClient(host.app) as client:  # type: ignore[attr-defined]
            r = client.get("/probe")
        assert r.status_code == 200
        assert r.json() == {"user": None, "chat": None, "_present": False}
        assert probe.captured == [None]

    def test_empty_header_value_treated_as_absent(self) -> None:
        """A header that's present but empty must not bind an empty key —
        ``IsolationContext`` rejects empty strings on the read side."""
        host, probe = _make_host_with_probe()
        with TestClient(host.app) as client:  # type: ignore[attr-defined]
            r = client.get(
                "/probe",
                headers={
                    ISOLATION_HEADER_USER: "",
                    ISOLATION_HEADER_CHAT: "general-cid",
                },
            )
        assert r.status_code == 200
        # Empty user header decodes to None; chat key stays bound.
        assert r.json() == {"user": None, "chat": "general-cid"}

    def test_contextvar_resets_after_request(self) -> None:
        """The middleware must call ``reset_current_isolation_keys`` in
        a ``finally`` so per-request state never leaks across requests
        or back into the calling thread's context."""
        host, probe = _make_host_with_probe()
        with TestClient(host.app) as client:  # type: ignore[attr-defined]
            r1 = client.get("/probe", headers={ISOLATION_HEADER_USER: "alice-uid"})
            assert r1.status_code == 200
            # Reading the contextvar OUTSIDE the request scope must see
            # the default — not the value the prior request bound.
            assert get_current_isolation_keys() is None
            # And a follow-up request without headers gets a clean
            # ``None`` rather than inheriting alice-uid.
            r2 = client.get("/probe")
            assert r2.json() == {"user": None, "chat": None, "_present": False}

    def test_concurrent_requests_get_isolated_contextvars(self) -> None:
        """Different requests run in different async contexts; binding
        from request A must NOT leak into a concurrent request B."""
        host, probe = _make_host_with_probe()

        async def _drive() -> None:
            # Run two requests in parallel asyncio tasks against the
            # same TestClient and assert their captures don't bleed
            # into each other.
            async def _hit(user_key: str) -> dict[str, str | None]:
                with TestClient(host.app) as client:  # type: ignore[attr-defined]
                    r = client.get("/probe", headers={ISOLATION_HEADER_USER: user_key})
                return r.json()  # type: ignore[no-any-return]

            r_alice, r_bob = await asyncio.gather(_hit("alice-uid"), _hit("bob-uid"))
            assert r_alice == {"user": "alice-uid", "chat": None}
            assert r_bob == {"user": "bob-uid", "chat": None}

        asyncio.run(_drive())


class TestNonHttpScopesPassThrough:
    """The middleware intentionally only inspects ``http`` scopes;
    lifespan / websocket scopes are forwarded untouched. A regression
    that touched lifespan scopes here would crash boot."""

    @pytest.mark.asyncio
    async def test_lifespan_scope_does_not_consult_headers(self) -> None:
        # The TestClient context manager exercises the lifespan scope
        # implicitly; if the middleware tried to decode headers on a
        # non-http scope this would raise. Exercise it without binding
        # any contextvar work.
        host, _probe = _make_host_with_probe()
        with TestClient(host.app):  # type: ignore[attr-defined]
            # Just enter / exit; no requests.
            pass
