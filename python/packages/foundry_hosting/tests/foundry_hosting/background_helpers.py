# Copyright (c) Microsoft. All rights reserved.

"""Real agents and middleware for provider-background boundary tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import (
    Agent,
    AgentContext,
    ChatContext,
    ChatMiddlewareLayer,
    ChatMiddlewareTypes,
    RawAgent,
    Workflow,
    WorkflowBuilder,
)
from starlette.requests import Request

from .options_helpers import OptionsClient


class LayeredOptionsClient(ChatMiddlewareLayer, OptionsClient):
    pass


class BackgroundCallbacks:
    def __init__(
        self,
        *,
        source: str,
        location: str,
        injected: dict[str, Any],
        raw: bool = False,
    ) -> None:
        self.client = LayeredOptionsClient()
        self.source = source
        self.location = location
        self.injected = injected
        middleware: list[ChatMiddlewareTypes] = [self.inject_chat] if source == "chat" else []
        self.client.chat_middleware = middleware
        self.agent = (
            RawAgent(client=self.client)
            if raw
            else Agent(client=self.client, middleware=[self.inject_agent] if source == "agent" else None)
        )

    async def inject_agent(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if self.location == "options":
            context.options = {**(context.options or {}), **self.injected}
        else:
            context.client_kwargs.update(self.injected)
        await call_next()

    async def inject_chat(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if self.location == "options":
            context.options = {**(context.options or {}), **self.injected}
        else:
            context.kwargs.update(self.injected)
        await call_next()

    def factory(self, *, request: Request) -> Agent[Any] | RawAgent[Any]:
        return self.agent

    def workflow(self, request: Request) -> Workflow:
        return WorkflowBuilder(start_executor=self.agent).build()


class AgentChatCallbacks(BackgroundCallbacks):
    def __init__(self) -> None:
        super().__init__(source="none", location="options", injected={"background": True})
        self.agent = Agent(client=self.client, middleware=[self.inject_chat])


class ReplacedMiddlewareCallbacks(BackgroundCallbacks):
    async def inject_agent(self, context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
        context.client_kwargs["middleware"] = (self.inject_chat,)
        await call_next()
