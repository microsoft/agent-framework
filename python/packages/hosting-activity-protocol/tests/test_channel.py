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
        # Bot Framework still expects 200 to dequeue.
        assert r.status_code == 200
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
