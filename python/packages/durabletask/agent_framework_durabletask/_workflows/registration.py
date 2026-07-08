# Copyright (c) Microsoft. All rights reserved.

"""Host-agnostic plan for registering a MAF Workflow as a durable orchestration.

A MAF :class:`Workflow` is hosted by turning each graph node into a durable
primitive:

- each :class:`AgentExecutor` becomes a durable **entity**,
- each :class:`WorkflowExecutor` (a nested sub-workflow) becomes a durable
  **child orchestration**, and
- each other :class:`Executor` becomes a durable **activity**,

driven by a single workflow **orchestrator**.

The *decision* of which executor maps to which primitive is identical on every
host (Azure Functions or a standalone durabletask worker); only the *mechanism*
for registering them differs (Functions trigger decorators vs.
``worker.add_*``). :func:`plan_workflow_registration` captures the shared
decision so each host applies one consistent plan with its own registration
mechanism — analogous to .NET's shared ``DurableWorkflowOptions`` feeding
host-specific trigger generation.

Sub-workflows nest: a hosted workflow may contain :class:`WorkflowExecutor`
nodes whose inner workflows must themselves be registered (their orchestrator,
agents, and activities) so the parent can drive them via
``call_sub_orchestrator``. :func:`collect_hosted_workflows` walks that tree so a
host registers every reachable workflow exactly once.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from agent_framework import AgentExecutor, Executor, Workflow, WorkflowExecutor


@dataclass
class WorkflowRegistrationPlan:
    """The durable primitives a workflow registers, independent of host.

    Attributes:
        agent_executors: Agent executors to register as durable entities. The
            full :class:`AgentExecutor` is carried (not just its agent) so each
            host can register the entity under the executor's ``id`` — the same
            identity the orchestrator dispatches to — which keeps
            ``AgentExecutor(agent, id=...)`` working when the id differs from
            ``agent.name``.
        activity_executors: Non-agent, non-subworkflow executors to register as
            durable activities.
        subworkflow_executors: :class:`WorkflowExecutor` nodes whose inner
            workflows are driven as durable child orchestrations. The node itself
            is *not* registered as an activity; its inner workflow is registered
            separately (see :func:`collect_hosted_workflows`).
    """

    agent_executors: list[AgentExecutor]
    activity_executors: list[Executor]
    subworkflow_executors: list[WorkflowExecutor]


def plan_workflow_registration(workflow: Workflow) -> WorkflowRegistrationPlan:
    """Classify a workflow's executors into the durable primitives to register.

    Args:
        workflow: The MAF :class:`Workflow` to host.

    Returns:
        A :class:`WorkflowRegistrationPlan` describing the agent executors
        (entities), sub-workflow executors (child orchestrations), and the
        remaining non-agent executors (activities).
    """
    agent_executors: list[AgentExecutor] = []
    activity_executors: list[Executor] = []
    subworkflow_executors: list[WorkflowExecutor] = []

    for executor in workflow.executors.values():
        if isinstance(executor, AgentExecutor):
            agent_executors.append(executor)
        elif isinstance(executor, WorkflowExecutor):
            subworkflow_executors.append(executor)
        else:
            activity_executors.append(executor)

    return WorkflowRegistrationPlan(
        agent_executors=agent_executors,
        activity_executors=activity_executors,
        subworkflow_executors=subworkflow_executors,
    )


def collect_hosted_workflows(workflow: Workflow) -> Iterator[Workflow]:
    """Yield ``workflow`` and every nested sub-workflow, deduped by name.

    A host registers the orchestration primitives for each yielded workflow so a
    parent orchestration can invoke its sub-workflows as child orchestrations.
    Workflows are deduped by :attr:`Workflow.name`, **compared case-insensitively**:
    the *same* sub-workflow instance reused across the tree (or shared by two
    top-level workflows) is yielded once, which is the expected fan-out pattern. Two
    **different** workflow instances whose names collide (including case-only
    differences) are rejected, since both would resolve to one durable orchestration
    (``dafx-{name}``) -- whose name the route ownership check compares
    case-insensitively -- and would silently shadow each other. The top-level
    ``workflow`` is yielded first.

    Args:
        workflow: The top-level workflow to walk.

    Yields:
        Each distinct workflow in the nesting tree, parent before child.

    Raises:
        ValueError: If two different workflow instances in the tree have colliding
            (case-insensitive) names.
    """
    seen: dict[str, Workflow] = {}

    def _walk(current: Workflow) -> Iterator[Workflow]:
        key = current.name.casefold()
        existing = seen.get(key)
        if existing is not None:
            if existing is not current:
                raise ValueError(
                    f"A different workflow named '{current.name}' collides with '{existing.name}'. A "
                    f"workflow name maps to a single durable orchestration ('dafx-{current.name}'), "
                    "compared case-insensitively, so names must be unique within a hosted composition. "
                    "Rename one, or reuse the same Workflow instance if they are meant to be the same "
                    "sub-workflow."
                )
            return
        seen[key] = current
        yield current
        plan = plan_workflow_registration(current)
        for sub in plan.subworkflow_executors:
            yield from _walk(sub.workflow)

    yield from _walk(workflow)
