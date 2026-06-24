# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableAIAgentWorker.

Focuses on critical worker flows: agent registration, validation, callbacks, and lifecycle.
"""

from unittest.mock import Mock

import pytest

from agent_framework_durabletask import DurableAIAgentWorker


@pytest.fixture
def mock_grpc_worker() -> Mock:
    """Create a mock TaskHubGrpcWorker for testing."""
    mock = Mock()
    mock.add_entity = Mock(return_value="dafx-test_agent")
    mock.start = Mock()
    mock.stop = Mock()
    return mock


@pytest.fixture
def mock_agent() -> Mock:
    """Create a mock agent for testing."""
    agent = Mock()
    agent.name = "test_agent"
    return agent


@pytest.fixture
def agent_worker(mock_grpc_worker: Mock) -> DurableAIAgentWorker:
    """Create a DurableAIAgentWorker with mock worker."""
    return DurableAIAgentWorker(mock_grpc_worker)


class TestDurableAIAgentWorkerRegistration:
    """Test agent registration behavior."""

    def test_add_agent_accepts_agent_with_name(
        self, agent_worker: DurableAIAgentWorker, mock_agent: Mock, mock_grpc_worker: Mock
    ) -> None:
        """Verify that agents with names can be registered."""
        agent_worker.add_agent(mock_agent)

        # Verify entity was registered with underlying worker
        mock_grpc_worker.add_entity.assert_called_once()
        # Verify agent name is tracked
        assert "test_agent" in agent_worker.registered_agent_names

    def test_add_agent_rejects_agent_without_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """Verify that agents without names are rejected."""
        agent_no_name = Mock()
        agent_no_name.name = None

        with pytest.raises(ValueError, match="Agent must have a name"):
            agent_worker.add_agent(agent_no_name)

    def test_add_agent_rejects_empty_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """Verify that agents with empty names are rejected."""
        agent_empty_name = Mock()
        agent_empty_name.name = ""

        with pytest.raises(ValueError, match="Agent must have a name"):
            agent_worker.add_agent(agent_empty_name)

    def test_add_agent_rejects_duplicate_names(self, agent_worker: DurableAIAgentWorker, mock_agent: Mock) -> None:
        """Verify duplicate agent names are not allowed."""
        agent_worker.add_agent(mock_agent)

        # Try to register another agent with the same name
        duplicate_agent = Mock()
        duplicate_agent.name = "test_agent"

        with pytest.raises(ValueError, match="already registered"):
            agent_worker.add_agent(duplicate_agent)

    def test_registered_agent_names_tracks_multiple_agents(self, agent_worker: DurableAIAgentWorker) -> None:
        """Verify registered_agent_names tracks all registered agents."""
        agent1 = Mock()
        agent1.name = "agent1"
        agent2 = Mock()
        agent2.name = "agent2"
        agent3 = Mock()
        agent3.name = "agent3"

        agent_worker.add_agent(agent1)
        agent_worker.add_agent(agent2)
        agent_worker.add_agent(agent3)

        registered = agent_worker.registered_agent_names
        assert "agent1" in registered
        assert "agent2" in registered
        assert "agent3" in registered
        assert len(registered) == 3


class TestDurableAIAgentWorkerCallbacks:
    """Test callback configuration behavior."""

    def test_worker_level_callback_accepted(self, mock_grpc_worker: Mock) -> None:
        """Verify worker-level callback can be set."""
        mock_callback = Mock()
        agent_worker = DurableAIAgentWorker(mock_grpc_worker, callback=mock_callback)

        assert agent_worker is not None

    def test_agent_level_callback_accepted(self, agent_worker: DurableAIAgentWorker, mock_agent: Mock) -> None:
        """Verify agent-level callback can be set during registration."""
        mock_callback = Mock()

        # Should not raise exception
        agent_worker.add_agent(mock_agent, callback=mock_callback)

        assert "test_agent" in agent_worker.registered_agent_names

    def test_none_callback_accepted(self, mock_grpc_worker: Mock, mock_agent: Mock) -> None:
        """Verify None callback is valid (no callbacks required)."""
        agent_worker = DurableAIAgentWorker(mock_grpc_worker, callback=None)
        agent_worker.add_agent(mock_agent, callback=None)

        assert "test_agent" in agent_worker.registered_agent_names


class TestDurableAIAgentWorkerLifecycle:
    """Test worker lifecycle behavior."""

    def test_start_delegates_to_underlying_worker(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Verify start() delegates to wrapped worker."""
        agent_worker.start()

        mock_grpc_worker.start.assert_called_once()

    def test_stop_delegates_to_underlying_worker(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Verify stop() delegates to wrapped worker."""
        agent_worker.stop()

        mock_grpc_worker.stop.assert_called_once()

    def test_start_works_with_no_agents(self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock) -> None:
        """Verify worker can start even with no agents registered."""
        agent_worker.start()

        mock_grpc_worker.start.assert_called_once()

    def test_start_works_with_multiple_agents(self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock) -> None:
        """Verify worker can start with multiple agents registered."""
        agent1 = Mock()
        agent1.name = "agent1"
        agent2 = Mock()
        agent2.name = "agent2"

        agent_worker.add_agent(agent1)
        agent_worker.add_agent(agent2)
        agent_worker.start()

        mock_grpc_worker.start.assert_called_once()
        assert len(agent_worker.registered_agent_names) == 2


class TestDurableAIAgentWorkerWorkflow:
    """Test workflow registration, including the agent-executor identity fix."""

    def test_add_agent_with_entity_id_registers_under_override(
        self, agent_worker: DurableAIAgentWorker, mock_agent: Mock
    ) -> None:
        """An explicit entity_id overrides the agent name as the entity identity."""
        agent_worker.add_agent(mock_agent, entity_id="node-7")

        assert "node-7" in agent_worker.registered_agent_names
        assert "test_agent" not in agent_worker.registered_agent_names

    def test_configure_workflow_registers_agent_entity_by_executor_id(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Workflow agent executors register entities keyed by the workflow-scoped id.

        The orchestrator dispatches by the scoped identity
        ``{workflow}-{executorId}``, so an ``AgentExecutor(agent, id=...)`` whose id
        differs from the agent name must still be reachable under that scoped id.
        """
        from agent_framework import AgentExecutor

        agent = Mock()
        agent.name = "Reviewer"
        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = "custom-executor-id"
        agent_executor.agent = agent

        workflow = Mock()
        workflow.name = "review"
        workflow.executors = {"custom-executor-id": agent_executor}

        agent_worker.configure_workflow(workflow)

        assert "review-custom-executor-id" in agent_worker.registered_agent_names
        assert "Reviewer" not in agent_worker.registered_agent_names
        assert "custom-executor-id" not in agent_worker.registered_agent_names
        mock_grpc_worker.add_orchestrator.assert_called_once()

    def test_configure_workflow_registers_non_agent_executor_as_activity(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Non-agent executors are registered as activities, not entities."""
        from agent_framework import Executor

        activity_executor = Mock(spec=Executor)
        activity_executor.id = "router-node"

        workflow = Mock()
        workflow.name = "route"
        workflow.executors = {"router-node": activity_executor}

        agent_worker.configure_workflow(workflow)

        assert agent_worker.registered_agent_names == []
        mock_grpc_worker.add_activity.assert_called_once()
        mock_grpc_worker.add_orchestrator.assert_called_once()
        # The activity is registered under the workflow-scoped name.
        registered_activity = mock_grpc_worker.add_activity.call_args[0][0]
        assert registered_activity.__name__ == "dafx-route-router-node"


class TestMultiWorkflowRegistration:
    """Test hosting multiple workflows on one worker with scoped names."""

    def _agent_workflow(self, name: str, executor_id: str) -> Mock:
        from agent_framework import AgentExecutor

        agent = Mock()
        agent.name = "Assistant"
        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = executor_id
        agent_executor.agent = agent

        workflow = Mock()
        workflow.name = name
        workflow.executors = {executor_id: agent_executor}
        return workflow

    def test_two_workflows_reusing_executor_id_do_not_collide(self, agent_worker: DurableAIAgentWorker) -> None:
        """Two workflows that reuse an executor id register distinct scoped entities."""
        agent_worker.configure_workflow(self._agent_workflow("orders", "assistant"))
        agent_worker.configure_workflow(self._agent_workflow("billing", "assistant"))

        assert "orders-assistant" in agent_worker.registered_agent_names
        assert "billing-assistant" in agent_worker.registered_agent_names
        assert set(agent_worker.registered_workflow_names) == {"orders", "billing"}

    def test_registers_one_orchestrator_per_workflow(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Each configured workflow registers its own orchestrator."""
        agent_worker.configure_workflow(self._agent_workflow("orders", "a"))
        agent_worker.configure_workflow(self._agent_workflow("billing", "b"))

        assert mock_grpc_worker.add_orchestrator.call_count == 2
        registered_names = {call.args[0].__name__ for call in mock_grpc_worker.add_orchestrator.call_args_list}
        assert registered_names == {"dafx-orders", "dafx-billing"}

    def test_rejects_duplicate_workflow_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """Configuring two workflows with the same name is rejected."""
        agent_worker.configure_workflow(self._agent_workflow("orders", "a"))

        with pytest.raises(ValueError, match="already registered"):
            agent_worker.configure_workflow(self._agent_workflow("orders", "b"))

    def test_rejects_auto_generated_workflow_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """A workflow with an auto-generated WorkflowBuilder name is rejected."""
        import uuid

        workflow = self._agent_workflow(f"WorkflowBuilder-{uuid.uuid4()}", "a")

        with pytest.raises(ValueError, match="auto-generated"):
            agent_worker.configure_workflow(workflow)

    def test_rejects_invalid_workflow_name(self, agent_worker: DurableAIAgentWorker) -> None:
        """A workflow with an invalid name is rejected."""
        workflow = self._agent_workflow("has space", "a")

        with pytest.raises(ValueError, match="invalid"):
            agent_worker.configure_workflow(workflow)


class TestSubworkflowRegistration:
    """Test recursive registration of nested sub-workflows on one worker."""

    def _inner_agent_workflow(self, name: str, executor_id: str) -> Mock:
        from agent_framework import AgentExecutor

        agent = Mock()
        agent.name = "InnerAssistant"
        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = executor_id
        agent_executor.agent = agent

        workflow = Mock()
        workflow.name = name
        workflow.executors = {executor_id: agent_executor}
        return workflow

    def _outer_workflow(self, name: str, inner: Mock, *, sub_ids: tuple[str, ...] = ("sub",)) -> Mock:
        from agent_framework import Executor, WorkflowExecutor

        executors: dict[str, Mock] = {}
        for sub_id in sub_ids:
            sub = Mock(spec=WorkflowExecutor)
            sub.id = sub_id
            sub.workflow = inner
            sub.allow_direct_output = False
            executors[sub_id] = sub

        router = Mock(spec=Executor)
        router.id = "router"
        executors["router"] = router

        workflow = Mock()
        workflow.name = name
        workflow.executors = executors
        return workflow

    def test_nested_workflow_registers_both_orchestrations(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """Configuring an outer workflow registers the inner workflow's orchestration too."""
        inner = self._inner_agent_workflow("inner", "agent_node")
        outer = self._outer_workflow("outer", inner)

        agent_worker.configure_workflow(outer)

        registered = {call.args[0].__name__ for call in mock_grpc_worker.add_orchestrator.call_args_list}
        assert registered == {"dafx-outer", "dafx-inner"}

    def test_nested_workflow_registers_inner_agent_scoped(self, agent_worker: DurableAIAgentWorker) -> None:
        """The inner workflow's agent is registered under the inner-scoped id."""
        inner = self._inner_agent_workflow("inner", "agent_node")
        outer = self._outer_workflow("outer", inner)

        agent_worker.configure_workflow(outer)

        assert "inner-agent_node" in agent_worker.registered_agent_names

    def test_subworkflow_node_not_registered_as_activity(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """A WorkflowExecutor node is driven as a child orchestration, not an activity."""
        inner = self._inner_agent_workflow("inner", "agent_node")
        outer = self._outer_workflow("outer", inner)

        agent_worker.configure_workflow(outer)

        # Only the outer 'router' non-agent executor becomes an activity.
        registered_activities = {call.args[0].__name__ for call in mock_grpc_worker.add_activity.call_args_list}
        assert registered_activities == {"dafx-outer-router"}

    def test_top_level_names_exclude_nested_workflows(self, agent_worker: DurableAIAgentWorker) -> None:
        """``registered_workflow_names`` reports only top-level workflows."""
        inner = self._inner_agent_workflow("inner", "agent_node")
        outer = self._outer_workflow("outer", inner)

        agent_worker.configure_workflow(outer)

        assert agent_worker.registered_workflow_names == ["outer"]

    def test_shared_subworkflow_registered_once(
        self, agent_worker: DurableAIAgentWorker, mock_grpc_worker: Mock
    ) -> None:
        """A sub-workflow reused by two nodes registers its orchestration only once."""
        inner = self._inner_agent_workflow("inner", "agent_node")
        outer = self._outer_workflow("outer", inner, sub_ids=("sub_a", "sub_b"))

        agent_worker.configure_workflow(outer)

        registered = [call.args[0].__name__ for call in mock_grpc_worker.add_orchestrator.call_args_list]
        assert sorted(registered) == ["dafx-inner", "dafx-outer"]

    def test_nested_workflow_with_invalid_name_is_rejected(self, agent_worker: DurableAIAgentWorker) -> None:
        """A nested sub-workflow must also have a valid, stable name."""
        inner = self._inner_agent_workflow("has space", "agent_node")
        outer = self._outer_workflow("outer", inner)

        with pytest.raises(ValueError, match="invalid"):
            agent_worker.configure_workflow(outer)

    def test_different_subworkflow_sharing_a_name_is_rejected(self, agent_worker: DurableAIAgentWorker) -> None:
        """Two different sub-workflow instances that share a name collide and are rejected."""
        from agent_framework import Executor, WorkflowExecutor

        inner_a = self._inner_agent_workflow("shared", "agent_node")
        inner_b = self._inner_agent_workflow("shared", "other_node")  # different instance, same name

        sub_a = Mock(spec=WorkflowExecutor)
        sub_a.id = "a"
        sub_a.workflow = inner_a
        sub_b = Mock(spec=WorkflowExecutor)
        sub_b.id = "b"
        sub_b.workflow = inner_b
        router = Mock(spec=Executor)
        router.id = "router"
        outer = Mock()
        outer.name = "outer"
        outer.executors = {"a": sub_a, "b": sub_b, "router": router}

        with pytest.raises(ValueError, match="different workflow|different workflows"):
            agent_worker.configure_workflow(outer)

    def test_executor_id_with_reserved_separator_is_rejected(self, agent_worker: DurableAIAgentWorker) -> None:
        """An executor id containing the nested-HITL separator is rejected at registration."""
        workflow = self._agent_workflow_with_executor_id("orders", "bad~id")

        with pytest.raises(ValueError, match="reserved sub-workflow request separator"):
            agent_worker.configure_workflow(workflow)

    @staticmethod
    def _agent_workflow_with_executor_id(name: str, executor_id: str) -> Mock:
        from agent_framework import AgentExecutor

        agent = Mock()
        agent.name = "Assistant"
        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = executor_id
        agent_executor.agent = agent
        workflow = Mock()
        workflow.name = name
        workflow.executors = {executor_id: agent_executor}
        return workflow


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
