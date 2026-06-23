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

from .orchestrator import WORKFLOW_ORCHESTRATOR_NAME


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
        orchestrator_name: Deprecated fixed orchestrator name. Hosts derive the
            actual per-workflow name via
            :func:`~agent_framework_durabletask._workflows.naming.workflow_orchestrator_name`;
            this field is retained for source compatibility only.
    """

    agent_executors: list[AgentExecutor]
    activity_executors: list[Executor]
    subworkflow_executors: list[WorkflowExecutor]
    orchestrator_name: str


def plan_workflow_registration(workflow: Workflow) -> WorkflowRegistrationPlan:
    """Classify a workflow's executors into the durable primitives to register.

    Args:
        workflow: The MAF :class:`Workflow` to host.

    Returns:
        A :class:`WorkflowRegistrationPlan` describing the agent executors
        (entities), sub-workflow executors (child orchestrations), the remaining
        non-agent executors (activities), and the orchestrator name.
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
        orchestrator_name=WORKFLOW_ORCHESTRATOR_NAME,
    )


def collect_hosted_workflows(workflow: Workflow) -> Iterator[Workflow]:
    """Yield ``workflow`` and every nested sub-workflow, deduped by name.

    A host registers the orchestration primitives for each yielded workflow so a
    parent orchestration can invoke its sub-workflows as child orchestrations.
    Workflows are deduped by :attr:`Workflow.name`: a sub-workflow reused across
    the tree (or shared by two top-level workflows) is yielded once. The top-level
    ``workflow`` is yielded first.

    Args:
        workflow: The top-level workflow to walk.

    Yields:
        Each distinct workflow in the nesting tree, parent before child.
    """
    seen: set[str] = set()

    def _walk(current: Workflow) -> Iterator[Workflow]:
        if current.name in seen:
            return
        seen.add(current.name)
        yield current
        plan = plan_workflow_registration(current)
        for sub in plan.subworkflow_executors:
            yield from _walk(sub.workflow)

    yield from _walk(workflow)
