# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from ._executor import Executor
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover

logger = logging.getLogger(__name__)


class Edge:
    """Represents a directed edge in a graph."""

    ID_SEPARATOR: ClassVar[str] = "->"

    def __init__(
        self,
        source: Executor,
        target: Executor,
        condition: Callable[[Any], bool] | None = None,
    ) -> None:
        """Initialize the edge with a source and target node.

        Args:
            source (Executor): The source executor of the edge.
            target (Executor): The target executor of the edge.
            condition (Callable[[Any], bool], optional): A condition function that determines
                if the edge can handle the data. If None, the edge can handle any data type.
                Defaults to None.
        """
        self.source = source
        self.target = target
        self._condition = condition

    @property
    def source_id(self) -> str:
        """Get the source executor ID."""
        return self.source.id

    @property
    def target_id(self) -> str:
        """Get the target executor ID."""
        return self.target.id

    @property
    def id(self) -> str:
        """Get the unique ID of the edge."""
        return f"{self.source_id}{self.ID_SEPARATOR}{self.target_id}"

    def can_handle(self, message_data: Any) -> bool:
        """Check if the edge can handle the given data.

        Args:
            message_data (Any): The data to check.

        Returns:
            bool: True if the edge can handle the data, False otherwise.
        """
        return self.target.can_handle(message_data)

    def should_route(self, data: Any) -> bool:
        """Determine if message should be routed through this edge based on the condition."""
        if self._condition is None:
            return True

        return self._condition(data)

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> None:
        """Send a message along this edge.

        Args:
            message (Message): The message to send.
            shared_state (SharedState): The shared state to use for holding data.
            ctx (RunnerContext): The context for the runner.
        """
        if not self.can_handle(message.data):
            # Caller of this method should ensure that the edge can handle the data.
            raise RuntimeError(f"Edge {self.id} cannot handle data of type {type(message.data)}.")

        if self.should_route(message.data):
            await self.target.execute(
                message.data, WorkflowContext(self.target.id, [self.source.id], shared_state, ctx)
            )


class EdgeGroup(ABC):
    """Represents a group of edges that share some common properties and can be triggered together."""

    def __init__(self) -> None:
        """Initialize the edge group."""
        self._id = f"{self.__class__.__name__}/{uuid.uuid4()}"

    @abstractmethod
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the edge group.

        Args:
            message (Message): The message to send.
            shared_state (SharedState): The shared state to use for holding data.
            ctx (RunnerContext): The context for the runner.

        Returns:
            bool: True if the message was sent successfully, False otherwise. If a message can be delivered
                  but rejected due to a condition, it will still return True.
        """
        ...

    @property
    def id(self) -> str:
        """Get the unique ID of the edge group."""
        return self._id

    @abstractmethod
    def source_executors(self) -> list[Executor]:
        """Get the source executor IDs of the edges in the group."""
        ...

    @abstractmethod
    def target_executors(self) -> list[Executor]:
        """Get the target executor IDs of the edges in the group."""
        ...

    @abstractmethod
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        ...


class SingleEdgeGroup(EdgeGroup):
    """Represents a single edge group that contains only one edge."""

    def __init__(self, source: Executor, target: Executor, condition: Callable[[Any], bool] | None = None) -> None:
        """Initialize the single edge group with an edge.

        Args:
            source (Executor): The source executor.
            target (Executor): The target executor that the source executor can send messages to.
            condition (Callable[[Any], bool], optional): A condition function that determines
                if the edge will pass the data to the target executor. If None, the edge can
                will always pass the data to the target executor.
        """
        self._edge = Edge(source=source, target=target, condition=condition)

    @override
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the single edge."""
        if message.target_id and message.target_id != self._edge.target_id:
            return False

        if self._edge.can_handle(message.data):
            await self._edge.send_message(message, shared_state, ctx)
            return True

        return False

    @override
    def source_executors(self) -> list[Executor]:
        """Get the source executor of the edge."""
        return [self._edge.source]

    @override
    def target_executors(self) -> list[Executor]:
        """Get the target executor of the edge."""
        return [self._edge.target]

    @override
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return [self._edge]


class SourceEdgeGroup(EdgeGroup):
    """Represents a group of edges that share the same source executor.

    Assembles a Fan-out pattern where multiple edges share the same source executor
    and send messages to their respective target executors.
    """

    def __init__(self, source: Executor, targets: Sequence[Executor]) -> None:
        """Initialize the source edge group with a list of edges.

        Args:
            source (Executor): The source executor.
            targets (Sequence[Executor]): A list of target executors that the source executor can send messages to.
        """
        if len(targets) <= 1:
            raise ValueError("SourceEdgeGroup must contain at least two targets.")
        self._edges = [Edge(source=source, target=target) for target in targets]

    @override
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through all edges in the source edge group."""
        if message.target_id:
            # If the message has a target ID, send it to the specific target executor
            target_edge = next((edge for edge in self._edges if edge.target_id == message.target_id), None)
            if target_edge and target_edge.can_handle(message.data):
                await target_edge.send_message(message, shared_state, ctx)
                return True
            return False

        # If no target ID, send the message to all edges in the group
        await asyncio.gather(*(edge.send_message(message, shared_state, ctx) for edge in self._edges))
        return True

    @override
    def source_executors(self) -> list[Executor]:
        """Get the source executor of the edges in the group."""
        return [self._edges[0].source]

    @override
    def target_executors(self) -> list[Executor]:
        """Get the target executors of the edges in the group."""
        return [edge.target for edge in self._edges]

    @override
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return self._edges


class TargetEdgeGroup(EdgeGroup):
    """Represents a group of edges that share the same target executor.

    Assembles a Fan-in pattern where multiple edges send messages to a single target executor.
    Messages are buffered until all edges in the group have data to send.
    """

    def __init__(self, sources: Sequence[Executor], target: Executor) -> None:
        """Initialize the target edge group with a list of edges.

        Args:
            sources (Sequence[Executor]): A list of source executors that can send messages to the target executor.
            target (Executor): The target executor that receives a list of messages aggregated from all sources.
        """
        if len(sources) <= 1:
            raise ValueError("TargetEdgeGroup must contain at least two sources.")
        self._edges = [Edge(source=source, target=target) for source in sources]
        # Buffer to hold messages before sending them to the target executor
        # Key is the source executor ID, value is a list of messages
        self._buffer: dict[str, list[Message]] = defaultdict(list)

    @override
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through all edges in the target edge group."""
        if message.target_id and message.target_id != self._edges[0].target_id:
            return False

        if self._edges[0].can_handle([message.data]):
            # If the edge can handle the data, buffer the message
            self._buffer[message.source_id].append(message)
        else:
            # If the edge cannot handle the data, return False
            return False

        if self._is_ready_to_send():
            # If all edges in the group have data, send the buffered messages to the target executor
            messages_to_send = [msg for edge in self._edges for msg in self._buffer[edge.source_id]]
            self._buffer.clear()
            # Only trigger one edge to send the messages to avoid duplicate sends
            await self._edges[0].send_message(
                Message([msg.data for msg in messages_to_send], self._edges[0].source_id),
                shared_state,
                ctx,
            )

        return True

    def _is_ready_to_send(self) -> bool:
        """Check if all edges in the group have data to send."""
        return all(self._buffer[edge.source_id] for edge in self._edges)

    @override
    def source_executors(self) -> list[Executor]:
        """Get the source executors of the edges in the group."""
        return [edge.source for edge in self._edges]

    @override
    def target_executors(self) -> list[Executor]:
        """Get the target executor of the edges in the group."""
        return [self._edges[0].target]

    @override
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return self._edges


class ConditionalEdgeGroup(SourceEdgeGroup):
    """Represents a group of edges that assemble a conditional routing pattern.

    This is similar to a switch-case construct:
        switch(data):
            case condition_1:
                edge_1
                break
            case condition_2:
                edge_2
                break
            default:
                edge_3
                break
    Or equivalently an if-elif-else construct:
        if condition_1:
            edge_1
        elif condition_2:
            edge_2
        else:
            edge_4
    """

    def __init__(
        self,
        source: Executor,
        targets: Sequence[Executor],
        conditions: Sequence[Callable[[Any], bool]],
    ) -> None:
        """Initialize the conditional edge group with a list of edges.

        Args:
            source (Executor): The source executor.
            targets (Sequence[Executor]): A list of target executors that the source executor can send messages to.
            conditions (Sequence[Callable[[Any], bool]]): A list of condition functions that determine
                which target executor to route the message to based on the data. The number of conditions
                must be one less than the number of targets, as the last target is the default case. The
                index of the condition corresponds to the index of the target executor.
        """
        if len(targets) <= 1:
            raise ValueError("ConditionalEdgeGroup must contain at least two targets.")

        if len(targets) != len(conditions) + 1:
            raise ValueError("Number of targets must be one more than the number of conditions.")

        self._edges = [
            Edge(source, target, condition) for target, condition in zip(targets, [*conditions, None], strict=False)
        ]

    @override
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the conditional edge group."""
        if message.target_id:
            # Find the index of the target edge in the edges list if target_id is specified
            index = next((i for i, edge in enumerate(self._edges) if edge.target_id == message.target_id), None)
            if index is None:
                return False
            if self._edges[index].can_handle(message.data) and self._edges[index].should_route(message.data):
                await self._edges[index].send_message(message, shared_state, ctx)
                return True
            return False

        for edge in self._edges:
            if edge.can_handle(message.data) and edge.should_route(message.data):
                await edge.send_message(message, shared_state, ctx)
                return True

        return False


class PartitioningEdgeGroup(SourceEdgeGroup):
    """Represents a group of edges that can route messages based on a partitioning strategy.

    Messages from the source executor are routed to multiple target executors based on a partitioning function.
    """

    def __init__(
        self, source: Executor, targets: Sequence[Executor], partition_func: Callable[[Any, int], list[int]]
    ) -> None:
        """Initialize the partitioning edge group with a list of edges.

        Args:
            source (Executor): The source executor.
            targets (Sequence[Executor]): A list of target executors that the source executor can send messages to.
            partition_func (Callable[[Any, int], list[int]]): A partitioning function that determines which target
                executors to route the message to based on the data. The function should take the message data and
                the number of targets, and return a list of indices of the target executors to route the message to.
        """
        self._edges = [Edge(source=source, target=target) for target in targets]
        self._partition_func = partition_func

    @override
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the partitioning edge group."""
        partition_result = self._partition_func(message.data, len(self._edges))
        if not self._validate_partition_result(partition_result):
            raise RuntimeError(
                f"Invalid partition result: {partition_result}. Expected indices in range [0, {len(self._edges) - 1}]."
            )

        if message.target_id:
            # If the target ID is specified and the partition result contains it, send the message to that edge
            has_target = message.target_id in [self._edges[index].target_id for index in partition_result]
            if has_target:
                edge = next((edge for edge in self._edges if edge.target_id == message.target_id), None)
                if edge and edge.can_handle(message.data):
                    await edge.send_message(message, shared_state, ctx)
                    return True
            return False

        async def send_to_edge(edge: Edge) -> bool:
            """Send the message to the edge at the specified index."""
            if edge.can_handle(message.data):
                await edge.send_message(message, shared_state, ctx)
                return True
            return False

        tasks = [send_to_edge(self._edges[index]) for index in partition_result]
        results = await asyncio.gather(*tasks)
        return any(results)

    def _validate_partition_result(self, partition_result: list[int]) -> bool:
        """Validate the partition result to ensure all indices are within bounds."""
        return all(0 <= index < len(self._edges) for index in partition_result)
