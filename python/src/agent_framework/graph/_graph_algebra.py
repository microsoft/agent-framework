# Copyright (c) Microsoft. All rights reserved.
from typing import Generic, Protocol, TypeVar, runtime_checkable

from agent_framework.graph._graph_low import ExecutableGraph, Lowering
from agent_framework.graph._graph_shared import GraphNode

from ._graph_mid import GraphBuilder, RunnableStep, StepT, TIn, TOut

TIn2 = TypeVar("TIn2", contravariant=True)
TOut2 = TypeVar("TOut2", covariant=True)
TInOut = TypeVar("TInOut", contravariant=False, covariant=False)


def check_step(step: StepT[TIn, TOut]) -> bool:
    if isinstance(step, RunnableStep):
        _ = Lowering.check_and_extract_types(step.run)
        return True

    if callable(step):
        _ = Lowering.check_and_extract_types(step)
        return True

    return False


@runtime_checkable
class Subflow(Protocol, Generic[TIn, TOut]):
    @property
    def input_condition(self) -> StepT[TIn, bool] | None:
        """Returns the condition to check before executing the subflow."""
        ...

    def map_input_node(self, builder: GraphBuilder) -> GraphNode[TIn, TOut]:
        """Returns the input node of the subflow."""
        ...

    @property
    def output_node(self) -> str:
        """Returns the output node of the subflow."""
        ...


class AlgebraicNode(Generic[TIn, TOut]):
    def __init__(self, builder: GraphBuilder, id: str):
        self.builder = builder
        self.id = id

    def __add__(
        self, other: StepT[TOut, TOut2] | Subflow[TOut, TOut2] | "AlgebraicNode[TOut, TOut2]"
    ) -> "AlgebraicNode[TOut, TOut2]":
        """Adds an edge to another node in the graph, and returns the new algebraic node."""
        return JoinBuilder(self.builder, self) + other

    def __or__(
        self, other: StepT[TIn2, TOut] | Subflow[TIn2, TOut] | "AlgebraicNode[TIn2, TOut]"
    ) -> "JoinBuilder[TIn|TIn2, TOut]":
        """Joins the current algebraic node with another node in the graph.

        This means that an edge will be added from the current node and the other node to a new node.
        """
        other_source: str

        if isinstance(other, AlgebraicNode):
            other_source = other.id
        elif isinstance(other, Subflow):
            node = other.map_input_node(self.builder)
            other_source = other.output_node
        elif check_step(other):
            node, _ = self.builder.ensure_node(other)
            other_source = node.id
        else:
            raise TypeError(
                f"Unsupported type for OR operation: {type(other)}. Expected StepT or Subflow or AlgebraicNode."
            )

        return JoinBuilder(self.builder, self, AlgebraicNode(self.builder, other_source))

    def as_result(self) -> ExecutableGraph:
        """Returns the graph as an executable graph."""
        return self.builder.build(output_node=self.id)


StepishT = StepT[TIn, TOut] | Subflow[TIn, TOut] | AlgebraicNode[TIn, TOut]


class JoinBuilder(Generic[TIn, TOut]):
    """A class that builds a join operation in the graph."""

    def __init__(self, builder: GraphBuilder, *inputs: AlgebraicNode[TIn, TOut]):
        self.builder = builder
        self.inputs = inputs

    def __or__(self, other: AlgebraicNode[TIn2, TOut]) -> "JoinBuilder[TIn|TIn2, TOut]":
        """Adds another step to the join operation."""
        return JoinBuilder(self.builder, *self.inputs, other)

    def __add__(self, other: StepishT[TOut, TOut2]) -> AlgebraicNode[TOut, TOut2]:
        """Adds another step to the join operation."""
        if isinstance(other, AlgebraicNode):
            for input_node in self.inputs:
                self.builder.add_edge(source=input_node.id, target=other.id)
            return other

        if isinstance(other, AlgebraicNode):
            self.builder.add_edge(source=self.id, target=other.id)
            return other

        target: str
        condition: StepT[TOut, bool] | None = None

        if isinstance(other, Subflow):
            node = other.map_input_node(self.builder)
            target = node.id
            condition = other.input_condition
        elif check_step(other):
            node, _ = self.builder.ensure_node(other)
            target = node.id
        else:
            raise TypeError(
                f"Unsupported type for addition: {type(other)}. Expected StepT or Subflow or AlgebraicNode."
            )

        for input_node in self.inputs:
            # print(f"Adding edge from {input_node.id} to {target} with condition ({condition}.__name__)")  # noqa: E501, ERA001
            self.builder.add_edge(source=input_node.id, target=target, condition=condition)

        return AlgebraicNode(self.builder, target)


class IfComplete(Subflow[TIn, TOut], Generic[TIn, TOut]):
    """A class that represents a complete if condition in the graph."""

    def __init__(self, condition: StepT[TIn, bool], then_branch: StepishT[TIn, TOut]):
        self.condition = condition
        self.then_branch = then_branch

    def map_input_node(self, builder: GraphBuilder) -> GraphNode[TIn, TOut]:
        """Returns the input node of the subflow."""
        node, _ = builder.ensure_node(self.then_branch)

        return node

    @property
    def input_condition(self) -> StepT[TIn, bool] | None:
        """Returns the condition to check before executing the subflow."""
        return self.condition

    @property
    def output_node(self) -> str:
        return self.input_node


class If(Generic[TIn]):
    """A class that represents an if condition in the graph."""

    def __init__(self, condition: StepT[TIn, bool]):
        self.condition = condition

    def __lshift__(self, then_branch: StepishT[TIn, TOut]) -> IfComplete[TIn, TOut]:
        """Creates a complete if condition with a then branch."""
        return IfComplete(condition=self.condition, then_branch=then_branch)


class GraphAlgebra(Generic[TIn]):
    """A class that provides algebraic operations for graphs."""

    @staticmethod
    def start(input_step: StepT[TIn, TOut]) -> AlgebraicNode[TIn, TOut]:
        builder = GraphBuilder.start(input_step)
        return AlgebraicNode(builder, builder.start_name)
