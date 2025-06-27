# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

import ast
import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Protocol, TypeVar, cast, get_type_hints

from . import EdgeCondition, EpsilonAction, GraphEdge, GraphNode, NodeAction

DEFAULT_START_NAME = "_START_"


TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut", covariant=True)
TInOut = TypeVar("TInOut", contravariant=False, covariant=False)


@dataclass(init=False, slots=True)
class StepPayload:
    type_: type
    value: Any

    def __init__(self, type_: type, value: Any):
        if not isinstance(value, type_):
            raise TypeError(f"Expected value of type {type_.__name__}, got {type(value).__name__}")
        self.type_ = type_
        self.value = value

    @staticmethod
    def wrap(value: Any) -> StepPayload:
        """Wraps a value in a StepPayload."""
        return StepPayload(type(value), value)


ExecutableNode = GraphNode[StepPayload, StepPayload]
ExecutableEdge = GraphEdge[StepPayload]
ExecutableNodeAction = NodeAction[StepPayload, StepPayload]
ExecutableEdgeCondition = EdgeCondition[StepPayload]


class LowerableKind(enum.Enum):
    """Enum to represent the kind of object being lowered."""

    NODE = "node"
    EDGE = "edge"
    ACTION = "action"
    CONDITION = "condition"
    EPSILON = "epsilon_action"


@dataclass
class LoweringContext:
    lowered_item_map: dict[LowerableKind, dict[int, Any]] = field(default_factory=dict)

    def ensure_maps(self, kind: LowerableKind):
        """Ensures that the maps for the given kind are initialized."""
        if kind not in self.lowered_item_map:
            self.lowered_item_map[kind] = {}

    @property
    def lowered_actions(self) -> dict[int, ExecutableNodeAction]:
        """Returns the map of lowered actions."""
        self.ensure_maps(LowerableKind.ACTION)
        return cast(dict[int, ExecutableNodeAction], self.lowered_item_map[LowerableKind.ACTION])

    @property
    def lowered_edges(self) -> dict[int, ExecutableEdge]:
        """Returns the map of lowered edges."""
        self.ensure_maps(LowerableKind.EDGE)
        return cast(dict[int, ExecutableEdge], self.lowered_item_map[LowerableKind.EDGE])

    @property
    def lowered_nodes(self) -> dict[int, ExecutableNode]:
        """Returns the map of lowered nodes."""
        self.ensure_maps(LowerableKind.NODE)
        return cast(dict[int, ExecutableNode], self.lowered_item_map[LowerableKind.NODE])

    @property
    def lowered_conditions(self) -> dict[int, ExecutableEdgeCondition]:
        """Returns the map of lowered conditions."""
        self.ensure_maps(LowerableKind.CONDITION)
        return cast(
            dict[int, ExecutableEdgeCondition],
            self.lowered_item_map[LowerableKind.CONDITION],
        )

    @property
    def lowered_epsilon_actions(self) -> dict[int, EpsilonAction[StepPayload]]:
        """Returns the map of lowered epsilon actions."""
        self.ensure_maps(LowerableKind.EPSILON)
        return cast(
            dict[int, EpsilonAction[StepPayload]],
            self.lowered_item_map[LowerableKind.EPSILON],
        )


@dataclass
class ExecutableGraph:
    nodes: dict[str, ExecutableNode]
    start_loname: str
    input_type: type
    output_loname: str | None = None
    output_type: type | None = None


class Lowering:
    def __init__(self, strict_typing: bool = True):
        self.strict_typing = strict_typing

    @staticmethod
    def lower_name(name: str) -> str:
        """Lower a name to a valid identifier."""
        if not isinstance(name, str):
            raise TypeError(f"Expected name to be a string, got {type(name)}")

        return f"_l({name})"

    @staticmethod
    def raise_name(loname: str) -> str:
        """Raise a lowered name to its original identifier."""
        if not isinstance(loname, str):
            raise TypeError(f"Expected loname to be a string, got {type(loname)}")

        if not loname.startswith("_l(") or not loname.endswith(")"):
            raise ValueError(f"Invalid lowered name format: {loname}")

        return loname[3:-1]

    @staticmethod
    def check_and_extract_types(
        action_or_condition: NodeAction[TIn, TOut] | EdgeCondition[TIn] | EpsilonAction[TInOut],
        expecting: type | None = None,
    ) -> tuple[type, type]:
        if expecting is not None and not isinstance(expecting, type):
            raise TypeError(
                f"Expected incoming object to be of type '{expecting.__name__}', got {type(expecting).__name__}"
            )

        if not callable(action_or_condition):
            raise TypeError(f"Expected a callable, got {type(action_or_condition).__name__}")

        annotations = get_type_hints(action_or_condition)
        if len(annotations) not in (2, 3) or "input" not in annotations or "return" not in annotations:
            raise TypeError(f"{expecting.__name__} must have 'input' and 'return' annotations.")

        input_type = annotations["input"]
        if isinstance(input_type, str):
            input_type: type = ast.literal_eval(input_type)

        output_type = annotations["return"]
        if isinstance(output_type, str):
            output_type: type = ast.literal_eval(output_type)

        return input_type, output_type

    def lower_epsilon_action(self, action: EpsilonAction[TInOut], **kwargs) -> EpsilonAction[StepPayload]:
        context: LoweringContext = kwargs.get("context", LoweringContext())

        if id(action) in context.lowered_epsilon_actions:
            return context.lowered_epsilon_actions[id(action)]

        input_type, output_type = Lowering.check_and_extract_types(action, expecting=EpsilonAction)
        assert input_type == output_type, "Epsilon action input and output types must match."  # noqa: S101

        def wrapped_action(input: StepPayload, node_id: str) -> StepPayload:
            unwrapped = input.value
            if self.strict_typing and not isinstance(unwrapped, input_type):
                raise TypeError(f"Expected input of type {input_type.__name__}, got {type(unwrapped).__name__}")

            node_id = self.raise_name(node_id)
            output = action(unwrapped, node_id)

            if self.strict_typing and not isinstance(output, output_type):
                raise TypeError(f"Expected output of type {output_type.__name__}, got {type(output).__name__}")

            return StepPayload.wrap(output)

        context.lowered_epsilon_actions[id(action)] = wrapped_action
        return wrapped_action

    def lower_action(self, action: NodeAction[TIn, TOut], **kwargs) -> ExecutableNodeAction:
        context: LoweringContext = kwargs.get("context", LoweringContext())

        if id(action) in context.lowered_actions:
            return context.lowered_actions[id(action)]

        input_type, output_type = Lowering.check_and_extract_types(action, expecting=NodeAction)

        def wrapped_action(input: StepPayload) -> StepPayload:
            unwrapped = input.value
            if self.strict_typing and not isinstance(unwrapped, input_type):
                raise TypeError(f"Expected input of type {input_type.__name__}, got {type(unwrapped).__name__}")

            output = action(unwrapped)

            if self.strict_typing and not isinstance(output, output_type):
                raise TypeError(f"Expected output of type {output_type.__name__}, got {type(output).__name__}")

            return StepPayload.wrap(output)

        context.lowered_actions[id(action)] = wrapped_action
        return wrapped_action

    def lower_condition(self, condition: EdgeCondition[TIn, TOut], **kwargs) -> ExecutableEdgeCondition:
        context: LoweringContext = kwargs.get("context", LoweringContext())

        if id(condition) in context.lowered_conditions:
            return context.lowered_conditions[id(condition)]

        input_type, output_type = Lowering.check_and_extract_types(condition, expecting=EdgeCondition)
        if output_type is not bool:
            raise TypeError(f"Expected output type of condition to be bool, got {output_type.__name__}")

        def wrapped_condition(input: StepPayload) -> bool:
            unwrapped = input.value
            if self.strict_typing and not isinstance(unwrapped, input_type):
                raise TypeError(f"Expected input of type {input_type.__name__}, got {type(unwrapped).__name__}")

            # Do not wrap the resulting bool back - since this is known to be a condition, it is always a bool
            # No need to type-erase it.
            return condition(unwrapped)

        context.lowered_conditions[id(condition)] = wrapped_condition
        return wrapped_condition

    def lower_node(self, node: GraphNode[TIn, TOut], **kwargs) -> ExecutableNode:
        """Lower a GraphNode to an ExecutableNode."""
        context: LoweringContext = kwargs.get("context", LoweringContext())
        if id(node) in context.lowered_nodes:
            return context.lowered_nodes[id(node)]

        lowered_id = self.lower_name(node.id)
        lowered_action = self.lower_action(node.action, context=context)
        lowered_epsilon_action = (
            None if node.epsilon_action is None else self.lower_epsilon_action(node.epsilon_action, context=context)
        )

        result = ExecutableNode(id=lowered_id, action=lowered_action, epsilon_action=lowered_epsilon_action)
        context.lowered_nodes[id(node)] = result

        # Lower the edges after caching the node, that way we can reference it if there is a loop in the graph.
        lowered_edges = None if node.edges is None else [self.lower_edge(edge, context=context) for edge in node.edges]
        result.edges = lowered_edges

        context.lowered_nodes[id(node)] = result
        return result

    def lower_edge(self, edge: GraphEdge[TIn, TOut], **kwargs) -> ExecutableEdge:
        """Lower a GraphEdge to an ExecutableEdge."""
        context: LoweringContext = kwargs.get("context", LoweringContext())
        if id(edge) in context.lowered_edges:
            return context.lowered_edges[id(edge)]

        target_loname = self.lower_name(edge.target)
        lowered_condition = self.lower_condition(edge.condition, context=context) if edge.condition else None

        result = ExecutableEdge(target=target_loname, condition=lowered_condition)

        context.lowered_edges[id(edge)] = result
        return result

    def _lower_graph_nodes_dict(
        self, nodes: dict[str, GraphNode[TIn, TOut]], context: LoweringContext
    ) -> dict[str, ExecutableNode]:
        """Lower a dictionary of GraphNodes to ExecutableNodes."""

        def check_and_lower_name(name: str, node: GraphNode[TIn, TOut]) -> str:
            if node.id != name:
                raise ValueError(f"Node ID '{node.id}' does not match the provided name '{name}'.")

            return self.lower_name(name)

        return {
            check_and_lower_name(name, node): self.lower_node(node, context=context) for name, node in nodes.items()
        }

    def _lower_graph_nodes_list(
        self, nodes: list[GraphNode[TIn, TOut]], context: LoweringContext
    ) -> dict[str, ExecutableNode]:
        """Lower a list of GraphNodes to ExecutableNodes."""
        return {self.lower_name(node.id): self.lower_node(node, context=context) for node in nodes}

    def lower_graph(
        self,
        nodes: list[GraphNode[TIn, TOut]] | dict[str, GraphNode[TIn, TOut]],
        start_name: str = DEFAULT_START_NAME,
        output_node_name: str | None = None,
    ) -> ExecutableGraph:
        context = LoweringContext()

        start_node: GraphNode[TIn, TOut]
        lowered_nodes: dict[str, ExecutableNode]
        input_type: type

        if isinstance(nodes, dict):
            lowered_nodes = self._lower_graph_nodes_dict(nodes, context=context)
            start_node = nodes.get(start_name, None)
            output_node = nodes.get(output_node_name, None) if output_node_name else None

        elif isinstance(nodes, list):
            lowered_nodes = self._lower_graph_nodes_list(nodes, context=context)
            start_node = next((node for node in nodes if node.id == start_name), None)
            output_node = (
                next((node for node in nodes if node.id == output_node_name), None) if output_node_name else None
            )

        output_type = None
        if output_node is not None:
            _, output_type = self.check_and_extract_types(output_node.action, expecting=NodeAction)

        if start_node is None:
            raise ValueError(f"Start node '{start_name}' not found in the provided nodes.")

        lowered_start_name = self.lower_name(start_name)
        lowered_output_name = self.lower_name(output_node_name) if output_node_name else None
        input_type, _ = self.check_and_extract_types(start_node.action, expecting=NodeAction)

        return ExecutableGraph(
            nodes=lowered_nodes,
            start_loname=lowered_start_name,
            input_type=input_type,
            output_loname=lowered_output_name,
            output_type=output_type,
        )


@dataclass
class EpsilonInfo:
    initial_value: Any


@dataclass
class ExecutionStep(Generic[TIn, TOut]):
    id: str
    path: list[int]
    target: GraphNode[TIn, TOut]
    input: TIn  # needed?
    output: TOut
    exits: list[ExecutionTransition] | None = None
    epsilon: EpsilonInfo | None = None

    @property
    def is_epsilon(self) -> bool:
        """Checks if the step is an epsilon step."""
        return self.epsilon is not None


@dataclass
class ExecutionTransition:
    value: StepPayload
    edge: ExecutableEdge
    target: ExecutableNode


RleTuple = tuple[int, int]


class GraphTracer(Protocol):
    def trace_step(self, step: ExecutionStep) -> None:
        """Records the execution of a step."""
        ...

    def trace_arc(self, base_step: ExecutionStep, transition: ExecutionTransition) -> None:
        """Records the execution of an arc."""
        ...


class LogTracer(GraphTracer):
    def __init__(self, logger_callback: Callable[[str], None], raise_names: bool = False):
        self.logger_callback = logger_callback
        self.raise_names = raise_names

    def format_step(self, step: ExecutionStep) -> str:
        id = step.target.id if not self.raise_names else Lowering.raise_name(step.target.id)

        return f"s[{id}]::({step.input}) -> {step.output}"

    def format_transition(self, transition: ExecutionTransition) -> str:
        id = transition.edge.target if not self.raise_names else Lowering.raise_name(transition.edge.target)

        return f"t[{id}]::({transition.value.value}) -> {transition.target.id}"

    def trace_step(self, step: ExecutionStep) -> None:
        """Calls the step callback."""
        self.logger_callback(self.format_step(step))

    def trace_arc(self, base_step: ExecutionStep, transition: ExecutionTransition) -> None:
        """Calls the arc callback."""
        self.logger_callback(self.format_transition(transition))


@dataclass
class ExecutionContext:
    incoming_path: list[int | RleTuple]
    graph_tracer: GraphTracer | None = None

    def extend(self, step_index: int) -> ExecutionContext:
        if len(self.incoming_path) == 0:
            return ExecutionContext(incoming_path=[step_index], graph_tracer=self.graph_tracer)

        new_path = self.incoming_path.copy()
        last_step = new_path[-1]

        if isinstance(last_step, int):
            if last_step == step_index:
                new_path[-1] = (last_step, 2)
            else:
                new_path.append(step_index)
        elif isinstance(last_step, tuple):
            if last_step[0] == step_index:
                new_path[-1] = (last_step[0], last_step[1] + 1)
            else:
                new_path.append(step_index)
        else:
            raise ValueError(
                f"Invalid last step in path: {last_step}. Expected int or RleTuple, got {type(last_step)}."
            )

        return ExecutionContext(incoming_path=new_path, graph_tracer=self.graph_tracer)

    @property
    def path(self) -> str:
        def _str(item: int | RleTuple) -> str:
            if isinstance(item, int):
                return str(item)

            if isinstance(item, tuple):
                return f"{item[0]}*{item[1]}"

            raise TypeError(f"Unsupported type in path: {type(item)}")

        return str.join("/", map(_str, self.incoming_path))

    def trace_step(self, step: ExecutionStep) -> None:
        if self.graph_tracer:
            self.graph_tracer.trace_step(step)

    def trace_arc(self, base_step: ExecutionStep, transition: ExecutionTransition) -> None:
        if self.graph_tracer:
            self.graph_tracer.trace_arc(base_step, transition)


@dataclass
class ExecutionFrame:
    input: StepPayload
    target: ExecutableNode
    context: ExecutionContext

    def __call__(self) -> TransitionFrame:
        """Executes the node action and returns an ExecutionStep."""
        output = self.target.action(self.input)
        if not isinstance(output, StepPayload):
            raise TypeError(f"Expected output of type StepPayload, got {type(output).__name__}")

        return TransitionFrame(execution=self, output=output)


@dataclass
class TransitionFrame:
    execution: ExecutionFrame
    output: StepPayload

    @property
    def source(self) -> ExecutableNode:
        """Returns the source node of the transition."""
        return self.execution.target

    def _match_outgoing_edges(self, output: StepPayload) -> list[ExecutableEdge] | None:
        if self.source.edges is None:
            return None

        return [edge for edge in self.source.edges if edge.handles(output)]

    def __call__(self, node_map: dict[str, ExecutableNode]) -> ExecutionStep:
        """Matches the outgoing transitions against the output, and returns the matching transitions or EpsilonInfo."""
        epsilon_info: EpsilonInfo | None = None
        matching_edges = self._match_outgoing_edges(self.output)

        terminal_step = False
        if not matching_edges:
            if self.source.epsilon_action is None:
                # If no edges match and no epsilon action is defined, we have no further progress in this step.
                terminal_step = True
            else:
                # Nodes with an epsilon action cannot be terminal, as they either produce a transition or raise an error
                epsilon_info = EpsilonInfo(initial_value=self.output)
                last_value = self.output

                try:
                    while not matching_edges:
                        epsilon_output = self.source.epsilon_action(last_value, self.source.id)
                        if epsilon_output.value == last_value.value or id(epsilon_output.value) == id(last_value.value):
                            # If the output hasn't changed, we are in an infinite loop.
                            raise ValueError(
                                f"Epsilon action for node {self.source.id} produced no change in output: {last_value}"
                            )

                        matching_edges = self._match_outgoing_edges(epsilon_output)
                except:
                    raise

        # If we got here, we have matching edges, and optionally epsilon_info.
        transitions: list[ExecutionTransition] = [
            ExecutionTransition(value=self.output, edge=edge, target=node_map[edge.target])
            for edge in matching_edges or []
        ]

        if not transitions and not terminal_step:
            raise ValueError(f"No valid transitions found for output: {self.output.value} in node {self.source.id}")

        return ExecutionStep(
            id=str(self.execution.context.path),
            path=self.execution.context.incoming_path,
            target=self.source,
            input=self.execution.input.value,
            output=self.output,
            exits=transitions,
            epsilon=epsilon_info,
        )


class Executor:
    """Executes an ExecutableGraph with a given input (reference impl - real executor logic TBD)."""

    def __init__(self, graph: ExecutableGraph, tracer: GraphTracer | None = None):
        self.graph = graph
        self.tracer = tracer

    def run(self, input: Any) -> Any:
        unwrap = False
        if not isinstance(input, StepPayload):
            if not isinstance(input, self.graph.input_type):
                raise TypeError(f"Expected input of type {self.graph.input_type.__name__}, got {type(input).__name__}")

            unwrap = True
            input_payload = StepPayload.wrap(input)
        elif isinstance(input, StepPayload):
            if not isinstance(input.value, self.graph.input_type):
                raise TypeError(f"Expected input of type {self.graph.input_type.__name__}, got {input.type_.__name__}")

            input_payload = input

        execution_context = ExecutionContext(incoming_path=[], graph_tracer=self.tracer)
        start_node: ExecutableNode = self.graph.nodes.get(self.graph.start_loname, None)
        if start_node is None:
            raise ValueError(f"Start node '{self.graph.start_loname}' not found in the graph.")

        next_frames: list[list[ExecutionFrame]] = [
            [ExecutionFrame(input=input_payload, target=start_node, context=execution_context)]
        ]

        outputs: list[StepPayload] = []
        while next_frames:
            queued_frames = next_frames.pop(0)

            if not queued_frames:
                continue

            incoming_frames = []

            for idx, frame in enumerate(queued_frames):
                exec_frame: ExecutionFrame = cast(ExecutionFrame, frame)
                execution_context = exec_frame.context.extend(idx)
                transition_frame: TransitionFrame = exec_frame()

                step = transition_frame(self.graph.nodes)

                execution_context.trace_step(step)
                if step.is_epsilon:
                    # TODO(J.A.[@lokitoth]): Trace the epsilon invocation(s).
                    if step.exits is not None and len(step.exits) == 0:
                        # We should have raised an error if no exits were found.
                        raise ValueError("No valid transitions found for epsilon step.")
                elif step.target.id == self.graph.output_loname:
                    outputs.append(step.output)

                for transition in step.exits:
                    execution_context.trace_arc(step, transition)

                    next_frame = ExecutionFrame(
                        input=transition.value, target=transition.target, context=execution_context
                    )
                    incoming_frames.append(next_frame)

            next_frames.append(incoming_frames)

        # If we reach here, we have executed all frames.
        if self.graph.output_loname is None:
            return None

        # not yet implemented
        if len(outputs) == 0:
            return None

        if len(outputs) == 1:
            return outputs[0].value if unwrap else outputs[0]

        return [output.value for output in outputs] if unwrap else outputs
