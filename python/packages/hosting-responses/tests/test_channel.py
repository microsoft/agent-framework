# Copyright (c) Microsoft. All rights reserved.

"""End-to-end tests for :class:`ResponsesChannel` via Starlette's ``TestClient``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelIdentity,
    HostedRunResult,
)
from starlette.testclient import TestClient

from agent_framework_hosting_responses import ResponsesChannel

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeAgentResponse:
    text: str


@dataclass
class _FakeUpdate:
    text: str


class _FakeStream:
    """Minimal stand-in for AF's ``ResponseStream`` returned by ``run(stream=True)``."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self._final = _FakeAgentResponse(text="".join(chunks))

    def __aiter__(self) -> AsyncIterator[_FakeUpdate]:
        async def _gen() -> AsyncIterator[_FakeUpdate]:
            for c in self._chunks:
                yield _FakeUpdate(c)

        return _gen()

    async def get_final_response(self) -> _FakeAgentResponse:
        return self._final


class _FakeAgent:
    def __init__(self, reply: str = "hello", chunks: list[str] | None = None) -> None:
        self._reply = reply
        self._chunks = chunks or [reply]
        self.calls: list[dict[str, Any]] = []

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "kwargs": kwargs})
        if stream:
            return _FakeStream(self._chunks)

        async def _coro() -> _FakeAgentResponse:
            return _FakeAgentResponse(text=self._reply)

        return _coro()


class _RecordingPushChannel:
    name = "telegram"
    path = "/telegram"

    def __init__(self) -> None:
        self.pushes: list[tuple[ChannelIdentity, HostedRunResult]] = []

    def contribute(self, _ctx: Any) -> Any:
        from agent_framework_hosting import ChannelContribution

        return ChannelContribution()

    async def push(self, identity: ChannelIdentity, payload: HostedRunResult) -> None:
        self.pushes.append((identity, payload))


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def _make_client(agent: _FakeAgent | None = None) -> tuple[TestClient, AgentFrameworkHost, _FakeAgent]:
    agent = agent or _FakeAgent()
    host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel()])
    return TestClient(host.app), host, agent


class TestResponsesChannelNonStreaming:
    def test_post_responses_returns_completed_envelope(self) -> None:
        client, _host, agent = _make_client(_FakeAgent(reply="hi back"))
        with client:
            r = client.post("/responses", json={"input": "hi"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["object"] == "response"
        assert body["id"].startswith("resp_")
        assert body["output"][0]["content"][0]["text"] == "hi back"
        assert len(agent.calls) == 1

    def test_invalid_json_returns_400(self) -> None:
        client, *_ = _make_client()
        with client:
            r = client.post("/responses", content=b"{not json", headers={"content-type": "application/json"})
        assert r.status_code == 400

    def test_invalid_input_returns_422(self) -> None:
        client, *_ = _make_client()
        with client:
            r = client.post("/responses", json={"input": 42})
        assert r.status_code == 422

    def test_options_propagate_to_target_run(self) -> None:
        client, _host, agent = _make_client()
        with client:
            r = client.post("/responses", json={"input": "x", "temperature": 0.5, "max_output_tokens": 64})
        assert r.status_code == 200
        opts = agent.calls[0]["kwargs"]["options"]
        assert opts == {"temperature": 0.5, "max_tokens": 64}

    def test_previous_response_id_creates_session(self) -> None:
        client, _host, agent = _make_client()
        with client:
            client.post("/responses", json={"input": "x", "previous_response_id": "resp_42"})
        # AgentFrameworkHost converts the channel session into an AgentSession.
        sess = agent.calls[0]["kwargs"].get("session")
        assert sess is not None
        # _FakeAgent.create_session stashes the session_id on the dict it returns.
        assert sess["session_id"] == "resp_42"

    def test_chat_isolation_header_creates_session_when_no_prev_id(self) -> None:
        """Foundry-style ``x-agent-chat-isolation-key`` falls back to a session anchor.

        First-turn requests have no ``previous_response_id`` (the client
        doesn't have one yet), but Foundry Hosted Agents always inject
        the isolation headers. The channel must derive a session from the
        chat key so the host can build a stable per-conversation session
        that history providers persist under.
        """
        client, _host, agent = _make_client()
        with client:
            client.post(
                "/responses",
                json={"input": "x"},
                headers={"x-agent-chat-isolation-key": "chat-abc"},
            )
        sess = agent.calls[0]["kwargs"].get("session")
        assert sess is not None
        assert sess["session_id"] == "chat-abc"

    def test_prev_response_id_wins_over_chat_isolation_header(self) -> None:
        """When both anchors are present, ``previous_response_id`` wins.

        ``previous_response_id`` is the protocol-native chain anchor; the
        header fallback is only meant to bootstrap when no protocol
        anchor exists.
        """
        client, _host, agent = _make_client()
        with client:
            client.post(
                "/responses",
                json={"input": "x", "previous_response_id": "resp_99"},
                headers={"x-agent-chat-isolation-key": "chat-abc"},
            )
        sess = agent.calls[0]["kwargs"].get("session")
        assert sess is not None
        assert sess["session_id"] == "resp_99"

    def test_response_target_channel_returns_ack_text_when_pushed(self) -> None:
        agent = _FakeAgent(reply="real reply")
        push_ch = _RecordingPushChannel()
        host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel(), push_ch])

        with TestClient(host.app) as client:
            r = client.post(
                "/responses",
                json={
                    "input": "hi",
                    "response_target": "telegram:42",
                },
            )
        assert r.status_code == 200
        body = r.json()
        text = body["output"][0]["content"][0]["text"]
        assert "delivered out-of-band" in text
        assert "telegram:42" in text
        assert push_ch.pushes and push_ch.pushes[0][1].text == "real reply"
        assert push_ch.pushes[0][0].native_id == "42"


class TestResponsesChannelStreaming:
    def test_sse_emits_created_delta_completed(self) -> None:
        agent = _FakeAgent(reply="hello world", chunks=["hello", " ", "world"])
        host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel()])
        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi", "stream": True})
            assert r.status_code == 200
            body = r.text

        # SSE event lines look like "event: <type>\ndata: <json>\n\n".
        events = [line[len("event: ") :] for line in body.splitlines() if line.startswith("event: ")]
        assert events[0] == "response.created"
        assert events[-1] == "response.completed"
        assert events.count("response.output_text.delta") == 3

    def test_sse_emits_failed_when_stream_raises(self) -> None:
        # Regression: ResponseOutputMessage.status only accepts in_progress/
        # completed/incomplete, so building an OpenAIResponse with status="failed"
        # used to crash with a pydantic ValidationError. The channel must map the
        # nested message status to "incomplete" while keeping the top-level
        # Response.status="failed".
        class _BoomStream:
            def __aiter__(self) -> AsyncIterator[_FakeUpdate]:
                async def _gen() -> AsyncIterator[_FakeUpdate]:
                    yield _FakeUpdate("partial")
                    raise RuntimeError("upstream blew up")

                return _gen()

            async def get_final_response(self) -> _FakeAgentResponse:  # pragma: no cover
                return _FakeAgentResponse(text="")

        class _BoomAgent(_FakeAgent):
            def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
                self.calls.append({"messages": messages, "stream": stream, "kwargs": kwargs})
                if stream:
                    return _BoomStream()
                raise AssertionError("non-streaming path not exercised here")

        host = AgentFrameworkHost(target=_BoomAgent(), channels=[ResponsesChannel()])
        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi", "stream": True})
            assert r.status_code == 200
            body = r.text

        events = [line[len("event: ") :] for line in body.splitlines() if line.startswith("event: ")]
        assert events[0] == "response.created"
        assert events[-1] == "response.failed"
        # The failed envelope must serialize cleanly — i.e. no ValidationError raised.
        assert "upstream blew up" in body
