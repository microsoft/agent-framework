# Copyright (c) Microsoft. All rights reserved.

"""Controlled provider and storage boundaries for Responses host integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_framework import (
    AgentContext,
    AgentMiddleware,
    AgentResponseUpdate,
    AgentSession,
    BaseChatClient,
    ChatContext,
    ChatMiddleware,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    SessionStore,
)
from agent_framework.openai import OpenAIContinuationToken

from .approval_helpers import SqliteSessionStore


class BackgroundAgentMiddleware(AgentMiddleware):
    def __init__(self, *, nested: bool, value: bool = True, in_kwargs: bool = False, on_poll: bool = False) -> None:
        self.nested = nested
        self.value = value
        self.in_kwargs = in_kwargs
        self.on_poll = on_poll

    async def process(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if not self.on_poll or (context.options or {}).get("continuation_token") is not None:
            override = {"extra_body": {"background": self.value}} if self.nested else {"background": self.value}
            if self.in_kwargs:
                context.client_kwargs.update(override)
            else:
                context.options = {**(context.options or {}), **override}
        await call_next()


class BackgroundChatMiddleware(ChatMiddleware):
    def __init__(self, *, nested: bool, value: bool = True, in_kwargs: bool = False, on_poll: bool = False) -> None:
        self.nested = nested
        self.value = value
        self.in_kwargs = in_kwargs
        self.on_poll = on_poll

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if not self.on_poll or (context.options or {}).get("continuation_token") is not None:
            override = {"extra_body": {"background": self.value}} if self.nested else {"background": self.value}
            if self.in_kwargs:
                context.kwargs.update(override)
            else:
                context.options = {**(context.options or {}), **override}
        await call_next()


class BackgroundPollingClient(ChatMiddlewareLayer[Any], BaseChatClient[Any]):
    STORES_BY_DEFAULT = True

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del messages, kwargs
        assert not stream
        self.calls.append(dict(options))

        async def response() -> ChatResponse:
            if len(self.calls) == 1:
                return ChatResponse(
                    conversation_id="provider-conversation",
                    continuation_token=OpenAIContinuationToken(response_id="provider-token"),
                )
            return ChatResponse(messages=[Message("assistant", "done")], conversation_id="provider-conversation")

        return response()


class ApprovalPublishingClient(ChatMiddlewareLayer[Any], BaseChatClient[Any]):
    STORES_BY_DEFAULT = False

    def __init__(self, approval: Content) -> None:
        super().__init__()
        self.approval = approval
        self.calls = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del messages, options, kwargs
        assert stream
        self.calls += 1

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[self.approval])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates)


class UnlayeredClient(BaseChatClient[Any]):
    STORES_BY_DEFAULT = True

    def __init__(self) -> None:
        super().__init__()
        self.kwargs: list[dict[str, Any]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del messages, options
        self.kwargs.append(dict(kwargs))

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("done")], conversation_id="service")

        async def response() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", "done")], conversation_id="service")

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else response()


class GatedApprovalStore(SqliteSessionStore):
    def __init__(self, path: Path, *, fail_alias: bool = False) -> None:
        super().__init__(path)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.fail_alias = fail_alias

    async def compare_and_set(self, session_id: str, session: AgentSession, *, expected_revision: str | None) -> str:
        if session_id.startswith("__foundry_agent_approval/") and expected_revision is None:
            self.started.set()
            await self.release.wait()
        return await super().compare_and_set(session_id, session, expected_revision=expected_revision)

    async def set(self, session_id: str, session: AgentSession) -> None:
        if self.fail_alias:
            raise RuntimeError("response session snapshot failed")
        await super().set(session_id, session)


class GatedClaimStore(SqliteSessionStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.claims = 0

    async def compare_and_set(self, session_id: str, session: AgentSession, *, expected_revision: str | None) -> str:
        if session_id.startswith("__foundry_agent_approval/") and expected_revision is not None:
            self.claims += 1
            if self.claims == 2:
                self.started.set()
            await self.release.wait()
        return await super().compare_and_set(session_id, session, expected_revision=expected_revision)


class GatedRequestRead:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def load(self) -> list[Any]:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()
        return []


class GatedSessionLoadStore(SessionStore):
    def __init__(self, request_started: asyncio.Event) -> None:
        super().__init__()
        self.request_started = request_started
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def get(self, session_id: str) -> AgentSession | None:
        del session_id
        await self.request_started.wait()
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()
        return None


class GatedAgentStream:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.stopped = asyncio.Event()

    async def updates(self) -> AsyncIterator[AgentResponseUpdate]:
        self.started.set()
        try:
            await self.release.wait()
            yield AgentResponseUpdate(role="assistant", contents=[Content.from_text("too late")])
        finally:
            self.stopped.set()


async def collect_host_events(source: AsyncIterator[Any], events: list[Any]) -> None:
    async for event in source:
        events.append(event)


class StatefulConsentClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
    """Mimic a service-backed conversation with one settled and one consent batch."""

    STORES_BY_DEFAULT = True

    def __init__(self, tool_names: Sequence[str]) -> None:
        super().__init__()
        self.tool_names = list(tool_names)
        self.calls: list[list[Message]] = []
        self.options: list[dict[str, Any]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del kwargs
        self.calls.append(list(messages))
        self.options.append(dict(options))
        if len(self.calls) == 1:
            contents = [Content.from_function_call(call_id="old-0", name=self.tool_names[0], arguments="{}")]
        elif len(self.calls) == 2:
            contents = [
                Content.from_function_call(call_id=f"pending-{index}", name=name, arguments="{}")
                for index, name in enumerate(self.tool_names)
            ]
        else:
            contents = [Content.from_text("done")]

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(
                role="assistant", contents=contents, conversation_id="provider-conversation", response_id="provider"
            )

        async def complete() -> ChatResponse:
            return ChatResponse(
                messages=[Message("assistant", contents=contents)],
                conversation_id="provider-conversation",
                response_id="provider",
            )

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()
