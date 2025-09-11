# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

import pytest
from agent_framework import AgentRunResponse, AgentRunResponseUpdate, AgentThread, BaseAgent, ChatMessage, Role
from agent_framework.workflow import AgentExecutor, Executor, WorkflowBuilder, WorkflowContext, handler


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


def test_builder_agents_always_stream():
    agent = DummyAgent(id="agentX", name="streamer")
    wf = WorkflowBuilder().set_start_executor(agent).build()
    exec_obj = wf.get_start_executor()
    assert isinstance(exec_obj, AgentExecutor)
    assert getattr(exec_obj, "_streaming", False) is True


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

    assert len(workflow.edge_groups) == 4
    assert workflow.start_executor_id == executor_a.id
    assert len(workflow.executors) == 6
