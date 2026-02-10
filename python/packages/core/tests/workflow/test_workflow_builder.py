# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework import (
    AgentExecutor,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowValidationError,
    handler,
)


class DummyAgent(BaseAgent):
    def run(self, messages=None, *, stream: bool = False, thread: AgentThread | None = None, **kwargs):  # type: ignore[override]
        if stream:
            return self._run_stream_impl()
        return self._run_impl(messages)

    async def _run_impl(self, messages=None) -> AgentResponse:
        norm: list[ChatMessage] = []
        if messages:
            for m in messages:  # type: ignore[iteration-over-optional]
                if isinstance(m, ChatMessage):
                    norm.append(m)
                elif isinstance(m, str):
                    norm.append(ChatMessage(role="user", text=m))
        return AgentResponse(messages=norm)

    async def _run_stream_impl(self):  # type: ignore[override]
        # Minimal async generator
        yield AgentResponseUpdate()


def test_builder_accepts_agents_directly():
    agent1 = DummyAgent(id="agent1", name="writer")
    agent2 = DummyAgent(id="agent2", name="reviewer")

    wf = WorkflowBuilder(start_executor=agent1).add_edge(agent1, agent2).build()

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
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext[MockMessage, MockMessage]) -> None:
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
    with pytest.raises(TypeError):
        WorkflowBuilder()  # type: ignore[call-arg]


def test_workflow_builder_fluent_api():
    """Test the fluent API of the workflow builder."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")
    executor_c = MockExecutor(id="executor_c")
    executor_d = MockExecutor(id="executor_d")
    executor_e = MockAggregator(id="executor_e")
    executor_f = MockExecutor(id="executor_f")

    workflow = (
        WorkflowBuilder(max_iterations=5, start_executor=executor_a)
        .add_edge(executor_a, executor_b)
        .add_fan_out_edges(executor_b, [executor_c, executor_d])
        .add_fan_in_edges([executor_c, executor_d], executor_e)
        .add_chain([executor_e, executor_f])
        .build()
    )

    assert len(workflow.edge_groups) == 4 + 6  # 4 defined edges + 6 internal edges for request-response handling
    assert workflow.start_executor_id == executor_a.id
    assert len(workflow.executors) == 6


def test_add_agent_reuses_same_wrapper():
    """Test that using the same agent instance multiple times reuses the same wrapper."""
    reuse_agent = DummyAgent(id="agent_reuse", name="reuse_agent")
    agent_a = DummyAgent(id="agent_a", name="agent_a")

    builder = WorkflowBuilder(start_executor=reuse_agent)
    # Use the same agent instance in add_edge - should reuse the same wrapper
    builder.add_edge(reuse_agent, agent_a)
    builder.add_edge(agent_a, reuse_agent)

    workflow = builder.build()

    # Verify only one executor exists for this agent
    assert workflow.start_executor_id == "reuse_agent"
    assert "reuse_agent" in workflow.executors
    assert len([e for e in workflow.executors.values() if isinstance(e, AgentExecutor)]) == 2


def test_add_agent_duplicate_id_raises_error():
    """Test that adding agents with duplicate IDs raises an error."""
    agent1 = DummyAgent(id="agent1", name="first")
    agent2 = DummyAgent(id="agent2", name="first")  # Same name as agent1
    builder = WorkflowBuilder(start_executor=agent1)

    with pytest.raises(ValueError, match="Duplicate executor ID"):
        builder.add_edge(agent1, agent2).build()


def test_fan_out_edges_with_direct_instances():
    """Test fan-out edges with direct executor instances."""
    source = MockExecutor(id="Source")
    target1 = MockExecutor(id="Target1")
    target2 = MockExecutor(id="Target2")

    workflow = WorkflowBuilder(start_executor=source).add_fan_out_edges(source, [target1, target2]).build()

    assert "Source" in workflow.executors
    assert "Target1" in workflow.executors
    assert "Target2" in workflow.executors


def test_fan_in_edges_with_direct_instances():
    """Test fan-in edges with direct executor instances."""
    source1 = MockExecutor(id="Source1")
    source2 = MockExecutor(id="Source2")
    aggregator = MockAggregator(id="Aggregator")

    workflow = (
        WorkflowBuilder(start_executor=source1)
        .add_edge(source1, source2)
        .add_fan_in_edges([source1, source2], aggregator)
        .build()
    )

    assert "Source1" in workflow.executors
    assert "Source2" in workflow.executors
    assert "Aggregator" in workflow.executors


def test_chain_with_direct_instances():
    """Test add_chain with direct executor instances."""
    step1 = MockExecutor(id="Step1")
    step2 = MockExecutor(id="Step2")
    step3 = MockExecutor(id="Step3")

    workflow = WorkflowBuilder(start_executor=step1).add_chain([step1, step2, step3]).build()

    assert "Step1" in workflow.executors
    assert "Step2" in workflow.executors
    assert "Step3" in workflow.executors
    assert workflow.start_executor_id == "Step1"


def test_add_edge_with_condition():
    """Test adding edges with conditions using direct executor instances."""
    source = MockExecutor(id="Source")
    target = MockExecutor(id="Target")

    def condition_func(msg: MockMessage) -> bool:
        return msg.data > 0

    workflow = WorkflowBuilder(start_executor=source).add_edge(source, target, condition=condition_func).build()

    assert "Source" in workflow.executors
    assert "Target" in workflow.executors


# region with_output_from tests


def test_with_output_from_returns_builder():
    """Test that with_output_from returns the builder for method chaining."""
    executor_a = MockExecutor(id="executor_a")
    builder = WorkflowBuilder(output_executors=[executor_a], start_executor=executor_a)

    # Verify builder was created with output_executors
    assert builder._output_executors == [executor_a]


def test_with_output_from_with_executor_instances():
    """Test with_output_from with direct executor instances."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_b])
        .add_edge(executor_a, executor_b)
        .build()
    )

    # Verify that the workflow was built with the correct output executors
    assert workflow._output_executors == ["executor_b"]  # type: ignore


def test_with_output_from_with_agent_instances():
    """Test with_output_from with agent instances."""
    agent_a = DummyAgent(id="agent_a", name="writer")
    agent_b = DummyAgent(id="agent_b", name="reviewer")

    workflow = WorkflowBuilder(start_executor=agent_a, output_executors=[agent_b]).add_edge(agent_a, agent_b).build()

    # Verify that the workflow was built with the agent's name as output executor
    assert workflow._output_executors == ["reviewer"]  # type: ignore


def test_with_output_from_with_executor_instances_by_id():
    """Test with_output_from with direct executor instances resolves to executor IDs."""
    executor_a = MockExecutor(id="ExecutorA")
    executor_b = MockExecutor(id="ExecutorB")

    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_b])
        .add_edge(executor_a, executor_b)
        .build()
    )

    assert workflow._output_executors == ["ExecutorB"]  # type: ignore


def test_with_output_from_with_multiple_executors():
    """Test with_output_from with multiple executors."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")
    executor_c = MockExecutor(id="executor_c")

    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_a, executor_c])
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_c)
        .build()
    )

    # Verify that the workflow was built with both output executors
    assert set(workflow._output_executors) == {"executor_a", "executor_c"}  # type: ignore


def test_with_output_from_can_be_set_to_different_value():
    """Test that output_executors can be set at construction time."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")

    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_b])
        .add_edge(executor_a, executor_b)
        .build()
    )

    # Verify that the setting is applied
    assert workflow._output_executors == ["executor_b"]  # type: ignore


def test_with_output_from_with_agent_instances_resolves_name():
    """Test with_output_from with agent instances resolves to agent names."""
    agent_writer = DummyAgent(id="agent1", name="writer")
    agent_reviewer = DummyAgent(id="agent2", name="reviewer")

    workflow = (
        WorkflowBuilder(start_executor=agent_writer, output_executors=[agent_reviewer])
        .add_edge(agent_writer, agent_reviewer)
        .build()
    )

    assert workflow._output_executors == ["reviewer"]  # type: ignore


def test_with_output_from_in_constructor():
    """Test that output_executors works correctly when set in the constructor."""
    executor_a = MockExecutor(id="executor_a")
    executor_b = MockExecutor(id="executor_b")
    executor_c = MockExecutor(id="executor_c")

    # Build workflow with output_executors in the constructor
    workflow = (
        WorkflowBuilder(start_executor=executor_a, output_executors=[executor_c])
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_c)
        .build()
    )

    # Verify that the setting persists through the chain
    assert workflow._output_executors == ["executor_c"]  # type: ignore


def test_with_output_from_with_invalid_executor_raises_validation_error():
    """Test that with_output_from with an invalid executor raises an error."""
    executor_a = MockExecutor(id="executor_a")

    builder = WorkflowBuilder(start_executor=executor_a, output_executors=[MockExecutor(id="executor_b")])

    # Attempting to set output from an executor not in the workflow should raise an error
    with pytest.raises(
        WorkflowValidationError, match="Output executor 'executor_b' is not present in the workflow graph"
    ):
        builder.build()


# endregion
