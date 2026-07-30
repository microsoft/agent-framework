# Copyright (c) Microsoft. All rights reserved.
"""Tests for the AGENT-HOOKS-0.1 middleware."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from agent_framework import (
    AgentContext,
    ChatContext,
    FunctionInvocationContext,
    MiddlewareTermination,
)
from agent_framework_agent_hooks import (
    AgentHooksChatMiddleware,
    AgentHooksFunctionMiddleware,
    agent_hooks_middleware,
)
from agent_hooks import Decision, Transform, Verdict


class _AllowAll:
    def intercept(self, context: dict[str, Any]) -> Verdict:
        return Verdict(decision=Decision.ALLOW)


class _DenyTool:
    def __init__(self, name: str) -> None:
        self._name = name

    def intercept(self, context: dict[str, Any]) -> Verdict:
        if context["interception_point"] == "pre_tool_call" and context["tool_call"]["name"] == self._name:
            return Verdict.deny(reason="blocked_tool")
        return Verdict(decision=Decision.ALLOW)


class _RedactArg:
    def intercept(self, context: dict[str, Any]) -> Verdict:
        if context["interception_point"] == "pre_tool_call":
            return Verdict(decision=Decision.TRANSFORM, transform=Transform(path="$target.query", value="[redacted]"))
        return Verdict(decision=Decision.ALLOW)


class _FakeFunction:
    name = "search"


def _agent_context(stream: bool = False) -> AgentContext:
    context = AgentContext.__new__(AgentContext)
    context.agent = type("A", (), {"name": "test-agent"})()
    context.messages = []
    context.tools = None
    context.stream = stream
    context.result = None
    return context


def _function_context(arguments: dict[str, Any]) -> FunctionInvocationContext:
    return FunctionInvocationContext(function=_FakeFunction(), arguments=arguments)


async def _run(
    middlewares: list[Any],
    fn_ctx: FunctionInvocationContext,
    tool: Callable[[], Awaitable[None]] | None = None,
) -> list[Any]:
    """Drive the agent middleware bracket around one function invocation."""
    agent_mw, _, fn_mw = middlewares
    records: list[Any] = []

    async def inner() -> None:
        async def call_fn() -> None:
            fn_ctx.result = "ok"

        await fn_mw.process(fn_ctx, tool or call_fn)

    agent_ctx = _agent_context()
    await agent_mw.process(agent_ctx, inner)
    return records


async def test_allow_run_completes_and_records() -> None:
    records: list[Any] = []
    middlewares = agent_hooks_middleware([_AllowAll()], record_sink=records.append)
    fn_ctx = _function_context({"query": "cats"})
    await _run(middlewares, fn_ctx)
    assert fn_ctx.result == "ok"
    points = [r.interception_point.value for r in records]
    assert points == [
        "agent_startup",
        "input",
        "pre_tool_call",
        "post_tool_call",
        "output",
        "agent_shutdown",
    ]


async def test_deny_blocks_tool_and_terminates() -> None:
    records: list[Any] = []
    middlewares = agent_hooks_middleware([_DenyTool("search")], record_sink=records.append)
    fn_ctx = _function_context({"query": "cats"})
    with pytest.raises(MiddlewareTermination, match="blocked_tool"):
        await _run(middlewares, fn_ctx)
    assert fn_ctx.result is None  # tool never executed
    points = [r.interception_point.value for r in records]
    assert "post_tool_call" not in points  # blocked pre point suppresses post
    assert points[-1] == "agent_shutdown"  # session trail still closed
    assert records[-1].verdict.to_wire()["decision"] == "allow"


async def test_transform_rewrites_executed_arguments() -> None:
    middlewares = agent_hooks_middleware([_RedactArg()])
    fn_ctx = _function_context({"query": "secret data"})
    seen: dict[str, Any] = {}

    async def inner() -> None:
        async def call_fn() -> None:
            seen.update(dict(fn_ctx.arguments))
            fn_ctx.result = "ok"

        await middlewares[2].process(fn_ctx, call_fn)

    await middlewares[0].process(_agent_context(), inner)
    assert seen == {"query": "[redacted]"}  # execution saw the approved value


async def test_chat_middleware_noop_outside_run() -> None:
    called: list[bool] = []

    async def call_next() -> None:
        called.append(True)

    chat_ctx = ChatContext.__new__(ChatContext)
    chat_ctx.stream = False
    await AgentHooksChatMiddleware().process(chat_ctx, call_next)
    assert called == [True]


async def test_function_middleware_noop_outside_run() -> None:
    fn_ctx = _function_context({"q": 1})

    async def call_next() -> None:
        fn_ctx.result = "ran"

    await AgentHooksFunctionMiddleware().process(fn_ctx, call_next)
    assert fn_ctx.result == "ran"


async def test_tool_error_still_emits_post_tool_call() -> None:
    records: list[Any] = []
    middlewares = agent_hooks_middleware([_AllowAll()], record_sink=records.append)
    fn_ctx = _function_context({"query": "cats"})

    async def exploding_tool() -> None:
        raise RuntimeError("tool exploded")

    with pytest.raises(RuntimeError, match="tool exploded"):
        await _run(middlewares, fn_ctx, tool=exploding_tool)

    posts = [r for r in records if r.interception_point.value == "post_tool_call"]
    assert len(posts) == 1
    assert records[-1].interception_point.value == "agent_shutdown"
