# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework import (
    AgentExecutor,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)


class DummyAgent(BaseAgent):
    async def run(self, messages=None, *, thread: AgentThread | None = None, **kwargs):  # type: ignore[override]
        norm: list[ChatMessage] = []
        if messages:
            for m in messages:  # type: ignore[iteration-over-optional]
                if isinstance(m, ChatMessage):
                    norm.append(m)
                elif isinstance(m, str):
                    norm.append(ChatMessage(role=Role.USER, text=m))
        return AgentRunResponse(messages=norm)

    async def run_stream(self, messages=None, *, thread: AgentThread | None = None, **kwargs):  # type: ignore[override]
        # Minimal async generator
        yield AgentRunResponseUpdate()


def test_builder_accepts_agents_directly():
    agent1 = DummyAgent(id="agent1", name="writer")
    agent2 = DummyAgent(id="agent2", name="reviewer")

    wf = WorkflowBuilder().set_start_executor(agent1).add_edge(agent1, agent2).build()

    # Confirm auto-wrapped executors use agent names as IDs
    assert wf.start_executor_id == "writer"
    assert any(isinstance(e, AgentExecutor) and e.id in {"writer", "reviewer"} for e in wf.executors.values())


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: Any


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext[MockMessage]) -> None:
        """A mock handler that does nothing."""
        pass


class MockAggregator(Executor):
    """A mock executor that aggregates results from multiple executors."""

    @handler
    async def mock_handler(self, messages: list[MockMessage], ctx: WorkflowContext[MockMessage]) -> None:
        # This mock simply returns the data incremented by 1
        pass


def test_workflow_builder_without_start_executor_throws():
    """Test creating a workflow builder without a start executor."""

    builder = WorkflowBuilder()
    with pytest.raises(ValueError):
        builder.build()


def test_workflow_builder_fluent_api():
    """Test the fluent API of the workflow builder."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")
    executor_c = MockExecutor(id="executor_c")
    executor_d = MockExecutor(id="executor_d")
    executor_e = MockAggregator(id="executor_e")
    executor_f = MockExecutor(id="executor_f")

    workflow = (
        WorkflowBuilder()
        .set_start_executor(executor_a)
        .add_edge(executor_a, executor_b)
        .add_fan_out_edges(executor_b, [executor_c, executor_d])
        .add_fan_in_edges([executor_c, executor_d], executor_e)
        .add_chain([executor_e, executor_f])
        .set_max_iterations(5)
        .build()
    )

    assert len(workflow.edge_groups) == 4 + 6  # 4 defined edges + 6 internal edges for request-response handling
    assert workflow.start_executor_id == executor_a.id
    assert len(workflow.executors) == 6


def test_add_agent_with_custom_parameters():
    """Test adding an agent with custom parameters."""
    agent = DummyAgent(id="agent_custom", name="custom_agent")
    builder = WorkflowBuilder()

    # Add agent with custom parameters
    result = builder.add_agent(agent, output_response=True, id="my_custom_id")

    # Verify that add_agent returns the builder for chaining
    assert result is builder

    # Build workflow and verify executor is present
    workflow = builder.set_start_executor(agent).build()
    assert "my_custom_id" in workflow.executors

    # Verify the executor was created with correct parameters
    executor = workflow.executors["my_custom_id"]
    assert isinstance(executor, AgentExecutor)
    assert executor.id == "my_custom_id"
    assert getattr(executor, "_output_response", False) is True


def test_add_agent_reuses_same_wrapper():
    """Test that using the same agent instance multiple times reuses the same wrapper."""
    agent = DummyAgent(id="agent_reuse", name="reuse_agent")
    builder = WorkflowBuilder()

    # Add agent with specific parameters
    builder.add_agent(agent, output_response=True, id="agent_exec")

    # Use the same agent instance in add_edge - should reuse the same wrapper
    builder.set_start_executor(agent)

    workflow = builder.build()

    # Verify only one executor exists for this agent
    assert workflow.start_executor_id == "agent_exec"
    assert "agent_exec" in workflow.executors
    assert len([e for e in workflow.executors.values() if isinstance(e, AgentExecutor)]) == 1

    # Verify the executor has the parameters from add_agent
    start_executor = workflow.get_start_executor()
    assert isinstance(start_executor, AgentExecutor)
    assert getattr(start_executor, "_output_response", False) is True


def test_add_agent_then_use_in_edges():
    """Test that an agent added via add_agent can be used in edge definitions."""
    agent1 = DummyAgent(id="agent1", name="first")
    agent2 = DummyAgent(id="agent2", name="second")
    builder = WorkflowBuilder()

    # Add agents with specific settings
    builder.add_agent(agent1, output_response=False, id="exec1")
    builder.add_agent(agent2, output_response=True, id="exec2")

    # Use the same agent instances to create edges
    workflow = builder.set_start_executor(agent1).add_edge(agent1, agent2).build()

    # Verify the executors maintain their settings
    assert workflow.start_executor_id == "exec1"
    assert "exec1" in workflow.executors
    assert "exec2" in workflow.executors

    e1 = workflow.executors["exec1"]
    e2 = workflow.executors["exec2"]

    assert isinstance(e1, AgentExecutor)
    assert isinstance(e2, AgentExecutor)
    assert getattr(e1, "_output_response", True) is False
    assert getattr(e2, "_output_response", False) is True


def test_add_agent_without_explicit_id_uses_agent_name():
    """Test that add_agent uses agent name as id when no explicit id is provided."""
    agent = DummyAgent(id="agent_x", name="named_agent")
    builder = WorkflowBuilder()

    result = builder.add_agent(agent)

    # Verify that add_agent returns the builder for chaining
    assert result is builder

    workflow = builder.set_start_executor(agent).build()
    assert "named_agent" in workflow.executors

    # Verify the executor id matches the agent name
    executor = workflow.executors["named_agent"]
    assert executor.id == "named_agent"


def test_add_agent_duplicate_id_raises_error():
    """Test that adding agents with duplicate IDs raises an error."""
    agent1 = DummyAgent(id="agent1", name="first")
    agent2 = DummyAgent(id="agent2", name="first")  # Same name as agent1
    builder = WorkflowBuilder()

    # Add first agent
    builder.add_agent(agent1)

    # Adding second agent with same name should raise ValueError
    with pytest.raises(ValueError, match="Duplicate executor ID"):
        builder.add_agent(agent2)


# Tests for new executor registration patterns


def test_register_executor_basic():
    """Test basic executor registration with lazy initialization."""
    builder = WorkflowBuilder()

    # Register an executor factory - ID must match the registered name
    result = builder.register_executor(lambda: MockExecutor(id="TestExecutor"), name="TestExecutor")

    # Verify that register returns the builder for chaining
    assert result is builder

    # Build workflow and verify executor is instantiated
    workflow = builder.set_start_executor("TestExecutor").build()
    assert "TestExecutor" in workflow.executors
    assert isinstance(workflow.executors["TestExecutor"], MockExecutor)


def test_register_multiple_executors():
    """Test registering multiple executors and connecting them with edges."""
    builder = WorkflowBuilder()

    # Register multiple executors - IDs must match registered names
    builder.register_executor(lambda: MockExecutor(id="ExecutorA"), name="ExecutorA")
    builder.register_executor(lambda: MockExecutor(id="ExecutorB"), name="ExecutorB")
    builder.register_executor(lambda: MockExecutor(id="ExecutorC"), name="ExecutorC")

    # Build workflow with edges using registered names
    workflow = (
        builder.set_start_executor("ExecutorA")
        .add_edge("ExecutorA", "ExecutorB")
        .add_edge("ExecutorB", "ExecutorC")
        .build()
    )

    # Verify all executors are present
    assert "ExecutorA" in workflow.executors
    assert "ExecutorB" in workflow.executors
    assert "ExecutorC" in workflow.executors
    assert workflow.start_executor_id == "ExecutorA"


def test_register_with_multiple_names():
    """Test registering the same factory function under multiple names."""
    builder = WorkflowBuilder()

    # Register same executor factory under multiple names
    # Note: Each call creates a new instance, so IDs won't conflict
    counter = {"val": 0}

    def make_executor():
        counter["val"] += 1
        return MockExecutor(id="ExecutorA" if counter["val"] == 1 else "ExecutorB")

    builder.register_executor(make_executor, name=["ExecutorA", "ExecutorB"])

    # Set up workflow
    workflow = builder.set_start_executor("ExecutorA").add_edge("ExecutorA", "ExecutorB").build()

    # Verify both executors are present
    assert "ExecutorA" in workflow.executors
    assert "ExecutorB" in workflow.executors
    assert workflow.start_executor_id == "ExecutorA"


def test_register_duplicate_name_raises_error():
    """Test that registering duplicate names raises an error."""
    builder = WorkflowBuilder()

    # Register first executor
    builder.register_executor(lambda: MockExecutor(id="executor_1"), name="MyExecutor")

    # Registering second executor with same name should raise ValueError
    with pytest.raises(ValueError, match="already registered"):
        builder.register_executor(lambda: MockExecutor(id="executor_2"), name="MyExecutor")


def test_register_agent_basic():
    """Test basic agent registration with lazy initialization."""
    builder = WorkflowBuilder()

    # Register an agent factory
    result = builder.register_agent(
        lambda: DummyAgent(id="agent_test", name="test_agent"), name="TestAgent", output_response=True
    )

    # Verify that register_agent returns the builder for chaining
    assert result is builder

    # Build workflow and verify agent is wrapped in AgentExecutor
    workflow = builder.set_start_executor("TestAgent").build()
    assert "test_agent" in workflow.executors
    assert isinstance(workflow.executors["test_agent"], AgentExecutor)
    assert workflow.executors["test_agent"]._output_response is True  # type: ignore


def test_register_agent_with_thread():
    """Test registering an agent with a custom thread."""
    builder = WorkflowBuilder()
    custom_thread = AgentThread()

    # Register agent with custom thread
    builder.register_agent(
        lambda: DummyAgent(id="agent_with_thread", name="threaded_agent"),
        name="ThreadedAgent",
        agent_thread=custom_thread,
        output_response=False,
    )

    # Build workflow and verify agent executor configuration
    workflow = builder.set_start_executor("ThreadedAgent").build()
    executor = workflow.executors["threaded_agent"]

    assert isinstance(executor, AgentExecutor)
    assert executor.id == "threaded_agent"
    assert executor._output_response is False  # type: ignore
    assert executor._agent_thread is custom_thread  # type: ignore


def test_register_agent_duplicate_name_raises_error():
    """Test that registering agents with duplicate names raises an error."""
    builder = WorkflowBuilder()

    # Register first agent
    builder.register_agent(lambda: DummyAgent(id="agent1", name="first"), name="MyAgent")

    # Registering second agent with same name should raise ValueError
    with pytest.raises(ValueError, match="already registered"):
        builder.register_agent(lambda: DummyAgent(id="agent2", name="second"), name="MyAgent")


def test_register_and_add_edge_with_strings():
    """Test that registered executors can be connected using string names."""
    builder = WorkflowBuilder()

    # Register executors
    builder.register_executor(lambda: MockExecutor(id="source"), name="Source")
    builder.register_executor(lambda: MockExecutor(id="target"), name="Target")

    # Add edge using string names
    workflow = builder.set_start_executor("Source").add_edge("Source", "Target").build()

    # Verify edge is created correctly
    assert workflow.start_executor_id == "source"
    assert "source" in workflow.executors
    assert "target" in workflow.executors


def test_register_agent_and_add_edge_with_strings():
    """Test that registered agents can be connected using string names."""
    builder = WorkflowBuilder()

    # Register agents
    builder.register_agent(lambda: DummyAgent(id="writer_id", name="writer"), name="Writer")
    builder.register_agent(lambda: DummyAgent(id="reviewer_id", name="reviewer"), name="Reviewer")

    # Add edge using string names
    workflow = builder.set_start_executor("Writer").add_edge("Writer", "Reviewer").build()

    # Verify edge is created correctly
    assert workflow.start_executor_id == "writer"
    assert "writer" in workflow.executors
    assert "reviewer" in workflow.executors
    assert all(isinstance(e, AgentExecutor) for e in workflow.executors.values())


def test_register_with_fan_out_edges():
    """Test using registered names with fan-out edge groups."""
    builder = WorkflowBuilder()

    # Register executors - IDs must match registered names
    builder.register_executor(lambda: MockExecutor(id="Source"), name="Source")
    builder.register_executor(lambda: MockExecutor(id="Target1"), name="Target1")
    builder.register_executor(lambda: MockExecutor(id="Target2"), name="Target2")

    # Add fan-out edges using registered names
    workflow = builder.set_start_executor("Source").add_fan_out_edges("Source", ["Target1", "Target2"]).build()

    # Verify all executors are present
    assert "Source" in workflow.executors
    assert "Target1" in workflow.executors
    assert "Target2" in workflow.executors


def test_register_with_fan_in_edges():
    """Test using registered names with fan-in edge groups."""
    builder = WorkflowBuilder()

    # Register executors - IDs must match registered names
    builder.register_executor(lambda: MockExecutor(id="Source1"), name="Source1")
    builder.register_executor(lambda: MockExecutor(id="Source2"), name="Source2")
    builder.register_executor(lambda: MockAggregator(id="Aggregator"), name="Aggregator")

    # Add fan-in edges using registered names
    # Both Source1 and Source2 need to be reachable, so connect Source1 to Source2
    workflow = (
        builder.set_start_executor("Source1")
        .add_edge("Source1", "Source2")
        .add_fan_in_edges(["Source1", "Source2"], "Aggregator")
        .build()
    )

    # Verify all executors are present
    assert "Source1" in workflow.executors
    assert "Source2" in workflow.executors
    assert "Aggregator" in workflow.executors


def test_register_with_chain():
    """Test using registered names with add_chain."""
    builder = WorkflowBuilder()

    # Register executors - IDs must match registered names
    builder.register_executor(lambda: MockExecutor(id="Step1"), name="Step1")
    builder.register_executor(lambda: MockExecutor(id="Step2"), name="Step2")
    builder.register_executor(lambda: MockExecutor(id="Step3"), name="Step3")

    # Add chain using registered names
    workflow = builder.add_chain(["Step1", "Step2", "Step3"]).set_start_executor("Step1").build()

    # Verify all executors are present
    assert "Step1" in workflow.executors
    assert "Step2" in workflow.executors
    assert "Step3" in workflow.executors
    assert workflow.start_executor_id == "Step1"


def test_register_factory_called_only_once():
    """Test that registered factory functions are called only during build."""
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return MockExecutor(id="Test")

    builder = WorkflowBuilder()
    builder.register_executor(factory, name="Test")

    # Factory should not be called yet
    assert call_count == 0

    # Add edge without building
    builder.set_start_executor("Test")

    # Factory should still not be called
    assert call_count == 0

    # Build workflow
    workflow = builder.build()

    # Factory should now be called exactly once
    assert call_count == 1
    assert "Test" in workflow.executors


def test_mixing_eager_and_lazy_initialization_error():
    """Test that mixing eager executor instances with lazy string names raises appropriate error."""
    builder = WorkflowBuilder()

    # Create an eager executor instance
    eager_executor = MockExecutor(id="eager")

    # Register a lazy executor
    builder.register_executor(lambda: MockExecutor(id="Lazy"), name="Lazy")

    # Mixing eager and lazy should raise an error during add_edge
    with pytest.raises(ValueError, match="Both source and target must be either names"):
        builder.add_edge(eager_executor, "Lazy")


def test_register_with_condition():
    """Test adding edges with conditions using registered names."""
    builder = WorkflowBuilder()

    def condition_func(msg: MockMessage) -> bool:
        return msg.data > 0

    # Register executors - IDs must match registered names
    builder.register_executor(lambda: MockExecutor(id="Source"), name="Source")
    builder.register_executor(lambda: MockExecutor(id="Target"), name="Target")

    # Add edge with condition
    workflow = builder.set_start_executor("Source").add_edge("Source", "Target", condition=condition_func).build()

    # Verify workflow is built correctly
    assert "Source" in workflow.executors
    assert "Target" in workflow.executors


def test_register_agent_creates_unique_instances():
    """Test that registered agent factories create new instances on each build."""
    instance_ids: list[int] = []

    def agent_factory() -> DummyAgent:
        agent = DummyAgent(id=f"agent_{len(instance_ids)}", name="test")
        instance_ids.append(id(agent))
        return agent

    # Build first workflow
    builder1 = WorkflowBuilder()
    builder1.register_agent(agent_factory, name="Agent")
    _ = builder1.set_start_executor("Agent").build()

    # Build second workflow
    builder2 = WorkflowBuilder()
    builder2.register_agent(agent_factory, name="Agent")
    _ = builder2.set_start_executor("Agent").build()

    # Verify that two different agent instances were created
    assert len(instance_ids) == 2
    assert instance_ids[0] != instance_ids[1]
