# Copyright (c) Microsoft. All rights reserved.

"""Offline clients and callbacks for host option-boundary tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from typing import Any, cast

from agent_framework import (
    Agent,
    AgentContext,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    Workflow,
    WorkflowBuilder,
)
from starlette.requests import Request


class OptionsClient(BaseChatClient[ChatOptions]):
    STORES_BY_DEFAULT = False

    def __init__(self, *, delay: float = 0) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []
        self.delay = delay

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.calls.append(dict(options))
        return ResponseStream(self.updates(), finalizer=ChatResponse.from_updates) if stream else self.complete()

    async def updates(self) -> AsyncIterator[ChatResponseUpdate]:
        if self.delay:
            await asyncio.sleep(self.delay)
        yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("ok")])

    async def complete(self) -> ChatResponse:
        return ChatResponse(messages=[Message("assistant", ["ok"])])


class OptionCallbacks:
    def __init__(self, *, defaults: dict[str, Any] | None = None, injected: dict[str, Any] | None = None) -> None:
        self.client = OptionsClient()
        self.defaults = cast(ChatOptions, defaults or {})
        self.injected = injected or {}
        self.events: list[str] = []

    def factory(self, *, request: Request) -> Agent:
        self.events.append("factory")
        return Agent(client=self.client, default_options=self.defaults)

    def prepare(self, request: Request, options: dict[str, Any]) -> dict[str, Any]:
        self.events.append("hook")
        options.pop("model", None)
        return options

    async def prepare_async(self, request: Request, options: dict[str, Any]) -> dict[str, Any]:
        return self.prepare(request, options)

    async def inject(self, context: AgentContext, call_next: Any) -> None:
        context.options = {**(context.options or {}), **self.injected}
        await call_next()

    def workflow(self, request: Request) -> Workflow:
        self.events.append("factory")
        agent = Agent(
            client=self.client,
            default_options=self.defaults,
            middleware=[self.inject] if self.injected else None,
        )
        return WorkflowBuilder(start_executor=agent).build()
