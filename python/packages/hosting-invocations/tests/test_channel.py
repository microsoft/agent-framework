# Copyright (c) Microsoft. All rights reserved.

"""End-to-end tests for :class:`InvocationsChannel`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

from agent_framework_hosting import AgentFrameworkHost, ChannelRequest
from starlette.testclient import TestClient

from agent_framework_hosting_invocations import InvocationsChannel


@dataclass
class _FakeAgentResponse:
    text: str


@dataclass
class _FakeUpdate:
    text: str


class _FakeStream:
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
    def __init__(self, reply: str = "hi", chunks: list[str] | None = None) -> None:
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


def _make_client(agent: _FakeAgent | None = None) -> tuple[TestClient, _FakeAgent]:
    agent = agent or _FakeAgent()
    host = AgentFrameworkHost(target=agent, channels=[InvocationsChannel()])
    return TestClient(host.app), agent


class TestInvocations:
    def test_post_invoke_returns_response(self) -> None:
        client, _agent = _make_client(_FakeAgent(reply="pong"))
        with client:
            r = client.post("/invocations/invoke", json={"message": "ping"})
        assert r.status_code == 200
        assert r.json() == {"response": "pong", "session_id": None}

    def test_session_id_propagates_to_target(self) -> None:
        client, agent = _make_client()
        with client:
            r = client.post("/invocations/invoke", json={"message": "x", "session_id": "s1"})
        assert r.status_code == 200
        assert r.json()["session_id"] == "s1"
        sess = agent.calls[0]["kwargs"].get("session")
        # Host converts ChannelSession.isolation_key -> AgentSession via
        # target.create_session(session_id=...). Our fake stashes that here.
        assert sess is not None
        assert sess["session_id"] == "invocations:s1"

    def test_invalid_json_returns_400(self) -> None:
        client, _ = _make_client()
        with client:
            r = client.post(
                "/invocations/invoke",
                content=b"{not json",
                headers={"content-type": "application/json"},
            )
        assert r.status_code == 400

    def test_empty_message_returns_422(self) -> None:
        client, _ = _make_client()
        with client:
            r = client.post("/invocations/invoke", json={"message": ""})
        assert r.status_code == 422

    def test_non_string_session_id_returns_422(self) -> None:
        client, _ = _make_client()
        with client:
            r = client.post("/invocations/invoke", json={"message": "x", "session_id": 1})
        assert r.status_code == 422

    def test_non_object_body_returns_422(self) -> None:
        client, _ = _make_client()
        with client:
            r = client.post("/invocations/invoke", json=[])
        assert r.status_code == 422

    def test_streaming_emits_data_lines_and_done(self) -> None:
        agent = _FakeAgent(chunks=["hel", "lo"])
        host = AgentFrameworkHost(target=agent, channels=[InvocationsChannel()])
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        body = r.text
        assert "data: hel" in body
        assert "data: lo" in body
        assert body.rstrip().endswith("data: [DONE]")

    def test_run_hook_can_rewrite_request(self) -> None:
        captured: list[ChannelRequest] = []

        async def hook(req: ChannelRequest, **_: Any) -> ChannelRequest:
            captured.append(req)
            # Force stream off even if requested.
            return replace(req, stream=False)

        agent = _FakeAgent(reply="ok")
        host = AgentFrameworkHost(target=agent, channels=[InvocationsChannel(run_hook=hook)])
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        # Even though caller asked for stream=True, hook flipped it off — so
        # we get JSON back, not SSE.
        assert r.headers["content-type"].startswith("application/json")
        assert captured and captured[0].channel == "invocations"

    def test_stream_transform_hook_can_rewrite_chunks(self) -> None:
        agent = _FakeAgent(chunks=["foo", "bar"])

        def transform(update: Any) -> Any:
            return _FakeUpdate(text=update.text.upper())

        host = AgentFrameworkHost(
            target=agent,
            channels=[InvocationsChannel(stream_transform_hook=transform)],
        )
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        body = r.text
        assert "data: FOO" in body
        assert "data: BAR" in body
        assert "data: foo" not in body

    def test_stream_transform_hook_can_drop_chunks(self) -> None:
        agent = _FakeAgent(chunks=["keep", "drop", "keep2"])

        def transform(update: Any) -> Any:
            return None if update.text == "drop" else update

        host = AgentFrameworkHost(
            target=agent,
            channels=[InvocationsChannel(stream_transform_hook=transform)],
        )
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        body = r.text
        assert "data: keep" in body
        assert "data: keep2" in body
        assert "data: drop" not in body

    def test_stream_transform_hook_supports_async(self) -> None:
        agent = _FakeAgent(chunks=["aa"])

        async def transform(update: Any) -> Any:
            return _FakeUpdate(text=update.text + "!")

        host = AgentFrameworkHost(
            target=agent,
            channels=[InvocationsChannel(stream_transform_hook=transform)],
        )
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        assert "data: aa!" in r.text

    def test_streaming_chunk_with_crlf_splits_into_separate_data_lines(self) -> None:
        # Per SSE spec, ``\r``, ``\n`` and ``\r\n`` are all line terminators;
        # a chunk like ``"line1\r\nline2"`` must produce two ``data:`` lines,
        # not one ``data:`` line containing an embedded ``\r``.
        agent = _FakeAgent(chunks=["line1\r\nline2"])
        host = AgentFrameworkHost(target=agent, channels=[InvocationsChannel()])
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        body = r.text
        assert "data: line1\n" in body
        assert "data: line2\n" in body
        assert "\r" not in body.split("data: [DONE]")[0]

    def test_streaming_finalize_error_emits_error_frame_no_done(self) -> None:
        # ``get_final_response()`` is what triggers history-provider
        # persistence on the agent side; if it fails we must surface that
        # to the client as ``event: error`` rather than emitting ``[DONE]``
        # as if the run completed cleanly.
        class _FailingFinalStream(_FakeStream):
            async def get_final_response(self) -> _FakeAgentResponse:
                raise RuntimeError("history backend exploded")

        class _AgentWithFailingFinal(_FakeAgent):
            def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
                self.calls.append({"messages": messages, "stream": stream, "kwargs": kwargs})
                if stream:
                    return _FailingFinalStream(["partial"])
                return super().run(messages, stream=stream, **kwargs)

        agent = _AgentWithFailingFinal()
        host = AgentFrameworkHost(target=agent, channels=[InvocationsChannel()])
        with TestClient(host.app) as client:
            r = client.post("/invocations/invoke", json={"message": "x", "stream": True})
        assert r.status_code == 200
        body = r.text
        assert "data: partial" in body
        assert "event: error" in body
        assert "history backend exploded" in body
        assert "[DONE]" not in body
