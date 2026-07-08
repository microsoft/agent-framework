# Copyright (c) Microsoft. All rights reserved.

"""End-to-end tests for :class:`ResponsesChannel` via Starlette's ``TestClient``."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ServiceSessionId
from agent_framework_hosting import (
    AgentFrameworkHost,
    HostedRunResult,
)
from opentelemetry import context as otel_context
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.testclient import TestClient

from agent_framework_hosting_responses import ResponsesChannel
from agent_framework_hosting_responses._channel import (  # pyright: ignore[reportPrivateUsage]
    _result_to_output_items,
    _result_to_text,
)

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeAgentResponse:
    text: str


class _FakeStream:
    """Minimal stand-in for AF's ``ResponseStream`` returned by ``run(stream=True)``."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self._final = _FakeAgentResponse(text="".join(chunks))

    def __aiter__(self) -> AsyncIterator[AgentResponseUpdate]:
        async def _gen() -> AsyncIterator[AgentResponseUpdate]:
            for c in self._chunks:
                yield AgentResponseUpdate(contents=[Content.from_text(c)], role="assistant")

        return _gen()

    async def get_final_response(self) -> _FakeAgentResponse:
        return self._final


class _FakeAgent:
    def __init__(self, reply: Any = "hello", chunks: list[str] | None = None) -> None:
        self.id = "fake-agent"
        self.name: str | None = "Fake Agent"
        self.description: str | None = "Test fake agent"
        self._reply = reply
        self._chunks = chunks or [reply]
        self.calls: list[dict[str, Any]] = []

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> Any:
        return {"service_session_id": service_session_id, "session_id": session_id}

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "kwargs": kwargs})
        if stream:
            return _FakeStream(self._chunks)

        async def _coro() -> Any:
            if not isinstance(self._reply, str):
                return self._reply
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


def _sse_payload(body: str, event_type: str) -> dict[str, Any]:
    current_event: str | None = None
    for line in body.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
            continue
        if current_event == event_type and line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError(f"Missing SSE event: {event_type}")


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

    def test_non_object_json_returns_422(self) -> None:
        client, *_ = _make_client()
        with client:
            r = client.post("/responses", json=["not", "an", "object"])
        assert r.status_code == 422
        assert r.json()["error"] == "request body must be a JSON object"

    def test_invalid_input_returns_422(self) -> None:
        client, *_ = _make_client()
        with client:
            r = client.post("/responses", json={"input": 42})
        assert r.status_code == 422

    def test_request_options_are_not_forwarded_by_default(self) -> None:
        client, _host, agent = _make_client()
        with client:
            r = client.post(
                "/responses",
                json={"input": "x", "temperature": 0.5, "max_output_tokens": 64, "truncation": "auto"},
            )
        assert r.status_code == 200
        assert "options" not in agent.calls[0]["kwargs"]

    def test_custom_run_hook_can_forward_options(self) -> None:
        import dataclasses

        def keep_temperature(request: Any, **_: Any) -> Any:
            opts = dict(request.options or {})
            return dataclasses.replace(request, options={"temperature": opts.get("temperature")})

        agent = _FakeAgent()
        host = AgentFrameworkHost(
            target=agent,
            channels=[ResponsesChannel(run_hook=keep_temperature)],
        )
        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "x", "temperature": 0.7, "truncation": "auto"})
        assert r.status_code == 200
        opts = agent.calls[0]["kwargs"]["options"]
        assert opts == {"temperature": 0.7}
        assert "truncation" not in opts

    def test_multimodal_agent_response_outputs_are_preserved(self) -> None:
        response = AgentResponse(
            messages=[
                Message(
                    "assistant",
                    [
                        Content.from_text_reasoning(id="rs_1", text="checking"),
                        Content.from_function_call("call_1", "collect_media", arguments={"city": "Seattle"}),
                        Content.from_function_result(
                            "call_1",
                            result=[
                                Content.from_text("caption"),
                                Content.from_uri("https://example.com/cat.png", media_type="image/png"),
                                Content.from_hosted_file("file_pdf", media_type="application/pdf"),
                            ],
                        ),
                        Content.from_text("done"),
                    ],
                )
            ],
        )
        client, _host, _agent = _make_client(_FakeAgent(reply=response))

        with client:
            r = client.post("/responses", json={"input": "hi"})

        assert r.status_code == 200
        output = r.json()["output"]
        assert [item["type"] for item in output] == [
            "reasoning",
            "function_call",
            "function_call_output",
            "message",
        ]
        assert output[0]["content"][0]["text"] == "checking"
        assert output[1]["name"] == "collect_media"
        assert output[1]["arguments"] == '{"city": "Seattle"}'
        assert output[2]["output"] == [
            {"text": "caption", "type": "input_text"},
            {"detail": "auto", "type": "input_image", "image_url": "https://example.com/cat.png"},
            {"type": "input_file", "file_id": "file_pdf"},
        ]
        assert output[3]["content"][0]["text"] == "done"

    def test_raw_responses_output_items_are_preserved(self) -> None:
        raw_item = {
            "id": "ig_1",
            "type": "image_generation_call",
            "result": "base64-image",
            "status": "completed",
        }
        response = AgentResponse(
            messages=[
                Message(
                    "assistant",
                    [
                        Content.from_image_generation_tool_call(image_id="ig_1", raw_representation=raw_item),
                        Content.from_image_generation_tool_result(
                            image_id="ig_1",
                            outputs=Content.from_uri("data:image/png;base64,base64-image", media_type="image/png"),
                            raw_representation=raw_item,
                        ),
                    ],
                )
            ],
        )
        client, _host, _agent = _make_client(_FakeAgent(reply=response))

        with client:
            r = client.post("/responses", json={"input": "hi"})

        assert r.status_code == 200
        assert r.json()["output"] == [raw_item]

    def test_later_raw_responses_output_item_replaces_earlier_partial_item(self) -> None:
        partial = {
            "id": "mcp_1",
            "type": "mcp_call",
            "server_label": "weather",
            "name": "lookup",
            "arguments": "{}",
            "status": "in_progress",
        }
        completed = {**partial, "status": "completed", "output": "sunny"}
        response = AgentResponse(
            messages=[
                Message(
                    "assistant",
                    [
                        Content.from_mcp_server_tool_call(
                            "mcp_1",
                            "lookup",
                            server_name="weather",
                            raw_representation=partial,
                        ),
                        Content.from_mcp_server_tool_result("mcp_1", output="sunny", raw_representation=completed),
                    ],
                )
            ],
        )
        client, _host, _agent = _make_client(_FakeAgent(reply=response))

        with client:
            r = client.post("/responses", json={"input": "hi"})

        assert r.status_code == 200
        assert r.json()["output"] == [completed]

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

    def test_result_output_items_project_workflow_message_and_content_outputs(self) -> None:
        class _WorkflowResult:
            def get_outputs(self) -> list[Any]:
                return [
                    Message("assistant", [Content.from_text("one")]),
                    Content.from_function_result(
                        "call_1",
                        result=[Content.from_uri("https://example.com/cat.png", media_type="image/png")],
                    ),
                ]

        output = [
            item.model_dump(mode="json", exclude_none=True)
            for item in _result_to_output_items(_WorkflowResult(), status="completed")
        ]
        assert output[0]["type"] == "message"
        assert output[0]["content"][0]["text"] == "one"
        assert output[1]["type"] == "function_call_output"
        assert output[1]["output"] == [
            {"detail": "auto", "type": "input_image", "image_url": "https://example.com/cat.png"}
        ]

    def test_function_result_exception_is_preserved(self) -> None:
        output = [
            item.model_dump(mode="json", exclude_none=True)
            for item in _result_to_output_items(
                Content.from_function_result("call_1", exception="tool failed"),
                status="completed",
            )
        ]
        assert output[0]["output"] == "tool failed"

    def test_stateful_call_and_result_content_coalesce_to_one_output_item(self) -> None:
        output = [
            item.model_dump(mode="json", exclude_none=True)
            for item in _result_to_output_items(
                Message(
                    "assistant",
                    [
                        Content.from_image_generation_tool_call(image_id="ig_1"),
                        Content.from_image_generation_tool_result(
                            image_id="ig_1",
                            outputs=Content.from_uri("data:image/png;base64,base64-image", media_type="image/png"),
                        ),
                        Content.from_mcp_server_tool_call(
                            "mcp_1",
                            "lookup",
                            server_name="weather",
                            arguments={"city": "Seattle"},
                        ),
                        Content.from_mcp_server_tool_result("mcp_1", output=[Content.from_text("sunny")]),
                    ],
                ),
                status="completed",
            )
        ]
        assert output == [
            {
                "id": "ig_1",
                "result": "base64-image",
                "status": "completed",
                "type": "image_generation_call",
            },
            {
                "id": "mcp_1",
                "arguments": '{"city": "Seattle"}',
                "name": "lookup",
                "output": "sunny",
                "server_label": "weather",
                "status": "completed",
                "type": "mcp_call",
            },
        ]

    def test_stateful_call_and_result_content_coalesce_across_messages(self) -> None:
        output = [
            item.model_dump(mode="json", exclude_none=True)
            for item in _result_to_output_items(
                AgentResponse(
                    messages=[
                        Message(
                            "assistant",
                            [
                                Content.from_mcp_server_tool_call(
                                    "mcp_1",
                                    "lookup",
                                    server_name="weather",
                                    arguments={"city": "Seattle"},
                                )
                            ],
                        ),
                        Message(
                            "tool",
                            [Content.from_mcp_server_tool_result("mcp_1", output=[Content.from_text("sunny")])],
                        ),
                    ]
                ),
                status="completed",
            )
        ]
        assert output == [
            {
                "id": "mcp_1",
                "arguments": '{"city": "Seattle"}',
                "name": "lookup",
                "output": "sunny",
                "server_label": "weather",
                "status": "completed",
                "type": "mcp_call",
            }
        ]


class TestResponsesChannelStreaming:
    def test_sse_streaming_uses_request_parent_span_context(self) -> None:
        observed: dict[str, int] = {}
        parent_ctx = trace.SpanContext(
            trace_id=0xABCDEF00112233445566778899AABBCC,
            span_id=0x1122334455667788,
            is_remote=False,
            trace_flags=trace.TraceFlags(0x01),
            trace_state=trace.TraceState(),
        )
        parent_span = trace.NonRecordingSpan(parent_ctx)

        class _SpanAwareAgent(_FakeAgent):
            def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
                self.calls.append({"messages": messages, "stream": stream, "kwargs": kwargs})
                if stream:
                    observed["run_span_id"] = trace.get_current_span().get_span_context().span_id
                    return _FakeStream(["chunk"])
                return super().run(messages=messages, stream=stream, **kwargs)

        async def _middleware_dispatch(request: Any, call_next: Any) -> Any:
            token = otel_context.attach(trace.set_span_in_context(parent_span))
            try:
                return await call_next(request)
            finally:
                otel_context.detach(token)

        host = AgentFrameworkHost(target=_SpanAwareAgent(), channels=[ResponsesChannel()])
        host.app.add_middleware(BaseHTTPMiddleware, dispatch=_middleware_dispatch)

        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi", "stream": True})

        assert r.status_code == 200
        assert observed["run_span_id"] == parent_ctx.span_id

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

        def transform(update: AgentResponseUpdate) -> AgentResponseUpdate:
            return AgentResponseUpdate(contents=[Content.from_text(update.text.upper())], role="assistant")

        host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel(stream_update_hook=transform)])
        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi", "stream": True})

        assert r.status_code == 200
        assert '"delta":"HE"' in r.text
        assert '"delta":"LLO"' in r.text
        # Stream update hooks are update-only; they do not rewrite get_final_response().
        assert '"text":"hello"' in r.text

    def test_sse_completed_preserves_streamed_multimodal_updates_when_finalize_fails(self) -> None:
        class _MultimodalStream:
            def __aiter__(self) -> AsyncIterator[AgentResponseUpdate]:
                async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                    yield AgentResponseUpdate(
                        contents=[
                            Content.from_text("caption"),
                            Content.from_text_reasoning(id="rs_1", text="thinking"),
                            Content.from_function_call("call_1", "lookup", arguments={"city": "Seattle"}),
                            Content.from_uri("https://example.com/cat.png", media_type="image/png"),
                        ],
                        role="assistant",
                    )

                return _gen()

            async def get_final_response(self) -> _FakeAgentResponse:
                raise RuntimeError("finalize unavailable")

        class _MultimodalAgent(_FakeAgent):
            def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
                self.calls.append({"messages": messages, "stream": stream, "kwargs": kwargs})
                if stream:
                    return _MultimodalStream()
                raise AssertionError("non-streaming path not exercised here")

        host = AgentFrameworkHost(target=_MultimodalAgent(), channels=[ResponsesChannel()])
        with TestClient(host.app) as client:
            r = client.post("/responses", json={"input": "hi", "stream": True})

        assert r.status_code == 200
        assert "event: response.output_item.added" in r.text
        assert "event: response.output_item.done" in r.text
        events = [line[len("event: ") :] for line in r.text.splitlines() if line.startswith("event: ")]
        assert "response.content_part.added" in events
        assert "response.output_text.done" in events
        assert "response.reasoning_text.delta" in events
        assert "response.reasoning_text.done" in events
        assert "response.function_call_arguments.delta" in events
        assert "response.function_call_arguments.done" in events
        content_part_added = _sse_payload(r.text, "response.content_part.added")
        assert content_part_added["part"] == {"annotations": [], "text": "", "type": "output_text"}
        added_items = [
            json.loads(line[len("data: ") :])["item"]
            for line in r.text.splitlines()
            if line.startswith("data: ") and '"type":"response.output_item.added"' in line
        ]
        assert [item["type"] for item in added_items] == [
            "message",
            "reasoning",
            "function_call",
            "function_call_output",
        ]
        assert added_items[0]["content"] == []
        assert added_items[1]["content"] == []
        assert added_items[2]["name"] == "lookup"
        assert added_items[2]["arguments"] == ""
        assert added_items[3]["output"] == [
            {"detail": "auto", "type": "input_image", "image_url": "https://example.com/cat.png"}
        ]
        completed = _sse_payload(r.text, "response.completed")
        assert completed["response"]["output"][0]["content"][0]["text"] == "caption"
        assert completed["response"]["output"][1]["content"][0]["text"] == "thinking"
        assert completed["response"]["output"][2]["name"] == "lookup"
        assert completed["response"]["output"][3]["output"] == [
            {"detail": "auto", "type": "input_image", "image_url": "https://example.com/cat.png"}
        ]

    def test_sse_emits_failed_when_stream_raises(self) -> None:
        # Regression: ResponseOutputMessage.status only accepts in_progress/
        # completed/incomplete, so building an OpenAIResponse with status="failed"
        # used to crash with a pydantic ValidationError. The channel must map the
        # nested message status to "incomplete" while keeping the top-level
        # Response.status="failed".
        class _BoomStream:
            def __aiter__(self) -> AsyncIterator[AgentResponseUpdate]:
                async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                    yield AgentResponseUpdate(contents=[Content.from_text("partial")], role="assistant")
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
