# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from agent_framework.workflow import Executor, WorkflowContext, handler

from agent_framework_workflow._edge import (
    ConditionalEdgeGroup,
    Edge,
    PartitioningEdgeGroup,
    SingleEdgeGroup,
    SourceEdgeGroup,
    TargetEdgeGroup,
)


@dataclass
class MockMessage:
    """A mock message for testing purposes."""

    data: Any


@dataclass
class MockMessageSecondary:
    """A secondary mock message for testing purposes."""

    data: Any


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        pass


class MockExecutorSecondary(Executor):
    """A secondary mock executor for testing purposes."""

    @handler
    async def mock_handler_secondary(self, message: MockMessageSecondary, ctx: WorkflowContext) -> None:
        """A secondary mock handler that does nothing."""
        pass


class MockAggregator(Executor):
    """A mock aggregator for testing purposes."""

    @handler
    async def mock_aggregator_handler(self, message: list[MockMessage], ctx: WorkflowContext) -> None:
        """A mock aggregator handler that does nothing."""
        pass


# region Edge


def test_create_edge():
    """Test creating an edge with a source and target executor."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge = Edge(source=source, target=target)

    assert edge.source_id == "source_executor"
    assert edge.target_id == "target_executor"
    assert edge.id == f"{edge.source_id}{Edge.ID_SEPARATOR}{edge.target_id}"


def test_edge_can_handle():
    """Test creating an edge with a source and target executor."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge = Edge(source=source, target=target)

    assert edge.can_handle(MockMessage(data="test"))


# endregion Edge

# region SingleEdgeGroup


def test_single_edge_group():
    """Test creating a single edge group."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source=source, target=target)

    assert edge_group.source_executors == [source]
    assert edge_group.target_executors == [target]
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor"


def test_single_edge_group_with_condition():
    """Test creating a single edge group with a condition."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source=source, target=target, condition=lambda x: x.data == "test")

    assert edge_group.source_executors == [source]
    assert edge_group.target_executors == [target]
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor"
    assert edge_group.edges[0]._condition is not None  # type: ignore


async def test_single_edge_group_send_message():
    """Test sending a message through a single edge group."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source=source, target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is True


async def test_single_edge_group_send_message_with_target():
    """Test sending a message through a single edge group."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source=source, target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is True


async def test_single_edge_group_send_message_with_invalid_target():
    """Test sending a message through a single edge group."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source=source, target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id="invalid_target")

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_single_edge_group_send_message_with_invalid_data():
    """Test sending a message through a single edge group."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source=source, target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


# endregion SingleEdgeGroup


# region SourceEdgeGroup


def test_source_edge_group():
    """Test creating a source edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SourceEdgeGroup(source=source, targets=[target1, target2])

    assert edge_group.source_executors == [source]
    assert edge_group.target_executors == [target1, target2]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor_1"
    assert edge_group.edges[1].source_id == "source_executor"
    assert edge_group.edges[1].target_id == "target_executor_2"


def test_source_edge_group_invalid_number_of_targets():
    """Test creating a source edge group with an invalid number of targets."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    with pytest.raises(ValueError, match="SourceEdgeGroup must contain at least two targets"):
        SourceEdgeGroup(source=source, targets=[target])


async def test_source_edge_group_send_message():
    """Test sending a message through a source edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SourceEdgeGroup(source=source, targets=[target1, target2])

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 2


async def test_source_edge_group_send_message_with_target():
    """Test sending a message through a source edge group with a target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SourceEdgeGroup(source=source, targets=[target1, target2])

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0].target_id == target1.id


async def test_source_edge_group_send_message_with_invalid_target():
    """Test sending a message through a source edge group with an invalid target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SourceEdgeGroup(source=source, targets=[target1, target2])

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id="invalid_target")

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_source_edge_group_send_message_with_invalid_data():
    """Test sending a message through a source edge group with invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SourceEdgeGroup(source=source, targets=[target1, target2])

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_source_edge_group_send_message_only_one_successful_send():
    """Test sending a message through a source edge group where only one edge can handle the message."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutorSecondary(id="target_executor_2")

    edge_group = SourceEdgeGroup(source=source, targets=[target1, target2])

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1


# endregion SourceEdgeGroup

# region TargetEdgeGroup


def test_target_edge_group():
    """Test creating a target edge group."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = TargetEdgeGroup(sources=[source1, source2], target=target)

    assert edge_group.source_executors == [source1, source2]
    assert edge_group.target_executors == [target]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor_1"
    assert edge_group.edges[0].target_id == "target_executor"
    assert edge_group.edges[1].source_id == "source_executor_2"
    assert edge_group.edges[1].target_id == "target_executor"


def test_target_edge_group_invalid_number_of_sources():
    """Test creating a target edge group with an invalid number of sources."""
    source = MockExecutor(id="source_executor")
    target = MockAggregator(id="target_executor")

    with pytest.raises(ValueError, match="TargetEdgeGroup must contain at least two sources"):
        TargetEdgeGroup(sources=[source], target=target)


async def test_target_edge_group_send_message_buffer():
    """Test sending a message through a target edge group with buffering."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = TargetEdgeGroup(sources=[source1, source2], target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(
            Message(data=data, source_id=source1.id),
            shared_state,
            ctx,
        )

        assert success is True
        assert mock_send.call_count == 0  # The message should be buffered and wait for the second source
        assert len(edge_group._buffer[source1.id]) == 1  # type: ignore

        success = await edge_group.send_message(
            Message(data=data, source_id=source2.id),
            shared_state,
            ctx,
        )
        assert success is True
        assert mock_send.call_count == 1  # The message should be sent now that both sources have sent their messages

        # Buffer should be cleared after sending
        assert not edge_group._buffer  # type: ignore


async def test_target_edge_group_send_message_with_invalid_target():
    """Test sending a message through a target edge group with an invalid target."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = TargetEdgeGroup(sources=[source1, source2], target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source1.id, target_id="invalid_target")

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_target_edge_group_send_message_with_invalid_data():
    """Test sending a message through a target edge group with invalid data."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = TargetEdgeGroup(sources=[source1, source2], target=target)

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source1.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


# endregion TargetEdgeGroup

# region ConditionalEdgeGroup


def test_conditional_edge_group():
    """Test creating a conditional edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = ConditionalEdgeGroup(
        source=source,
        targets=[target1, target2],
        conditions=[lambda x: x.data < 0],
    )

    assert edge_group.source_executors == [source]
    assert edge_group.target_executors == [target1, target2]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor_1"
    assert edge_group.edges[0]._condition is not None  # type: ignore
    assert edge_group.edges[1].source_id == "source_executor"
    assert edge_group.edges[1].target_id == "target_executor_2"
    assert edge_group.edges[1]._condition is None  # type: ignore


def test_conditional_edge_group_invalid_number_of_targets():
    """Test creating a conditional edge group with an invalid number of targets."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    with pytest.raises(ValueError, match="ConditionalEdgeGroup must contain at least two targets"):
        ConditionalEdgeGroup(
            source=source,
            targets=[target],
            conditions=[lambda x: x.data < 0],
        )


def test_conditional_edge_group_invalid_number_of_conditions():
    """Test creating a conditional edge group with an invalid number of conditions."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    with pytest.raises(ValueError, match="Number of targets must be one more than the number of conditions."):
        ConditionalEdgeGroup(
            source=source,
            targets=[target1, target2],
            conditions=[lambda x: x.data < 0, lambda x: x.data > 0],
        )


async def test_conditional_edge_group_send_message():
    """Test sending a message through a conditional edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = ConditionalEdgeGroup(
        source=source,
        targets=[target1, target2],
        conditions=[lambda x: x.data < 0],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data=-1)
    message = Message(data=data, source_id=source.id)

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1

    # Default condition should
    data = MockMessage(data=1)
    message = Message(data=data, source_id=source.id)
    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1


async def test_conditional_edge_group_send_message_with_invalid_target():
    """Test sending a message through a conditional edge group with an invalid target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = ConditionalEdgeGroup(
        source=source,
        targets=[target1, target2],
        conditions=[lambda x: x.data < 0],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data=-1)
    message = Message(data=data, source_id=source.id, target_id="invalid_target")

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_conditional_edge_group_send_message_with_valid_target():
    """Test sending a message through a conditional edge group with a target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = ConditionalEdgeGroup(
        source=source,
        targets=[target1, target2],
        conditions=[lambda x: x.data < 0],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data=1)  # Condition will fail
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False

    data = MockMessage(data=-1)  # Condition will pass
    message = Message(data=data, source_id=source.id, target_id=target1.id)
    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is True


async def test_conditional_edge_group_send_message_with_invalid_data():
    """Test sending a message through a conditional edge group with invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = ConditionalEdgeGroup(
        source=source,
        targets=[target1, target2],
        conditions=[lambda x: x.data < 0],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


# endregion ConditionalEdgeGroup


# region PartitioningEdgeGroup


def test_partitioning_edge_group():
    """Test creating a partitioning edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0],
    )

    assert edge_group.source_executors == [source]
    assert edge_group.target_executors == [target1, target2]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor_1"
    assert edge_group.edges[1].source_id == "source_executor"
    assert edge_group.edges[1].target_id == "target_executor_2"


def test_partitioning_edge_group_invalid_number_of_targets():
    """Test creating a partitioning edge group with an invalid number of targets."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    with pytest.raises(ValueError, match="PartitioningEdgeGroup must contain at least two targets."):
        PartitioningEdgeGroup(
            source=source,
            targets=[target],
            partition_func=lambda data, num_edges: [0],
        )


async def test_partitioning_edge_group_send_message():
    """Test sending a message through a partitioning edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0, 1],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 2


async def test_partitioning_edge_group_send_message_with_invalid_partition_result():
    """Test sending a message through a partitioning edge group with an invalid partition result."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0, 2],  # Invalid index
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    with pytest.raises(RuntimeError):
        await edge_group.send_message(message, shared_state, ctx)


async def test_partitioning_edge_group_send_message_with_target():
    """Test sending a message through a partitioning edge group with a target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0, 1],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    with patch("agent_framework_workflow._edge.Edge.send_message") as mock_send:
        success = await edge_group.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0].target_id == target1.id


async def test_partitioning_edge_group_send_message_with_target_not_in_partition():
    """Test sending a message through a partitioning edge group with a target not in the partition."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0],  # Only target1 will receive the message
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target2.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_partitioning_edge_group_send_message_with_invalid_data():
    """Test sending a message through a partitioning edge group with invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0, 1],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


async def test_partitioning_edge_group_send_message_with_target_invalid_data():
    """Test sending a message through a partitioning edge group with a target and invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = PartitioningEdgeGroup(
        source=source,
        targets=[target1, target2],
        partition_func=lambda data, num_edges: [0, 1],
    )

    from agent_framework_workflow._runner_context import InProcRunnerContext, Message
    from agent_framework_workflow._shared_state import SharedState

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    success = await edge_group.send_message(message, shared_state, ctx)
    assert success is False


# endregion PartitioningEdgeGroup
