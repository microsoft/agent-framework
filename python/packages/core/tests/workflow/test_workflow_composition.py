# Copyright (c) Microsoft. All rights reserved.

"""Tests for workflow composition via add_workflow()."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework import (
    ChatAgent,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    SequentialBuilder,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework._workflows._edge import Case, Default


def create_mock_agent(name: str) -> ChatAgent:
    """Create a mock agent for testing."""
    mock_client = MagicMock()
    mock_client.create_response = AsyncMock(
        return_value=MagicMock(
            content="test response",
            messages=[MagicMock(role="assistant", content="test response")],
        )
    )
    return ChatAgent(name=name, chat_client=mock_client)


# Test executors
class EchoExecutor(Executor):
    """Simple executor that echoes the input."""

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"echo: {message}")


class UpperExecutor(Executor):
    """Executor that converts input to uppercase."""

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(message.upper())


class OutputExecutor(Executor):
    """Terminal executor that yields output."""

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[None, str]) -> None:
        await ctx.yield_output(message)


class ListOutputExecutor(Executor):
    """Terminal executor that yields list output."""

    @handler
    async def handle(self, messages: list, ctx: WorkflowContext[None, list]) -> None:
        await ctx.yield_output(messages)


class StringPassthroughExecutor(Executor):
    """Executor that passes through string messages."""

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(message)


class ChatMessageListPassthroughExecutor(Executor):
    """Executor that passes through list[ChatMessage] messages."""

    @handler
    async def handle(self, messages: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        await ctx.send_message(messages)


# Basic add_workflow tests


def test_add_workflow_with_concurrent_builder():
    """Test adding a ConcurrentBuilder workflow."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    result = builder.add_workflow(concurrent, id="analysis")

    # Should return self for chaining
    assert result is builder

    # Should track the workflow mapping
    assert "analysis" in builder._workflow_mappings
    mapping = builder._workflow_mappings["analysis"]
    assert mapping.entry == "analysis/dispatcher"
    assert mapping.exits == ["analysis/aggregator"]


def test_add_workflow_with_sequential_builder():
    """Test adding a SequentialBuilder workflow."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    sequential = SequentialBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    result = builder.add_workflow(sequential, id="pipeline")

    # Should return self for chaining
    assert result is builder

    # Should track the workflow mapping
    assert "pipeline" in builder._workflow_mappings
    mapping = builder._workflow_mappings["pipeline"]
    assert mapping.entry == "pipeline/input-conversation"
    assert mapping.exits == ["pipeline/end"]


def test_add_workflow_id_conflicts():
    """Test that duplicate workflow IDs raise errors."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    builder.add_workflow(concurrent, id="analysis")

    # Adding with same ID should fail
    with pytest.raises(ValueError, match="already been used"):
        builder.add_workflow(concurrent, id="analysis")


def test_add_workflow_executor_registry_conflict():
    """Test that workflow ID conflicts with executor registry raise errors."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    builder.register_executor(lambda: EchoExecutor(id="analysis"), name="analysis")

    # Adding workflow with same ID should fail
    with pytest.raises(ValueError, match="conflicts with an existing registered executor name"):
        builder.add_workflow(concurrent, id="analysis")


# Logical ID resolution tests


def test_set_start_executor_with_workflow_logical_id():
    """Test that set_start_executor resolves workflow logical IDs."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    builder.add_workflow(concurrent, id="analysis")
    builder.set_start_executor("analysis")

    # Should resolve to the entry point
    assert builder._start_executor == "analysis/dispatcher"


def test_add_edge_with_workflow_logical_ids():
    """Test that add_edge resolves workflow logical IDs."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")
    agent3 = create_mock_agent("agent3")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])
    sequential = SequentialBuilder().participants([agent3])

    builder = WorkflowBuilder()
    builder.add_workflow(concurrent, id="analysis")
    builder.add_workflow(sequential, id="summary")
    builder.add_edge("analysis", "summary")

    # Check that the edge was registered with resolved IDs
    assert len(builder._edge_registry) == 1
    edge_reg = builder._edge_registry[0]
    assert edge_reg.source == "analysis/aggregator"  # exit point
    assert edge_reg.target == "summary/input-conversation"  # entry point


def test_add_edge_mixed_workflow_and_executor_ids():
    """Test mixing workflow logical IDs with regular executor IDs."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    builder.register_executor(lambda: EchoExecutor(id="prep"), name="prep")
    builder.add_workflow(concurrent, id="analysis")
    builder.register_executor(lambda: OutputExecutor(id="out"), name="output")

    # Connect prep -> analysis
    builder.add_edge("prep", "analysis")
    # Connect analysis -> output
    builder.add_edge("analysis", "output")

    # Check that edges were resolved correctly
    assert len(builder._edge_registry) == 2
    # First edge: prep -> analysis entry
    assert builder._edge_registry[0].source == "prep"
    assert builder._edge_registry[0].target == "analysis/dispatcher"
    # Second edge: analysis exit -> output
    assert builder._edge_registry[1].source == "analysis/aggregator"
    assert builder._edge_registry[1].target == "output"


# Integration tests - full workflow builds


@pytest.mark.asyncio
async def test_compose_two_concurrent_workflows():
    """Test composing two concurrent workflows together."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")
    agent3 = create_mock_agent("agent3")

    analysis = ConcurrentBuilder().participants([agent1, agent2])
    summary = SequentialBuilder().participants([agent3])

    workflow = (
        WorkflowBuilder()
        .add_workflow(analysis, id="analysis")
        .add_workflow(summary, id="summary")
        .add_edge("analysis", "summary")
        .set_start_executor("analysis")
        .build()
    )

    # Verify the workflow structure
    assert workflow.start_executor_id == "analysis/dispatcher"
    assert "analysis/dispatcher" in workflow.executors
    assert "analysis/aggregator" in workflow.executors
    assert "summary/input-conversation" in workflow.executors
    assert "summary/end" in workflow.executors


@pytest.mark.asyncio
async def test_compose_with_pre_and_post_processing():
    """Test adding pre/post-processing executors around a workflow."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    # Pre-processor accepts str (like the dispatcher), post-processor accepts list[ChatMessage]
    # (like aggregator outputs)
    workflow = (
        WorkflowBuilder()
        .register_executor(lambda: StringPassthroughExecutor(id="pre"), name="pre")
        .add_workflow(concurrent, id="analysis")
        .register_executor(lambda: ChatMessageListPassthroughExecutor(id="post"), name="post")
        .add_edge("pre", "analysis")
        .add_edge("analysis", "post")
        .set_start_executor("pre")
        .build()
    )

    # Verify the workflow structure
    assert workflow.start_executor_id == "pre"
    assert "pre" in workflow.executors
    assert "analysis/dispatcher" in workflow.executors
    assert "analysis/aggregator" in workflow.executors
    assert "post" in workflow.executors


def test_add_fan_out_with_workflow_ids():
    """Test fan-out edges with workflow logical IDs."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")
    agent3 = create_mock_agent("agent3")
    agent4 = create_mock_agent("agent4")

    concurrent1 = ConcurrentBuilder().participants([agent1, agent2])
    concurrent2 = ConcurrentBuilder().participants([agent3, agent4])

    builder = WorkflowBuilder()
    builder.register_executor(lambda: EchoExecutor(id="source"), name="source")
    builder.add_workflow(concurrent1, id="path1")
    builder.add_workflow(concurrent2, id="path2")
    builder.add_fan_out_edges("source", ["path1", "path2"])

    # Check that the edge was registered with resolved IDs
    fan_out_reg = builder._edge_registry[0]
    assert fan_out_reg.source == "source"
    assert fan_out_reg.targets == ["path1/dispatcher", "path2/dispatcher"]


def test_add_fan_in_with_workflow_ids():
    """Test fan-in edges with workflow logical IDs."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")
    agent3 = create_mock_agent("agent3")
    agent4 = create_mock_agent("agent4")

    concurrent1 = ConcurrentBuilder().participants([agent1, agent2])
    concurrent2 = ConcurrentBuilder().participants([agent3, agent4])

    builder = WorkflowBuilder()
    builder.add_workflow(concurrent1, id="source1")
    builder.add_workflow(concurrent2, id="source2")
    builder.register_executor(lambda: ListOutputExecutor(id="agg"), name="aggregator")
    builder.add_fan_in_edges(["source1", "source2"], "aggregator")

    # Check that the edge was registered with resolved IDs
    fan_in_reg = builder._edge_registry[0]
    assert fan_in_reg.sources == ["source1/aggregator", "source2/aggregator"]
    assert fan_in_reg.target == "aggregator"


def test_add_switch_case_with_workflow_ids():
    """Test switch-case edges with workflow logical IDs."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")
    agent3 = create_mock_agent("agent3")
    agent4 = create_mock_agent("agent4")

    concurrent1 = ConcurrentBuilder().participants([agent1, agent2])
    concurrent2 = ConcurrentBuilder().participants([agent3, agent4])

    builder = WorkflowBuilder()
    builder.register_executor(lambda: EchoExecutor(id="classifier"), name="classifier")
    builder.add_workflow(concurrent1, id="fast")
    builder.add_workflow(concurrent2, id="slow")
    builder.add_switch_case_edge_group(
        "classifier",
        [
            Case(condition=lambda x: len(x) > 10, target="fast"),
            Default(target="slow"),
        ],
    )

    # Check that the edge was registered with resolved IDs
    switch_reg = builder._edge_registry[0]
    assert switch_reg.source == "classifier"
    assert switch_reg.cases[0].target == "fast/dispatcher"
    assert switch_reg.cases[1].target == "slow/dispatcher"


def test_invalid_source_type():
    """Test that invalid source types raise errors."""
    builder = WorkflowBuilder()

    with pytest.raises(ValueError, match="must be an orchestration builder"):
        builder.add_workflow("not a builder", id="test")


def test_workflow_executor_prefix():
    """Test that executor IDs are properly prefixed."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])

    builder = WorkflowBuilder()
    builder.add_workflow(concurrent, id="myworkflow")

    # Executors should be prefixed
    assert "myworkflow/dispatcher" in builder._executors
    # The agents get wrapped in AgentExecutors with the agent's name as ID
    assert "myworkflow/agent1" in builder._executors
    assert "myworkflow/agent2" in builder._executors
    assert "myworkflow/aggregator" in builder._executors


def test_chained_add_workflow_calls():
    """Test that add_workflow returns self for chaining."""
    agent1 = create_mock_agent("agent1")
    agent2 = create_mock_agent("agent2")
    agent3 = create_mock_agent("agent3")

    concurrent = ConcurrentBuilder().participants([agent1, agent2])
    sequential = SequentialBuilder().participants([agent3])

    # Should be able to chain all calls
    builder = (
        WorkflowBuilder()
        .add_workflow(concurrent, id="analysis")
        .add_workflow(sequential, id="summary")
        .add_edge("analysis", "summary")
        .set_start_executor("analysis")
    )

    assert "analysis" in builder._workflow_mappings
    assert "summary" in builder._workflow_mappings
