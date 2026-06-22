# Copyright (c) Microsoft. All rights reserved.

"""Host-agnostic plan for registering a MAF Workflow as a durable orchestration.

A MAF :class:`Workflow` is hosted by turning each graph node into a durable
primitive:

- each :class:`AgentExecutor` becomes a durable **entity**, and
- each other :class:`Executor` becomes a durable **activity**,

driven by a single workflow **orchestrator**.

The *decision* of which executor maps to which primitive is identical on every
host (Azure Functions or a standalone durabletask worker); only the *mechanism*
for registering them differs (Functions trigger decorators vs.
``worker.add_*``). :func:`plan_workflow_registration` captures the shared
decision so each host applies one consistent plan with its own registration
mechanism — analogous to .NET's shared ``DurableWorkflowOptions`` feeding
host-specific trigger generation.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_framework import AgentExecutor, Executor, Workflow

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
        activity_executors: Non-agent executors to register as durable activities.
        orchestrator_name: The orchestrator name to register and to start runs with.
    """

    agent_executors: list[AgentExecutor]
    activity_executors: list[Executor]
    orchestrator_name: str


def plan_workflow_registration(workflow: Workflow) -> WorkflowRegistrationPlan:
    """Classify a workflow's executors into the durable primitives to register.

    Args:
        workflow: The MAF :class:`Workflow` to host.

    Returns:
        A :class:`WorkflowRegistrationPlan` describing the agent executors
        (entities), non-agent executors (activities), and the orchestrator name.
    """
    agent_executors: list[AgentExecutor] = []
    activity_executors: list[Executor] = []

    for executor in workflow.executors.values():
        if isinstance(executor, AgentExecutor):
            agent_executors.append(executor)
        else:
            activity_executors.append(executor)

    return WorkflowRegistrationPlan(
        agent_executors=agent_executors,
        activity_executors=activity_executors,
        orchestrator_name=WORKFLOW_ORCHESTRATOR_NAME,
    )
