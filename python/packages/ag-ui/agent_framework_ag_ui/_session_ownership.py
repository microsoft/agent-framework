# Copyright (c) Microsoft. All rights reserved.

"""Authorization-scope ownership of the agent sessions that a workflow holds.

An ``AgentExecutor`` owns one ``AgentSession`` for its whole lifetime. Conversation history, pending approval
requests, and standing approval rules live in that session, and the session is not tied to a caller. An executor
that serves two authorization scopes would therefore expose the conversation and approval state of one scope to the
other. AG-UI binds each executor to the first authorization scope that runs it and refuses every other scope.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Iterator

from agent_framework import AgentExecutor, Workflow, WorkflowAgent, WorkflowExecutor

SCOPE_CONFLICT_CODE = "WORKFLOW_SCOPE_CONFLICT"
SCOPE_CONFLICT_MESSAGE = "This workflow is bound to a different authorization scope."
SCOPE_CONFLICT_LOG_MESSAGE = (
    "Workflow %r holds AgentExecutor instances that already belong to another authorization scope. Each "
    "AgentExecutor owns one AgentSession, so serving a second scope would expose the first scope's conversation "
    "and approval state. Pass AgentFrameworkWorkflow(workflow_factory=...) with a factory that builds a new "
    "Workflow, including new AgentExecutor instances, for every call, or register the endpoint with "
    "single_user=True when every caller is the same principal."
)

_EXECUTOR_SCOPES: weakref.WeakKeyDictionary[AgentExecutor, str] = weakref.WeakKeyDictionary()
_CLAIM_LOCK = threading.Lock()


def _agent_executors(workflow: Workflow, visited: set[int] | None = None) -> Iterator[AgentExecutor]:
    """Yield the ``AgentExecutor`` instances of ``workflow`` and of every workflow nested in it.

    Nested workflows are sub-workflows of ``WorkflowExecutor`` and the workflow behind a ``WorkflowAgent`` that an
    ``AgentExecutor`` wraps.
    """
    visited = set() if visited is None else visited
    if id(workflow) in visited:
        return
    visited.add(id(workflow))
    for executor in workflow.get_executors_list():
        nested: Workflow | None = None
        if isinstance(executor, AgentExecutor):
            yield executor
            if isinstance(executor.agent, WorkflowAgent):
                nested = executor.agent.workflow
        elif isinstance(executor, WorkflowExecutor):
            nested = executor.workflow
        if nested is not None:
            yield from _agent_executors(nested, visited)


def claim_agent_executors(workflow: Workflow, scope: str | None) -> bool:
    """Bind every ``AgentExecutor`` of ``workflow`` to ``scope``.

    Args:
        workflow: The workflow that is about to run, including the workflows nested in it.
        scope: The authorization scope of the run. ``None`` means the run has no scope, so nothing is bound.

    Returns:
        ``False`` when an executor already belongs to a different scope. Nothing is bound in that case.
    """
    if scope is None:
        return True
    executors = list(_agent_executors(workflow))
    with _CLAIM_LOCK:
        if any(_EXECUTOR_SCOPES.get(executor, scope) != scope for executor in executors):
            return False
        for executor in executors:
            _EXECUTOR_SCOPES[executor] = scope
    return True
