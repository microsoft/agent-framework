# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for plan_workflow_registration.

Verifies the host-agnostic decision of which executors become durable entities
(agent executors) versus durable activities (everything else), and that agent
executors are carried whole so each host can register entities under the
executor id the orchestrator dispatches to.
"""

from unittest.mock import Mock

import pytest
from agent_framework import AgentExecutor, Executor, WorkflowExecutor

from agent_framework_durabletask import (
    WorkflowRegistrationPlan,
    collect_hosted_workflows,
    plan_workflow_registration,
)


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


def _subworkflow_executor(executor_id: str, inner_workflow: Mock) -> Mock:
    executor = Mock(spec=WorkflowExecutor)
    executor.id = executor_id
    executor.workflow = inner_workflow
    return executor


def _workflow(name: str, executors: dict[str, Mock]) -> Mock:
    workflow = Mock()
    workflow.name = name
    workflow.executors = executors
    return workflow


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

    def test_subworkflow_executor_classified_separately(self) -> None:
        """A WorkflowExecutor goes to subworkflow_executors, not activities."""
        inner = _workflow("inner", {})
        sub_exec = _subworkflow_executor("sub-node", inner)
        activity_exec = _activity_executor("router-node")
        workflow = _workflow("outer", {"sub-node": sub_exec, "router-node": activity_exec})

        plan = plan_workflow_registration(workflow)

        assert plan.subworkflow_executors == [sub_exec]
        assert plan.activity_executors == [activity_exec]
        assert plan.agent_executors == []


class TestCollectHostedWorkflows:
    """Test the recursive walk over nested sub-workflows."""

    def test_single_workflow_yields_itself(self) -> None:
        workflow = _workflow("solo", {"node": _activity_executor("node")})

        assert [w.name for w in collect_hosted_workflows(workflow)] == ["solo"]

    def test_yields_nested_subworkflows_parent_first(self) -> None:
        inner = _workflow("inner", {"leaf": _activity_executor("leaf")})
        sub_exec = _subworkflow_executor("sub", inner)
        outer = _workflow("outer", {"sub": sub_exec})

        assert [w.name for w in collect_hosted_workflows(outer)] == ["outer", "inner"]

    def test_dedupes_shared_subworkflow_by_name(self) -> None:
        """A sub-workflow reused by two nodes is yielded once."""
        inner = _workflow("shared", {"leaf": _activity_executor("leaf")})
        sub_a = _subworkflow_executor("a", inner)
        sub_b = _subworkflow_executor("b", inner)
        outer = _workflow("outer", {"a": sub_a, "b": sub_b})

        assert [w.name for w in collect_hosted_workflows(outer)] == ["outer", "shared"]

    def test_walks_multiple_levels(self) -> None:
        leaf = _workflow("leaf_wf", {"x": _activity_executor("x")})
        mid = _workflow("mid_wf", {"l": _subworkflow_executor("l", leaf)})
        top = _workflow("top_wf", {"m": _subworkflow_executor("m", mid)})

        assert [w.name for w in collect_hosted_workflows(top)] == ["top_wf", "mid_wf", "leaf_wf"]

    def test_rejects_two_different_workflows_sharing_a_name(self) -> None:
        """Two different sub-workflow instances with the same name collide and raise."""
        inner_a = _workflow("shared", {"x": _activity_executor("x")})
        inner_b = _workflow("shared", {"y": _activity_executor("y")})  # different instance, same name
        outer = _workflow("outer", {"a": _subworkflow_executor("a", inner_a), "b": _subworkflow_executor("b", inner_b)})

        with pytest.raises(ValueError, match="collides"):
            list(collect_hosted_workflows(outer))

    def test_rejects_case_insensitive_name_collision(self) -> None:
        """Two different instances whose names differ only by case collide and raise.

        The route ownership guard compares the durable orchestration name
        case-insensitively, so case-only name variants must be rejected here or one
        workflow's routes could operate on the other's instances.
        """
        inner_a = _workflow("shared", {"x": _activity_executor("x")})
        inner_b = _workflow("Shared", {"y": _activity_executor("y")})  # case-only difference
        outer = _workflow("outer", {"a": _subworkflow_executor("a", inner_a), "b": _subworkflow_executor("b", inner_b)})

        with pytest.raises(ValueError, match="collides"):
            list(collect_hosted_workflows(outer))

    def test_same_instance_reused_is_deduped_not_rejected(self) -> None:
        """The same sub-workflow instance referenced by two nodes (fan-out) is yielded once."""
        inner = _workflow("shared", {"x": _activity_executor("x")})
        outer = _workflow("outer", {"a": _subworkflow_executor("a", inner), "b": _subworkflow_executor("b", inner)})

        assert [w.name for w in collect_hosted_workflows(outer)] == ["outer", "shared"]
