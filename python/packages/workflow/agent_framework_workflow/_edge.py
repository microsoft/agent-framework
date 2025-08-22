# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from agent_framework._pydantic import AFBaseModel
from pydantic import Field

from agent_framework_workflow._executor import Executor

logger = logging.getLogger(__name__)


class Edge(AFBaseModel):
    """Represents a directed edge in a graph."""

    ID_SEPARATOR: ClassVar[str] = "->"

    source_id: str = Field(min_length=1, description="The ID of the source executor of the edge")
    target_id: str = Field(min_length=1, description="The ID of the target executor of the edge")

    def __init__(
        self,
        source_id: str,
        target_id: str,
        condition: Callable[[Any], bool] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the edge with a source and target node.

        Args:
            source_id (str): The ID of the source executor of the edge.
            target_id (str): The ID of the target executor of the edge.
            condition (Callable[[Any], bool], optional): A condition function that determines
                if the edge can handle the data. If None, the edge can handle any data type.
                Defaults to None.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        kwargs.update({"source_id": source_id, "target_id": target_id})
        super().__init__(**kwargs)
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


class EdgeGroup(AFBaseModel):
    """Represents a group of edges that share some common properties and can be triggered together."""

    id: str = Field(
        default_factory=lambda: f"EdgeGroup/{uuid.uuid4()}", description="Unique identifier for the edge group"
    )
    type: str = Field(description="The type of edge group, corresponding to the class name")
    edges: list[Edge] = Field(default_factory=list, description="List of edges in this group")

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the edge group."""
        if "id" not in kwargs:
            kwargs["id"] = f"{self.__class__.__name__}/{uuid.uuid4()}"
        if "type" not in kwargs:
            kwargs["type"] = self.__class__.__name__
        super().__init__(**kwargs)

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the source executor IDs of the edges in the group."""
        seen = set()
        result = []
        for edge in self.edges:
            if edge.source_id not in seen:
                result.append(edge.source_id)
                seen.add(edge.source_id)
        return result

    @property
    def target_executor_ids(self) -> list[str]:
        """Get the target executor IDs of the edges in the group."""
        seen = set()
        result = []
        for edge in self.edges:
            if edge.target_id not in seen:
                result.append(edge.target_id)
                seen.add(edge.target_id)
        return result


class SingleEdgeGroup(EdgeGroup):
    """Represents a single edge group that contains only one edge.

    A concrete implementation of EdgeGroup that represent a group containing exactly one edge.
    """

    def __init__(
        self, source_id: str, target_id: str, condition: Callable[[Any], bool] | None = None, **kwargs: Any
    ) -> None:
        """Initialize the single edge group with an edge.

        Args:
            source_id (str): The source executor ID.
            target_id (str): The target executor ID that the source executor can send messages to.
            condition (Callable[[Any], bool], optional): A condition function that determines
                if the edge will pass the data to the target executor. If None, the edge will
                always pass the data to the target executor.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        edge = Edge(source_id=source_id, target_id=target_id, condition=condition)
        kwargs["edges"] = [edge]
        super().__init__(**kwargs)


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
        **kwargs: Any,
    ) -> None:
        """Initialize the fan-out edge group with a list of edges.

        Args:
            source_id (str): The source executor ID.
            target_ids (Sequence[str]): A list of target executor IDs that the source executor can send messages to.
            selection_func (Callable[[Any, list[str]], list[str]], optional): A function that selects which target
                executors to send messages to. The function takes in the message data and a list of target executor
                IDs, and returns a list of selected target executor IDs.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        if len(target_ids) <= 1:
            raise ValueError("FanOutEdgeGroup must contain at least two targets.")

        edges = [Edge(source_id=source_id, target_id=target_id) for target_id in target_ids]
        kwargs["edges"] = edges
        super().__init__(**kwargs)

        self._target_ids = list(target_ids)
        self._selection_func = selection_func

    @property
    def target_ids(self) -> list[str]:
        """Get the target executor IDs for selection."""
        return self._target_ids

    @property
    def selection_func(self) -> Callable[[Any, list[str]], list[str]] | None:
        """Get the selection function for this fan-out group."""
        return self._selection_func


class FanInEdgeGroup(EdgeGroup):
    """Represents a group of edges that share the same target executor.

    Assembles a Fan-in pattern where multiple edges send messages to a single target executor.
    Messages are buffered until all edges in the group have data to send.
    """

    def __init__(self, source_ids: Sequence[str], target_id: str, **kwargs: Any) -> None:
        """Initialize the fan-in edge group with a list of edges.

        Args:
            source_ids (Sequence[str]): A list of source executor IDs that can send messages to the target executor.
            target_id (str): The target executor ID that receives a list of messages aggregated from all sources.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        if len(source_ids) <= 1:
            raise ValueError("FanInEdgeGroup must contain at least two sources.")

        edges = [Edge(source_id=source_id, target_id=target_id) for source_id in source_ids]
        kwargs["edges"] = edges
        super().__init__(**kwargs)


@dataclass
class Case:
    """Represents a single case in the switch-case edge group.

    Args:
        condition (Callable[[Any], bool]): The condition function for the case.
        target (Executor): The target executor for the case.
    """

    condition: Callable[[Any], bool]
    target: Executor


@dataclass
class Default:
    """Represents the default case in the switch-case edge group.

    Args:
        target (Executor): The target executor for the default case.
    """

    target: Executor


@dataclass
class SwitchCaseEdgeGroupCase:
    """A single case in the SwitchCaseEdgeGroup. This is used internally."""

    condition: Callable[[Any], bool]
    target_id: str


@dataclass
class SwitchCaseEdgeGroupDefault:
    """The default case in the SwitchCaseEdgeGroup. This is used internally."""

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
        cases: Sequence[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault],
        **kwargs: Any,
    ) -> None:
        """Initialize the switch-case edge group with a list of edges.

        Args:
            source_id (str): The source executor ID.
            cases (Sequence[Case | Default]): A list of cases for the switch-case edge group.
                There should be exactly one default case.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        if len(cases) < 2:
            raise ValueError("SwitchCaseEdgeGroup must contain at least two cases (including the default case).")

        default_case = [isinstance(case, SwitchCaseEdgeGroupDefault) for case in cases]
        if sum(default_case) != 1:
            raise ValueError("SwitchCaseEdgeGroup must contain exactly one default case.")

        if not isinstance(cases[-1], SwitchCaseEdgeGroupDefault):
            logger.warning(
                "Default case in the switch-case edge group is not the last case. "
                "This will result in unexpected behavior."
            )

        def selection_func(data: Any, targets: list[str]) -> list[str]:
            """Select the target executor based on the conditions."""
            for index, case in enumerate(cases):
                if isinstance(case, SwitchCaseEdgeGroupDefault):
                    return [case.target_id]
                if isinstance(case, SwitchCaseEdgeGroupCase):
                    try:
                        if case.condition(data):
                            return [case.target_id]
                    except Exception as e:
                        logger.warning(f"Error occurred while evaluating condition for case {index}: {e}")

            raise RuntimeError("No matching case found in SwitchCaseEdgeGroup.")

        target_ids = [case.target_id for case in cases]
        super().__init__(source_id, target_ids, selection_func=selection_func, **kwargs)
        self._cases = cases

    @property
    def cases(self) -> Sequence[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault]:
        """Get the cases for this switch-case group."""
        return self._cases
