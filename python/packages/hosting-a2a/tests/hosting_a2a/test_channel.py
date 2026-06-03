# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :class:`A2AChannel` and :class:`HostAgentExecutor`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from typing import Any

import pytest
from a2a.server.events import EventQueue
from a2a.types import AgentCard, Message, Part, Role, Task, TaskState
from agent_framework import Content
from agent_framework_hosting import ChannelContribution, ChannelRequest, HostedRunResult

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
        await super().enqueue_event(event)


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


def _status_states(events: list[Any]) -> list[int]:
    states: list[int] = []
    for event in events:
        status = getattr(event, "status", None)
        if status is not None and getattr(status, "state", None):
            states.append(status.state)
    return states


# --------------------------------------------------------------------------- #
# A2AChannel tests                                                             #
# --------------------------------------------------------------------------- #


def test_default_name_and_root_path() -> None:
    channel = A2AChannel()
    assert channel.name == "a2a"
    assert channel.path == ""


def test_build_agent_card_defaults_from_target() -> None:
    channel = A2AChannel(url="https://example.com/")
    card = channel._build_agent_card(_FakeContext())  # type: ignore[arg-type]
    assert card.name == "Assistant"
    assert card.description == "A helpful assistant."
    assert card.capabilities.streaming is True
    assert card.supported_interfaces[0].url == "https://example.com/"


def test_build_agent_card_override_wins() -> None:
    custom = AgentCard(name="Custom", description="custom card", version="9.9.9")
    channel = A2AChannel(agent_card=custom)
    card = channel._build_agent_card(_FakeContext())  # type: ignore[arg-type]
    assert card.name == "Custom"
    assert card.version == "9.9.9"


def test_contribute_returns_card_and_jsonrpc_routes() -> None:
    channel = A2AChannel(url="https://example.com/")
    contribution = channel.contribute(_FakeContext())  # type: ignore[arg-type]
    assert isinstance(contribution, ChannelContribution)
    paths = {getattr(r, "path", None) for r in contribution.routes}
    assert "/.well-known/agent-card.json" in paths
    assert any(p == "/" for p in paths)


# --------------------------------------------------------------------------- #
# HostAgentExecutor tests                                                      #
# --------------------------------------------------------------------------- #


async def test_execute_routes_through_host_and_completes() -> None:
    ctx = _FakeContext(reply="hi back")
    executor = HostAgentExecutor(ctx, channel_name="a2a", streaming=False)  # type: ignore[arg-type]
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="conv-1", text="hello")

    await executor.execute(request_context, queue)  # type: ignore[arg-type]

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
    executor = HostAgentExecutor(ctx, channel_name="a2a", streaming=True)  # type: ignore[arg-type]
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="conv-2", text="hello")

    await executor.execute(request_context, queue)  # type: ignore[arg-type]

    artifact_events = [e for e in queue.events if getattr(e, "artifact", None)]
    assert artifact_events, "expected at least one artifact update event"
    assert ctx.requests[0].stream is True
    assert TaskState.TASK_STATE_COMPLETED in _status_states(queue.events)


async def test_execute_requires_context_id() -> None:
    ctx = _FakeContext()
    executor = HostAgentExecutor(ctx, channel_name="a2a")  # type: ignore[arg-type]
    queue = _RecordingEventQueue()
    request_context = _FakeRequestContext(context_id="x", text="hello")
    request_context.context_id = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="Context ID"):
        await executor.execute(request_context, queue)  # type: ignore[arg-type]


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
