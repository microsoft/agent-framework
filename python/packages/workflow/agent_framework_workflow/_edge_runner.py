# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from ._edge import Edge, EdgeGroup, FanInEdgeGroup, FanOutEdgeGroup, SingleEdgeGroup, SwitchCaseEdgeGroup
from ._executor import Executor
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState
from ._workflow_context import WorkflowContext

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
            bool: True if the message was sent successfully, False if the target executor cannot handle the message.
        """
        raise NotImplementedError

    def _can_handle(self, executor_id: str, message_data: Any) -> bool:
        """Check if an executor can handle the given message data."""
        if executor_id not in self._executors:
            return False
        return self._executors[executor_id].can_handle(message_data)

    async def _execute_on_target(
        self, target_id: str, source_id: str, message: Message, shared_state: SharedState, ctx: RunnerContext
    ) -> None:
        """Execute a message on a target executor with trace context."""
        if target_id not in self._executors:
            raise RuntimeError(f"Target executor {target_id} not found.")

        target_executor = self._executors[target_id]

        # Handle both old single trace context format and new multiple trace contexts format
        trace_contexts = getattr(message, "trace_contexts", None)
        source_span_ids = getattr(message, "source_span_ids", None)

        # Backwards compatibility: if old format is used, convert to new format
        if trace_contexts is None and hasattr(message, "trace_context") and message.trace_context:
            trace_contexts = [message.trace_context]
        if source_span_ids is None and hasattr(message, "source_span_id") and message.source_span_id:
            source_span_ids = [message.source_span_id]

        # Create WorkflowContext with trace contexts from message
        workflow_context: WorkflowContext[Any] = WorkflowContext(
            target_id,
            [source_id],
            shared_state,
            ctx,
            trace_contexts=trace_contexts,  # Pass trace contexts to WorkflowContext
            source_span_ids=source_span_ids,  # Pass source span IDs for linking
        )

        # Execute with trace context in WorkflowContext
        await target_executor.execute(message.data, workflow_context)


class SingleEdgeRunner(EdgeRunner):
    """Runner for single edge groups."""

    def __init__(self, edge_group: SingleEdgeGroup, executors: dict[str, Executor]) -> None:
        super().__init__(edge_group, executors)
        self._edge = edge_group.edges[0]

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the single edge."""
        if message.target_id and message.target_id != self._edge.target_id:
            return False

        if self._can_handle(self._edge.target_id, message.data):
            if self._edge.should_route(message.data):
                await self._execute_on_target(self._edge.target_id, self._edge.source_id, message, shared_state, ctx)
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
        selection_results = (
            self._selection_func(message.data, self._target_ids) if self._selection_func else self._target_ids
        )
        if not self._validate_selection_result(selection_results):
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
                        await self._execute_on_target(edge.target_id, edge.source_id, message, shared_state, ctx)
                    return True
            return False

        # If no target ID, send the message to the selected targets
        async def send_to_edge(edge: Edge) -> bool:
            """Send the message to the edge."""
            if self._can_handle(edge.target_id, message.data):
                if edge.should_route(message.data):
                    await self._execute_on_target(edge.target_id, edge.source_id, message, shared_state, ctx)
                return True
            return False

        tasks = [send_to_edge(self._target_map[target_id]) for target_id in selection_results]
        results = await asyncio.gather(*tasks)
        return any(results)

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
        if message.target_id and message.target_id != self._edges[0].target_id:
            return False

        # Check if target can handle list of message data (fan-in aggregates multiple messages)
        if self._can_handle(self._edges[0].target_id, [message.data]):
            # If the edge can handle the data, buffer the message
            self._buffer[message.source_id].append(message)
        else:
            # If the edge cannot handle the data, return False
            return False

        if self._is_ready_to_send():
            # If all edges in the group have data, send the buffered messages to the target executor
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
                source_id=self._edge_group.__class__.__name__,
                trace_contexts=trace_contexts,
                source_span_ids=source_span_ids,
            )
            await self._execute_on_target(
                self._edges[0].target_id, self._edge_group.__class__.__name__, aggregated_message, shared_state, ctx
            )

        return True

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
