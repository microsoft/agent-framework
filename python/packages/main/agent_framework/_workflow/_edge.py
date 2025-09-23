# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import Field

from .._pydantic import AFBaseModel
from ._executor import Executor

logger = logging.getLogger(__name__)


def _extract_function_name(func: Callable[..., Any]) -> str:
    """Extract the name of any callable function for serialization.

    Args:
        func: The function to extract the name from.

    Returns:
        The name of the function, or a placeholder for lambda functions.
    """
    if hasattr(func, "__name__"):
        name = func.__name__
        # Check if it's a lambda function
        if name == "<lambda>":
            return "<lambda>"
        return name
    # Fallback for other callable objects
    return "<callable>"


class Edge(AFBaseModel):
    """Represents a directed edge in a graph."""

    ID_SEPARATOR: ClassVar[str] = "->"

    source_id: str = Field(min_length=1, description="The ID of the source executor of the edge")
    target_id: str = Field(min_length=1, description="The ID of the target executor of the edge")
    condition_name: str | None = Field(default=None, description="The name of the condition function for serialization")

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
        condition_name = _extract_function_name(condition) if condition is not None else None
        kwargs.update({"source_id": source_id, "target_id": target_id, "condition_name": condition_name})
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


def _default_edge_list() -> list[Edge]:
    """Get the default list of edges for the group."""
    return []


class EdgeGroup(AFBaseModel):
    """Represents a group of edges that share some common properties and can be triggered together."""

    id: str = Field(
        default_factory=lambda: f"EdgeGroup/{uuid.uuid4()}", description="Unique identifier for the edge group"
    )
    type: str = Field(description="The type of edge group, corresponding to the class name")
    edges: list[Edge] = Field(default_factory=_default_edge_list, description="List of edges in this group")

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
        return list(dict.fromkeys(edge.source_id for edge in self.edges))

    @property
    def target_executor_ids(self) -> list[str]:
        """Get the target executor IDs of the edges in the group."""
        return list(dict.fromkeys(edge.target_id for edge in self.edges))


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

    selection_func_name: str | None = Field(
        default=None, description="The name of the selection function for serialization"
    )

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

        # Extract selection function name for serialization
        selection_func_name = None
        if selection_func is not None:
            selection_func_name = _extract_function_name(selection_func)

        edges = [Edge(source_id=source_id, target_id=target_id) for target_id in target_ids]
        kwargs.update({"edges": edges, "selection_func_name": selection_func_name})
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


class SwitchCaseEdgeGroupCase(AFBaseModel):
    """A single case in the SwitchCaseEdgeGroup. This is used internally."""

    target_id: str = Field(description="The target executor ID for this case")
    condition_name: str | None = Field(default=None, description="The name of the condition function for serialization")
    type: str = Field(default="Case", description="The type of the case")

    def __init__(self, condition: Callable[[Any], bool], target_id: str, **kwargs: Any) -> None:
        """Initialize the switch case with a condition and target.

        Args:
            condition: The condition function for the case.
            target_id: The target executor ID for this case.
            kwargs: Additional keyword arguments.
        """
        condition_name = _extract_function_name(condition)
        kwargs.update({"target_id": target_id, "condition_name": condition_name})
        super().__init__(**kwargs)
        self._condition = condition

    @property
    def condition(self) -> Callable[[Any], bool]:
        """Get the condition function for this case."""
        return self._condition


class SwitchCaseEdgeGroupDefault(AFBaseModel):
    """The default case in the SwitchCaseEdgeGroup. This is used internally."""

    target_id: str = Field(description="The target executor ID for the default case")
    type: str = Field(default="Default", description="The type of the case")


def _default_case_list() -> list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault]:
    """Get the default list of cases for the group."""
    return []


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

    cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = Field(
        default_factory=_default_case_list,
        description="List of conditional cases for this switch-case group",
    )

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

        kwargs.update({"cases": cases})
        super().__init__(source_id, target_ids, selection_func=selection_func, **kwargs)
