# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

import pytest
from agent_framework.workflow import Executor, WorkflowBuilder, WorkflowContext, handler


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: Any


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler(output_types=[MockMessage])
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        pass


class MockAggregator(Executor):
    """A mock executor that aggregates results from multiple executors."""

    @handler(output_types=[MockMessage])
    async def mock_handler(self, messages: list[MockMessage], ctx: WorkflowContext) -> None:
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

    assert len(workflow.edges) == 6
    assert workflow.start_executor.id == executor_a.id
    assert len(workflow.executors) == 6
