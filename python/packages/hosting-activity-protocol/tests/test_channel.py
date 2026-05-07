# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :mod:`agent_framework_hosting_activity_protocol`.

The Bot Framework outbound calls and azure-identity credentials are mocked
out so the suite never touches the network. Live token acquisition,
streaming edits and certificate paths are out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework_hosting import AgentFrameworkHost
from starlette.testclient import TestClient

from agent_framework_hosting_activity_protocol import ActivityProtocolChannel, activity_protocol_isolation_key
from agent_framework_hosting_activity_protocol._channel import _parse_activity


def test_activity_protocol_isolation_key_format() -> None:
    assert activity_protocol_isolation_key("19:meeting_xyz@thread.v2") == "activity:19:meeting_xyz@thread.v2"
    assert activity_protocol_isolation_key(123) == "activity:123"


class TestParseActivity:
    def test_text_only(self) -> None:
        msg = _parse_activity({"type": "message", "text": "hello"})
        assert msg.role == "user"
        assert msg.text == "hello"

    def test_with_attachment(self) -> None:
        msg = _parse_activity({
            "type": "message",
            "text": "see this",
            "attachments": [
                {"contentType": "image/png", "contentUrl": "https://example.com/x.png"},
            ],
        })
        assert msg.text == "see this"
        assert any((getattr(c, "uri", None) or "").endswith("/x.png") for c in msg.contents)

    def test_skips_invalid_attachments(self) -> None:
        msg = _parse_activity({
            "type": "message",
            "text": "hi",
            "attachments": [
                "not-a-mapping",
                {"contentType": "image/png"},  # no url
                {"contentUrl": "https://example.com/y", "contentType": "no-slash"},
            ],
        })
        assert msg.text == "hi"
        # No URI content survived.
        assert not any(getattr(c, "uri", None) for c in msg.contents)


@dataclass
class _FakeAgentResponse:
    text: str


class _FakeAgent:
    def __init__(self, reply: str = "ok") -> None:
        self._reply = reply
        self.runs: list[Any] = []

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        self.runs.append({"messages": messages, "stream": stream, "kwargs": kwargs})

        async def _coro() -> _FakeAgentResponse:
            return _FakeAgentResponse(text=self._reply)

        return _coro()


def _make_teams(stream: bool = False) -> tuple[ActivityProtocolChannel, _FakeAgent]:
    agent = _FakeAgent("hi there")
    ch = ActivityProtocolChannel(stream=stream, send_typing_action=False)
    fake_http = MagicMock()
    response_mock = MagicMock()
    response_mock.raise_for_status = MagicMock()
    response_mock.json = MagicMock(return_value={"id": "act-1"})
    fake_http.post = AsyncMock(return_value=response_mock)
    fake_http.put = AsyncMock(return_value=response_mock)
    fake_http.aclose = AsyncMock()
    ch._http = fake_http
    return ch, agent


_VALID_ACTIVITY: dict[str, Any] = {
    "type": "message",
    "id": "in-1",
    "text": "hello bot",
    "conversation": {"id": "19:meeting_xyz@thread.v2"},
    "from": {"id": "user-1"},
    "recipient": {"id": "bot-1"},
    "channelId": "msteams",
    "serviceUrl": "https://smba.trafficmanager.net/amer/",
}


class TestTeamsWebhook:
    def test_message_activity_dispatches_to_agent(self) -> None:
        ch, agent = _make_teams()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=_VALID_ACTIVITY)
        assert r.status_code == 200
        assert agent.runs, "expected the agent to be invoked"
        # And the channel posted a reply back to the conversation URL.
        assert ch._http is not None
        ch._http.post.assert_called()  # type: ignore[attr-defined]
        url, _ = ch._http.post.call_args[0], ch._http.post.call_args[1]  # type: ignore[attr-defined] # noqa: F841
        assert "/v3/conversations/" in ch._http.post.call_args[0][0]  # type: ignore[attr-defined]

    def test_non_message_activities_are_acked(self) -> None:
        ch, agent = _make_teams()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post(
                "/activity/messages",
                json={"type": "conversationUpdate", "conversation": {"id": "x"}},
            )
        assert r.status_code == 202
        assert not agent.runs

    def test_invalid_json_returns_400(self) -> None:
        ch, agent = _make_teams()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post(
                "/activity/messages",
                content=b"not-json",
                headers={"content-type": "application/json"},
            )
        assert r.status_code == 400
        assert not agent.runs

    def test_message_missing_serviceurl_is_dropped(self) -> None:
        ch, agent = _make_teams()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        bad = dict(_VALID_ACTIVITY)
        bad.pop("serviceUrl")
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=bad)
        # No serviceUrl → fails the allow-list check (None doesn't match
        # any allowed host suffix), surfaced as 400 so a misconfigured
        # caller knows the activity was structurally invalid.
        assert r.status_code == 400
        assert not agent.runs


@pytest.mark.asyncio
class TestOutbound:
    async def test_send_message_posts_to_conversation_url(self) -> None:
        ch, _agent = _make_teams()
        await ch._send_message(_VALID_ACTIVITY, "hi")
        assert ch._http is not None
        ch._http.post.assert_called()  # type: ignore[attr-defined]
        url = ch._http.post.call_args[0][0]  # type: ignore[attr-defined]
        assert "/v3/conversations/" in url
        body = ch._http.post.call_args[1]["json"]  # type: ignore[attr-defined]
        assert body["text"] == "hi"


class TestConfig:
    def test_rejects_both_secret_and_certificate(self) -> None:
        with pytest.raises(ValueError, match="not both"):
            ActivityProtocolChannel(
                app_id="x",
                app_password="s",
                certificate_path="/tmp/does-not-exist.pem",
            )

    def test_dev_mode_no_credential(self) -> None:
        ch = ActivityProtocolChannel()
        assert ch._credential is None


class TestServiceUrlAllowList:
    """``serviceUrl`` is supplied by the inbound activity and the channel
    POSTs a real bearer token to it — anything outside the Bot Framework
    host suffixes must be rejected so a malicious caller can't redirect
    outbound replies to an attacker-controlled host."""

    def test_default_allows_smba_trafficmanager(self) -> None:
        ch = ActivityProtocolChannel()
        assert ch._is_service_url_allowed("https://smba.trafficmanager.net/amer/")
        assert ch._is_service_url_allowed("https://emea.smba.trafficmanager.net/")
        assert ch._is_service_url_allowed("https://api.botframework.com/")

    def test_default_rejects_arbitrary_host(self) -> None:
        ch = ActivityProtocolChannel()
        assert not ch._is_service_url_allowed("https://attacker.example.com/")
        assert not ch._is_service_url_allowed("https://botframework.com.attacker.com/")
        assert not ch._is_service_url_allowed("")
        assert not ch._is_service_url_allowed(None)

    def test_custom_allowlist(self) -> None:
        ch = ActivityProtocolChannel(service_url_allowed_hosts=("internal.contoso.com",))
        assert ch._is_service_url_allowed("https://internal.contoso.com/v3/")
        assert ch._is_service_url_allowed("https://eu.internal.contoso.com/")
        assert not ch._is_service_url_allowed("https://smba.trafficmanager.net/")

    def test_empty_allowlist_disables_check(self) -> None:
        ch = ActivityProtocolChannel(service_url_allowed_hosts=())
        assert ch._is_service_url_allowed("https://anywhere.example.org/")

    def test_webhook_rejects_disallowed_serviceurl(self) -> None:
        ch, agent = _make_teams()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        bad = dict(_VALID_ACTIVITY)
        bad["serviceUrl"] = "https://attacker.example.com/v3/"
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=bad)
        assert r.status_code == 400
        assert not agent.runs
        # No outbound POST attempted with a bearer token.
        assert ch._http is not None
        ch._http.post.assert_not_called()  # type: ignore[attr-defined]


class TestInboundAuthValidator:
    def test_allow_passes_through(self) -> None:
        async def allow(_req: Any) -> bool:
            return True

        ch, agent = _make_teams()
        ch._inbound_auth_validator = allow
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=_VALID_ACTIVITY)
        assert r.status_code == 200
        assert agent.runs

    def test_reject_returns_401(self) -> None:
        async def deny(_req: Any) -> bool:
            return False

        ch, agent = _make_teams()
        ch._inbound_auth_validator = deny
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=_VALID_ACTIVITY)
        assert r.status_code == 401
        assert not agent.runs

    def test_validator_raises_returns_401(self) -> None:
        async def boom(_req: Any) -> bool:
            raise RuntimeError("validator broke")

        ch, agent = _make_teams()
        ch._inbound_auth_validator = boom
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=_VALID_ACTIVITY)
        assert r.status_code == 401
        assert not agent.runs


@pytest.mark.asyncio
class TestOutboundAuthHeader:
    async def test_no_credential_sends_no_authorization_header(self) -> None:
        ch, _agent = _make_teams()
        # Default _make_teams has no credential — dev mode.
        await ch._send_message(_VALID_ACTIVITY, "hi")
        assert ch._http is not None
        headers = ch._http.post.call_args[1]["headers"]  # type: ignore[attr-defined]
        assert "Authorization" not in headers

    async def test_with_credential_sends_bearer_token(self) -> None:
        ch, _agent = _make_teams()
        # Inject a fake credential with a fixed token.
        token_obj = MagicMock()
        token_obj.token = "tok-abc123"
        cred = MagicMock()
        cred.get_token = AsyncMock(return_value=token_obj)
        ch._credential = cred  # type: ignore[assignment]
        await ch._send_message(_VALID_ACTIVITY, "hi")
        assert ch._http is not None
        headers = ch._http.post.call_args[1]["headers"]  # type: ignore[attr-defined]
        assert headers.get("Authorization") == "Bearer tok-abc123"


class TestRetrySignal:
    """Distinguish transient outbound failures (network / 5xx) — which
    must surface 502 so Bot Service retries — from deterministic agent
    failures (which must return 200 to avoid retry loops)."""

    def test_outbound_http_error_returns_502(self) -> None:
        import httpx as _httpx

        ch, agent = _make_teams()
        # Make _send_message raise a transient httpx error.
        assert ch._http is not None
        ch._http.post = AsyncMock(side_effect=_httpx.ConnectError("nope"))  # type: ignore[attr-defined]
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=_VALID_ACTIVITY)
        assert r.status_code == 502

    def test_deterministic_agent_failure_returns_200(self) -> None:
        ch, agent = _make_teams()

        def boom(messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
            async def _coro() -> Any:
                raise ValueError("agent crashed")

            return _coro()

        agent.run = boom  # type: ignore[assignment]
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post("/activity/messages", json=_VALID_ACTIVITY)
        # Deterministic failure → 200 (Bot Service does not retry the same
        # broken activity in a loop).
        assert r.status_code == 200


@pytest.mark.asyncio
class TestStreaming:
    async def test_stream_sends_placeholder_and_edits(self) -> None:
        ch, _agent = _make_teams(stream=True)

        # Build a fake stream that emits two text chunks then finalizes.
        @dataclass
        class _Up:
            text: str

        class _Stream:
            def __init__(self) -> None:
                self._chunks = ["hel", "lo"]

            def __aiter__(self) -> Any:
                async def gen() -> Any:
                    for c in self._chunks:
                        yield _Up(c)

                return gen()

            async def get_final_response(self) -> Any:
                return _FakeAgentResponse(text="hello")

        # Use a tight throttle so the test doesn't sit on `wait_for`.
        ch._stream_edit_min_interval = 0.0
        await ch._stream_to_conversation(_VALID_ACTIVITY, _Stream())  # type: ignore[arg-type]
        assert ch._http is not None
        # Placeholder POST + at least one final PUT.
        ch._http.post.assert_called()  # type: ignore[attr-defined]
        ch._http.put.assert_called()  # type: ignore[attr-defined]
        # Final edit body carries the full accumulated text.
        last_put_body = ch._http.put.call_args[1]["json"]  # type: ignore[attr-defined]
        assert last_put_body["text"] == "hello"

    async def test_stream_placeholder_failure_falls_back_to_single_post(self) -> None:
        # The bug: when send_initial_placeholder fails, activity_id stays
        # None, the edit_worker can never reach its exit condition
        # (`accumulated == last_sent` while no PUT possible) and the
        # whole conversation deadlocks. After the fix we fall back to
        # buffering the stream and POSTing a single final activity.
        ch, _agent = _make_teams(stream=True)
        # Make the FIRST POST (placeholder) raise; subsequent POST (final
        # fallback) succeeds.
        import httpx as _httpx

        ok_response = MagicMock()
        ok_response.raise_for_status = MagicMock()
        ok_response.json = MagicMock(return_value={"id": "act-final"})
        ok_response.content = b"{}"
        post_mock = AsyncMock(side_effect=[_httpx.HTTPError("boom"), ok_response])
        assert ch._http is not None
        ch._http.post = post_mock  # type: ignore[attr-defined]

        @dataclass
        class _Up:
            text: str

        class _Stream:
            def __aiter__(self) -> Any:
                async def gen() -> Any:
                    yield _Up("partial-1")
                    yield _Up("-partial-2")

                return gen()

            async def get_final_response(self) -> Any:
                return _FakeAgentResponse(text="partial-1-partial-2")

        ch._stream_edit_min_interval = 0.0
        # Should NOT hang. Use asyncio.wait_for with a small timeout to
        # guard the test against future regressions of the deadlock.
        import asyncio as _asyncio

        await _asyncio.wait_for(
            ch._stream_to_conversation(_VALID_ACTIVITY, _Stream()),  # type: ignore[arg-type]
            timeout=2.0,
        )
        # Two POSTs total: placeholder (failed) + fallback final.
        assert post_mock.await_count == 2
        # Fallback POST contains the full accumulated text.
        fallback_body = post_mock.call_args[1]["json"]
        assert fallback_body["text"] == "partial-1-partial-2"

    async def test_stream_with_no_text_replaces_placeholder(self) -> None:
        ch, _agent = _make_teams(stream=True)

        class _EmptyStream:
            def __aiter__(self) -> Any:
                async def gen() -> Any:
                    if False:
                        yield None  # type: ignore[unreachable]

                return gen()

            async def get_final_response(self) -> Any:
                return _FakeAgentResponse(text="")

        ch._stream_edit_min_interval = 0.0
        await ch._stream_to_conversation(_VALID_ACTIVITY, _EmptyStream())  # type: ignore[arg-type]
        # The placeholder PUT-replaces with "(no response)" so the user
        # isn't left staring at "…".
        assert ch._http is not None
        last_put_body = ch._http.put.call_args[1]["json"]  # type: ignore[attr-defined]
        assert last_put_body["text"] == "(no response)"
