# Copyright (c) Microsoft. All rights reserved.

"""Private request factory and execution-scope support."""

from __future__ import annotations

import asyncio
import inspect
import weakref
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypeAlias, TypeGuard, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    FunctionalWorkflowAgent,
    ResponseStream,
    SupportsAgentRun,
    WorkflowAgent,
)

HostedAgent: TypeAlias = SupportsAgentRun | FunctionalWorkflowAgent
AgentFactory: TypeAlias = Callable[[], HostedAgent | Awaitable[HostedAgent]]
WorkflowAgentTypes: TypeAlias = WorkflowAgent | FunctionalWorkflowAgent


def is_workflow_agent(agent: object) -> TypeGuard[WorkflowAgentTypes]:
    """Recognize the built-in workflow adapters, including subclasses."""
    return isinstance(agent, (WorkflowAgent, FunctionalWorkflowAgent))


def validate_agent_source(agent: HostedAgent | None, agent_factory: AgentFactory | None) -> None:
    if (agent is None) == (agent_factory is None):
        raise ValueError("Provide exactly one of agent or agent_factory.")
    if agent is not None and is_workflow_agent(agent):
        raise TypeError(
            "Workflow agents must be supplied through agent_factory. "
            "The factory must create a new workflow and new mutable executors for each request."
        )
    if agent_factory is not None and not callable(agent_factory):
        raise TypeError("agent_factory must be a callable accepting no arguments, not a coroutine object.")


class AgentFactoryResolver:
    """Resolve request agents without retaining completed workflow runtimes."""

    def __init__(self, factory: AgentFactory) -> None:
        self._factory = factory
        self._seen: weakref.WeakValueDictionary[int, object] = weakref.WeakValueDictionary()

    async def resolve(self) -> HostedAgent:
        result = self._factory()
        agent = await result if inspect.isawaitable(result) else result
        if not isinstance(agent, (SupportsAgentRun, FunctionalWorkflowAgent)):
            raise TypeError("agent_factory must return an agent implementing SupportsAgentRun or a workflow agent.")
        if is_workflow_agent(agent):
            workflow = agent.workflow if isinstance(agent, WorkflowAgent) else agent._workflow  # pyright: ignore[reportPrivateUsage]
            for value in (agent, workflow):
                if self._seen.get(id(value)) is value:
                    raise RuntimeError(
                        "agent_factory reused a workflow agent or workflow. Create a new workflow and "
                        "new mutable executors for each request."
                    )
            for value in (agent, workflow):
                self._seen[id(value)] = value
        return agent


@dataclass
class _ScopeLock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class ScopeLocks:
    """Serialize a scope while retaining locks for both holders and waiters."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str | None, ...], _ScopeLock] = {}

    @asynccontextmanager
    async def hold(self, key: tuple[str | None, ...]) -> AsyncGenerator[None]:
        entry = self._entries.setdefault(key, _ScopeLock())
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if not entry.users:
                del self._entries[key]


async def close_run_iterator(iterator: AsyncIterator[Any]) -> None:
    """Close the concrete run iterator, including known ResponseStream wrappers."""
    wrappers: list[ResponseStream[AgentResponseUpdate, AgentResponse]] = []
    current: Any = iterator
    while isinstance(current, ResponseStream):
        wrapper = cast(ResponseStream[AgentResponseUpdate, AgentResponse], current)
        wrappers.append(wrapper)
        current = wrapper._iterator  # pyright: ignore[reportPrivateUsage]
    try:
        close = getattr(current, "aclose", None)
        if close is not None:
            await close()
    finally:
        for wrapper in reversed(wrappers):
            await wrapper._run_cleanup_hooks()  # pyright: ignore[reportPrivateUsage]
