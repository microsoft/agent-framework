# Copyright (c) Microsoft. All rights reserved.

"""Shared test fixtures and stubs for AG-UI tests."""

import sys
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Mapping, MutableSequence, Sequence
from types import SimpleNamespace
from typing import Any, Generic, Literal, cast, overload

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    SupportsAgentRun,
    SupportsChatGetResponse,
)
from agent_framework._clients import OptionsCoT
from agent_framework._middleware import ChatMiddlewareLayer
from agent_framework._tools import FunctionInvocationLayer
from agent_framework._types import ResponseStream
from agent_framework.observability import ChatTelemetryLayer

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

StreamFn = Callable[..., AsyncIterable[ChatResponseUpdate]]
ResponseFn = Callable[..., Awaitable[ChatResponse]]


class StreamingChatClientStub(
    ChatMiddlewareLayer[OptionsCoT],
    FunctionInvocationLayer[OptionsCoT],
    ChatTelemetryLayer[OptionsCoT],
    BaseChatClient[OptionsCoT],
    Generic[OptionsCoT],
):
    """Typed streaming stub that satisfies SupportsChatGetResponse."""

    def __init__(self, stream_fn: StreamFn, response_fn: ResponseFn | None = None) -> None:
        super().__init__(function_middleware=[])
        self._stream_fn = stream_fn
        self._response_fn = response_fn
        self.last_session: AgentSession | None = None
        self.last_service_session_id: str | None = None

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsCoT | ChatOptions[None] | None = ...,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsCoT | ChatOptions[Any] | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        self.last_session = kwargs.get("session")
        self.last_service_session_id = self.last_session.service_session_id if self.last_session else None
        return cast(
            Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]],
            super().get_response(
                messages=messages,
                stream=cast(Literal[True, False], stream),
                options=options,
                **kwargs,
            ),
        )

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:

            def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
                return ChatResponse.from_updates(updates)

            return ResponseStream(self._stream_fn(messages, options, **kwargs), finalizer=_finalize)

        return self._get_response_impl(messages, options, **kwargs)

    async def _get_response_impl(
        self, messages: Sequence[Message], options: Mapping[str, Any], **kwargs: Any
    ) -> ChatResponse:
        """Non-streaming implementation."""
        if self._response_fn is not None:
            return await self._response_fn(messages, options, **kwargs)

        contents: list[Any] = []
        async for update in self._stream_fn(list(messages), dict(options), **kwargs):
            contents.extend(update.contents)

        return ChatResponse(
            messages=[Message(role="assistant", contents=contents)],
            response_id="stub-response",
        )


def stream_from_updates(updates: list[ChatResponseUpdate]) -> StreamFn:
    """Create a stream function that yields from a static list of updates."""

    async def _stream(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        for update in updates:
            yield update

    return _stream


class StubAgent(SupportsAgentRun):
    """Minimal SupportsAgentRun stub for orchestrator tests."""

    def __init__(
        self,
        updates: list[AgentResponseUpdate] | None = None,
        *,
        agent_id: str = "stub-agent",
        agent_name: str | None = "stub-agent",
        default_options: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.id = agent_id
        self.name = agent_name
        self.description = "stub agent"
        self.updates = updates or [AgentResponseUpdate(contents=[Content.from_text(text="response")], role="assistant")]
        self.default_options: dict[str, Any] = (
            default_options if isinstance(default_options, dict) else {"tools": None, "response_format": None}
        )
        self.client = client or SimpleNamespace(function_invocation_configuration=None)
        self.messages_received: list[Any] = []
        self.tools_received: list[Any] | None = None

    @overload
    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        if stream:

            async def _stream() -> AsyncIterator[AgentResponseUpdate]:
                self.messages_received = [] if messages is None else list(messages)  # type: ignore[arg-type]
                self.tools_received = kwargs.get("tools")
                for update in self.updates:
                    yield update

            def _finalize(updates: Sequence[AgentResponseUpdate]) -> AgentResponse:
                return AgentResponse.from_updates(updates)

            return ResponseStream(_stream(), finalizer=_finalize)

        async def _get_response() -> AgentResponse[Any]:
            return AgentResponse(messages=[], response_id="stub-response")

        return _get_response()

    def create_session(self, **kwargs: Any) -> AgentSession:
        return AgentSession()


# Fixtures


@pytest.fixture
def streaming_chat_client_stub() -> type[SupportsChatGetResponse]:
    """Return the StreamingChatClientStub class for creating test instances."""
    return StreamingChatClientStub  # type: ignore[return-value]


@pytest.fixture
def stream_from_updates_fixture() -> Callable[[list[ChatResponseUpdate]], StreamFn]:
    """Return the stream_from_updates helper function."""
    return stream_from_updates


@pytest.fixture
def stub_agent() -> type[SupportsAgentRun]:
    """Return the StubAgent class for creating test instances."""
    return StubAgent  # type: ignore[return-value]
