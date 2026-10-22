# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeGuard, cast

from agent_framework import SupportsAgentRun

AgentSource: TypeAlias = SupportsAgentRun | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]]


def is_agent(value: object) -> TypeGuard[SupportsAgentRun]:
    return not inspect.isclass(value) and isinstance(value, SupportsAgentRun)


def validate_agent_source(source: object) -> None:
    if is_agent(source):
        return
    if not callable(source):
        raise TypeError("agent must be an agent instance or a zero-argument callable that creates one.")
    try:
        inspect.signature(source).bind()
    except (TypeError, ValueError) as exc:
        raise TypeError("agent callable must accept no arguments.") from exc


async def resolve_agent(source: AgentSource) -> SupportsAgentRun:
    """Resolve an agent instance or request-scoped agent factory."""
    if is_agent(source):
        return source

    factory = cast(Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]], source)
    result = factory()
    agent = await result if inspect.isawaitable(result) else result
    if not is_agent(agent):
        raise TypeError("The agent factory must return an object implementing SupportsAgentRun.")
    return agent
