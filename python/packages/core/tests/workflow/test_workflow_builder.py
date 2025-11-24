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
