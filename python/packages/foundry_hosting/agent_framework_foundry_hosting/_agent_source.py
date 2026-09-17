# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeGuard, cast

from agent_framework import SupportsAgentRun

AgentSource: TypeAlias = SupportsAgentRun | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]]


def is_agent(value: object) -> TypeGuard[SupportsAgentRun]:
    return hasattr(value, "run") and hasattr(value, "create_session")


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
