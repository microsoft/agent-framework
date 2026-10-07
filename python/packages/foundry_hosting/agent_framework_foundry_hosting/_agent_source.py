# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import weakref
from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias, TypeGuard, cast

from agent_framework import SupportsAgentRun, Workflow, WorkflowAgent, WorkflowExecutor

from ._workflow_source import workflow_agents

AgentSource: TypeAlias = SupportsAgentRun | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]]

_WORKFLOW_AGENT_INSTANCE_MESSAGE = (
    "WorkflowAgent instances cannot be hosted directly: a WorkflowAgent wraps mutable workflow and executor "
    "state that would be shared by every request. Pass a zero-argument callable that builds a fresh "
    "WorkflowAgent for each call, or host the built Workflow through workflow=."
)
_WORKFLOW_AGENT_REUSE_MESSAGE = (
    "The agent factory must return a fresh WorkflowAgent with a fresh workflow and executors for each request; "
    "it returned an object that was already served by an earlier request."
)
_WORKFLOW_AGENT_WEAKREF_MESSAGE = (
    "Every workflow, executor, and wrapped agent produced by the agent factory must support weak references "
    "so the host can verify it is not shared across requests without retaining it; got an instance of {type}."
)


def is_agent(value: object) -> TypeGuard[SupportsAgentRun]:
    return not inspect.isclass(value) and isinstance(value, SupportsAgentRun)


def validate_agent_source(source: object) -> None:
    if isinstance(source, WorkflowAgent):
        # A shared WorkflowAgent carries per-run workflow and executor state across unrelated requests, so
        # only request-scoped factories are accepted for workflow agents. Regular agents keep instance support.
        raise TypeError(_WORKFLOW_AGENT_INSTANCE_MESSAGE)
    if is_agent(source):
        return
    if not callable(source):
        raise TypeError("agent must be an agent instance or a zero-argument callable that creates one.")
    try:
        inspect.signature(source).bind()
    except (TypeError, ValueError) as exc:
        raise TypeError("agent callable must accept no arguments.") from exc


class WorkflowAgentReuseGuard:
    """Reject a factory that reuses a served ``WorkflowAgent``, workflow, executor, or wrapped agent.

    Mirrors ``WorkflowResolver`` for native workflows: this is an identity check on objects already served, not
    a proof that the factory allocates every resource freshly. The walk covers the outer workflow, every executor,
    each child workflow reached through a ``WorkflowExecutor`` (recursively), and every agent wrapped by an
    executor, because all of them carry per-run mutable state.

    Identity is tracked by ``id()`` and is only meaningful while the object is alive, so every served object is
    tracked through a weak reference whose callback forgets the identity on collection. ``WorkflowAgent``,
    ``Workflow``, ``Executor``, and ``Agent`` all support weak references (including slotted subclasses, since
    no base in their hierarchy defines ``__slots__``). A duck-typed object that cannot be weakly referenced is
    rejected up front: retaining it strongly would grow host memory for every request the factory serves, and
    evicting it after a bound would silently accept reuse in a long-lived host. Rejecting is the only option that
    keeps both memory and the sharing check exact.
    """

    def __init__(self) -> None:
        self._owned: dict[int, weakref.ReferenceType[Any]] = {}

    def claim(self, agent: WorkflowAgent) -> None:
        resources: list[object] = [agent]

        def collect(graph: Workflow) -> None:
            resources.append(graph)
            for executor in graph.get_executors_list():
                resources.append(executor)
                if isinstance(executor, WorkflowExecutor):
                    collect(executor.workflow)

        collect(agent.workflow)
        resources.extend(workflow_agents(agent.workflow))
        unique_resources = {id(resource): resource for resource in resources}
        # Validate and check every identity before recording any, so a rejected claim leaves no partial state
        # behind that could wrongly block the next fresh agent.
        references: dict[int, weakref.ReferenceType[Any]] = {}
        for identifier, resource in unique_resources.items():
            try:
                references[identifier] = weakref.ref(resource, lambda ref, key=identifier: self._forget(key, ref))
            except TypeError:
                raise TypeError(_WORKFLOW_AGENT_WEAKREF_MESSAGE.format(type=type(resource).__qualname__)) from None
            previous = self._owned.get(identifier)
            if previous is not None and previous() is resource:
                raise RuntimeError(_WORKFLOW_AGENT_REUSE_MESSAGE)
        self._owned.update(references)

    def _forget(self, key: int, reference: weakref.ReferenceType[Any]) -> None:
        if self._owned.get(key) is reference:
            del self._owned[key]


async def resolve_agent(source: AgentSource, *, reuse_guard: WorkflowAgentReuseGuard | None = None) -> SupportsAgentRun:
    """Resolve an agent instance or request-scoped agent factory.

    When ``reuse_guard`` is given, a ``WorkflowAgent`` produced by the factory must not have been served before.
    """
    if is_agent(source):
        return source

    factory = cast(Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]], source)
    result = factory()
    agent = await result if inspect.isawaitable(result) else result
    if not is_agent(agent):
        raise TypeError("The agent factory must return an object implementing SupportsAgentRun.")
    if reuse_guard is not None and isinstance(agent, WorkflowAgent):
        reuse_guard.claim(agent)
    return agent
