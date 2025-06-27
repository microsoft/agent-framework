# Copyright (c) Microsoft. All rights reserved.
import ast
import inspect
import uuid
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any, Tuple, TypeVar

import pytest  # noqa: F401

from agent_framework.graph import (
    REJECT_EPSILON,
    EdgeCondition,
    EpsilonAction,
    Executor,
    GraphEdge,
    GraphNode,
    Lowering,
    NodeAction,
    StepPayload,
)

from .test_utils import Assertions, CallTracker


class ParamsBuilder:
    """A builder for constructing a sequence of parameters."""

    def __init__(self):
        """Initialize an empty ParamsBuilder."""
        self.params = []

    def append(self, name: str, type_: type, parameter_kind: inspect._ParameterKind) -> "ParamsBuilder":
        """Append a parameter to the builder."""
        self.params.append(inspect.Parameter(name, parameter_kind, annotation=type_))
        return self

    def __add__(self, other: inspect.Parameter) -> "ParamsBuilder":
        """Add a parameter to the builder."""
        self.params.append(other)
        return self

    def build(self) -> Sequence[inspect.Parameter]:
        """Build and return the parameters as a sequence."""
        return self.params


TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut", covariant=True)
TInOut = TypeVar("TInOut", contravariant=False, covariant=False)


class GraphTestContext:
    """A builder for constructing graph parts with actions and conditions."""

    def __init__(self, reject_epsilon_by_default: bool = True):
        """Initialize the test fixtures."""
        self.action_call_tracker = CallTracker()
        self.condition_call_tracker = CallTracker()
        self.deafult_epsilon_action = REJECT_EPSILON if reject_epsilon_by_default else None

    def check_action_calls(self, ids: int | set[int]) -> bool:
        """Check if the action calls contain the given ids."""
        if isinstance(ids, set):
            return not self.action_call_tracker.calls.issuperset(ids)

        if isinstance(ids, int):
            return ids in self.action_call_tracker

        raise TypeError(f"Expected int or set[int], got {type(ids).__name__}")

    def check_condition_calls(self, ids: int | set[int]) -> bool:
        """Check if the condition calls contain the given ids."""
        if isinstance(ids, set):
            return not self.condition_call_tracker.calls.issuperset(ids)

        if isinstance(ids, int):
            return ids in self.condition_call_tracker

        raise TypeError(f"Expected int or set[int], got {type(ids).__name__}")

    def create_int_action(self, id: int | None = None) -> Tuple[int, NodeAction[int, str]]:
        """Return a sample action function."""

        def default_action(input: int) -> str:
            """Default action function if none is provided."""
            return f"Processed({input})"

        return self.track_action(default_action, id)

    def create_string_action(self, id: int | None = None) -> Tuple[int, NodeAction[str, str]]:
        """Return a sample string action function."""

        def default_action(input: str) -> str:
            """Default action function if none is provided."""
            return f"Processed({input})"

        return self.track_action(default_action, id)

    def track_action(self, action: Callable[[TIn], TOut], id: int | None = None) -> Tuple[int, NodeAction[TIn, TOut]]:
        """Return a sample string to int action function."""
        if action is None:
            raise ValueError("Action cannot be None")

        # Check if the action is already tracked
        if id is not None:
            if action.__call_tracking.get("tracker") != self.action_call_tracker:
                raise ValueError("Action is already tracked with a different tracker")
            if action.__call_tracking.get("id") != id and action.__call_tracking.get("id") is not None:
                raise ValueError(f"Action is already tracked with a different id: {action.__call_tracking['id']}")

            return action.__call_tracking["id"], action

        ATIn, ATOut = Lowering.check_and_extract_types(action)

        call_notifier = self.action_call_tracker.create_notifier(id)

        def action_func(input: TIn) -> TOut:
            call_notifier()
            return action(input)

        # Annotate the action function with the input and output types
        action_func.__annotations__ = {
            "input": ATIn if isinstance(ATIn, type) else ast.literal_eval(ATIn),
            "return": ATOut if isinstance(ATOut, type) else ast.literal_eval(ATOut),
        }
        action_func.__call_tracking = {
            "id": call_notifier.id,
            "tracker": self.action_call_tracker,
        }

        return call_notifier.id, action_func

    def create_string_condition(self, id: int | None = None) -> Tuple[int, EdgeCondition[str]]:
        """Return a sample condition function."""

        def default_validator(input: str) -> bool:
            """Default validator function if none is provided."""
            return input.startswith("valid")

        return self.track_condition(default_validator, id)

    def track_condition(
        self, condition: Callable[[TIn], bool], id: int | None = None
    ) -> Tuple[int, EdgeCondition[TIn]]:
        """Return a sample condition function."""
        if condition is None:
            raise ValueError("Condition cannot be None")

        # Check if the condition is already tracked
        if id is not None:
            if condition.__call_tracking.get("tracker") != self.condition_call_tracker:
                raise ValueError("Condition is already tracked with a different tracker")
            if condition.__call_tracking.get("id") is not None and condition.__call_tracking.get("id") != id:
                raise ValueError(f"Condition is already tracked with a different id: {condition.__call_tracking['id']}")

            return condition.__call_tracking["id"], condition

        ATIn, ATOut = Lowering.check_and_extract_types(condition, expecting=EdgeCondition)
        assert ATOut is bool, "Condition must return a boolean value"  # noqa: S101

        call_notifier = self.condition_call_tracker.create_notifier(id)

        def condition_func(input: TIn) -> bool:
            call_notifier()
            return condition(input)

        # Annotate the condition function with the input and output types
        condition_func.__annotations__ = {
            "input": ATIn.__name__ if isinstance(ATIn, type) else ATIn,
            "return": "bool",
        }
        condition_func.__call_tracking = {
            "id": call_notifier.id,
            "tracker": self.condition_call_tracker,
        }

        return call_notifier.id, condition_func

    def track_node(
        self,
        action: NodeAction[TIn, TOut],
        id: int | None = None,
        *,
        edges: Sequence[GraphEdge[TOut]] | None = None,
        epsilon_action: Callable[[TOut], TOut] | None = None,
    ) -> Tuple[int, GraphNode[TIn, TOut]]:
        """Create a sample graph node with the given edges."""
        if action is None:
            raise ValueError("Action cannot be None.")

        action_id, action = self.track_action(action, id)
        node = GraphNode(
            id=f"N(action_{action_id})",
            action=action,
            edges=edges,
            epsilon_action=epsilon_action if epsilon_action is not None else self.deafult_epsilon_action,
        )

        return action_id, node

    def create_string_node(
        self,
        id: int | None = None,
        *,
        action: NodeAction[str, str] | None = None,
        edges: Sequence[GraphEdge[str]] | None = None,
        epsilon_action: Callable[[str], str] | None = None,
    ) -> Tuple[int, GraphNode[str, str]]:
        """Create a sample graph node with the given edges."""
        action_id, action = self.track_action(id, action) if action is not None else self.create_string_action(id)

        node = GraphNode(
            name=Lowering.lower_name(f"node_{action_id}"),
            action=action,
            edges=edges,
            epsilon_action=epsilon_action if epsilon_action is not None else REJECT_EPSILON,
        )
        return action_id, node

    def track_edge(
        self, target_node: GraphNode[TIn, TOut], id: int | None = None, condition: EdgeCondition[TIn] | None = None
    ) -> Tuple[int, GraphEdge[TIn]]:
        """Create a sample graph edge with the given condition and target node."""
        if target_node is None:
            raise ValueError("Target node cannot be None")

        condition_id, condition = self.track_condition(condition, id)

        edge = GraphEdge(
            condition=condition,
            target=target_node.id,
        )

        return condition_id, edge

    def reset(self, action_invocations: set[int] | None = None, condition_invocations: set[int] | None = None) -> None:
        """Reset the called flags.

        Args:
            action_invocations: Optional set of action invocations to reset. If None, all action invocations are reset.
            condition_invocations: Optional set of condition invocations to reset. If None, all condition invocations
            are reset.
        """
        self.action_call_tracker.reset(action_invocations)
        self.condition_call_tracker.reset(condition_invocations)


class TestLowering:
    """Tests for the Lowering class."""

    def test_name_rountrip(self):
        """Test that name lowering can be reversed."""
        name = str(uuid.uuid4())
        lowered_name = Lowering.lower_name(name)
        restored_name = Lowering.raise_name(lowered_name)

        Assertions.check(restored_name == name, "Restored name should match original name")

    @staticmethod
    def check_lowered_name(actual: str, original_name: str) -> None:
        """Check that the lowered name matches the expected format."""
        Assertions.check(
            actual == Lowering.lower_name(original_name),
            (f"Lowered name {actual} should match the expected lowered name for {original_name}"),
        )

    @staticmethod
    def check_lowered_action(actual: Any, original_action: NodeAction[TIn, TOut]) -> None:
        """Check that the lowered action has the correct annotations."""
        Assertions.check(inspect.isfunction(actual), "Lowered action should be a function")
        Assertions.check_annotations(
            actual,
            params=OrderedDict([("input", StepPayload)]),
            returns=StepPayload,
            is_async=False,
        )

    @staticmethod
    def validate_invocation_result(result: StepPayload, expected_type: type, expected_value: Any):
        """Validate the result of an action invocation."""
        Assertions.check(isinstance(result, StepPayload), "Result should be a StepPayload")
        Assertions.check(result.type_ is expected_type, "Result type should match the expected type")
        Assertions.check(result.value == expected_value, "Result value should match the expected value")

    @staticmethod
    def run_action_invocation_test(
        lowered_action: NodeAction[StepPayload, StepPayload],
        input_value: TIn,
        expected_output: TOut,
        action_id: int,
        test_context: GraphTestContext,
    ) -> None:
        """Run a test for the lowered action invocation."""
        wrapped = StepPayload.wrap(input_value)

        result = lowered_action(wrapped)

        TestLowering.validate_invocation_result(result, type(expected_output), expected_output)
        Assertions.check(test_context.check_action_calls(action_id), "Action function should have been called")

    def test_lower_node_action(self):
        """Test lowering a node with an action."""
        action: NodeAction[int, str]

        test_context = GraphTestContext()
        action_id, action = test_context.create_string_action()

        lowering = Lowering()
        lowered_action = lowering.lower_action(action)

        TestLowering.check_lowered_action(lowered_action, action)
        TestLowering.run_action_invocation_test(
            lowered_action,
            input_value="test",
            expected_output="Processed(test)",
            action_id=action_id,
            test_context=test_context,
        )

    @staticmethod
    def check_lowered_node(actual: Any, original_node: GraphNode[TIn, TOut]) -> None:
        """Check that the node was lowered correctly."""
        Assertions.check(isinstance(actual, GraphNode), "Lowered node should be a GraphNode")
        TestLowering.check_lowered_name(actual.id, original_node.id)
        Assertions.check(actual.action is not None, "Lowered node should have an action")
        TestLowering.check_lowered_action(actual.action, original_node.action)

        if original_node.epsilon_action is not None:
            Assertions.check(actual.epsilon_action is not None, "Lowered node should have an epsilon action")
            TestLowering.check_lowered_epsilon(actual.epsilon_action, original_node.epsilon_action)

    def test_lower_graph_node_action_only(self):
        """Test lowering a graph node with only an action."""
        test_context = GraphTestContext()

        action_id, action = test_context.create_int_action()
        _, node = test_context.track_node(
            id=action_id,
            action=action,
        )

        lowering = Lowering()

        lowered_node = lowering.lower_node(node)

        TestLowering.check_lowered_node(lowered_node, node)
        TestLowering.run_action_invocation_test(
            lowered_node.action,
            input_value=42,
            expected_output="Processed(42)",
            action_id=action_id,
            test_context=test_context,
        )

    @staticmethod
    def check_lowered_epsilon(actual: Any, original_epsilon_action: EpsilonAction[TInOut]) -> None:
        """Check that the epsilon action was lowered correctly."""
        Assertions.check(inspect.isfunction(actual), "Lowered epsilon action should be a function")
        Assertions.check_annotations(
            actual,
            params=OrderedDict([("input", StepPayload), ("node_id", str)]),
            returns=StepPayload,
            is_async=False,
        )

    @staticmethod
    def run_epsilon_invocation_test(
        epsilon_action: EpsilonAction[StepPayload],
        input_value: TInOut,
        expected_output: TInOut,
        node_id: str,
        action_id: int,
        test_context: GraphTestContext,
    ) -> None:
        """Run a test for the epsilon action invocation."""
        wrapped_input = StepPayload.wrap(input_value)

        result = epsilon_action(wrapped_input, node_id)

        TestLowering.validate_invocation_result(result, type(expected_output), expected_output)
        Assertions.check(test_context.check_action_calls(action_id), "Epsilon action should have been called")

    def test_lower_graph_node_with_epsilon(self):
        """Test lowering a graph node with an epsilon action."""
        test_context = GraphTestContext()

        node_action_id, action = test_context.create_int_action()
        epsilon_action_id, string_action = test_context.create_string_action()

        def trackable_epsilon(input: str, node_id: str) -> str:
            """Trackable epsilon action that processes the input."""
            return string_action(f"{node_id}:{input}")

        _, node = test_context.track_node(
            id=node_action_id,
            action=action,
            epsilon_action=trackable_epsilon,
        )

        lowering = Lowering()
        lowered_node = lowering.lower_node(node)

        TestLowering.check_lowered_node(lowered_node, node)
        TestLowering.run_epsilon_invocation_test(
            lowered_node.epsilon_action,
            input_value="test_input",
            expected_output=f"Processed({node.id}:test_input)",
            node_id=lowered_node.id,
            action_id=epsilon_action_id,
            test_context=test_context,
        )

    @staticmethod
    def check_lowered_condition(actual: Any, original_condition: EdgeCondition[TIn]) -> None:
        """Check that the lowered condition has the correct annotations."""
        Assertions.check(inspect.isfunction(actual), "Lowered condition should be a function")
        Assertions.check_annotations(
            actual,
            params=OrderedDict([("input", StepPayload)]),
            returns=bool,
            is_async=False,
        )

    @staticmethod
    def run_condition_invocation_test(
        lowered_condition: EdgeCondition[StepPayload],
        input_value: TIn,
        expected_output: bool,
        condition_id: int,
        test_context: GraphTestContext,
    ) -> None:
        """Run a test for the lowered condition invocation."""
        wrapped = StepPayload.wrap(input_value)
        result = lowered_condition(wrapped)

        Assertions.check(isinstance(result, bool), "Condition result should be a boolean")
        Assertions.check(result == expected_output, f"Condition result should be {expected_output}, got {result}")
        Assertions.check(test_context.check_condition_calls(condition_id), "Condition function should have been called")

    def test_lower_edge_condition(self):
        """Test lowering a graph edge condition."""
        condition: EdgeCondition[str]

        test_context = GraphTestContext()
        condition_id, condition = test_context.create_string_condition()

        lowering = Lowering()

        lowered_condition = lowering.lower_condition(condition)

        TestLowering.check_lowered_condition(lowered_condition, condition)
        TestLowering.run_condition_invocation_test(
            lowered_condition,
            input_value="valid_input",
            expected_output=True,
            condition_id=condition_id,
            test_context=test_context,
        )

    @staticmethod
    def check_lowered_edge(actual: Any, original_edge: GraphEdge[TIn]) -> None:
        """Check that the edge was lowered correctly."""
        Assertions.check(isinstance(actual, GraphEdge), "Lowered edge should be a GraphEdge")
        TestLowering.check_lowered_name(actual.target, original_edge.target)
        TestLowering.check_lowered_condition(actual.condition, original_edge.condition)

    def test_lower_graph_edge(self):
        """Test lowering a graph edge with a condition."""
        test_context = GraphTestContext()

        # Create the target node
        target_action: NodeAction[str, str]
        target_action_id, target_action = test_context.create_string_action()
        _, target_node = test_context.track_node(
            id=target_action_id,
            action=target_action,
        )

        # Create the condition
        condition: EdgeCondition[str]
        condition_id, condition = test_context.create_string_condition()
        _, edge = test_context.track_edge(
            target_node=target_node,
            id=condition_id,
            condition=condition,
        )

        lowering = Lowering()
        lowered_edge = lowering.lower_edge(edge)

        TestLowering.check_lowered_edge(lowered_edge, edge)
        TestLowering.run_condition_invocation_test(
            lowered_edge.condition,
            input_value="valid_input",
            expected_output=True,
            condition_id=condition_id,
            test_context=test_context,
        )

    def test_lower_graph_node_with_loop(self):
        """Test lowering a graph node with a loop condition."""
        test_context = GraphTestContext()

        string_action_id, string_action = test_context.create_string_action()
        condition_id, condition = test_context.create_string_condition()

        # Create the target node
        _, target_node = test_context.track_node(
            id=string_action_id,
            action=string_action,
        )

        # Create the edge with the condition
        _, edge = test_context.track_edge(
            target_node=target_node,
            id=condition_id,
            condition=condition,
        )

        # Patch the edge into the target node
        target_node.edges = [edge]

        lowering = Lowering()
        lowered_node = lowering.lower_node(target_node)

        TestLowering.check_lowered_node(lowered_node, target_node)
        TestLowering.run_action_invocation_test(
            lowered_node.action,
            input_value="valid_input",
            expected_output="Processed(valid_input)",
            action_id=string_action_id,
            test_context=test_context,
        )

        TestLowering.run_condition_invocation_test(
            lowered_node.edges[0].condition,
            input_value="Processed(valid_input)",
            expected_output=False,
            condition_id=condition_id,
            test_context=test_context,
        )


class TestExecution:
    """Tests for the execution of graphs with nodes and actions."""

    def test_single_node_execution(self):
        """Test execution of a single node with an action."""
        test_context = GraphTestContext(
            reject_epsilon_by_default=False  # allow graphs to terminate without explicitly clearing epsilon actions
        )

        action_id, action = test_context.create_string_action()
        _, node = test_context.track_node(id=action_id, action=action, epsilon_action=None)

        lowering = Lowering()
        graph = lowering.lower_graph(nodes=[node], start_name=node.id, output_node_name=node.id)

        # Execute the graph
        executor = Executor(graph)
        input_value = StepPayload.wrap("test_input")
        result = executor.run(input_value)

        TestLowering.validate_invocation_result(result, str, "Processed(test_input)")

        result = executor.run("test_input")
        Assertions.check(isinstance(result, str), "Result should be unrapped if input is passed unwrapped")
        Assertions.check(result == "Processed(test_input)", "Result should match the expected output")

    def test_single_transition_execution(self):
        """Test execution of a graph with two nodes and a single successful transition between them."""
        # A(int) => "Processed({input})"
        # B(str) => "Processed({input})"
        #  expected ouptut: # "Processed(Processed({input}))"
        test_context = GraphTestContext(reject_epsilon_by_default=False)

        action_a_id, action_a = test_context.create_int_action()
        action_b_id, action_b = test_context.create_string_action()

        def condition_func(input: str) -> bool:
            """A simple condition testing that we have a number inside of Processed()."""
            import re

            return bool(re.match(r"Processed\(\d+\)", input))

        _, condition = test_context.track_condition(
            condition=condition_func,
        )

        _, input_node = test_context.track_node(id=action_a_id, action=action_a, epsilon_action=REJECT_EPSILON)
        _, output_node = test_context.track_node(
            id=action_b_id,
            action=action_b,
        )
        _, edge = test_context.track_edge(
            target_node=output_node,
            condition=condition,
        )
        input_node.edges = [edge]

        lowering = Lowering()
        graph = lowering.lower_graph(
            nodes=[input_node, output_node],
            start_name=input_node.id,
            output_node_name=output_node.id,
        )

        # Execute the graph
        executor = Executor(graph)
        input_value = StepPayload.wrap(42)
        result = executor.run(input_value)

        TestLowering.validate_invocation_result(result, str, "Processed(Processed(42))")
