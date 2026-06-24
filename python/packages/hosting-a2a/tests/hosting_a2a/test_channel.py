# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :class:`A2AChannel` and :class:`HostAgentExecutor`."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
import uvicorn
from a2a.server.events import EventQueue
from a2a.types import AgentCard, AgentInterface, Message, Part, Role, Task, TaskState
from agent_framework import AgentResponse, Content
from agent_framework import Message as AFMessage
from agent_framework_a2a import A2AAgent
from agent_framework_hosting import AgentFrameworkHost, ChannelContribution, ChannelRequest, HostedRunResult
from starlette.types import ASGIApp

from agent_framework_hosting_a2a import A2AChannel, HostAgentExecutor

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeResp:
    text: str
    messages: list[Message] = field(default_factory=list)


@dataclass
class _FakeUpdate:
    text: str
    contents: list[Content] = field(default_factory=list)
    message_id: str | None = None


class _FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self._final = _FakeResp(text="".join(chunks))

    def __aiter__(self) -> AsyncIterator[_FakeUpdate]:
        async def _gen() -> AsyncIterator[_FakeUpdate]:
            for i, c in enumerate(self._chunks):
                yield _FakeUpdate(text=c, contents=[Content.from_text(text=c)], message_id=f"m{i}")

        return _gen()

    async def get_final_response(self) -> _FakeResp:
        return self._final


@dataclass
class _FakeTarget:
    name: str = "Assistant"
    description: str = "A helpful assistant."


class _FakeContext:
    def __init__(
        self,
        *,
        reply: str = "hello",
        chunks: list[str] | None = None,
    ) -> None:
        self.target = _FakeTarget()
        self._reply = reply
        self._chunks = chunks or [reply]
        self.requests: list[ChannelRequest] = []

    async def run(
        self,
        request: ChannelRequest,
        *,
        run_hook: Any | None = None,
        protocol_request: Any | None = None,
        response_hook: Any | None = None,
        channel_name: str | None = None,
    ) -> HostedRunResult[Any]:
        if run_hook is not None:
            maybe_request = run_hook(request, target=self.target, protocol_request=protocol_request)
            if isinstance(maybe_request, Awaitable):
                request = await maybe_request
            else:
                request = maybe_request
        self.requests.append(request)
        msg = Message(role=Role.ROLE_AGENT, parts=[Part(text=self._reply)])
        result = HostedRunResult(_FakeResp(text=self._reply, messages=[msg]))
        if response_hook is not None:
            maybe_result = response_hook(result, request=request, channel_name=channel_name or request.channel)
            if isinstance(maybe_result, Awaitable):
                return await maybe_result
            return maybe_result
        return result

    async def run_stream(
        self,
        request: ChannelRequest,
        *,
        run_hook: Any | None = None,
        protocol_request: Any | None = None,
        stream_update_hook: Any | None = None,
        response_hook: Any | None = None,
        channel_name: str | None = None,
    ) -> _FakeStream:
        if run_hook is not None:
            maybe_request = run_hook(request, target=self.target, protocol_request=protocol_request)
            if isinstance(maybe_request, Awaitable):
                request = await maybe_request
            else:
                request = maybe_request
        self.requests.append(request)
        return _FakeStream(self._chunks)


class _RecordingEventQueue(EventQueue):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


class _FakeRequestContext:
    def __init__(self, *, context_id: str, text: str, current_task: Task | None = None) -> None:
        self.context_id = context_id
        self.task_id: str | None = None
        self.message = Message(
            message_id="msg-1",
            context_id=context_id,
            role=Role.ROLE_USER,
            parts=[Part(text=text)],
        )
        self.current_task = current_task
        self._text = text

    def get_user_input(self) -> str:
        return self._text


class _HostedAgent:
    id = "hosted-agent"
    name: str | None = "HostedAssistant"
    description: str | None = "A hosted test assistant."

    async def run(self, messages: Any = None, *, stream: bool = False, **_kwargs: Any) -> AgentResponse[Any]:
        text = messages.text if isinstance(messages, AFMessage) else str(messages)
        return AgentResponse(messages=[AFMessage(role="assistant", contents=[Content.from_text(text=f"host: {text}")])])

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> Any:
        return {"service_session_id": service_session_id, "session_id": session_id}


@asynccontextmanager
async def _serve_app(app: ASGIApp, *, port: int) -> AsyncIterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.01)
        else:
            raise RuntimeError("Test A2A server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


def _status_states(events: list[Any]) -> list[int]:
    states: list[int] = []
    for event in events:
        status = getattr(event, "status", None)
        if status is not None and getattr(status, "state", None):
            states.append(status.state)
    return states


def _status_texts(events: list[Any]) -> list[str]:
    texts: list[str] = []
    for event in events:
        status = getattr(event, "status", None)
        message = getattr(status, "message", None)
        for part in cast("list[Any]", getattr(message, "parts", None) or []):
            text = getattr(part, "text", None)
            if isinstance(text, str):
                texts.append(text)
    return texts


# --------------------------------------------------------------------------- #
# A2AChannel tests                                                             #
# --------------------------------------------------------------------------- #


def test_default_name_and_root_path() -> None:
    channel = A2AChannel()
    assert channel.name == "a2a"
    assert channel.path == ""


def test_build_agent_card_defaults_from_target() -> None:
    channel = A2AChannel(url="https://example.com/")
    card = channel._build_agent_card(cast(Any, _FakeContext()))
    assert card.name == "Assistant"
    assert card.description == "A helpful assistant."
    assert card.capabilities.streaming is True
    assert card.supported_interfaces[0].url == "https://example.com/"


def test_build_agent_card_accepts_supported_interfaces() -> None:
    interfaces = [
        AgentInterface(url="https://example.com/jsonrpc", protocol_binding="JSONRPC"),
        AgentInterface(url="https://example.com/grpc", protocol_binding="GRPC"),
    ]
    channel = A2AChannel(supported_interfaces=interfaces)
    card = channel._build_agent_card(cast(Any, _FakeContext()))
    assert card.supported_interfaces == interfaces


def test_build_agent_card_override_wins() -> None:
    custom = AgentCard(name="Custom", description="custom card", version="9.9.9")
    channel = A2AChannel(agent_card=custom)
    card = channel._build_agent_card(cast(Any, _FakeContext()))
    assert card.name == "Custom"
    assert card.version == "9.9.9"


def test_contribute_returns_card_and_jsonrpc_routes() -> None:
    channel = A2AChannel(url="https://example.com/")
    contribution = channel.contribute(cast(Any, _FakeContext()))
    assert isinstance(contribution, ChannelContribution)
    paths = {getattr(r, "path", None) for r in contribution.routes}
    assert "/.well-known/agent-card.json" in paths
    assert any(p == "/" for p in paths)


# --------------------------------------------------------------------------- #
# HostAgentExecutor tests                                                      #
# --------------------------------------------------------------------------- #


async def test_execute_routes_through_host_and_completes() -> None:
    ctx = _FakeContext(reply="hi back")
    executor = HostAgentExecutor(cast(Any, ctx), channel_name="a2a", streaming=False)
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="conv-1", text="hello")

    await executor.execute(cast(Any, request_context), queue)

    # Routed through the host with the context id mapped onto the session.
    assert len(ctx.requests) == 1
    request = ctx.requests[0]
    assert request.channel == "a2a"
    assert request.input == "hello"
    assert request.session is not None
    assert request.session.isolation_key == "conv-1"
    assert request.identity is not None
    assert request.identity.native_id == "conv-1"
    # Task progressed to a completed state.
    assert TaskState.TASK_STATE_COMPLETED in _status_states(queue.events)


async def test_execute_streaming_emits_artifacts() -> None:
    ctx = _FakeContext(chunks=["foo", "bar"])
    executor = HostAgentExecutor(cast(Any, ctx), channel_name="a2a", streaming=True)
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="conv-2", text="hello")

    await executor.execute(cast(Any, request_context), queue)

    artifact_events = [e for e in queue.events if getattr(e, "artifact", None)]
    assert artifact_events, "expected at least one artifact update event"
    artifact_ids = {getattr(getattr(e, "artifact", None), "artifact_id", None) for e in artifact_events}
    assert len(artifact_ids) == 1
    assert None not in artifact_ids
    assert ctx.requests[0].stream is True
    assert TaskState.TASK_STATE_COMPLETED in _status_states(queue.events)


async def test_execute_requires_context_id() -> None:
    ctx = _FakeContext()
    executor = HostAgentExecutor(cast(Any, ctx), channel_name="a2a")
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="x", text="hello")
    cast(Any, request_context).context_id = None

    with pytest.raises(ValueError, match="Context ID"):
        await executor.execute(cast(Any, request_context), queue)


async def test_a2a_agent_can_call_hosted_channel(unused_tcp_port: int) -> None:
    host = AgentFrameworkHost(target=cast(Any, _HostedAgent()), channels=[A2AChannel(streaming=False)])

    async with (
        _serve_app(host.app, port=unused_tcp_port) as base_url,
        A2AAgent(
            url=base_url,
            timeout=5.0,
        ) as agent,
    ):
        response = await agent.run("hello")

    assert response.messages[0].text == "host: hello"


async def test_execute_projects_workflow_outputs() -> None:
    class _WorkflowResult:
        value = None

        def get_outputs(self) -> list[AFMessage]:
            return [AFMessage(role="assistant", contents=[Content.from_text("workflow output")])]

    class _WorkflowContext(_FakeContext):
        async def run(
            self,
            request: ChannelRequest,
            *,
            run_hook: Any | None = None,
            protocol_request: Any | None = None,
            response_hook: Any | None = None,
            channel_name: str | None = None,
        ) -> HostedRunResult[Any]:
            self.requests.append(request)
            return HostedRunResult(_WorkflowResult())

    ctx = _WorkflowContext()
    executor = HostAgentExecutor(cast(Any, ctx), channel_name="a2a", streaming=False)
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="conv-workflow", text="hello")

    await executor.execute(cast(Any, request_context), queue)

    assert "workflow output" in _status_texts(queue.events)


def test_contents_to_parts_conversion() -> None:
    from agent_framework_hosting_a2a._executor import _contents_to_parts

    contents = [
        Content.from_text(text="hello"),
        Content.from_uri(uri="https://x/y.png", media_type="image/png"),
        Content.from_data(data=b"AAAA", media_type="image/png"),
    ]
    parts = _contents_to_parts(contents)
    assert parts[0].text == "hello"
    assert parts[1].url == "https://x/y.png"
    assert parts[2].raw == b"AAAA"


async def test_default_hook_strips_options_when_no_run_hook_supplied() -> None:
    """When no run_hook is provided, the default hook strips all options."""
    ctx = _FakeContext(reply="ok")
    executor = HostAgentExecutor(cast(Any, ctx), channel_name="a2a", run_hook=None)
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="ctx-default-hook", text="hello")

    await executor.execute(cast(Any, request_context), queue)

    assert len(ctx.requests) == 1
    assert ctx.requests[0].options is None
