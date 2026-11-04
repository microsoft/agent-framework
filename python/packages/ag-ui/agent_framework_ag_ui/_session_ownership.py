# Copyright (c) Microsoft. All rights reserved.

"""Authorization-scope ownership of the agent sessions that a workflow holds.

An ``AgentExecutor`` keeps one ``AgentSession`` between runs. Conversation history, pending approval requests, and
standing approval rules live in that session, and the session is not tied to a caller. An executor, or a session,
that serves two authorization scopes would therefore expose the conversation and approval state of one scope to the
other. AG-UI binds each executor, and the session it holds, to the first authorization scope that runs it and
refuses every other scope. A run without a scope is an owner of its own, so a workflow that ran locally is not
handed to an authorization scope later, and the reverse.

The binding follows live objects. It does not see state that an application loads from storage into a new object.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Iterator
from typing import Any, Final

from agent_framework import AgentExecutor, AgentSession, Workflow, WorkflowAgent, WorkflowExecutor

SCOPE_CONFLICT_CODE = "WORKFLOW_SCOPE_CONFLICT"
SCOPE_CONFLICT_MESSAGE = "This workflow is bound to a different authorization scope."
SCOPE_CONFLICT_LOG_MESSAGE = (
    "Workflow %r holds an AgentExecutor or AgentSession that already serves a different authorization scope, "
    "or runs without a scope. An AgentSession keeps the conversation and approval state of one scope, so serving "
    "another scope would expose that state. Pass AgentFrameworkWorkflow(workflow_factory=...) with a factory that "
    "builds a new Workflow, including new AgentExecutor and AgentSession instances, for every call, or register "
    "the endpoint with single_user=True when every caller is the same principal."
)

# The owner of runs that carry no authorization scope. It never equals a scope string.
_UNSCOPED: Final = object()


class IdentityOwners:
    """Owners of objects, keyed by object identity.

    The registry never calls ``__hash__`` or ``__eq__`` of the objects it tracks. An unhashable object works, and two
    distinct objects that compare equal stay apart. It holds weak references only, and an entry disappears when its
    object is collected. Callers serialize ``bind`` and ``owner_of`` themselves. The cleanup callback takes no lock,
    because it can run at any time, including while a caller holds one.
    """

    def __init__(self) -> None:
        self._entries: dict[int, tuple[weakref.ref[Any], object]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def owner_of(self, subject: object, default: object) -> object:
        """Return the owner of ``subject``, or ``default`` when it has none."""
        entry = self._entries.get(id(subject))
        # A dead or different referent means the identity was reused after the original object was collected.
        return entry[1] if entry is not None and entry[0]() is subject else default

    def bind(self, subject: object, owner: object) -> None:
        """Bind ``subject`` to ``owner`` and replace any previous owner."""
        key = id(subject)
        entries = self._entries
        entry = entries.get(key)
        if entry is not None and entry[0]() is subject:
            entries[key] = (entry[0], owner)
            return

        def forget(reference: weakref.ref[Any]) -> None:
            current = entries.get(key)
            if current is not None and current[0] is reference:
                entries.pop(key, None)

        entries[key] = (weakref.ref(subject, forget), owner)


_OWNERS = IdentityOwners()
_CLAIM_LOCK = threading.Lock()


def _unwrap_a2ui_runners(agent: Any) -> Any:
    """Return the agent inside the A2UI runners that wrap ``agent``."""
    try:
        from ._a2ui import A2UIAgent
    except ImportError:
        return agent
    while isinstance(agent, A2UIAgent):
        agent = agent.inner_agent
    return agent


def _workflow_behind(agent: Any) -> Workflow | None:
    """Return the workflow that ``agent`` runs, looking through A2UI runners, or ``None``."""
    unwrapped = _unwrap_a2ui_runners(agent)
    return unwrapped.workflow if isinstance(unwrapped, WorkflowAgent) else None


def _agent_executors(workflow: object, visited: set[int] | None = None) -> Iterator[AgentExecutor]:
    """Yield the ``AgentExecutor`` instances of ``workflow`` and of every workflow nested in it.

    Nested workflows are sub-workflows of ``WorkflowExecutor`` and the workflow behind a ``WorkflowAgent`` that an
    ``AgentExecutor`` wraps. An object that is not a ``Workflow`` has no executors to inspect.
    """
    if not isinstance(workflow, Workflow):
        return
    visited = set() if visited is None else visited
    if id(workflow) in visited:
        return
    visited.add(id(workflow))
    for executor in workflow.get_executors_list():
        nested: Workflow | None = None
        if isinstance(executor, AgentExecutor):
            yield executor
            nested = _workflow_behind(executor.agent)
        elif isinstance(executor, WorkflowExecutor):
            nested = executor.workflow
        if nested is not None:
            yield from _agent_executors(nested, visited)


def _state_holders(workflow: Workflow) -> Iterator[AgentExecutor | AgentSession]:
    """Yield what keeps conversation and approval state: each ``AgentExecutor`` and the session it holds.

    Executors can share a session, for example to share one service-side conversation inside one workflow.
    """
    for executor in _agent_executors(workflow):
        yield executor
        session = getattr(executor, "_session", None)
        if isinstance(session, AgentSession):
            yield session


def claim_agent_executors(workflow: Workflow, scope: str | None) -> bool:
    """Bind every ``AgentExecutor`` of ``workflow``, and the session each one holds, to ``scope``.

    Args:
        workflow: The workflow that is about to run, including the workflows nested in it.
        scope: The authorization scope of the run. ``None`` stands for runs without a scope, which own what they
            run just as a scope does.

    Returns:
        ``False`` when an executor or session already belongs to a different owner. Nothing is bound in that case.
    """
    owner: object = _UNSCOPED if scope is None else scope
    holders = list(_state_holders(workflow))
    with _CLAIM_LOCK:
        if any(_OWNERS.owner_of(holder, owner) != owner for holder in holders):
            return False
        for holder in holders:
            _OWNERS.bind(holder, owner)
    return True


def claim_workflow_agent(agent: Any, scope: str | None) -> bool:
    """Bind the executors behind ``agent`` to ``scope`` when ``agent`` runs a workflow.

    Looks through A2UI runners. An agent that does not run a workflow keeps its state in sessions that AG-UI
    already scopes itself, so it needs no claim.
    """
    workflow = _workflow_behind(agent)
    return workflow is None or claim_agent_executors(workflow, scope)
