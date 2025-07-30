# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

from ._executor import Executor
from ._runner_context import RunnerContext
from ._shared_state import SharedState
from ._workflow_context import WorkflowContext


class Edge:
    """Represents a directed edge in a graph."""

    ID_SEPARATOR: ClassVar[str] = "->"

    def __init__(
        self,
        source: Executor[Any],
        target: Executor[Any],
        condition: Callable[[Any], bool] | None = None,
    ):
        """Initialize the edge with a source and target node."""
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

    @classmethod
    def source_and_target_from_id(cls, edge_id: str) -> tuple[str, str]:
        """Extract the source and target IDs from the edge ID."""
        if cls.ID_SEPARATOR not in edge_id:
            raise ValueError(f"Invalid edge ID format: {edge_id}")
        ids = edge_id.split(cls.ID_SEPARATOR)
        if len(ids) != 2:
            raise ValueError(f"Invalid edge ID format: {edge_id}")
        return ids[0], ids[1]

    async def send_message(self, data: Any, shared_state: SharedState, ctx: RunnerContext) -> None:
        """Send a message along this edge."""
        if not self._edge_group_ids and self._should_route(data):
            await self.target.execute(data, WorkflowContext(self.target.id, shared_state, ctx))
        elif self._edge_group_ids:
            # Logic:
            # 1. If not all edges in the edge group have data in the shared state,
            #    add the data to the shared state.
            # 2. If all edges in the edge group have data in the shared state,
            #    copy the data to a list and send it to the target executor.
            messages = []
            async with shared_state.hold() as held_shared_state:
                has_data = await asyncio.gather(
                    *(held_shared_state.has_within_hold(edge_id) for edge_id in self._edge_group_ids)
                )
                if not all(has_data):
                    await held_shared_state.set_within_hold(self.id, data)
                else:
                    messages = [
                        await held_shared_state.get_within_hold(edge_id) for edge_id in self._edge_group_ids
                    ] + [data]
                    # Remove the data from the shared state after retrieving it
                    await asyncio.gather(
                        *(held_shared_state.delete_within_hold(edge_id) for edge_id in self._edge_group_ids)
                    )

            if messages:
                await self.target.execute(messages, WorkflowContext(self.target.id, shared_state, ctx))

    def _should_route(self, data: Any) -> bool:
        """Determine if message should be routed through this edge."""
        if not self.target.can_handle(data):
            return False

        if self._condition is None:
            return True

        return self._condition(data)

    def set_edge_group(self, edge_group_ids: list[str]) -> None:
        """Set the edge group IDs for this edge."""
        # Validate that the edges in the edge group contain the same target executor as this edge
        # TODO(@taochen): An edge cannot be part of multiple edge groups.
        # TODO(@taochen): Can an edge have both a condition and an edge group?
        if edge_group_ids:
            for edge_id in edge_group_ids:
                if Edge.source_and_target_from_id(edge_id)[1] != self.target.id:
                    raise ValueError("All edges in the group must have the same target executor.")
        self._edge_group_ids = edge_group_ids
