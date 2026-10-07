# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
import weakref
from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias, TypeGuard, cast

from agent_framework import SupportsAgentRun, WorkflowAgent

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
    """Reject a factory that hands the same ``WorkflowAgent``, workflow, or executor to more than one request.

    Mirrors ``WorkflowResolver`` for native workflows: this is an identity check on objects already served, not
    a proof that the factory allocates every resource freshly.

    Identity is tracked by ``id()`` and is only meaningful while the object is alive, so every served object is
    tracked through a weak reference whose callback forgets the identity on collection. ``WorkflowAgent``,
    ``Workflow``, and ``Executor`` all support weak references (including slotted subclasses, since no base in
    their hierarchy defines ``__slots__``). A duck-typed executor that cannot be weakly referenced is retained
    strongly for the lifetime of the guard instead: that keeps the check exact at the cost of host memory
    proportional to how many such executors the factory creates, which is preferred over an eviction window
    that would silently accept reuse in a long-lived host.
    """

    def __init__(self) -> None:
        self._owned: dict[int, weakref.ReferenceType[Any]] = {}
        self._retained: dict[int, object] = {}

    def claim(self, agent: WorkflowAgent) -> None:
        resources: list[object] = [agent, agent.workflow, *agent.workflow.get_executors_list()]
        unique_resources = {id(resource): resource for resource in resources}
        # Check every identity before recording any, so a rejected claim leaves no partial state behind.
        for identifier, resource in unique_resources.items():
            previous = self._owned.get(identifier)
            if (previous is not None and previous() is resource) or self._retained.get(identifier) is resource:
                raise RuntimeError(_WORKFLOW_AGENT_REUSE_MESSAGE)
        for identifier, resource in unique_resources.items():
            try:
                self._owned[identifier] = weakref.ref(resource, lambda ref, key=identifier: self._forget(key, ref))
            except TypeError:
                self._retained[identifier] = resource

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
