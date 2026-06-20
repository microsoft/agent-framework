# Copyright (c) Microsoft. All rights reserved.

"""End-to-end tests for :class:`ResponsesChannel` via Starlette's ``TestClient``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agent_framework_hosting import (
    AgentFrameworkHost,
    HostedRunResult,
)
from starlette.testclient import TestClient

from agent_framework_hosting_responses import ResponsesChannel
from agent_framework_hosting_responses._channel import _result_to_text  # pyright: ignore[reportPrivateUsage]

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


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def _make_client(
    agent: _FakeAgent | None = None,
    *,
    path: str = "/responses",
    response_id_factory: Any | None = None,
) -> tuple[TestClient, AgentFrameworkHost, _FakeAgent]:
    agent = agent or _FakeAgent()
    host = AgentFrameworkHost(
        target=agent,
        channels=[ResponsesChannel(path=path, response_id_factory=response_id_factory)],
    )
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
        assert isinstance(body["created_at"], int)
        assert body["output"][0]["content"][0]["text"] == "hi back"
        assert len(agent.calls) == 1

    def test_non_string_model_falls_back_to_agent(self) -> None:
        client, _host, _agent = _make_client(_FakeAgent(reply="hi"))
        with client:
            r = client.post("/responses", json={"input": "hi", "model": None})
        assert r.status_code == 200
        assert r.json()["model"] == "agent"

    def test_empty_path_mounts_at_app_root(self) -> None:
        client, _host, _agent = _make_client(_FakeAgent(reply="hi back"), path="")
        with client:
            r = client.post("/", json={"input": "hi"})
        assert r.status_code == 200
        assert r.json()["output"][0]["content"][0]["text"] == "hi back"

    def test_custom_path_mounts_route_under_host_path(self) -> None:
        client, _host, _agent = _make_client(_FakeAgent(reply="custom"), path="/api/responses")
        with client:
            r = client.post("/api/responses", json={"input": "hi"})
            missing = client.post("/api/responses/responses", json={"input": "hi"})
        assert r.status_code == 200
        assert r.json()["output"][0]["content"][0]["text"] == "custom"
        assert missing.status_code == 404

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

    def test_first_turn_response_id_creates_session(self) -> None:
        client, _host, agent = _make_client(response_id_factory=lambda *_: "resp_first")
        with client:
            client.post("/responses", json={"input": "x"})
        sess = agent.calls[0]["kwargs"].get("session")
        assert sess is not None
        assert sess["session_id"] == "resp_first"

    def test_chat_isolation_header_ignored_outside_foundry(self) -> None:
        client, _host, agent = _make_client(response_id_factory=lambda *_: "resp_local")
        with client:
            client.post(
                "/responses",
                json={"input": "x"},
                headers={"x-agent-chat-isolation-key": "chat-abc"},
            )
        sess = agent.calls[0]["kwargs"].get("session")
        assert sess is not None
        assert sess["session_id"] == "resp_local"

    def test_chat_isolation_header_creates_session_in_foundry(self, monkeypatch: Any) -> None:
        """Foundry-style ``x-agent-chat-isolation-key`` falls back to a session anchor.

        First-turn requests have no ``previous_response_id`` (the client
        doesn't have one yet), but Foundry Hosted Agents always inject
        the isolation headers. The channel must derive a session from the
        chat key so the host can build a stable per-conversation session
        that history providers persist under.
        """
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
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

    def test_prev_response_id_wins_over_chat_isolation_header(self, monkeypatch: Any) -> None:
        """When both anchors are present, ``previous_response_id`` wins.

        ``previous_response_id`` is the protocol-native chain anchor; the
        header fallback is only meant to bootstrap when no protocol
        anchor exists.
        """
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
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

    def test_response_hook_can_rewrite_originating_reply(self) -> None:
        seen_kwargs: list[dict[str, Any]] = []

        def hook(result: HostedRunResult, **kwargs: Any) -> HostedRunResult:
            seen_kwargs.append(dict(kwargs))
            return HostedRunResult(_FakeAgentResponse(text=result.result.text.upper()), session=result.session)

        agent = _FakeAgent(reply="hooked")
        host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel(response_hook=hook)])

        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi"})

        assert r.status_code == 200
        body = r.json()
        assert body["output"][0]["content"][0]["text"] == "HOOKED"
        assert seen_kwargs
        assert seen_kwargs[0]["channel_name"] == "responses"


class TestResultTextRendering:
    def test_result_text_prefers_text_property(self) -> None:
        assert _result_to_text(_FakeAgentResponse(text="plain")) == "plain"

    def test_result_text_projects_workflow_outputs(self) -> None:
        class _WorkflowResult:
            def get_outputs(self) -> list[Any]:
                return [_FakeAgentResponse(text="one"), " two"]

        assert _result_to_text(_WorkflowResult()) == "one two"

    def test_result_text_empty_outputs_falls_back_to_final_state(self) -> None:
        """When get_outputs() returns an empty list, fall back to get_final_state()."""

        class _EmptyOutputsResult:
            def get_outputs(self) -> list[Any]:
                return []

            def get_final_state(self) -> str:
                return "final state content"

        assert _result_to_text(_EmptyOutputsResult()) == "final state content"

    def test_result_text_empty_outputs_no_final_state_falls_back_to_str(self) -> None:
        """When get_outputs() is empty and no get_final_state(), use str()."""

        class _EmptyResult:
            def get_outputs(self) -> list[Any]:
                return []

            def __str__(self) -> str:
                return "stringified result"

        assert _result_to_text(_EmptyResult()) == "stringified result"

    def test_result_text_plain_string_uses_str(self) -> None:
        assert _result_to_text("just a string") == "just a string"


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

    def test_sse_transform_hook_can_rewrite_chunks(self) -> None:
        agent = _FakeAgent(reply="hello", chunks=["he", "llo"])

        def transform(update: _FakeUpdate) -> _FakeUpdate:
            return _FakeUpdate(text=update.text.upper())

        host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel(stream_update_hook=transform)])
        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi", "stream": True})

        assert r.status_code == 200
        assert '"delta":"HE"' in r.text
        assert '"delta":"LLO"' in r.text
        # Stream update hooks are update-only; they do not rewrite get_final_response().
        assert '"text":"hello"' in r.text

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
