# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for InvocationsHostServer.

These tests exercise ``InvocationsHostServer`` directly by constructing the
host, driving ``_partition_key`` and ``_handle_invoke`` with a fake agent and
mock requests. The Foundry request context is injected via the public
``set_request_context`` / ``reset_request_context`` helpers rather than by
patching, matching the style used in ``test_toolbox.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    Message,
    ServiceSessionId,
)
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from typing_extensions import Any

from agent_framework_foundry_hosting import InvocationsHostServer

# region Helpers


class _FakeAgent:
    """Minimal agent implementing the ``SupportsAgentRun`` protocol.

    ``run`` returns an awaitable when ``stream`` is ``False`` and an async
    iterator when ``stream`` is ``True``. Call arguments are recorded on
    ``calls`` for assertions.
    """

    def __init__(
        self,
        *,
        response: AgentResponse | None = None,
        stream_updates: list[AgentResponseUpdate] | None = None,
    ) -> None:
        self.id = "fake-agent"
        self.name: str | None = "Fake Agent"
        self.description: str | None = "A fake agent for testing"
        self._response = response
        self._stream_updates = stream_updates or []
        self.calls: list[dict[str, Any]] = []

    def run(
        self,
        messages: Any = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append({"messages": messages, "stream": stream, "session": session})
        if stream:

            async def _gen() -> AsyncIterator[AgentResponseUpdate]:
                for update in self._stream_updates:
                    yield update

            return _gen()

        async def _run() -> AgentResponse:
            assert self._response is not None
            return self._response

        return _run()

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self,
        service_session_id: str | ServiceSessionId,
        *,
        session_id: str | None = None,
    ) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)


def _make_agent(
    *,
    response_text: str | None = None,
    stream_texts: list[str] | None = None,
) -> _FakeAgent:
    """Build a ``_FakeAgent`` from plain text for non-streaming/streaming runs."""
    response = None
    if response_text is not None:
        response = AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(response_text)])])
    stream_updates = None
    if stream_texts is not None:
        stream_updates = [AgentResponseUpdate(contents=[Content.from_text(t)]) for t in stream_texts]
    return _FakeAgent(response=response, stream_updates=stream_updates)


def _make_request(payload: dict[str, Any]) -> Request:
    """Build a mock Starlette request whose ``json()`` returns ``payload``."""
    request = MagicMock(spec=Request)
    request.json = AsyncMock(return_value=payload)
    return request


@contextmanager
def _request_context(
    *,
    call_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[None]:
    """Install a Foundry request context for the duration of the block."""
    token = set_request_context(FoundryAgentRequestContext(call_id=call_id, user_id=user_id, session_id=session_id))
    try:
        yield
    finally:
        reset_request_context(token)


async def _collect_stream(response: StreamingResponse) -> str:
    """Concatenate the string chunks produced by a StreamingResponse."""
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else bytes(chunk).decode())
    return "".join(chunks)


# endregion


# region Initialization


class TestInit:
    def test_accepts_supports_agent_run(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        assert server._agent is not None  # pyright: ignore[reportPrivateUsage]
        assert server._sessions == {}  # pyright: ignore[reportPrivateUsage]


# endregion


# region Partition key


class TestPartitionKey:
    def test_local_returns_session_id(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        with _request_context(session_id="sess-1"):
            assert server._partition_key() == "sess-1"  # pyright: ignore[reportPrivateUsage]

    def test_local_missing_session_id_raises(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        with _request_context(), pytest.raises(RuntimeError, match="missing session_id"):
            server._partition_key()  # pyright: ignore[reportPrivateUsage]

    def test_hosted_without_call_id_raises_protocol_error(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        server.config.is_hosted = True
        with (
            _request_context(session_id="sess-1", user_id="user-1"),
            pytest.raises(RuntimeError, match="protocol 2.0.0"),
        ):
            server._partition_key()  # pyright: ignore[reportPrivateUsage]

    def test_hosted_missing_user_id_raises(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        server.config.is_hosted = True
        with (
            _request_context(call_id="call-1", session_id="sess-1"),
            pytest.raises(RuntimeError, match="missing session_id or user_id"),
        ):
            server._partition_key()  # pyright: ignore[reportPrivateUsage]

    def test_hosted_returns_composite_key(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        server.config.is_hosted = True
        with _request_context(call_id="call-1", session_id="sess-1", user_id="user-1"):
            assert server._partition_key() == "sess-1:user-1"  # pyright: ignore[reportPrivateUsage]


# endregion


# region Handle invoke


class TestHandleInvoke:
    async def test_missing_message_returns_400(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        request = _make_request({"stream": False})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
        assert isinstance(response, Response)
        assert response.status_code == 400

    async def test_missing_message_streaming_returns_400(self) -> None:
        server = InvocationsHostServer(_make_agent(stream_texts=["a"]))
        request = _make_request({"stream": True})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
        assert isinstance(response, StreamingResponse)
        assert response.status_code == 400

    async def test_partition_key_failure_returns_500(self) -> None:
        server = InvocationsHostServer(_make_agent(response_text="hi"))
        request = _make_request({"message": "Hi"})
        # No session_id in the (local) context -> _partition_key raises -> 500.
        with _request_context():
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]
        assert isinstance(response, Response)
        assert response.status_code == 500

    async def test_non_streaming_returns_agent_text(self) -> None:
        agent = _make_agent(response_text="Hello!")
        server = InvocationsHostServer(agent)
        request = _make_request({"message": "Hi", "stream": False})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert bytes(response.body).decode() == "Hello!"
        # Agent is called with the message wrapped in a list and the cached session.
        assert agent.calls[0]["messages"] == ["Hi"]
        assert agent.calls[0]["stream"] is False
        assert agent.calls[0]["session"] is server._sessions["sess-1"]  # pyright: ignore[reportPrivateUsage]

    async def test_streaming_yields_update_text(self) -> None:
        agent = _make_agent(stream_texts=["Hel", "lo", "!"])
        server = InvocationsHostServer(agent)
        request = _make_request({"message": "Hi", "stream": True})
        with _request_context(session_id="sess-1"):
            response = await server._handle_invoke(request)  # pyright: ignore[reportPrivateUsage]

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert await _collect_stream(response) == "Hello!"
        assert agent.calls[0]["messages"] == "Hi"
        assert agent.calls[0]["stream"] is True

    async def test_session_is_reused_across_requests(self) -> None:
        agent = _make_agent(response_text="ok")
        server = InvocationsHostServer(agent)

        with _request_context(session_id="sess-1"):
            await server._handle_invoke(_make_request({"message": "one"}))  # pyright: ignore[reportPrivateUsage]
            first_session = server._sessions["sess-1"]  # pyright: ignore[reportPrivateUsage]
            await server._handle_invoke(_make_request({"message": "two"}))  # pyright: ignore[reportPrivateUsage]
            second_session = server._sessions["sess-1"]  # pyright: ignore[reportPrivateUsage]

        assert first_session is second_session
        assert list(server._sessions) == ["sess-1"]  # pyright: ignore[reportPrivateUsage]
        assert agent.calls[0]["session"] is agent.calls[1]["session"]


# endregion
