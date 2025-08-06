# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

from agent_framework.workflow import Executor, WorkflowContext, handler

from agent_framework_workflow._edge import Edge


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: Any


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        pass


def test_create_edge():
    """Test creating an edge with a source and target executor."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge = Edge(source=source, target=target)

    assert edge.source_id == "source_executor"
    assert edge.target_id == "target_executor"
    assert edge.id == f"{edge.source_id}{Edge.ID_SEPARATOR}{edge.target_id}"
    assert (edge.source_id, edge.target_id) == Edge.source_and_target_from_id(edge.id)


def test_edge_can_handle():
    """Test creating an edge with a source and target executor."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge = Edge(source=source, target=target)

    assert edge.can_handle(MockMessage(data="test"))
