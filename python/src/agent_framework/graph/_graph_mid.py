# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, Callable, Generic, Protocol, Tuple, TypeVar, runtime_checkable

from agent_framework.graph import ExecutableGraph, GraphEdge, GraphNode, Lowering, NodeAction

TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut", covariant=True)


@runtime_checkable
class RunnableStep(Protocol, Generic[TIn, TOut]):
    def run(self, input: TIn, *args, **kwargs) -> TOut:
        """Defines the action to be performed by the step."""
        ...


@runtime_checkable
class Identified(Protocol):
    @property
    def id(self) -> str:
        """Returns the ID."""
        ...


RunnableCallableT = Callable[[TIn], TOut]
StepT = RunnableStep[TIn, TOut] | RunnableCallableT[TIn, TOut]


def runnable(step: StepT[TIn, TOut], id: str | None = None) -> RunnableStep[TIn, TOut]:
    class RunnableStepAdapter(RunnableStep[TIn, TOut], Identified):
        def __init__(self, step: StepT[TIn, TOut], id: str | None = None):
            self._runnable_step: RunnableStep[TIn, TOut] | None = None
            self._callable_step: RunnableCallableT[TIn, TOut] | None = None

            if isinstance(step, RunnableStep):
                self._runnable_step = step
                self.id = step.id if isinstance(step, Identified) else id or step.__class__.__name__
            elif callable(step):
                self._callable_step = step
                self.id = step.id if isinstance(step, Identified) else id or step.__name__
            else:
                raise TypeError(f"Unsupported step type: {type(step)}. Expected RunnableStep or Callable.")

            if id is None:
                raise ValueError("ID must be provided for the step or the step must be Identified.")

            if self._runnable_step is None and self._callable_step is None:
                # This should never happen due to the type check above.
                raise ValueError("Step must be either a RunnableStep or a Callable.")

        def run(self, input: TIn, *args, **kwargs) -> TOut:
            if self._runnable_step is not None:
                # If the step is a RunnableStep, call its run method.
                return self._runnable_step.run(input, *args, **kwargs)

            if self._callable_step is not None:
                # If the step is a callable, call it directly.
                return self._callable_step(input, *args, **kwargs)

            raise RuntimeError("This should never happen: step is neither RunnableStep nor Callable.")

        @property
        def id(self) -> str:
            return self._id if self._id is not None else "unnamed_step"

    if isinstance(step, RunnableStep) and isinstance(step, Identified):
        # If the step is already a RunnableStep and Identified, return it directly.
        return step

    return RunnableStepAdapter(step, id)


class GraphBuilder(Generic[TIn]):
    def __init__(self):
        self.nodes_map: dict[str, GraphNode] = {}
        self.start_node: GraphNode | None = None
        self.missing_agents: set[str] = set()

    @staticmethod
    def start(target: StepT[TIn, TOut]) -> "GraphBuilder[TIn, TOut]":
        """Creates a new GraphBuilder instance with the specified start node."""
        builder = GraphBuilder()
        builder.start_node, _ = builder.ensure_node(target)
        return builder

    @staticmethod
    def create_action(target: StepT[TIn, TOut]) -> NodeAction[TIn, TOut]:
        """Creates an action function for the node based on the target."""
        if isinstance(target, RunnableStep):
            return target.run

        if callable(target):
            return target

        raise TypeError(f"Unsupported target type: {type(target)}. Expected RunnableStep or Callable.")

    @property
    def start_name(self) -> str:
        """Returns the name of the start node."""
        return self.start_node.id

    @staticmethod
    def extract_name(step: StepT[TIn, TOut] | str) -> str:
        """Extracts the name from the step or string."""
        if isinstance(step, str):
            return step

        if isinstance(step, Identified):
            return step.id

        return step.__name__ if callable(step) else step.__class__.__name__

    def ensure_node(self, step: StepT[TIn, TOut] | str) -> Tuple[GraphNode[TIn, TOut], bool]:
        id: str = self.extract_name(step)

        created = False
        if id not in self.nodes_map:
            self.nodes_map[id] = GraphNode(
                id,
                action=self.create_action(step),
                edges=[],
                # epsilon_action=REJECT_EPSILON,  # noqa: ERA001
            )

            created = True
            if isinstance(step, str):
                self.missing_agents.add(id)

        return self.nodes_map[id], created

    def add_edge(
        self,
        source: StepT[TIn, TOut] | str | GraphNode[TIn, TOut],
        target: StepT[TOut, Any] | str | GraphNode[TOut, Any],
        condition: str | Callable[[TIn], bool] | None = None,
    ) -> "GraphBuilder[TIn]":
        source_node, _ = self.ensure_node(source)
        target_node, _ = self.ensure_node(target)

        edge: GraphEdge[TOut] = GraphEdge(target=target_node.id, condition=condition)
        # if source_node.edges is None:
        #     source_node.edges = []  # noqa: ERA001

        source_node.edges.append(edge)

        return self

    def set_node(self, target: StepT[TIn, TOut]) -> GraphNode[TIn, TOut]:
        """For late-binding an agent to a node."""
        node, _ = self.ensure_node(target)

        node.action = GraphBuilder.create_action(target)

        return node

    def override_epsilon(self, target: StepT[TIn, TOut] | str, epsilon_handler: NodeAction[TOut, TOut]) -> None:
        """Overrides the epsilon handler for a specific node."""
        node, _ = self.ensure_node(target)

        node.epsilon_action = epsilon_handler

    def build(
        self,
        *,
        ignore_missing: bool = False,
        ignore_orphans: bool = False,
        strict_typing: bool = True,
        output_node: str | None = None,
    ) -> ExecutableGraph:
        if not ignore_missing and self.missing_agents:
            raise ValueError(f"Missing agents for nodes: {', '.join(self.missing_agents)}")

        if not ignore_orphans:
            seen_nodes = set()
            undiscovered_edges = set(self.nodes_map.keys()) - {self.start_node.id}
            exploring_edges = {self.start_node.id}

            while exploring_edges:
                next_edges = set()
                for node_name in exploring_edges:
                    if node_name in seen_nodes:
                        continue

                    seen_nodes.add(node_name)
                    node = self.nodes_map[node_name]
                    if node.edges:
                        next_edges.update(edge.target for edge in node.edges)

                undiscovered_edges -= next_edges
                exploring_edges = next_edges

            if undiscovered_edges:
                raise ValueError(f"Orphan nodes found: {', '.join(undiscovered_edges)}")

        if output_node is not None:
            if output_node not in self.nodes_map:
                raise ValueError(f"Output node '{output_node}' not found in the graph.")

            output_node_instance = self.nodes_map.get(output_node)
            output_node_instance.epsilon_action = None  # Output actions are allowed to be terminal

        lowering = Lowering(strict_typing=strict_typing)
        return lowering.lower_graph(self.nodes_map, self.start_node.id, output_node_name=output_node)
