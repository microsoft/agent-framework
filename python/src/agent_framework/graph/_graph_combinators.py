# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import enum
import typing
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, Generic, Protocol, Tuple, TypeVar, cast, runtime_checkable

from agent_framework.graph._graph_shared import GraphNode

from . import ExecutableGraph
from . import GraphBuilder as GraphBuilder
from ._graph_mid import Identified, RunnableStep, StepT, TIn, TOut
from ._graph_shared import TInOut

TIn2 = TypeVar("TIn2", contravariant=True)
TOut2 = TypeVar("TOut2", covariant=True)
TInOut2 = TypeVar("TInOut2", contravariant=False, covariant=False)


NodeId = str


def _merge_conditions(*conditions: StepT[TIn, bool]) -> StepT[TIn, bool]:
    """Merges multiple conditions into a single condition.

    Args:
        *conditions (StepT[TIn, bool]): The conditions to merge.

    Returns:
        StepT[TIn, bool]: A new condition that combines all the input conditions.
    """
    if len(conditions) == 0:
        raise ValueError("At least one condition must be provided.")

    if len(conditions) == 1:
        return conditions[0]

    if len(conditions) == 2:
        first, second = conditions

        def _both(input: TIn) -> bool:
            return first(input) and second(input)

        return _both

    def _all(input: TIn) -> bool:
        return all(condition(input) for condition in conditions)

    return _all


@runtime_checkable
class Flow(Protocol, Generic[TIn, TOut]):
    """A protocol for defining a flow in the graph."""

    def ensure_nodes(self, builder: FlowBuilder) -> list[NodeId, bool]:
        """Ensures the nodes are created in the graph builder.

        Args:
            builder (FlowBuilder): The flow builder to use for creating nodes.

        Returns a list of pairs of node ID and True if the node was created by this
        call, or False if it already existed.
        """
        ...

    def get_types(self) -> tuple[type[TIn], type[TOut]]:
        """Returns the input and output types of the flow."""
        ...


InputT = Tuple[NodeId, StepT[TIn, bool] | None]


class InFlow(Protocol, Flow[TIn, TOut], Generic[TIn, TOut]):
    """A protocol for defining an input flow in the graph."""

    @property
    def inputs(self) -> list[InputT]:
        """Returns the input nodes of the flow."""
        ...


def _with_condition(
    step_tuple: InputT, condition: StepT[TIn, bool] | None
) -> InputT:
    """Merges a step tuple with a condition.

    Args:
        step_tuple (InputT): The input step tuple.
        condition (StepT[TIn, bool] | None): The condition to merge with the step tuple.

    Returns:
        InputT: A new step tuple with the merged condition.
    """
    node_id, existing_condition = step_tuple
    if existing_condition is not None:
        # TODO(jaalber): Turn this into a __call__ implementing class so we can coalesce
        # conditions (rather than create a tree of conditions/combiners)
        existing_condition = _merge_conditions(existing_condition, condition)
    else:
        existing_condition = condition

    return (node_id, existing_condition)


class OutFlow(Protocol, Flow[TIn, TOut], Generic[TIn, TOut]):
    """A protocol for defining an output flow in the graph."""

    @property
    def outputs(self) -> list[NodeId]:
        """Returns the output nodes of the flow."""
        ...


InFlowishT = InFlow[TIn, TOut] | StepT[TIn, TOut]
OutFlowishT = OutFlow[TIn, TOut] | StepT[TIn, TOut]


class FlowBase(ABC, Flow[TIn, TOut], Generic[TIn, TOut]):
    """A base class for defining a flow in the graph."""

    @abstractmethod
    def ensure_nodes(self, builder: FlowBuilder) -> list[NodeId, bool]:
        """Ensures the nodes are created in the graph builder.

        Args:
            builder (FlowBuilder): The flow builder to use for creating nodes.

        Returns a list of pairs of node ID and True if the node was created by this
        call, or False if it already existed.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    def get_types(self) -> tuple[type[TIn], type[TOut]]:
        """Returns the input and output types of the flow.

        This method attempts to extract the input and output types from the underlying
        type arguments. It is likely that more concrete implementations will have better
        logic for extracting these types, but this provides a fallback.

        Returns:
            tuple[type[TIn], type[TOut]]: The concrete input and output types of the flow

        Raises:
            TypeError: If the input and output types cannot be determined.
        """
        # If the type arguments have been bound, we can extract concrete types from them.
        ArgTIn, ArgTOut = typing.get_args(self)

        # If we got real types, we can return them directly.
        if ArgTIn is not None and isinstance(ArgTIn, type) and ArgTOut is not None and isinstance(ArgTOut, type):
            return ArgTIn, ArgTOut

        raise TypeError(
            f"Could not determine input and output types for step {self.step}. "
            "Please ensure the step is properly annotated with type hints."
        )

    def _get_flowbase(
        self,
        flowish: InFlowishT[TIn, TOut] | OutFlowishT[TIn, TOut],
        require_in: bool = False,
        require_out: bool = False,
    ) -> FlowBase[TIn, TOut]:
        if isinstance(flowish, FlowBase):
            return flowish
        if (isinstance(flowish, InFlow) and not require_out) or (isinstance(flowish, OutFlow) and not require_in):
            # TODO(jaalber): this needs to be wrapped in a FlowBase, ideally (or just merge FlowBase
            # and Flow).
            if not isinstance(flowish, FlowBase):
                # Technically, there are no flows that are not FlowBase, but unless we do the
                # merge as mentioned above, a user could pass in a non-FlowBase flowish object
                raise NotImplementedError(
                    f"FlowBase wrapping not implemented for InFlow or OutFlow, on type={type(flowish)}"
                )

            return cast(FlowBase[TIn, TOut], flowish)
        if StepFlow.check_type(flowish):
            # Since this is definitely a step, wrap it in a StepFlow.
            return StepFlow(flowish)

        allowed = []
        if not require_out:
            allowed.append("InFlow")
        if not require_in:
            allowed.append("OutFlow")
        if not require_in and not require_out:
            allowed.append("StepT")
            allowed.append("FlowBase")

        raise TypeError(f"Invalid type for flowish: {type(flowish)}. Expected {(', '.join(allowed))}.")

    @staticmethod
    def _combine_flows(input_flow: FlowBase[TIn, TInOut], output_flow: FlowBase[TInOut, TOut]) -> FlowBase[TIn, TOut]:
        """Combines two flows into a sequence flow."""
        return SequenceFlow.combine_flows(input_flow, output_flow)

    def __add__(self, other: OutFlowishT[TOut, TOut2]) -> Flow[TIn, TOut2]:
        exit_flow: FlowBase[TOut, TOut2] = self._get_flowbase(other, require_out=True)

        return FlowBase._combine_flows(self, exit_flow)

    def __addr__(self, other: InFlowishT[TIn2, TInOut2]) -> Flow[TIn2, TOut]:
        input_flow = self._get_flowbase(other, require_in=True)

        return FlowBase._combine_flows(input_flow, self)


class StepFlow(InFlow[TIn, TOut], OutFlow[TIn, TOut], FlowBase[TIn, TOut]):
    """A class for defining a step flow in the graph."""

    @staticmethod
    def check_type(step: StepT[TIn, TOut]) -> bool:
        """Checks if the step is a valid type for a flow."""
        if isinstance(step, RunnableStep):
            return True
        if callable(step):  # noqa: SIM103
            # TODO(jaalber): Validate the types of the callable step.
            return True
        return False

    def __init__(self, step: StepT[TIn, TOut]):
        """Initializes the StepFlow with a step.

        Args:
            step (StepT[TIn, TOut]): The step to be used in the flow.
        """
        if not self.check_type(step):
            raise TypeError("Invalid step type")

        self.step = step
        self.id = GraphBuilder.extract_name(step)

    @property
    def inputs(self) -> list[InputT]:
        return [(self.id, None)]

    @property
    def outputs(self) -> list[NodeId]:
        return [self.id]

    def ensure_nodes(self, builder: FlowBuilder) -> list[Tuple[NodeId, bool]]:
        return builder.builder.ensure_node(self.step)

    def get_types(self) -> tuple[type[TIn], type[TOut]]:
        # We have a number of ways to get at this, but let's try the easiest first:
        type_hints = typing.get_type_hints(self.step)

        if "return" in type_hints and "input" in type_hints:
            return type_hints["input"], type_hints["return"]

        # Fallback to the base implementation if type hints are not available.
        return super().get_types()


class AutoIdSource:
    next_id: int = 0
    prefix: str

    def next(self) -> str:
        """Generates the next ID in the sequence."""
        id_ = f"{self.prefix}_{self.next_id}"
        self.next_id += 1
        return id_


class SequenceFlow(InFlow[TIn, TOut], OutFlow[TIn, TOut], FlowBase[TIn, TOut]):
    """A class for defining a sequence flow in the graph."""

    def __init__(self, steps: list[FlowBase[TIn, TOut]], id: str | None = None):
        """Initializes the SequenceFlow with a list of steps.

        Args:
            steps (list[StepT[TIn, TOut]]): The steps to be used in the flow.
            id (str | None): Optional ID for the sequence flow. If not provided, a unique ID will be generated.
        """
        if not all(StepFlow.check_type(step) for step in steps):
            raise TypeError("Invalid step type in sequence")

        self.steps = steps

    @staticmethod
    def _promote_flow(flow: FlowBase[TIn, TOut]) -> SequenceFlow[TIn, TOut]:
        """Promotes a flow to a SequenceFlow if it is not already one."""
        if isinstance(flow, SequenceFlow):
            return flow

        return SequenceFlow([flow])

    @staticmethod
    def combine_flows(
        input_flow: FlowBase[TIn, TInOut], output_flow: FlowBase[TInOut, TOut]
    ) -> SequenceFlow[TIn, TOut]:
        """Combines two flows into a sequence flow."""
        in_sequence = SequenceFlow._promote_flow(input_flow)
        out_sequence = SequenceFlow._promote_flow(output_flow)

        return SequenceFlow([*in_sequence.steps, *out_sequence.steps])

    @property
    def inputs(self) -> list[InputT]:
        return self.steps[0].inputs

    @property
    def outputs(self) -> list[NodeId]:
        return self.steps[-1].outputs

    def ensure_nodes(self, builder: FlowBuilder) -> list[Tuple[NodeId, bool]]:
        nodes = []

        for step in self.steps:
            node, built = builder.builder.ensure_node(step)
            if nodes and (built or nodes[-1][1]):
                # If either this node, or the last node was just built,
                # they need to be connected. TODO(jaalber): The lower-level API is not well-suited
                # for doing operations like this idempotently.
                builder.bind(nodes[-1][0], node)

            nodes.append((node, built))

        return nodes


class LoopFlow(InFlow[TInOut, TInOut], OutFlow[TInOut, TInOut], FlowBase[TInOut, TInOut]):
    def __init__(self, while_: StepT[TInOut, bool], do_: Flow[TInOut, TInOut] | list[StepT], id: str | None = None):
        """Initializes the LoopFlow with a while condition and a do flow.

        Args:
            while_ (StepT[TInOut, bool]): The condition to check for the loop.
            do_ (Flow[TInOut, TInOut] | list[StepT]): The flow or steps to execute in the loop.
            id (str | None): Optional ID for the loop flow. If not provided, a unique ID will be generated.
        """
        # TODO(jaalber): do_ should also be able to be list[Flow], or a plain StepT, but the
        # type check / dispatch becomes more complex.
        if while_ is None:
            raise ValueError("LoopFlow must have a while condition.")
        if not StepFlow.check_type(while_):
            raise TypeError("Invalid while condition type")

        self.while_ = while_

        if isinstance(do_, Flow):
            self.steps = do_
        elif isinstance(do_, list):
            first_step = do_[0] if do_ else None
            last_step = do_[-1] if do_ else None

            if first_step is None or last_step is None:
                raise ValueError("LoopFlow must contain at least one step.")

            # TODO(jaalber): The actual type checking logic here
            # ATInFirst, _ = first_step.get_types()
            # if ATInFirst is not TInOut:
            #     raise TypeError(
            #         f"First step of LoopFlow must accept input of type {TInOut}, "
            #         f"but got {ATInFirst}."
            #     )
            # _, ATOutLast = last_step.get_types()

            self.steps = SequenceFlow(do_)

    @property
    def inputs(self) -> list[InputT]:
        """Returns the input nodes of the loop flow."""

        return [_with_condition(input_) for input_ in self.steps.inputs]

    @property
    def outputs(self) -> list[NodeId]:
        """Returns the output nodes of the loop flow."""
        return self.steps.outputs

    def ensure_nodes(self, builder: FlowBuilder) -> list[Tuple[NodeId, bool]]:
        nodes = self.steps.ensure_nodes(builder)

        # If any of the nodes has not been built, then this loop's ensure_nodes has not
        # been called, and we need to attach the edge loop back to itself
        if any([node[1] for node in nodes]):
            builder.bind(self, self)

        return nodes


def case(condition_or_value: StepT[TIn, bool] | TIn) -> StepT[TIn, bool]:
    """Creates a case condition for a switch flow.

    Args:
        condition_or_value (StepT[TIn, bool] | TIn): The condition or value to check.

    Returns:
        StepT[TIn, bool]: A step that checks the condition or value.
    """
    if isinstance(condition_or_value, StepT):
        return condition_or_value

    def _case(input: TIn) -> bool:
        return input == condition_or_value  # Should order be reversed?

    return _case


class SwitchFlow(InFlow[TIn, TOut], OutFlow[TIn, TOut], FlowBase[TIn, TOut]):
    """A class for defining a switch flow in the graph."""

    def __init__(self, branches: dict[StepT[TIn, bool], FlowBase[TIn, TOut]]):
        """Initializes the SwitchFlow with branches.

        Args:
            branches (dict[StepT[TIn, bool], FlowBase[TIn, TOut]]): The branches of the switch.
        """
        # In principle, we could allow branches to have different output types, but that
        # would make the type hints a lot more difficult to build; fine for a prototype, but
        # if we do decide to make this the frontend, we'll want to expand the type system to
        # encompass the full expressiveness that we want to support.
        #
        # The other API change possiblity here is to split out a TInCond, and let the user
        # supply a mapping function from the true input to the condition input:
        #
        # SwitchFlow({
        #    case("foo"): ...
        #    case("bar"): ...
        # }, map = lambda input: input.type)
        #
        if not branches:
            raise ValueError("SwitchFlow must have at least one branch.")

        self.branches = branches

    @property
    def inputs(self) -> list[InputT]:
        return [
            _with_condition(branch_input, condition)
            for condition, branch in self.branches.items()
                for branch_input in branch.inputs
        ]

    @property
    def outputs(self) -> list[NodeId]:
        return [
            output
            for branch in self.branches.values()
                for output in branch.outputs
        ]

    def ensure_nodes(self, builder: FlowBuilder) -> list[Tuple[NodeId, bool]]:
        nodes = []

        for condition, branch in self.branches.items():
            # Ensure the branch nodes are created.
            branch_nodes = branch.ensure_nodes(builder)

            # For each node in the branch, create an edge from the condition to the node.
            for node_id, _ in branch_nodes:
                # Create an edge from the condition to the output node.
                builder.builder.add_edge(condition, node_id, None)
                nodes.append((node_id, True))


class FlowBuilder():
    """A class for building flows in the graph."""

    @staticmethod
    def ensure_flow(
        flowish: InFlowishT[TIn, TInOut] | OutFlowishT[TInOut, TOut],
    ) -> InFlow[TIn, TOut] | OutFlow[TIn, TOut]:
        if isinstance(flowish, (InFlow, OutFlow)):
            return flowish

        if not StepFlow.check_type(flowish):
            raise TypeError(f"Invalid flow type: {type(flowish)}. Expected [In/Out]Flow or StepT.")

        # Since this is definitely a step, wrap it in a StepFlow.
        return StepFlow(flowish)

    def bind(self, incoming: InFlowishT[TIn, TInOut], outgoing: OutFlowishT[TInOut, TOut]) -> None:
        """Binds an incoming flow to an outgoing flow in the graph builder.

        Args:
            builder (FlowBuilder): The flow builder to use for binding.
            incoming (InFlowishT[TIn, TInOut]): The incoming flow or step to bind.
            outgoing (OutFlowishT[TInOut, TOut]): The outgoing flow or step to bind
        """
        # Ensure that both incoming and outgoing are flows
        incoming = cast(InFlow[TIn, TInOut], self.ensure_flow(incoming))
        outgoing = cast(OutFlow[TInOut, TOut], self.ensure_flow(outgoing))

        # Ensure all input and output nodes are materialized in the builder.
        _ = incoming.ensure_nodes(self)
        _ = outgoing.ensure_nodes(self)

        # This is effectively an outer join operation:
        for input_node_id, input_condition in incoming.inputs:
            for output_node_id in outgoing.outputs:
                # Create an edge from the input node to the output node.
                self.builder.add_edge(input_node_id, output_node_id, input_condition)

    def build(self, root: Flow[TInOut, TOut]) -> ExecutableGraph:
        """Builds the graph from the root flow.

        Args:
            root (Flow[TIn, TOut]): The root flow to build the graph from.

        Returns:
            ExecutableGraph: The built executable graph.
        """
        ATIn, _ = root.get_types()

        def _start(input: TInOut) -> TInOut:
            """The start node of the graph."""
            if not isinstance(input, ATIn):
                raise TypeError(f"Input to the graph must be of type {ATIn}, but got {type(input)}.")
            return input

        _start.__annotations__ = {"input": ATIn, "return": TInOut}

        self.
