# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, runtime_checkable

TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut", covariant=True)
TInOut = TypeVar("TInOut", contravariant=False, covariant=False)


@runtime_checkable
class NodeAction(Protocol, Generic[TIn, TOut]):
    def __call__(self, input: TIn) -> TOut:
        """Defines the action to be performed by the node."""
        ...

    @classmethod
    def get_types(cls) -> tuple[type[TIn], type[TOut]]:
        """Returns the input and output types of the action."""
        return cls.__args__


@runtime_checkable
class EpsilonAction(Protocol, Generic[TInOut]):
    def __call__(self, input: TInOut, node_id: str) -> TInOut:
        """Defines the action to be performed when no edge matches the output."""
        ...

    @classmethod
    def get_types(cls) -> tuple[type[TInOut], type[TInOut]]:
        """Returns the type of the input and output for the epsilon action."""
        return (*cls.__args__,) * 2


@runtime_checkable
class EdgeCondition(Protocol, Generic[TIn]):
    def __call__(self, input: TIn) -> bool:
        """Defines the condition to be checked for the edge."""
        ...

    @classmethod
    def get_types(cls) -> tuple[type[TIn], type[bool]]:
        """Returns the type of the input for the edge condition."""
        return (*cls.__args__, bool)


def REJECT_EPSILON(input: TInOut, node_id: str) -> TInOut:
    """Raises an error if no edge is found for the input."""
    error = f"Missing edge for input: {input} in node {node_id}"
    raise ValueError(error)


@dataclass
class GraphNode(Generic[TIn, TOut]):
    id: str
    action: NodeAction[TIn, TOut]
    edges: list[GraphEdge[TOut]] | None = None

    epsilon_action: EpsilonAction[TOut] | None = REJECT_EPSILON
    """Action to be executed if no edge matches the output.

    Remarks:
        Replacing this is a powerful capability but should be used with caution.

        Defaults to `REJECT_EPSILON`, which raises an error if no edge matches the output.
        If set to `None`, no action will be taken when no edge matches, and this condition will be silently ignored.
        If set to a custom action, be wary that unless the action throws an error, it will keep being called
        successively on the output until the return of the epsilon action is a match for one of the outgoing edges.
    """

    def __post_init__(self):
        # Now that we have a real action, we need to make sure we set the types for EpsilonAction
        from ._graph_low import Lowering

        _, ATOut = Lowering.check_and_extract_types(self.action, expecting=NodeAction)

        if self.epsilon_action is None:
            return

        if not hasattr(self.epsilon_action, "__annotations__") or \
            self.epsilon_action.__annotations__.get("input") is not ATOut or \
            self.epsilon_action.__annotations__.get("return") is not ATOut:
            self.epsilon_action.__annotations__ = {
                "input": ATOut,
                "node_id": "str",
                "return": ATOut,
            }


@dataclass
class GraphEdge(Generic[TIn]):
    target: str
    condition: EdgeCondition[TIn] | None = None

    def handles(self, input: TIn) -> bool:
        """Checks if the edge can handle the given input."""
        if self.condition is None:
            return True
        return self.condition(input)
