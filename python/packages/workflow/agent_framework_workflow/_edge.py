# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

from ._executor import Executor
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState
from ._workflow_context import WorkflowContext


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

        # Edge group is used to group edges that share the same target executor.
        # It allows for sending messages to the target executor only when all edges in the group have data.
        self._edge_group_ids: list[str] = []

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

    def has_edge_group(self) -> bool:
        """Check if the edge is part of an edge group."""
        return bool(self._edge_group_ids)

    @classmethod
    def source_and_target_from_id(cls, edge_id: str) -> tuple[str, str]:
        """Extract the source and target IDs from the edge ID.

        Args:
            edge_id (str): The edge ID in the format "source_id->target_id".

        Returns:
            tuple[str, str]: A tuple containing the source ID and target ID.
        """
        if cls.ID_SEPARATOR not in edge_id:
            raise ValueError(f"Invalid edge ID format: {edge_id}")
        ids = edge_id.split(cls.ID_SEPARATOR)
        if len(ids) != 2:
            raise ValueError(f"Invalid edge ID format: {edge_id}")
        return ids[0], ids[1]

    def can_handle(self, message_data: Any) -> bool:
        """Check if the edge can handle the given data.

        Args:
            message_data (Any): The data to check.

        Returns:
            bool: True if the edge can handle the data, False otherwise.
        """
        if not self._edge_group_ids:
            return self.target.can_handle(message_data)

        # If the edge is part of an edge group, the target should expect a list of the data type.
        return self.target.can_handle([message_data])

    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> None:
        """Send a message along this edge.

        Args:
            message (Message): The message to send.
            shared_state (SharedState): The shared state to use for holding data.
            ctx (RunnerContext): The context for the runner.
        """
        if not self.can_handle(message.data):
            raise RuntimeError(f"Edge {self.id} cannot handle data of type {type(message.data)}.")

        if not self._edge_group_ids and self._should_route(message.data):
            await self.target.execute(
                message.data, WorkflowContext(self.target.id, [self.source.id], shared_state, ctx)
            )
        elif self._edge_group_ids:
            # Logic:
            # 1. If not all edges in the edge group have data in the shared state,
            #    add the data to the shared state.
            # 2. If all edges in the edge group have data in the shared state,
            #    copy the data to a list and send it to the target executor.
            message_list: list[Message] = []
            async with shared_state.hold() as held_shared_state:
                has_data = await asyncio.gather(
                    *(held_shared_state.has_within_hold(edge_id) for edge_id in self._edge_group_ids)
                )
                if not all(has_data):
                    await held_shared_state.set_within_hold(self.id, message)
                else:
                    message_list = [
                        await held_shared_state.get_within_hold(edge_id) for edge_id in self._edge_group_ids
                    ] + [message]
                    # Remove the data from the shared state after retrieving it
                    await asyncio.gather(
                        *(held_shared_state.delete_within_hold(edge_id) for edge_id in self._edge_group_ids)
                    )

            if message_list:
                data_list = [msg.data for msg in message_list]
                source_ids = [msg.source_id for msg in message_list]
                await self.target.execute(data_list, WorkflowContext(self.target.id, source_ids, shared_state, ctx))

    def _should_route(self, data: Any) -> bool:
        """Determine if message should be routed through this edge."""
        if self._condition is None:
            return True

        return self._condition(data)

    def set_edge_group(self, edge_group_ids: list[str]) -> None:
        """Set the edge group IDs for this edge.

        Args:
            edge_group_ids (list[str]): A list of edge IDs that belong to the same edge group.
        """
        # Validate that the edges in the edge group contain the same target executor as this edge
        # TODO(@taochen): An edge cannot be part of multiple edge groups.
        # TODO(@taochen): Can an edge have both a condition and an edge group?
        if edge_group_ids:
            for edge_id in edge_group_ids:
                if Edge.source_and_target_from_id(edge_id)[1] != self.target.id:
                    raise ValueError("All edges in the group must have the same target executor.")
        self._edge_group_ids = edge_group_ids
