# Copyright (c) Microsoft. All rights reserved.

"""Shared test stubs for AG-UI tests."""

from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, MutableSequence
from types import SimpleNamespace
from typing import Any

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatMessage,
    ChatOptions,
    TextContent,
)
from agent_framework._clients import BaseChatClient
from agent_framework._types import ChatResponse, ChatResponseUpdate

from agent_framework_ag_ui._orchestrators import ExecutionContext

StreamFn = Callable[..., AsyncIterator[ChatResponseUpdate]]
ResponseFn = Callable[..., Awaitable[ChatResponse]]


class StreamingChatClientStub(BaseChatClient):
    """Typed streaming stub that satisfies ChatClientProtocol."""

    def __init__(self, stream_fn: StreamFn, response_fn: ResponseFn | None = None) -> None:
        super().__init__()
        self._stream_fn = stream_fn
        self._response_fn = response_fn

    async def _inner_get_streaming_response(
        self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        async for update in self._stream_fn(messages, chat_options, **kwargs):
            yield update

    async def _inner_get_response(
        self, *, messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
    ) -> ChatResponse:
        if self._response_fn is not None:
            return await self._response_fn(messages, chat_options, **kwargs)

        contents: list[Any] = []
        async for update in self._stream_fn(messages, chat_options, **kwargs):
            contents.extend(update.contents)

        return ChatResponse(
            messages=[ChatMessage(role="assistant", contents=contents)],
            response_id="stub-response",
        )


def stream_from_updates(updates: list[ChatResponseUpdate]) -> StreamFn:
    """Create a stream function that yields from a static list of updates."""

    async def _stream(
        messages: MutableSequence[ChatMessage], chat_options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        for update in updates:
            yield update

    return _stream


class StubAgent(AgentProtocol):
    """Minimal AgentProtocol stub for orchestrator tests."""

    def __init__(
        self,
        updates: list[AgentRunResponseUpdate] | None = None,
        *,
        agent_id: str = "stub-agent",
        agent_name: str | None = "stub-agent",
        chat_options: Any | None = None,
        chat_client: Any | None = None,
    ) -> None:
        self._id = agent_id
        self._name = agent_name
        self._description = "stub agent"
        self.updates = updates or [AgentRunResponseUpdate(contents=[TextContent(text="response")], role="assistant")]
        self.chat_options = chat_options or SimpleNamespace(tools=None, response_format=None)
        self.chat_client = chat_client or SimpleNamespace(function_invocation_configuration=None)
        self.messages_received: list[Any] = []
        self.tools_received: list[Any] | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def display_name(self) -> str:
        return self._name or self._id

    @property
    def description(self) -> str | None:
        return self._description

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        return AgentRunResponse(messages=[], response_id="stub-response")

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        async def _stream() -> AsyncIterator[AgentRunResponseUpdate]:
            self.messages_received = [] if messages is None else list(messages)  # type: ignore[arg-type]
            self.tools_received = kwargs.get("tools")
            for update in self.updates:
                yield update

        return _stream()

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        return AgentThread()


class TestExecutionContext(ExecutionContext):
    """ExecutionContext helper that allows setting messages for tests."""

    def set_messages(self, messages: list[ChatMessage]) -> None:
        self._messages = messages
