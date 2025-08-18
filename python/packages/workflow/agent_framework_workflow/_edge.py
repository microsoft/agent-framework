# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from ._executor import Executor
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState
from ._workflow_context import WorkflowContext

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


class EdgeGroup:
    """Represents a group of edges that share some common properties and can be triggered together."""

    def __init__(self) -> None:
        """Initialize the edge group."""
        self._id = f"{self.__class__.__name__}/{uuid.uuid4()}"

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the edge group.

        Args:
            message (Message): The message to send.
            shared_state (SharedState): The shared state to use for holding data.
            ctx (RunnerContext): The context for the runner.

        Returns:
            bool: True if the message was sent successfully, False if the target executor cannot handle the message.
                  If a message can be delivered but rejected due to a condition, it will still return True.

        Note:
            Exception will not be raised if the target executor cannot handle the message. This is because
            a source executor can be connected to multiple target executors, and not every target executor may
            be able to handle all the messages sent by the source executor.
        """
        raise NotImplementedError

    @property
    def id(self) -> str:
        """Get the unique ID of the edge group."""
        return self._id

    @property
    def source_executors(self) -> list[Executor]:
        """Get the source executor IDs of the edges in the group."""
        raise NotImplementedError

    @property
    def target_executors(self) -> list[Executor]:
        """Get the target executor IDs of the edges in the group."""
        raise NotImplementedError

    @property
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        raise NotImplementedError


class SingleEdgeGroup(EdgeGroup):
    """Represents a single edge group that contains only one edge.

    A concrete implementation of EdgeGroup that represent a group containing exactly one edge.
    """

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

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through the single edge."""
        if message.target_id and message.target_id != self._edge.target_id:
            return False

        if self._edge.can_handle(message.data):
            await self._edge.send_message(message, shared_state, ctx)
            return True

        return False

    @property
    def source_executors(self) -> list[Executor]:
        """Get the source executor of the edge."""
        return [self._edge.source]

    @property
    def target_executors(self) -> list[Executor]:
        """Get the target executor of the edge."""
        return [self._edge.target]

    @property
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return [self._edge]


class FanOutEdgeGroup(EdgeGroup):
    """Represents a group of edges that share the same source executor.

    Assembles a Fan-out pattern where multiple edges share the same source executor
    and send messages to their respective target executors.
    """

    def __init__(
        self,
        source: Executor,
        targets: Sequence[Executor],
        selection_func: Callable[[Any, list[str]], list[str]] | None = None,
    ) -> None:
        """Initialize the fan-out edge group with a list of edges.

        Args:
            source (Executor): The source executor.
            targets (Sequence[Executor]): A list of target executors that the source executor can send messages to.
            selection_func (Callable[[Any, list[str]], list[str]], optional): A function that selects which target
                executors to send messages to. The function takes in the message data and a list of target executor
                IDs, and returns a list of selected target executor IDs.
        """
        if len(targets) <= 1:
            raise ValueError("FanOutEdgeGroup must contain at least two targets.")
        self._edges = [Edge(source=source, target=target) for target in targets]
        self._target_ids = [edge.target_id for edge in self._edges]
        self._target_map = {edge.target_id: edge for edge in self._edges}
        self._selection_func = selection_func

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
                edge = next((edge for edge in self._edges if edge.target_id == message.target_id), None)
                if edge and edge.can_handle(message.data):
                    await edge.send_message(message, shared_state, ctx)
                    return True
            return False

        # If no target ID, send the message to the selected targets
        async def send_to_edge(edge: Edge) -> bool:
            """Send the message to the edge at the specified index."""
            if edge.can_handle(message.data):
                await edge.send_message(message, shared_state, ctx)
                return True
            return False

        tasks = [send_to_edge(self._target_map[target_id]) for target_id in selection_results]
        results = await asyncio.gather(*tasks)
        return any(results)

    @property
    def source_executors(self) -> list[Executor]:
        """Get the source executor of the edges in the group."""
        return [self._edges[0].source]

    @property
    def target_executors(self) -> list[Executor]:
        """Get the target executors of the edges in the group."""
        return [edge.target for edge in self._edges]

    @property
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return self._edges

    def _validate_selection_result(self, selection_results: list[str]) -> bool:
        """Validate the selection results to ensure all IDs are valid target executor IDs."""
        return all(result in self._target_ids for result in selection_results)


class FanInEdgeGroup(EdgeGroup):
    """Represents a group of edges that share the same target executor.

    Assembles a Fan-in pattern where multiple edges send messages to a single target executor.
    Messages are buffered until all edges in the group have data to send.
    """

    def __init__(self, sources: Sequence[Executor], target: Executor) -> None:
        """Initialize the fan-in edge group with a list of edges.

        Args:
            sources (Sequence[Executor]): A list of source executors that can send messages to the target executor.
            target (Executor): The target executor that receives a list of messages aggregated from all sources.
        """
        if len(sources) <= 1:
            raise ValueError("FanInEdgeGroup must contain at least two sources.")
        self._edges = [Edge(source=source, target=target) for source in sources]
        # Buffer to hold messages before sending them to the target executor
        # Key is the source executor ID, value is a list of messages
        self._buffer: dict[str, list[Message]] = defaultdict(list)

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        """Send a message through all edges in the fan-in edge group."""
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
                Message([msg.data for msg in messages_to_send], self.__class__.__name__),
                shared_state,
                ctx,
            )

        return True

    def _is_ready_to_send(self) -> bool:
        """Check if all edges in the group have data to send."""
        return all(self._buffer[edge.source_id] for edge in self._edges)

    @property
    def source_executors(self) -> list[Executor]:
        """Get the source executors of the edges in the group."""
        return [edge.source for edge in self._edges]

    @property
    def target_executors(self) -> list[Executor]:
        """Get the target executor of the edges in the group."""
        return [self._edges[0].target]

    @property
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return self._edges


@dataclass
class Case:
    """Represents a single case in the conditional edge group.

    Args:
        condition (Callable[[Any], bool]): The condition function for the case.
        target (Executor): The target executor for the case.
    """

    condition: Callable[[Any], bool]
    target: Executor


@dataclass
class Default:
    """Represents the default case in the conditional edge group.

    Args:
        target (Executor): The target executor for the default case.
    """

    target: Executor


class SwitchCaseEdgeGroup(FanOutEdgeGroup):
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
        cases: Sequence[Case | Default],
    ) -> None:
        """Initialize the conditional edge group with a list of edges.

        Args:
            source (Executor): The source executor.
            cases (Sequence[Case | Default]): A list of cases for the conditional edge group.
                There should be exactly one default case.
        """
        if len(cases) < 2:
            raise ValueError("SwitchCaseEdgeGroup must contain at least two cases (including the default case).")

        default_case = [isinstance(case, Default) for case in cases]
        if sum(default_case) != 1:
            raise ValueError("SwitchCaseEdgeGroup must contain exactly one default case.")

        if isinstance(cases[-1], Default):
            logger.warning(
                "Default case in the conditional edge group is not the last case. "
                "This will result in unexpected behavior."
            )

        def selection_func(data: Any, targets: list[str]) -> list[str]:
            """Select the target executor based on the conditions."""
            for index, case in enumerate(cases):
                if isinstance(case, Default):
                    return [case.target.id]
                if isinstance(case, Case):
                    try:
                        if case.condition(data):
                            return [case.target.id]
                    except Exception as e:
                        logger.warning(f"Error occurred while evaluating condition for case {index}: {e}")

            raise RuntimeError("No matching case found in SwitchCaseEdgeGroup.")

        super().__init__(source, [case.target for case in cases], selection_func=selection_func)
