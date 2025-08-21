# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from ._runner_context import Message

logger = logging.getLogger(__name__)


class Edge:
    """Represents a directed edge in a graph."""

    ID_SEPARATOR: ClassVar[str] = "->"

    def __init__(
        self,
        source_id: str,
        target_id: str,
        condition: Callable[[Any], bool] | None = None,
    ) -> None:
        """Initialize the edge with a source and target node.

        Args:
            source_id (str): The ID of the source executor of the edge.
            target_id (str): The ID of the target executor of the edge.
            condition (Callable[[Any], bool], optional): A condition function that determines
                if the edge can handle the data. If None, the edge can handle any data type.
                Defaults to None.
        """
        self.source_id = source_id
        self.target_id = target_id
        self._condition = condition

    @property
    def id(self) -> str:
        """Get the unique ID of the edge."""
        return f"{self.source_id}{self.ID_SEPARATOR}{self.target_id}"

    def should_route(self, data: Any) -> bool:
        """Determine if message should be routed through this edge based on the condition."""
        if self._condition is None:
            return True

        return self._condition(data)


class EdgeGroup:
    """Represents a group of edges that share some common properties and can be triggered together."""

    def __init__(self) -> None:
        """Initialize the edge group."""
        self._id = f"{self.__class__.__name__}/{uuid.uuid4()}"

    @property
    def id(self) -> str:
        """Get the unique ID of the edge group."""
        return self._id

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the source executor IDs of the edges in the group."""
        raise NotImplementedError

    @property
    def target_executor_ids(self) -> list[str]:
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

    def __init__(self, source_id: str, target_id: str, condition: Callable[[Any], bool] | None = None) -> None:
        """Initialize the single edge group with an edge.

        Args:
            source_id (str): The source executor ID.
            target_id (str): The target executor ID that the source executor can send messages to.
            condition (Callable[[Any], bool], optional): A condition function that determines
                if the edge will pass the data to the target executor. If None, the edge will
                always pass the data to the target executor.
        """
        super().__init__()
        self._edge = Edge(source_id=source_id, target_id=target_id, condition=condition)

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the source executor ID of the edge."""
        return [self._edge.source_id]

    @property
    def target_executor_ids(self) -> list[str]:
        """Get the target executor ID of the edge."""
        return [self._edge.target_id]

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
        source_id: str,
        target_ids: Sequence[str],
        selection_func: Callable[[Any, list[str]], list[str]] | None = None,
    ) -> None:
        """Initialize the fan-out edge group with a list of edges.

        Args:
            source_id (str): The source executor ID.
            target_ids (Sequence[str]): A list of target executor IDs that the source executor can send messages to.
            selection_func (Callable[[Any, list[str]], list[str]], optional): A function that selects which target
                executors to send messages to. The function takes in the message data and a list of target executor
                IDs, and returns a list of selected target executor IDs.
        """
        if len(target_ids) <= 1:
            raise ValueError("FanOutEdgeGroup must contain at least two targets.")
        super().__init__()
        self._edges = [Edge(source_id=source_id, target_id=target_id) for target_id in target_ids]
        self._target_ids = list(target_ids)
        self._target_map = {edge.target_id: edge for edge in self._edges}
        self._selection_func = selection_func

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the source executor ID of the edges in the group."""
        return [self._edges[0].source_id]

    @property
    def target_executor_ids(self) -> list[str]:
        """Get the target executor IDs of the edges in the group."""
        return [edge.target_id for edge in self._edges]

    @property
    def target_ids(self) -> list[str]:
        """Get the target executor IDs for selection."""
        return self._target_ids

    @property
    def selection_func(self) -> Callable[[Any, list[str]], list[str]] | None:
        """Get the selection function for this fan-out group."""
        return self._selection_func

    @property
    def target_map(self) -> dict[str, Edge]:
        """Get the target ID to edge mapping."""
        return self._target_map

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

    def __init__(self, source_ids: Sequence[str], target_id: str) -> None:
        """Initialize the fan-in edge group with a list of edges.

        Args:
            source_ids (Sequence[str]): A list of source executor IDs that can send messages to the target executor.
            target_id (str): The target executor ID that receives a list of messages aggregated from all sources.
        """
        if len(source_ids) <= 1:
            raise ValueError("FanInEdgeGroup must contain at least two sources.")
        super().__init__()
        self._edges = [Edge(source_id=source_id, target_id=target_id) for source_id in source_ids]
        # Buffer to hold messages before sending them to the target executor
        # Key is the source executor ID, value is a list of messages
        self._buffer: dict[str, list[Message]] = defaultdict(list)

    def _is_ready_to_send(self) -> bool:
        """Check if all edges in the group have data to send."""
        return all(self._buffer[edge.source_id] for edge in self._edges)

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the source executor IDs of the edges in the group."""
        return [edge.source_id for edge in self._edges]

    @property
    def target_executor_ids(self) -> list[str]:
        """Get the target executor ID of the edges in the group."""
        return [self._edges[0].target_id]

    @property
    def buffer(self) -> dict[str, list[Message]]:
        """Get the message buffer for fan-in aggregation."""
        return self._buffer

    @property
    def edges(self) -> list[Edge]:
        """Get the edges in the group."""
        return self._edges


@dataclass
class Case:
    """Represents a single case in the conditional edge group.

    Args:
        condition (Callable[[Any], bool]): The condition function for the case.
        target_id (str): The target executor ID for the case.
    """

    condition: Callable[[Any], bool]
    target_id: str


@dataclass
class Default:
    """Represents the default case in the conditional edge group.

    Args:
        target_id (str): The target executor ID for the default case.
    """

    target_id: str


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
        source_id: str,
        cases: Sequence[Case | Default],
    ) -> None:
        """Initialize the conditional edge group with a list of edges.

        Args:
            source_id (str): The source executor ID.
            cases (Sequence[Case | Default]): A list of cases for the conditional edge group.
                There should be exactly one default case.
        """
        if len(cases) < 2:
            raise ValueError("SwitchCaseEdgeGroup must contain at least two cases (including the default case).")

        default_case = [isinstance(case, Default) for case in cases]
        if sum(default_case) != 1:
            raise ValueError("SwitchCaseEdgeGroup must contain exactly one default case.")

        if not isinstance(cases[-1], Default):
            logger.warning(
                "Default case in the conditional edge group is not the last case. "
                "This will result in unexpected behavior."
            )

        def selection_func(data: Any, targets: list[str]) -> list[str]:
            """Select the target executor based on the conditions."""
            for index, case in enumerate(cases):
                if isinstance(case, Default):
                    return [case.target_id]
                if isinstance(case, Case):
                    try:
                        if case.condition(data):
                            return [case.target_id]
                    except Exception as e:
                        logger.warning(f"Error occurred while evaluating condition for case {index}: {e}")

            raise RuntimeError("No matching case found in SwitchCaseEdgeGroup.")

        target_ids = [case.target_id for case in cases]
        super().__init__(source_id, target_ids, selection_func=selection_func)
        self._cases = cases

    @property
    def cases(self) -> Sequence[Case | Default]:
        """Get the cases for this switch-case group."""
        return self._cases
