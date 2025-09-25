# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from ..observability import EdgeGroupDeliveryStatus, OtelAttr, create_edge_group_processing_span
from ._edge import Edge, EdgeGroup, FanInEdgeGroup, FanOutEdgeGroup, SingleEdgeGroup, SwitchCaseEdgeGroup
from ._executor import Executor
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState

logger = logging.getLogger(__name__)


class EdgeRunner(ABC):
    """Abstract base class for edge runners that handle message delivery."""

    def __init__(self, edge_group: EdgeGroup, executors: dict[str, Executor]) -> None:
        """Initialize the edge runner with an edge group and executor map.

        Args:
            edge_group: The edge group to run.
            executors: Map of executor IDs to executor instances.
        """
        self._edge_group = edge_group
        self._executors = executors

    @abstractmethod
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the edge group.

        Args:
            message: The message to send.
            shared_state: The shared state to use for holding data.
            ctx: The context for the runner.

        Returns:
            bool: True if the message was processed successfully,
                False if the target executor cannot handle the message.
        """
        raise NotImplementedError

    def _can_handle(self, executor_id: str, message_data: Any) -> bool:
        """Check if an executor can handle the given message data."""
        if executor_id not in self._executors:
            return False
        return self._executors[executor_id].can_handle(message_data)

    async def _execute_on_target(
        self,
        target_id: str,
        source_ids: list[str],
        message: Message,
        shared_state: SharedState,
        ctx: RunnerContext,
    ) -> None:
        """Execute a message on a target executor with trace context."""
        if target_id not in self._executors:
            raise RuntimeError(f"Target executor {target_id} not found.")

        target_executor = self._executors[target_id]

        # Execute with trace context parameters
        await target_executor.execute(
            message.data,
            source_ids,  # source_executor_ids
            shared_state,  # shared_state
            ctx,  # runner_context
            trace_contexts=message.trace_contexts,  # Pass trace contexts
            source_span_ids=message.source_span_ids,  # Pass source span IDs for linking
        )


class SingleEdgeRunner(EdgeRunner):
    """Runner for single edge groups."""

    def __init__(self, edge_group: SingleEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edge = edge_group.edges[0]

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the single edge."""
        should_execute = False
        target_id = None
        source_id = None
        with create_edge_group_processing_span(
            self._edge_group.__class__.__name__,
            edge_group_id=self._edge_group.id,
            message_source_id=message.source_id,
            message_target_id=message.target_id,
            source_trace_contexts=message.trace_contexts,
            source_span_ids=message.source_span_ids,
        ) as span:
            try:
                if message.target_id and message.target_id != self._edge.target_id:
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: False,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TARGET_MISMATCH.value,
                    })
                    return False

                if self._can_handle(self._edge.target_id, message.data):
                    if self._edge.should_route(message.data):
                        span.set_attributes({
                            OtelAttr.EDGE_GROUP_DELIVERED: True,
                            OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DELIVERED.value,
                        })
                        should_execute = True
                        target_id = self._edge.target_id
                        source_id = self._edge.source_id
                    else:
                        span.set_attributes({
                            OtelAttr.EDGE_GROUP_DELIVERED: False,
                            OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_CONDITION_FALSE.value,
                        })
                        # Return True here because message was processed, just condition failed
                        return True
                else:
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: False,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value,
                    })
                    return False
            except Exception as e:
                span.set_attributes({
                    OtelAttr.EDGE_GROUP_DELIVERED: False,
                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.EXCEPTION.value,
                })
                raise e

        # Execute outside the span
        if should_execute and target_id and source_id:
            await self._execute_on_target(target_id, [source_id], message, shared_state, ctx)
            return True

        return False


class FanOutEdgeRunner(EdgeRunner):
    """Runner for fan-out edge groups."""

    def __init__(self, edge_group: FanOutEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edges = edge_group.edges
        self._target_ids = edge_group.target_ids
        self._target_map = {edge.target_id: edge for edge in self._edges}
        self._selection_func = edge_group.selection_func

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through all edges in the fan-out edge group."""
        deliverable_edges = []
        single_target_edge = None
        # Process routing logic within span
        with create_edge_group_processing_span(
            self._edge_group.__class__.__name__,
            edge_group_id=self._edge_group.id,
            message_source_id=message.source_id,
            message_target_id=message.target_id,
            source_trace_contexts=message.trace_contexts,
            source_span_ids=message.source_span_ids,
        ) as span:
            try:
                selection_results = (
                    self._selection_func(message.data, self._target_ids) if self._selection_func else self._target_ids
                )
                if not self._validate_selection_result(selection_results):
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: False,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.EXCEPTION.value,
                    })
                    raise RuntimeError(
                        f"Invalid selection result: {selection_results}. "
                        f"Expected selections to be a subset of valid target executor IDs: {self._target_ids}."
                    )

                if message.target_id:
                    # If the target ID is specified and the selection result contains it, send the message to that edge
                    if message.target_id in selection_results:
                        edge = self._target_map.get(message.target_id)
                        if edge and self._can_handle(edge.target_id, message.data):
                            if edge.should_route(message.data):
                                span.set_attributes({
                                    OtelAttr.EDGE_GROUP_DELIVERED: True,
                                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DELIVERED.value,
                                })
                                single_target_edge = edge
                            else:
                                span.set_attributes({
                                    OtelAttr.EDGE_GROUP_DELIVERED: False,
                                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_CONDITION_FALSE.value,  # noqa: E501
                                })
                                # For targeted messages with condition failure, return True (message was processed)
                                return True
                        else:
                            span.set_attributes({
                                OtelAttr.EDGE_GROUP_DELIVERED: False,
                                OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value,  # noqa: E501
                            })
                            # For targeted messages that can't be handled, return False
                            return False
                    else:
                        span.set_attributes({
                            OtelAttr.EDGE_GROUP_DELIVERED: False,
                            OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TARGET_MISMATCH.value,
                        })
                        # For targeted messages not in selection, return False
                        return False
                else:
                    # If no target ID, send the message to the selected targets
                    for target_id in selection_results:
                        edge = self._target_map[target_id]
                        if self._can_handle(edge.target_id, message.data) and edge.should_route(message.data):
                            deliverable_edges.append(edge)

                    if len(deliverable_edges) > 0:
                        span.set_attributes({
                            OtelAttr.EDGE_GROUP_DELIVERED: True,
                            OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DELIVERED.value,
                        })
                    else:
                        span.set_attributes({
                            OtelAttr.EDGE_GROUP_DELIVERED: False,
                            OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value,
                        })

            except Exception as e:
                span.set_attributes({
                    OtelAttr.EDGE_GROUP_DELIVERED: False,
                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.EXCEPTION.value,
                })
                raise e

        # Execute outside the span
        if single_target_edge:
            await self._execute_on_target(
                single_target_edge.target_id, [single_target_edge.source_id], message, shared_state, ctx
            )
            return True

        if deliverable_edges:

            async def send_to_edge(edge: Edge) -> bool:
                await self._execute_on_target(edge.target_id, [edge.source_id], message, shared_state, ctx)
                return True

            tasks = [send_to_edge(edge) for edge in deliverable_edges]
            results = await asyncio.gather(*tasks)
            return any(results)

        # If we get here, it's a broadcast message with no deliverable edges
        return False

    def _validate_selection_result(self, selection_results: list[str]) -> bool:
        """Validate the selection results to ensure all IDs are valid target executor IDs."""
        return all(result in self._target_ids for result in selection_results)


class FanInEdgeRunner(EdgeRunner):
    """Runner for fan-in edge groups."""

    def __init__(self, edge_group: FanInEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edges = edge_group.edges
        # Buffer to hold messages before sending them to the target executor
        # Key is the source executor ID, value is a list of messages
        self._buffer: dict[str, list[Message]] = defaultdict(list)

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through all edges in the fan-in edge group."""
        execution_data: dict[str, Any] | None = None
        with create_edge_group_processing_span(
            self._edge_group.__class__.__name__,
            edge_group_id=self._edge_group.id,
            message_source_id=message.source_id,
            message_target_id=message.target_id,
            source_trace_contexts=message.trace_contexts,
            source_span_ids=message.source_span_ids,
        ) as span:
            try:
                if message.target_id and message.target_id != self._edges[0].target_id:
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: False,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TARGET_MISMATCH.value,
                    })
                    return False

                # Check if target can handle list of message data (fan-in aggregates multiple messages)
                if self._can_handle(self._edges[0].target_id, [message.data]):
                    # If the edge can handle the data, buffer the message
                    self._buffer[message.source_id].append(message)
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: True,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.BUFFERED.value,
                    })
                else:
                    # If the edge cannot handle the data, return False
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: False,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value,
                    })
                    return False

                if self._is_ready_to_send():
                    # If all edges in the group have data, prepare for execution
                    messages_to_send = [msg for edge in self._edges for msg in self._buffer[edge.source_id]]
                    self._buffer.clear()
                    # Send aggregated data to target
                    aggregated_data = [msg.data for msg in messages_to_send]

                    # Collect all trace contexts and source span IDs for fan-in linking
                    trace_contexts = [msg.trace_context for msg in messages_to_send if msg.trace_context]
                    source_span_ids = [msg.source_span_id for msg in messages_to_send if msg.source_span_id]

                    # Create a new Message object for the aggregated data
                    aggregated_message = Message(
                        data=aggregated_data,
                        source_id=self._edge_group.__class__.__name__,  # This won't be used in self._execute_on_target.
                        trace_contexts=trace_contexts,
                        source_span_ids=source_span_ids,
                    )
                    span.set_attributes({
                        OtelAttr.EDGE_GROUP_DELIVERED: True,
                        OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DELIVERED.value,
                    })

                    # Store execution data for later
                    execution_data = {
                        "target_id": self._edges[0].target_id,
                        "source_ids": [edge.source_id for edge in self._edges],
                        "message": aggregated_message,
                    }

            except Exception as e:
                span.set_attributes({
                    OtelAttr.EDGE_GROUP_DELIVERED: False,
                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.EXCEPTION.value,
                })
                raise e

        # Execute outside the span if needed
        if execution_data:
            await self._execute_on_target(
                execution_data["target_id"], execution_data["source_ids"], execution_data["message"], shared_state, ctx
            )
            return True

        return True  # Return True for buffered messages (waiting for more)

    def _is_ready_to_send(self) -> bool:
        """Check if all edges in the group have data to send."""
        return all(self._buffer[edge.source_id] for edge in self._edges)


class SwitchCaseEdgeRunner(FanOutEdgeRunner):
    """Runner for switch-case edge groups (inherits from FanOutEdgeRunner)."""

    def __init__(self, edge_group: SwitchCaseEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)


def create_edge_runner(edge_group: EdgeGroup, executors: dict[str, Executor]) -> EdgeRunner:
    """Factory function to create the appropriate edge runner for an edge group.

    Args:
        edge_group: The edge group to create a runner for.
        executors: Map of executor IDs to executor instances.

    Returns:
        The appropriate EdgeRunner instance.
    """
    if isinstance(edge_group, SingleEdgeGroup):
        return SingleEdgeRunner(edge_group, executors)
    if isinstance(edge_group, SwitchCaseEdgeGroup):
        return SwitchCaseEdgeRunner(edge_group, executors)
    if isinstance(edge_group, FanOutEdgeGroup):
        return FanOutEdgeRunner(edge_group, executors)
    if isinstance(edge_group, FanInEdgeGroup):
        return FanInEdgeRunner(edge_group, executors)
    raise ValueError(f"Unsupported edge group type: {type(edge_group)}")
