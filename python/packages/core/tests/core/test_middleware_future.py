# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

import agent_framework
from agent_framework import (
    Agent,
    AgentContext,
    ChatContext,
    FunctionInvocationContext,
    Message,
    MiddlewareException,
)
from agent_framework._middleware import categorize_middleware

from .conftest import MockBaseChatClient


async def agent_mw(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
    await call_next()


async def function_mw(context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
    await call_next()


async def chat_mw(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
    await call_next()


async def qualified_chat_mw(context: agent_framework.ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
    await call_next()


class CallableChatMiddleware:
    async def __call__(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        await call_next()


# Quoted forward references keep their quotes under postponed evaluation (e.g. "'ChatContext'"). pyupgrade
# strips redundant quotes from annotations in this module, so the quoted definitions are compiled from source.
_QUOTED_MIDDLEWARE_SOURCE = """
from __future__ import annotations


async def quoted_chat_mw(context: "ChatContext", call_next):
    await call_next()


async def quoted_function_mw(context: "FunctionInvocationContext", call_next):
    await call_next()


async def quoted_qualified_agent_mw(context: "agent_framework.AgentContext", call_next):
    await call_next()
"""


def _compile_quoted_middleware() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(compile(_QUOTED_MIDDLEWARE_SOURCE, "<quoted_middleware>", "exec"), namespace)  # noqa: S102
    return namespace


def test_middleware_type_detected_from_postponed_annotations() -> None:
    """Context annotations stored as strings (PEP 563) still determine the middleware type."""
    callable_chat_mw = CallableChatMiddleware()

    result = categorize_middleware([agent_mw, function_mw, chat_mw, qualified_chat_mw, callable_chat_mw])

    assert result["agent"] == [agent_mw]
    assert result["function"] == [function_mw]
    assert result["chat"] == [chat_mw, qualified_chat_mw, callable_chat_mw]


def test_middleware_type_detected_from_quoted_postponed_annotations() -> None:
    """Quoted context annotations are matched like unquoted ones under postponed evaluation."""
    namespace = _compile_quoted_middleware()
    quoted_chat_mw = namespace["quoted_chat_mw"]
    quoted_function_mw = namespace["quoted_function_mw"]
    quoted_qualified_agent_mw = namespace["quoted_qualified_agent_mw"]
    assert quoted_chat_mw.__annotations__["context"] == "'ChatContext'"

    result = categorize_middleware([quoted_chat_mw, quoted_function_mw, quoted_qualified_agent_mw])

    assert result["agent"] == [quoted_qualified_agent_mw]
    assert result["function"] == [quoted_function_mw]
    assert result["chat"] == [quoted_chat_mw]


def test_middleware_with_unrecognized_postponed_annotation_still_raises() -> None:
    async def unknown_mw(context: Any, call_next: Any) -> None:
        await call_next()

    with pytest.raises(MiddlewareException, match="Cannot determine middleware type"):
        categorize_middleware([unknown_mw])


async def test_agent_runs_chat_middleware_with_postponed_annotations(chat_client_base: MockBaseChatClient) -> None:
    executed: list[str] = []

    async def logging_chat_mw(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        executed.append("chat")
        await call_next()

    agent = Agent(client=chat_client_base, middleware=[logging_chat_mw])
    response = await agent.run([Message(role="user", contents=["hello"])])

    assert response is not None
    assert executed == ["chat"]
