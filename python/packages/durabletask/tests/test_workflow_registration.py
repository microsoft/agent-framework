# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for plan_workflow_registration.

Verifies the host-agnostic decision of which executors become durable entities
(agent executors) versus durable activities (everything else), and that agent
executors are carried whole so each host can register entities under the
executor id the orchestrator dispatches to.
"""

from unittest.mock import Mock

from agent_framework import AgentExecutor, Executor

from agent_framework_durabletask import WorkflowRegistrationPlan, plan_workflow_registration
from agent_framework_durabletask._workflows.orchestrator import WORKFLOW_ORCHESTRATOR_NAME


def _agent_executor(executor_id: str, agent_name: str) -> Mock:
    agent = Mock()
    agent.name = agent_name
    executor = Mock(spec=AgentExecutor)
    executor.id = executor_id
    executor.agent = agent
    return executor


def _activity_executor(executor_id: str) -> Mock:
    executor = Mock(spec=Executor)
    executor.id = executor_id
    return executor


class TestPlanWorkflowRegistration:
    """Test classification of workflow executors into durable primitives."""

    def test_agent_executor_classified_as_entity(self) -> None:
        """An AgentExecutor is carried whole in agent_executors."""
        agent_exec = _agent_executor("reviewer-node", "Reviewer")
        workflow = Mock()
        workflow.executors = {"reviewer-node": agent_exec}

        plan = plan_workflow_registration(workflow)

        assert plan.agent_executors == [agent_exec]
        assert plan.activity_executors == []
        assert plan.orchestrator_name == WORKFLOW_ORCHESTRATOR_NAME

    def test_non_agent_executor_classified_as_activity(self) -> None:
        """A plain Executor is classified as an activity."""
        activity_exec = _activity_executor("router-node")
        workflow = Mock()
        workflow.executors = {"router-node": activity_exec}

        plan = plan_workflow_registration(workflow)

        assert plan.agent_executors == []
        assert plan.activity_executors == [activity_exec]

    def test_mixed_executors_are_partitioned(self) -> None:
        """Agent and non-agent executors are split into the correct buckets."""
        agent_exec = _agent_executor("agent-node", "Agent")
        activity_exec = _activity_executor("activity-node")
        workflow = Mock()
        workflow.executors = {"agent-node": agent_exec, "activity-node": activity_exec}

        plan = plan_workflow_registration(workflow)

        assert plan.agent_executors == [agent_exec]
        assert plan.activity_executors == [activity_exec]

    def test_agent_executor_id_is_preserved_when_distinct_from_name(self) -> None:
        """The plan keeps the executor (and its id), not just the bare agent.

        This is the core of the identity fix: dispatch targets the executor id,
        so registration must be able to use the id even when it differs from
        ``agent.name``.
        """
        agent_exec = _agent_executor("custom-executor-id", "ReusedAgentName")
        workflow = Mock()
        workflow.executors = {"custom-executor-id": agent_exec}

        plan = plan_workflow_registration(workflow)

        assert plan.agent_executors[0].id == "custom-executor-id"
        assert plan.agent_executors[0].agent.name == "ReusedAgentName"

    def test_returns_workflow_registration_plan(self) -> None:
        """The return value is a WorkflowRegistrationPlan."""
        workflow = Mock()
        workflow.executors = {}

        plan = plan_workflow_registration(workflow)

        assert isinstance(plan, WorkflowRegistrationPlan)
        assert plan.agent_executors == []
        assert plan.activity_executors == []
