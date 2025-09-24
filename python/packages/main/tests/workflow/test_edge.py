# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from agent_framework import (
    Executor,
    InProcRunnerContext,
    Message,
    SharedState,
    WorkflowContext,
    handler,
)
from agent_framework._workflow._edge import (
    Edge,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from agent_framework._workflow._edge_runner import create_edge_runner
from agent_framework.observability import EdgeGroupDeliveryStatus


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

    call_count: int = 0
    last_message: Any = None

    @handler
    async def mock_handler(self, message: MockMessage, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        self.call_count += 1
        self.last_message = message


class MockExecutorSecondary(Executor):
    """A secondary mock executor for testing purposes."""

    call_count: int = 0
    last_message: Any = None

    @handler
    async def mock_handler_secondary(self, message: MockMessageSecondary, ctx: WorkflowContext) -> None:
        """A secondary mock handler that does nothing."""
        self.call_count += 1
        self.last_message = message


class MockAggregator(Executor):
    """A mock aggregator for testing purposes."""

    call_count: int = 0
    last_message: Any = None

    @handler
    async def mock_aggregator_handler(self, message: list[MockMessage], ctx: WorkflowContext) -> None:
        """A mock aggregator handler that does nothing."""
        self.call_count += 1
        self.last_message = message

    @handler
    async def mock_aggregator_handler_secondary(
        self,
        message: list[MockMessageSecondary],
        ctx: WorkflowContext,
    ) -> None:
        """A mock aggregator handler that does nothing."""
        self.call_count += 1
        self.last_message = message


class MockAggregatorSecondary(Executor):
    """A mock aggregator that has a handler for a union type for testing purposes."""

    call_count: int = 0
    last_message: Any = None

    @handler
    async def mock_aggregator_handler_combine(
        self,
        message: list[MockMessage | MockMessageSecondary],
        ctx: WorkflowContext,
    ) -> None:
        """A mock aggregator handler that does nothing."""
        self.call_count += 1
        self.last_message = message


# region Edge


def test_create_edge():
    """Test creating an edge with a source and target executor."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge = Edge(source_id=source.id, target_id=target.id)

    assert edge.source_id == "source_executor"
    assert edge.target_id == "target_executor"
    assert edge.id == f"{edge.source_id}{Edge.ID_SEPARATOR}{edge.target_id}"


def test_edge_can_handle():
    """Test creating an edge with a source and target executor."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge = Edge(source_id=source.id, target_id=target.id)

    assert edge.should_route(MockMessage(data="test"))


# endregion Edge

# region SingleEdgeGroup


def test_single_edge_group():
    """Test creating a single edge group."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    assert edge_group.source_executor_ids == [source.id]
    assert edge_group.target_executor_ids == [target.id]
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor"


def test_single_edge_group_with_condition():
    """Test creating a single edge group with a condition."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id, condition=lambda x: x.data == "test")

    assert edge_group.source_executor_ids == [source.id]
    assert edge_group.target_executor_ids == [target.id]
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor"
    assert edge_group.edges[0]._condition is not None  # type: ignore


async def test_single_edge_group_send_message() -> None:
    """Test sending a message through a single edge runner."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True


async def test_single_edge_group_send_message_with_target() -> None:
    """Test sending a message through a single edge runner."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True


async def test_single_edge_group_send_message_with_invalid_target() -> None:
    """Test sending a message through a single edge runner."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id="invalid_target")

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_single_edge_group_send_message_with_invalid_data() -> None:
    """Test sending a message through a single edge runner with invalid data."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_single_edge_group_send_message_with_condition_pass() -> None:
    """Test sending a message through a single edge runner with a condition that passes."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    # Create edge group with condition that passes when data == "test"
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id, condition=lambda x: x.data == "test")

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True
    assert target.call_count == 1
    assert target.last_message.data == "test"


async def test_single_edge_group_send_message_with_condition_fail() -> None:
    """Test sending a message through a single edge runner with a condition that fails."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    # Create edge group with condition that passes when data == "test"
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id, condition=lambda x: x.data == "test")

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="different")
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    # Should return True because message was processed, but condition failed
    assert success is True
    # Target should not be called because condition failed
    assert target.call_count == 0


async def test_single_edge_group_tracing_success(span_exporter) -> None:
    """Test that single edge group processing creates proper success spans."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    # Create trace context and span IDs to simulate a message with tracing information
    trace_contexts = [{"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}]
    source_span_ids = ["00f067aa0ba902b7"]

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, trace_contexts=trace_contexts, source_span_ids=source_span_ids)

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "SingleEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is True
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DELIVERED.value
    assert span.attributes.get("edge_group.id") is not None
    assert span.attributes.get("message.source_id") == source.id

    # Verify span links are created
    assert span.links is not None
    assert len(span.links) == 1

    link = span.links[0]
    # Verify the link points to the correct trace and span
    assert link.context.trace_id == int("4bf92f3577b34da6a3ce929d0e0e4736", 16)
    assert link.context.span_id == int("00f067aa0ba902b7", 16)


async def test_single_edge_group_tracing_condition_failure(span_exporter) -> None:
    """Test that single edge group processing creates proper spans for condition failures."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id, condition=lambda x: x.data == "pass")

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="fail")
    message = Message(data=data, source_id=source.id)

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True  # Returns True but condition failed

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "SingleEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is False
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DROPPED_CONDITION_FALSE.value


async def test_single_edge_group_tracing_type_mismatch(span_exporter) -> None:
    """Test that single edge group processing creates proper spans for type mismatches."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    # Send incompatible data type
    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "SingleEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is False
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value


async def test_single_edge_group_tracing_target_mismatch(span_exporter) -> None:
    """Test that single edge group processing creates proper spans for target mismatches."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    executors: dict[str, Executor] = {source.id: source, target.id: target}
    edge_group = SingleEdgeGroup(source_id=source.id, target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id="wrong_target")

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "SingleEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is False
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DROPPED_TARGET_MISMATCH.value
    assert span.attributes.get("message.target_id") == "wrong_target"


# endregion SingleEdgeGroup


# region FanOutEdgeGroup


def test_source_edge_group():
    """Test creating a fan-out group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    assert edge_group.source_executor_ids == [source.id]
    assert edge_group.target_executor_ids == [target1.id, target2.id]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor_1"
    assert edge_group.edges[1].source_id == "source_executor"
    assert edge_group.edges[1].target_id == "target_executor_2"


def test_source_edge_group_invalid_number_of_targets() -> None:
    """Test creating a fan-out group with an invalid number of targets."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    with pytest.raises(ValueError, match="FanOutEdgeGroup must contain at least two targets"):
        FanOutEdgeGroup(source_id=source.id, target_ids=[target.id])


async def test_source_edge_group_send_message() -> None:
    """Test sending a message through a fan-out edge runner."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)

    assert success is True
    assert target1.call_count == 1
    assert target2.call_count == 1


async def test_source_edge_group_send_message_with_target() -> None:
    """Test sending a message through a fan-out group with a target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    success = await edge_runner.send_message(message, shared_state, ctx)

    assert success is True
    assert target1.call_count == 1
    assert target2.call_count == 0  # target2 should not be called since message targets target1


async def test_source_edge_group_send_message_with_invalid_target() -> None:
    """Test sending a message through a fan-out group with an invalid target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id="invalid_target")

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_source_edge_group_send_message_with_invalid_data() -> None:
    """Test sending a message through a fan-out group with invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_source_edge_group_send_message_only_one_successful_send() -> None:
    """Test sending a message through a fan-out group where only one edge can handle the message."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutorSecondary(id="target_executor_2")

    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)

    assert success is True
    assert target1.call_count == 1  # target1 can handle MockMessage
    assert target2.call_count == 0  # target2 (MockExecutorSecondary) cannot handle MockMessage


def test_source_edge_group_with_selection_func():
    """Test creating a partitioning edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id],
    )

    assert edge_group.source_executor_ids == [source.id]
    assert edge_group.target_executor_ids == [target1.id, target2.id]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor_1"
    assert edge_group.edges[1].source_id == "source_executor"
    assert edge_group.edges[1].target_id == "target_executor_2"


async def test_source_edge_group_with_selection_func_send_message() -> None:
    """Test sending a message through a fan-out group with a selection function."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id, target2.id],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    with patch("agent_framework._workflow._edge_runner.EdgeRunner._execute_on_target") as mock_send:
        success = await edge_runner.send_message(message, shared_state, ctx)

        assert success is True

        assert mock_send.call_count == 2


async def test_source_edge_group_with_selection_func_send_message_with_invalid_selection_result() -> None:
    """Test sending a message through a fan-out group with a selection func with an invalid selection result."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id, "invalid_target"],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id)

    with pytest.raises(RuntimeError):
        await edge_runner.send_message(message, shared_state, ctx)


async def test_source_edge_group_with_selection_func_send_message_with_target() -> None:
    """Test sending a message through a fan-out group with a selection func with a target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id, target2.id],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    with patch("agent_framework._workflow._edge_runner.EdgeRunner._execute_on_target") as mock_send:
        success = await edge_runner.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0] == target1.id


async def test_source_edge_group_with_selection_func_send_message_with_target_not_in_selection() -> None:
    """Test sending a message through a fan-out group with a selection func with a target not in the selection."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id],  # Only target1 will receive the message
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, target_id=target2.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_source_edge_group_with_selection_func_send_message_with_invalid_data() -> None:
    """Test sending a message through a fan-out group with a selection func with invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id, target2.id],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_source_edge_group_with_selection_func_send_message_with_target_invalid_data() -> None:
    """Test sending a message through a fan-out group with a selection func with a target and invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = FanOutEdgeGroup(
        source_id=source.id,
        target_ids=[target1.id, target2.id],
        selection_func=lambda data, target_ids: [target1.id, target2.id],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_fan_out_edge_group_tracing_success(span_exporter) -> None:
    """Test that fan-out edge group processing creates proper success spans."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    # Create trace context and span IDs to simulate a message with tracing information
    trace_contexts = [{"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}]
    source_span_ids = ["00f067aa0ba902b7"]

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source.id, trace_contexts=trace_contexts, source_span_ids=source_span_ids)

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "FanOutEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is True
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DELIVERED.value
    assert span.attributes.get("edge_group.id") is not None
    assert span.attributes.get("message.source_id") == source.id

    # Verify span links are created
    assert span.links is not None
    assert len(span.links) == 1

    link = span.links[0]
    # Verify the link points to the correct trace and span
    assert link.context.trace_id == int("4bf92f3577b34da6a3ce929d0e0e4736", 16)
    assert link.context.span_id == int("00f067aa0ba902b7", 16)


async def test_fan_out_edge_group_tracing_with_target(span_exporter) -> None:
    """Test that fan-out edge group processing creates proper spans for targeted messages."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_group = FanOutEdgeGroup(source_id=source.id, target_ids=[target1.id, target2.id])

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    # Create trace context and span IDs to simulate a message with tracing information
    trace_contexts = [{"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}]
    source_span_ids = ["00f067aa0ba902b7"]

    data = MockMessage(data="test")
    message = Message(
        data=data,
        source_id=source.id,
        target_id=target1.id,
        trace_contexts=trace_contexts,
        source_span_ids=source_span_ids,
    )

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "FanOutEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is True
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DELIVERED.value
    assert span.attributes.get("message.target_id") == target1.id

    # Verify span links are created
    assert span.links is not None
    assert len(span.links) == 1

    link = span.links[0]
    # Verify the link points to the correct trace and span
    assert link.context.trace_id == int("4bf92f3577b34da6a3ce929d0e0e4736", 16)
    assert link.context.span_id == int("00f067aa0ba902b7", 16)


# endregion FanOutEdgeGroup

# region FanInEdgeGroup


def test_target_edge_group():
    """Test creating a fan-in edge group."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    assert edge_group.source_executor_ids == [source1.id, source2.id]
    assert edge_group.target_executor_ids == [target.id]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor_1"
    assert edge_group.edges[0].target_id == "target_executor"
    assert edge_group.edges[1].source_id == "source_executor_2"
    assert edge_group.edges[1].target_id == "target_executor"


def test_target_edge_group_invalid_number_of_sources():
    """Test creating a fan-in edge group with an invalid number of sources."""
    source = MockExecutor(id="source_executor")
    target = MockAggregator(id="target_executor")

    with pytest.raises(ValueError, match="FanInEdgeGroup must contain at least two sources"):
        FanInEdgeGroup(source_ids=[source.id], target_id=target.id)


async def test_target_edge_group_send_message_buffer() -> None:
    """Test sending a message through a fan-in edge group with buffering."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")

    with patch("agent_framework._workflow._edge_runner.EdgeRunner._execute_on_target") as mock_send:
        success = await edge_runner.send_message(
            Message(data=data, source_id=source1.id),
            shared_state,
            ctx,
        )

        assert success is True
        assert mock_send.call_count == 0  # The message should be buffered and wait for the second source
        assert len(edge_runner._buffer[source1.id]) == 1  # type: ignore

        success = await edge_runner.send_message(
            Message(data=data, source_id=source2.id),
            shared_state,
            ctx,
        )
        assert success is True
        assert mock_send.call_count == 1  # The message should be sent now that both sources have sent their messages

        # Buffer should be cleared after sending
        assert not edge_runner._buffer  # type: ignore


async def test_target_edge_group_send_message_with_invalid_target() -> None:
    """Test sending a message through a fan-in edge group with an invalid target."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")
    message = Message(data=data, source_id=source1.id, target_id="invalid_target")

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_target_edge_group_send_message_with_invalid_data() -> None:
    """Test sending a message through a fan-in edge group with invalid data."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source1.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_fan_in_edge_group_tracing_buffered(span_exporter) -> None:
    """Test that fan-in edge group processing creates proper spans for buffered messages."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")

    # Create trace context and span IDs to simulate a message with tracing information
    trace_contexts1 = [{"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}]
    source_span_ids1 = ["00f067aa0ba902b7"]

    trace_contexts2 = [{"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b8-01"}]
    source_span_ids2 = ["00f067aa0ba902b8"]

    # Clear any build spans
    span_exporter.clear()

    # Send first message (should be buffered)
    success = await edge_runner.send_message(
        Message(data=data, source_id=source1.id, trace_contexts=trace_contexts1, source_span_ids=source_span_ids1),
        shared_state,
        ctx,
    )
    assert success is True

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "FanInEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is True
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.BUFFERED.value
    assert span.attributes.get("message.source_id") == source1.id

    # Verify span links are created for first message
    assert span.links is not None
    assert len(span.links) == 1

    link = span.links[0]
    # Verify the link points to the correct trace and span
    assert link.context.trace_id == int("4bf92f3577b34da6a3ce929d0e0e4736", 16)
    assert link.context.span_id == int("00f067aa0ba902b7", 16)

    # Clear spans and send second message (should trigger delivery)
    span_exporter.clear()

    success = await edge_runner.send_message(
        Message(data=data, source_id=source2.id, trace_contexts=trace_contexts2, source_span_ids=source_span_ids2),
        shared_state,
        ctx,
    )
    assert success is True

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "FanInEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is True
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DELIVERED.value
    assert span.attributes.get("message.source_id") == source2.id

    # Verify span links are created for second message
    assert span.links is not None
    assert len(span.links) == 1

    link = span.links[0]
    # Verify the link points to the correct trace and span for the second message
    assert link.context.trace_id == int("4bf92f3577b34da6a3ce929d0e0e4736", 16)
    assert link.context.span_id == int("00f067aa0ba902b8", 16)


async def test_fan_in_edge_group_tracing_type_mismatch(span_exporter) -> None:
    """Test that fan-in edge group processing creates proper spans for type mismatches."""
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    edge_runner = create_edge_runner(edge_group, executors)
    shared_state = SharedState()
    ctx = InProcRunnerContext()

    # Send incompatible data type
    data = "invalid_data"
    message = Message(data=data, source_id=source1.id)

    # Clear any build spans
    span_exporter.clear()

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False

    spans = span_exporter.get_finished_spans()
    edge_group_spans = [s for s in spans if s.name == "edge_group.process"]

    assert len(edge_group_spans) == 1

    span = edge_group_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("edge_group.type") == "FanInEdgeGroup"
    assert span.attributes.get("edge_group.delivered") is False
    assert span.attributes.get("edge_group.delivery_status") == EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value


async def test_fan_in_edge_group_with_multiple_message_types() -> None:
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregatorSecondary(id="target_executor")

    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")

    success = await edge_runner.send_message(
        Message(data=data, source_id=source1.id),
        shared_state,
        ctx,
    )
    assert success

    data2 = MockMessageSecondary(data="test")
    success = await edge_runner.send_message(
        Message(data=data2, source_id=source2.id),
        shared_state,
        ctx,
    )
    assert success


async def test_fan_in_edge_group_with_multiple_message_types_failed() -> None:
    source1 = MockExecutor(id="source_executor_1")
    source2 = MockExecutor(id="source_executor_2")
    target = MockAggregator(id="target_executor")

    edge_group = FanInEdgeGroup(source_ids=[source1.id, source2.id], target_id=target.id)

    executors: dict[str, Executor] = {source1.id: source1, source2.id: source2, target.id: target}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data="test")

    success = await edge_runner.send_message(
        Message(data=data, source_id=source1.id),
        shared_state,
        ctx,
    )
    assert success

    with pytest.raises(RuntimeError):
        # Although `MockAggregator` can handle `list[MockMessage]` and `list[MockMessageSecondary]`
        # separately (i.e., it has handlers for each type individually), it cannot handle
        # `list[MockMessage | MockMessageSecondary]` (a list containing a mix of both types).
        # With the fan-in edge group, the target executor must handle all message types from the
        # source executors as a union.
        data2 = MockMessageSecondary(data="test")
        _ = await edge_runner.send_message(
            Message(data=data2, source_id=source2.id),
            shared_state,
            ctx,
        )


# endregion FanInEdgeGroup

# region SwitchCaseEdgeGroup


def test_switch_case_edge_group() -> None:
    """Test creating a switch case edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SwitchCaseEdgeGroup(
        source_id=source.id,
        cases=[
            SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target1.id),
            SwitchCaseEdgeGroupDefault(target_id=target2.id),
        ],
    )

    assert edge_group.source_executor_ids == [source.id]
    assert edge_group.target_executor_ids == [target1.id, target2.id]
    assert len(edge_group.edges) == 2
    assert edge_group.edges[0].source_id == "source_executor"
    assert edge_group.edges[0].target_id == "target_executor_1"
    assert edge_group.edges[1].source_id == "source_executor"
    assert edge_group.edges[1].target_id == "target_executor_2"

    assert edge_group._selection_func is not None  # type: ignore
    assert edge_group._selection_func(MockMessage(data=-1), [target1.id, target2.id]) == [target1.id]  # type: ignore
    assert edge_group._selection_func(MockMessage(data=1), [target1.id, target2.id]) == [target2.id]  # type: ignore


def test_switch_case_edge_group_invalid_number_of_cases():
    """Test creating a switch case edge group with an invalid number of cases."""
    source = MockExecutor(id="source_executor")
    target = MockExecutor(id="target_executor")

    with pytest.raises(
        ValueError, match=r"SwitchCaseEdgeGroup must contain at least two cases \(including the default case\)."
    ):
        SwitchCaseEdgeGroup(
            source_id=source.id,
            cases=[
                SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target.id),
            ],
        )

    with pytest.raises(ValueError, match="SwitchCaseEdgeGroup must contain exactly one default case."):
        SwitchCaseEdgeGroup(
            source_id=source.id,
            cases=[
                SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target.id),
                SwitchCaseEdgeGroupCase(condition=lambda x: x.data >= 0, target_id=target.id),
            ],
        )


def test_switch_case_edge_group_invalid_number_of_default_cases():
    """Test creating a switch case edge group with an invalid number of conditions."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    with pytest.raises(ValueError, match="SwitchCaseEdgeGroup must contain exactly one default case."):
        SwitchCaseEdgeGroup(
            source_id=source.id,
            cases=[
                SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target1.id),
                SwitchCaseEdgeGroupDefault(target_id=target2.id),
                SwitchCaseEdgeGroupDefault(target_id=target2.id),
            ],
        )


async def test_switch_case_edge_group_send_message() -> None:
    """Test sending a message through a switch case edge group."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SwitchCaseEdgeGroup(
        source_id=source.id,
        cases=[
            SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target1.id),
            SwitchCaseEdgeGroupDefault(target_id=target2.id),
        ],
    )
    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data=-1)
    message = Message(data=data, source_id=source.id)

    with patch("agent_framework._workflow._edge_runner.EdgeRunner._execute_on_target") as mock_send:
        success = await edge_runner.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1

    # Default condition should
    data = MockMessage(data=1)
    message = Message(data=data, source_id=source.id)
    with patch("agent_framework._workflow._edge_runner.EdgeRunner._execute_on_target") as mock_send:
        success = await edge_runner.send_message(message, shared_state, ctx)

        assert success is True
        assert mock_send.call_count == 1


async def test_switch_case_edge_group_send_message_with_invalid_target() -> None:
    """Test sending a message through a switch case edge group with an invalid target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SwitchCaseEdgeGroup(
        source_id=source.id,
        cases=[
            SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target1.id),
            SwitchCaseEdgeGroupDefault(target_id=target2.id),
        ],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data=-1)
    message = Message(data=data, source_id=source.id, target_id="invalid_target")

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


async def test_switch_case_edge_group_send_message_with_valid_target() -> None:
    """Test sending a message through a switch case edge group with a target."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SwitchCaseEdgeGroup(
        source_id=source.id,
        cases=[
            SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target1.id),
            SwitchCaseEdgeGroupDefault(target_id=target2.id),
        ],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = MockMessage(data=1)  # Condition will fail
    message = Message(data=data, source_id=source.id, target_id=target1.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False

    data = MockMessage(data=-1)  # Condition will pass
    message = Message(data=data, source_id=source.id, target_id=target1.id)
    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is True


async def test_switch_case_edge_group_send_message_with_invalid_data() -> None:
    """Test sending a message through a switch case edge group with invalid data."""
    source = MockExecutor(id="source_executor")
    target1 = MockExecutor(id="target_executor_1")
    target2 = MockExecutor(id="target_executor_2")

    edge_group = SwitchCaseEdgeGroup(
        source_id=source.id,
        cases=[
            SwitchCaseEdgeGroupCase(condition=lambda x: x.data < 0, target_id=target1.id),
            SwitchCaseEdgeGroupDefault(target_id=target2.id),
        ],
    )

    executors: dict[str, Executor] = {source.id: source, target1.id: target1, target2.id: target2}
    edge_runner = create_edge_runner(edge_group, executors)

    shared_state = SharedState()
    ctx = InProcRunnerContext()

    data = "invalid_data"
    message = Message(data=data, source_id=source.id)

    success = await edge_runner.send_message(message, shared_state, ctx)
    assert success is False


# endregion SwitchCaseEdgeGroup
