# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from typing import Any, cast

from ..exceptions import WorkflowCheckpointException
from ..observability import EdgeGroupDeliveryStatus, OtelAttr, create_edge_group_processing_span
from ._edge import (
    Edge,
    EdgeGroup,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    InternalEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
)
from ._executor import Executor
from ._runner_context import RunnerContext, WorkflowMessage
from ._state import State

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
    async def send_message(
        self,
        message: WorkflowMessage,
        state: State,
        ctx: RunnerContext,
    ) -> bool:
        """Send a message through the edge group.

        Args:
            message: The message to send.
            state: The workflow state.
            ctx: The context for the runner.

        Returns:
            bool: True if the message was processed successfully,
                False if the target executor cannot handle the message.
        """
        raise NotImplementedError

    @property
    def state_key(self) -> str:
        """Return a topology-derived key identifying this runner across workflow instances.

        ``EdgeGroup.id`` defaults to a random UUID, so it differs between two instances of the
        same workflow definition and cannot key state that has to survive a rebuild. Checkpoint
        compatibility is decided by graph topology, so the key is derived from topology too.
        Builder validation rejects two edges that share a ``source -> target`` pair anywhere in
        the workflow, so no two edge groups can produce the same key.
        """
        edges = sorted(f"{edge.source_id}->{edge.target_id}" for edge in self._edge_group.edges)
        return f"{self._edge_group.__class__.__name__}:{','.join(edges)}"

    def snapshot_state(self) -> dict[str, Any] | None:
        """Capture in-flight delivery state so a checkpoint can restore it.

        Returns:
            A serializable snapshot, or None when the runner holds no state to checkpoint.
        """
        return None

    def restore_state(self, state: dict[str, Any] | None) -> None:
        """Reset in-flight delivery state, then apply ``state`` when one was checkpointed.

        Called on every runner during checkpoint restoration, including with ``None``, so that
        state left over from an interrupted run does not survive into the restored run.

        Args:
            state: A snapshot previously produced by :meth:`snapshot_state`, or None to only reset.
        """
        return

    def _can_handle(self, executor_id: str, message: WorkflowMessage) -> bool:
        """Check if an executor can handle the given message data."""
        if executor_id not in self._executors:
            return False
        return self._executors[executor_id].can_handle(message)

    async def _execute_on_target(
        self,
        target_id: str,
        source_ids: list[str],
        message: WorkflowMessage,
        state: State,
        ctx: RunnerContext,
    ) -> None:
        """Execute a message on a target executor with trace context."""
        if target_id not in self._executors:
            raise RuntimeError(f"Target executor {target_id} not found.")

        target_executor = self._executors[target_id]

        # Execute with trace context parameters
        await target_executor.execute(
            message,
            source_ids,  # source_executor_ids
            state,  # state
            ctx,  # runner_context
            trace_contexts=message.trace_contexts,  # Pass trace contexts
            source_span_ids=message.source_span_ids,  # Pass source span IDs for linking
        )


class SingleEdgeRunner(EdgeRunner):
    """Runner for single edge groups."""

    def __init__(self, edge_group: SingleEdgeGroup | InternalEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edge = edge_group.edges[0]

    async def send_message(
        self,
        message: WorkflowMessage,
        state: State,
        ctx: RunnerContext,
    ) -> bool:
        """Send a message through the single edge."""
        should_execute = False
        target_id: str | None = None
        source_id: str | None = None
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

                if self._can_handle(self._edge.target_id, message):
                    route_result = await self._edge.should_route(message.data)

                    if route_result:
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
            await self._execute_on_target(target_id, [source_id], message, state, ctx)
            return True

        return False


class FanOutEdgeRunner(EdgeRunner):
    """Runner for fan-out edge groups."""

    def __init__(self, edge_group: FanOutEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edges = edge_group.edges
        self._target_ids = edge_group.target_executor_ids
        self._target_map = {edge.target_id: edge for edge in self._edges}
        self._selection_func = cast(
            Callable[[Any, list[str]], list[str]] | None, getattr(edge_group, "selection_func", None)
        )

    async def send_message(
        self,
        message: WorkflowMessage,
        state: State,
        ctx: RunnerContext,
    ) -> bool:
        """Send a message through all edges in the fan-out edge group."""
        deliverable_edges: list[Edge] = []
        single_target_edge: Edge | None = None
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
                        if edge and self._can_handle(edge.target_id, message):
                            route_result = await edge.should_route(message.data)

                            if route_result:
                                span.set_attributes({
                                    OtelAttr.EDGE_GROUP_DELIVERED: True,
                                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DELIVERED.value,
                                })
                                single_target_edge = edge
                            else:
                                span.set_attributes({
                                    OtelAttr.EDGE_GROUP_DELIVERED: False,
                                    OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_CONDITION_FALSE.value,  # ruff:ignore[line-too-long]
                                })
                                # For targeted messages with condition failure, return True (message was processed)
                                return True
                        else:
                            span.set_attributes({
                                OtelAttr.EDGE_GROUP_DELIVERED: False,
                                OtelAttr.EDGE_GROUP_DELIVERY_STATUS: EdgeGroupDeliveryStatus.DROPPED_TYPE_MISMATCH.value,  # ruff:ignore[line-too-long]
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
                        if self._can_handle(edge.target_id, message):
                            route_result = await edge.should_route(message.data)
                            if route_result:
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
                single_target_edge.target_id,
                [single_target_edge.source_id],
                message,
                state,
                ctx,
            )
            return True

        if deliverable_edges:

            async def send_to_edge(edge: Edge) -> bool:
                await self._execute_on_target(edge.target_id, [edge.source_id], message, state, ctx)
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

    _BUFFER_KEY = "buffer"

    def __init__(self, edge_group: FanInEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edges = edge_group.edges
        # Buffer to hold messages before sending them to the target executor
        # Key is the source executor ID, value is a list of messages
        self._buffer: dict[str, list[WorkflowMessage]] = defaultdict(list)

    def snapshot_state(self) -> dict[str, Any] | None:
        """Capture the buffered messages that are still waiting for the remaining sources.

        A fan-in only delivers once every source has produced a message, so a superstep
        boundary can fall while the buffer holds a subset of them. Those messages have
        already been drained from the runner context, so the checkpoint has to carry them.
        """
        buffered = {source_id: list(messages) for source_id, messages in self._buffer.items() if messages}
        if not buffered:
            return None
        return {self._BUFFER_KEY: buffered}

    def restore_state(self, state: dict[str, Any] | None) -> None:
        """Reset the buffer, then refill it from the checkpointed snapshot when there is one.

        The reset matters on its own: a run that failed mid-superstep can leave messages from
        a subset of sources in the buffer, and the sources are re-executed after the restore.
        Without the reset those messages would be delivered twice, and the second delivery
        could fire the fan-in before the restored superstep produced all of its messages.
        """
        self._buffer.clear()
        if state is None:
            return

        buffered: Any = state.get(self._BUFFER_KEY, {})
        if not isinstance(buffered, dict):
            raise WorkflowCheckpointException(
                f"Fan-in buffer for edge group {self._edge_group.id} is not a dictionary. Unable to restore."
            )

        for source_id, messages in cast(dict[Any, Any], buffered).items():
            if (
                not isinstance(source_id, str)
                or not isinstance(messages, list)
                or not all(isinstance(message, WorkflowMessage) for message in cast(list[Any], messages))
            ):
                raise WorkflowCheckpointException(
                    f"Fan-in buffer for edge group {self._edge_group.id} is malformed. Unable to restore."
                )
            self._buffer[source_id] = list(cast(list[WorkflowMessage], messages))

    async def send_message(
        self,
        message: WorkflowMessage,
        state: State,
        ctx: RunnerContext,
    ) -> bool:
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
                if self._can_handle(
                    self._edges[0].target_id, WorkflowMessage(data=[message.data], source_id=message.source_id)
                ):
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

                    # Collect all trace contexts and source span IDs for fan-in linking.
                    # Iterate over the plural fields (trace_contexts / source_span_ids)
                    # so that messages carrying multiple contexts from a previous
                    # fan-in aggregation are fully preserved. Using the singular
                    # backward-compat properties would silently drop all but the
                    # first context per message.
                    #
                    # Pair contexts and span IDs per-message (via zip) so that a
                    # message with mismatched counts only drops its own orphans
                    # instead of shifting all subsequent pairs out of alignment
                    # when the flattened lists are later zipped by
                    # ``create_processing_span``.
                    trace_contexts: list[dict[str, str]] = []
                    source_span_ids: list[str] = []
                    for msg in messages_to_send:
                        msg_contexts = msg.trace_contexts or []
                        msg_span_ids = msg.source_span_ids or []
                        for trace_context, span_id in zip(msg_contexts, msg_span_ids, strict=False):
                            trace_contexts.append(trace_context)
                            source_span_ids.append(span_id)

                    # Create a new Message object for the aggregated data
                    aggregated_message = WorkflowMessage(
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
                execution_data["target_id"],
                execution_data["source_ids"],
                execution_data["message"],
                state,
                ctx,
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
    if isinstance(edge_group, (SingleEdgeGroup, InternalEdgeGroup)):
        return SingleEdgeRunner(edge_group, executors)
    if isinstance(edge_group, SwitchCaseEdgeGroup):
        return SwitchCaseEdgeRunner(edge_group, executors)
    if isinstance(edge_group, FanOutEdgeGroup):
        return FanOutEdgeRunner(edge_group, executors)
    if isinstance(edge_group, FanInEdgeGroup):
        return FanInEdgeRunner(edge_group, executors)
    raise ValueError(f"Unsupported edge group type: {type(edge_group)}")
