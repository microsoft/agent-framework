# Copyright (c) Microsoft. All rights reserved.

"""Shared test stubs for AG-UI tests."""

import sys
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, MutableSequence
from types import SimpleNamespace
from typing import Any, Generic

from agent_framework import (
    AgentProtocol,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
)
from agent_framework._clients import TOptions_co

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

StreamFn = Callable[..., AsyncIterator[ChatResponseUpdate]]
ResponseFn = Callable[..., Awaitable[ChatResponse]]


class StreamingChatClientStub(BaseChatClient[TOptions_co], Generic[TOptions_co]):
    """Typed streaming stub that satisfies ChatClientProtocol."""

    def __init__(self, stream_fn: StreamFn, response_fn: ResponseFn | None = None) -> None:
        super().__init__()
        self._stream_fn = stream_fn
        self._response_fn = response_fn

    @override
    async def _inner_get_streaming_response(
        self, *, messages: MutableSequence[ChatMessage], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        async for update in self._stream_fn(messages, options, **kwargs):
            yield update

    @override
    async def _inner_get_response(
        self, *, messages: MutableSequence[ChatMessage], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        if self._response_fn is not None:
            return await self._response_fn(messages, options, **kwargs)

        contents: list[Any] = []
        async for update in self._stream_fn(messages, options, **kwargs):
            contents.extend(update.contents)

        return ChatResponse(
            messages=[ChatMessage(role="assistant", contents=contents)],
            response_id="stub-response",
        )


def stream_from_updates(updates: list[ChatResponseUpdate]) -> StreamFn:
    """Create a stream function that yields from a static list of updates."""

    async def _stream(
        messages: MutableSequence[ChatMessage], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        for update in updates:
            yield update

    return _stream


class StubAgent(AgentProtocol):
    """Minimal AgentProtocol stub for orchestrator tests."""

    def __init__(
        self,
        updates: list[AgentResponseUpdate] | None = None,
        *,
        agent_id: str = "stub-agent",
        agent_name: str | None = "stub-agent",
        default_options: Any | None = None,
        chat_client: Any | None = None,
    ) -> None:
        self.id = agent_id
        self.name = agent_name
        self.description = "stub agent"
        self.updates = updates or [AgentResponseUpdate(contents=[Content.from_text(text="response")], role="assistant")]
        self.default_options: dict[str, Any] = (
            default_options if isinstance(default_options, dict) else {"tools": None, "response_format": None}
        )
        self.chat_client = chat_client or SimpleNamespace(function_invocation_configuration=None)
        self.messages_received: list[Any] = []
        self.tools_received: list[Any] | None = None

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        return AgentResponse(messages=[], response_id="stub-response")

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        async def _stream() -> AsyncIterator[AgentResponseUpdate]:
            self.messages_received = [] if messages is None else list(messages)  # type: ignore[arg-type]
            self.tools_received = kwargs.get("tools")
            for update in self.updates:
                yield update

        return _stream()

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        return AgentThread()
