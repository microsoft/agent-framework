# Copyright (c) Microsoft. All rights reserved.

import inspect
import logging
from collections import defaultdict
from collections.abc import Sequence
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin

from ._edge import Edge, EdgeGroup, FanInEdgeGroup
from ._executor import Executor

logger = logging.getLogger(__name__)


def _is_type_like(x: Any) -> bool:
    """Check if a value is a type-like entity.

    A "type-like" entry is either a class/type or a typing alias
    (e.g., list[str] has an origin and args).

    Args:
        x: The value to check

    Returns:
        True if the value is type-like, False otherwise
    """
    return isinstance(x, type) or get_origin(x) is not None


# region Enums and Base Classes
class ValidationTypeEnum(Enum):
    """Enumeration of workflow validation types."""

    EDGE_DUPLICATION = "EDGE_DUPLICATION"
    TYPE_COMPATIBILITY = "TYPE_COMPATIBILITY"
    GRAPH_CONNECTIVITY = "GRAPH_CONNECTIVITY"
    HANDLER_OUTPUT_ANNOTATION = "HANDLER_OUTPUT_ANNOTATION"
    INTERCEPTOR_CONFLICT = "INTERCEPTOR_CONFLICT"


class WorkflowValidationError(Exception):
    """Base exception for workflow validation errors."""

    def __init__(self, message: str, validation_type: ValidationTypeEnum):
        super().__init__(message)
        self.message = message
        self.validation_type = validation_type

    def __str__(self) -> str:
        return f"[{self.validation_type.value}] {self.message}"


class EdgeDuplicationError(WorkflowValidationError):
    """Exception raised when duplicate edges are detected in the workflow."""

    def __init__(self, edge_id: str):
        super().__init__(
            message=f"Duplicate edge detected: {edge_id}. Each edge in the workflow must be unique.",
            validation_type=ValidationTypeEnum.EDGE_DUPLICATION,
        )
        self.edge_id = edge_id


class TypeCompatibilityError(WorkflowValidationError):
    """Exception raised when type incompatibility is detected between connected executors."""

    def __init__(
        self,
        source_executor_id: str,
        target_executor_id: str,
        source_types: list[type[Any]],
        target_types: list[type[Any]],
    ):
        # Use a placeholder for incompatible types - will be computed in WorkflowGraphValidator
        super().__init__(
            message=f"Type incompatibility between executors '{source_executor_id}' -> '{target_executor_id}'. "
            f"Source executor outputs types {[str(t) for t in source_types]} but target executor "
            f"can only handle types {[str(t) for t in target_types]}.",
            validation_type=ValidationTypeEnum.TYPE_COMPATIBILITY,
        )
        self.source_executor_id = source_executor_id
        self.target_executor_id = target_executor_id
        self.source_types = source_types
        self.target_types = target_types


class GraphConnectivityError(WorkflowValidationError):
    """Exception raised when graph connectivity issues are detected."""

    def __init__(self, message: str):
        super().__init__(message, validation_type=ValidationTypeEnum.GRAPH_CONNECTIVITY)


class HandlerOutputAnnotationError(WorkflowValidationError):
    """Exception raised when a handler's WorkflowContext output annotation is invalid or missing."""

    def __init__(self, executor_id: str, handler_name: str, reason: str):
        super().__init__(
            message=(
                "Invalid WorkflowContext output annotation in handler "
                f"'{handler_name}' of executor '{executor_id}': {reason}. "
                "Handlers must annotate their third parameter as WorkflowContext[T]. "
                "Use WorkflowContext[None] if the handler emits no messages."
            ),
            validation_type=ValidationTypeEnum.HANDLER_OUTPUT_ANNOTATION,
        )
        self.executor_id = executor_id
        self.handler_name = handler_name


class InterceptorConflictError(WorkflowValidationError):
    """Exception raised when multiple executors intercept the same request type from the same sub-workflow."""

    def __init__(self, message: str):
        super().__init__(message, validation_type=ValidationTypeEnum.INTERCEPTOR_CONFLICT)


# endregion


# region Workflow Graph Validator
class WorkflowGraphValidator:
    """Validator for workflow graphs.

    This validator performs multiple validation checks:
    1. Edge duplication validation
    2. Type compatibility validation between connected executors
    3. Graph connectivity validation
    """

    def __init__(self) -> None:
        self._edges: list[Edge] = []
        self._executors: dict[str, Executor] = {}

    # region Core Validation Methods
    def validate_workflow(
        self, edge_groups: Sequence[EdgeGroup], executors: dict[str, Executor], start_executor: Executor | str
    ) -> None:
        """Validate the entire workflow graph.

        Args:
            edge_groups: list of edge groups in the workflow
            executors: Map of executor IDs to executor instances
            start_executor: The starting executor (can be instance or ID)

        Raises:
            WorkflowValidationError: If any validation fails
        """
        self._executors = executors
        self._edges = [edge for group in edge_groups for edge in group.edges]
        self._edge_groups = edge_groups

        # If only the start executor exists, add it to the executor map
        # Handle the special case where the workflow consists of only a single executor and no edges.
        # In this scenario, the executor map will be empty because there are no edge groups to reference executors.
        # Adding the start executor to the map ensures that single-executor workflows (without any edges) are supported,
        # allowing validation and execution to proceed for workflows that do not require inter-executor communication.
        if not self._executors and start_executor and isinstance(start_executor, Executor):
            self._executors[start_executor.id] = start_executor

        # Validate that start_executor exists in the graph
        # It should because we check for it in the WorkflowBuilder
        # but we do it here for completeness.
        start_executor_id = start_executor.id if isinstance(start_executor, Executor) else start_executor
        if start_executor_id not in self._executors:
            raise GraphConnectivityError(f"Start executor '{start_executor_id}' is not present in the workflow graph")

        # Additional presence verification:
        # A start executor that is only injected via the builder (present in the executors map)
        # but not referenced by any edge while other executors ARE referenced indicates a
        # configuration error: the chosen start node is effectively disconnected / unknown to the
        # defined graph topology. For single-node workflows (no edges) we allow the start executor
        # to stand alone (handled above when we inject it into the map). We perform this refined
        # check only when there is at least one edge group defined.
        if self._edges:  # Only evaluate when the workflow defines edges
            edge_executor_ids: set[str] = set()
            for _e in self._edges:
                edge_executor_ids.add(_e.source_id)
                edge_executor_ids.add(_e.target_id)
            if start_executor_id not in edge_executor_ids:
                raise GraphConnectivityError(
                    f"Start executor '{start_executor_id}' is not present in the workflow graph"
                )

        # Run all checks
        self._validate_edge_duplication()
        self._validate_handler_output_annotations()
        self._validate_type_compatibility()
        self._validate_graph_connectivity(start_executor_id)
        self._validate_self_loops()
        self._validate_handler_ambiguity()
        self._validate_dead_ends()
        self._validate_cycles()
        self._validate_interceptor_uniqueness()

    def _validate_handler_output_annotations(self) -> None:
        """Validate that each handler's ctx parameter is annotated with WorkflowContext[T].

        Requirements:
        - WorkflowContext annotation must be present
        - T_Out must be provided; if no outputs, it must be None
                - T_Out elements must be valid types (class) or typing generics (e.g., list[str]);
                    values like int() or 123 are invalid
        """
        from ._workflow_context import WorkflowContext  # Local import to avoid cycles

        # Iterate over all registered executors in the workflow graph
        for executor_id, executor in self._executors.items():
            for attr_name in dir(executor.__class__):
                if attr_name.startswith("_"):
                    continue
                # Retrieve attributes without binding (so the first parameter remains 'self').
                # This ensures inspect.signature sees all three parameters: (self, message, ctx).
                attr = None
                from contextlib import suppress

                with suppress(Exception):
                    attr = inspect.getattr_static(executor.__class__, attr_name)
                if attr is None:
                    continue
                # Consider only callables that were decorated with @handler
                if not callable(attr) or not hasattr(attr, "_handler_spec"):
                    continue

                handler_spec = attr._handler_spec  # type: ignore[attr-defined]
                handler_name = handler_spec.get("name", attr_name)

                try:
                    # Inspect the function signature of the unbound function
                    sig = inspect.signature(attr)
                except (TypeError, ValueError):
                    continue

                params = list(sig.parameters.values())
                # Handlers must have exactly three parameters: (self, message, ctx)
                if len(params) != 3:
                    continue

                ctx_param = params[2]
                ctx_ann = ctx_param.annotation

                # If ctx lacks an annotation entirely, fail fast with a clear message
                if ctx_ann is inspect.Parameter.empty:
                    raise HandlerOutputAnnotationError(executor_id, handler_name, "missing type annotation for ctx")

                # Validate that the ctx annotation is WorkflowContext[...] and is properly parameterized
                ctx_origin = get_origin(ctx_ann)
                if ctx_origin is None:
                    # If it's exactly the WorkflowContext class, T_Out is missing (e.g., WorkflowContext)
                    if ctx_ann is WorkflowContext:
                        raise HandlerOutputAnnotationError(
                            executor_id,
                            handler_name,
                            "T_Out is missing; use WorkflowContext[None] or specify concrete types",
                        )
                else:
                    # The annotation is parameterized, but must be for WorkflowContext
                    if ctx_origin is not WorkflowContext:
                        raise HandlerOutputAnnotationError(
                            executor_id, handler_name, f"ctx must be WorkflowContext[T], got {ctx_ann}"
                        )

                # Extract and validate T_Out
                type_args = get_args(ctx_ann)
                if not type_args:
                    raise HandlerOutputAnnotationError(
                        executor_id,
                        handler_name,
                        "T_Out is missing; use WorkflowContext[None] or specify concrete types",
                    )

                t_out = type_args[0]

                # Allow Any for T_Out (unspecified outputs). We accept this here and
                # skip type compatibility later, but still enforce shape validity elsewhere.
                if t_out is Any:
                    continue

                # Allow None (no outputs) explicitly declared
                if t_out is type(None):
                    continue

                # If T_Out is a union, validate each member (e.g., str | int)
                union_origin = get_origin(t_out)
                type_items: list[Any]
                type_items = list(get_args(t_out)) if union_origin in (Union, UnionType) else [t_out]

                invalid = [x for x in type_items if not _is_type_like(x) and x is not type(None)]
                if invalid:
                    raise HandlerOutputAnnotationError(
                        executor_id,
                        handler_name,
                        f"T_Out contains invalid entries: {invalid}. Use proper types or typing generics",
                    )

            # Also validate instance-level handler specs if present
            if hasattr(executor, "_instance_handler_specs"):
                for spec in executor._instance_handler_specs:
                    handler_name = spec.get("name", "unknown")
                    ctx_ann = spec.get("ctx_annotation")

                    if ctx_ann is None:
                        continue  # Skip if no annotation stored

                    # Validate that the ctx annotation is WorkflowContext[...] and is properly parameterized
                    ctx_origin = get_origin(ctx_ann)
                    if ctx_origin is None:
                        if ctx_ann is WorkflowContext:
                            raise HandlerOutputAnnotationError(
                                executor_id,
                                handler_name,
                                "T_Out is missing; use WorkflowContext[None] or specify concrete types",
                            )
                    else:
                        if ctx_origin is not WorkflowContext:
                            raise HandlerOutputAnnotationError(
                                executor_id, handler_name, f"ctx must be WorkflowContext[T], got {ctx_ann}"
                            )

                    # Extract and validate T_Out
                    type_args = get_args(ctx_ann)
                    if not type_args:
                        raise HandlerOutputAnnotationError(
                            executor_id,
                            handler_name,
                            "T_Out is missing; use WorkflowContext[None] or specify concrete types",
                        )

                    t_out = type_args[0]

                    # Allow Any for T_Out (unspecified outputs)
                    if t_out is Any:
                        continue

                    # Allow None (no outputs) explicitly declared
                    if t_out is type(None):
                        continue

                    # If T_Out is a union, validate each member
                    union_origin = get_origin(t_out)
                    instance_type_items: list[Any]
                    instance_type_items = list(get_args(t_out)) if union_origin in (Union, UnionType) else [t_out]

                    invalid = [x for x in instance_type_items if not _is_type_like(x) and x is not type(None)]
                    if invalid:
                        raise HandlerOutputAnnotationError(
                            executor_id,
                            handler_name,
                            f"T_Out contains invalid entries: {invalid}. Use proper types or typing generics",
                        )

    # endregion

    # region Edge and Type Validation
    def _validate_edge_duplication(self) -> None:
        """Validate that there are no duplicate edges in the workflow.

        Raises:
            EdgeDuplicationError: If duplicate edges are found
        """
        seen_edge_ids: set[str] = set()

        for edge in self._edges:
            edge_id = edge.id
            if edge_id in seen_edge_ids:
                raise EdgeDuplicationError(edge_id)
            seen_edge_ids.add(edge_id)

    def _validate_type_compatibility(self) -> None:
        """Validate type compatibility between connected executors.

        This checks that the output types of source executors are compatible
        with the input types expected by target executors.

        Raises:
            TypeCompatibilityError: If type incompatibility is detected
        """
        for edge_group in self._edge_groups:
            for edge in edge_group.edges:
                self._validate_edge_type_compatibility(edge, edge_group)

    def _validate_edge_type_compatibility(self, edge: Edge, edge_group: EdgeGroup) -> None:
        """Validate type compatibility for a specific edge.

        This checks that the output types of the source executor are compatible
        with the input types expected by the target executor.

        Args:
            edge: The edge to validate
            edge_group: The edge group containing this edge

        Raises:
            TypeCompatibilityError: If type incompatibility is detected
        """
        source_executor = self._executors[edge.source_id]
        target_executor = self._executors[edge.target_id]

        # Get output types from source executor
        source_output_types = self._get_executor_output_types(source_executor)

        # Get input types from target executor
        target_input_types = self._get_executor_input_types(target_executor)

        # If either executor has no type information, log warning and skip validation
        # This allows for dynamic typing scenarios but warns about reduced validation coverage
        if not source_output_types or not target_input_types:
            # Suppress warnings for built-in workflow components where dynamic typing is expected
            try:
                from ._executor import RequestInfoExecutor, WorkflowExecutor  # local import to avoid cycles

                builtin_types = (RequestInfoExecutor, WorkflowExecutor)
            except Exception:
                builtin_types = tuple()  # type: ignore[assignment]

            if not source_output_types and not isinstance(source_executor, builtin_types):
                logger.warning(
                    f"Executor '{source_executor.id}' has no output type annotations. "
                    f"Type compatibility validation will be skipped for edges from this executor. "
                    f"Consider adding WorkflowContext[T] generics in handlers for better validation."
                )
            if not target_input_types and not isinstance(target_executor, builtin_types):
                logger.warning(
                    f"Executor '{target_executor.id}' has no input type annotations. "
                    f"Type compatibility validation will be skipped for edges to this executor. "
                    f"Consider adding type annotations to message handler parameters for better validation."
                )
            return

        # Check if any source output type is compatible with any target input type
        compatible = False
        compatible_pairs: list[tuple[type[Any], type[Any]]] = []

        for source_type in source_output_types:
            for target_type in target_input_types:
                if isinstance(edge_group, FanInEdgeGroup):
                    # If the edge is part of an edge group, the target expects a list of data types
                    if self._is_type_compatible(list[source_type], target_type):  # type: ignore[valid-type]
                        compatible = True
                        compatible_pairs.append((list[source_type], target_type))  # type: ignore[valid-type]
                else:
                    if self._is_type_compatible(source_type, target_type):
                        compatible = True
                        compatible_pairs.append((source_type, target_type))

        # Log successful type compatibility for debugging
        if compatible:
            logger.debug(
                f"Type compatibility validated for edge '{source_executor.id}' -> '{target_executor.id}'. "
                f"Compatible type pairs: {[(str(s), str(t)) for s, t in compatible_pairs]}"
            )

        if not compatible:
            # Enhanced error with more detailed information
            raise TypeCompatibilityError(
                source_executor.id,
                target_executor.id,
                source_output_types,
                target_input_types,
            )

    def _get_executor_output_types(self, executor: Executor) -> list[type[Any]]:
        """Extract output types from an executor's message handlers.

        Args:
            executor: The executor to analyze

        Returns:
            list of types that this executor can output
        """
        output_types: list[type[Any]] = []

        for attr_name in dir(executor.__class__):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(executor.__class__, attr_name)
                if callable(attr) and hasattr(attr, "_handler_spec"):
                    handler_spec = attr._handler_spec  # type: ignore
                    handler_output_types = handler_spec.get("output_types", [])
                    output_types.extend(handler_output_types)
            except AttributeError:
                # Skip attributes that may not be accessible
                continue

        # Also include intercepted request types as potential outputs
        # since @intercepts_request methods can forward requests
        if hasattr(executor, "_request_interceptors"):
            for request_type in executor._request_interceptors:
                if isinstance(request_type, type):
                    output_types.append(request_type)

        # Include output types from instance-level handler specs
        if hasattr(executor, "_instance_handler_specs"):
            for spec in executor._instance_handler_specs:
                handler_output_types = spec.get("output_types", [])
                output_types.extend(handler_output_types)

        return output_types

    def _get_executor_input_types(self, executor: Executor) -> list[type[Any]]:
        """Extract input types from an executor's message handlers.

        Args:
            executor: The executor to analyze

        Returns:
            list of types that this executor can handle as input
        """
        input_types: list[type[Any]] = []

        # Access the private _handlers attribute to get input types
        if hasattr(executor, "_handlers"):
            input_types.extend(executor._handlers.keys())  # type: ignore

        return input_types

    # endregion

    # region Graph Connectivity Validation
    def _validate_graph_connectivity(self, start_executor_id: str) -> None:
        """Validate graph connectivity and detect potential issues.

        This performs several checks:
        - Detects unreachable executors from the start node
        - Detects isolated executors (no incoming or outgoing edges)
        - Warns about potential infinite loops

        Args:
            start_executor_id: The ID of the starting executor

        Raises:
            GraphConnectivityError: If connectivity issues are detected
        """
        # Build adjacency list for the graph
        graph: dict[str, list[str]] = defaultdict(list)
        all_executors = set(self._executors.keys())

        for edge in self._edges:
            graph[edge.source_id].append(edge.target_id)

        # Find reachable nodes from start
        reachable = self._find_reachable_nodes(graph, start_executor_id)

        # Check for unreachable executors
        unreachable = all_executors - reachable
        if unreachable:
            raise GraphConnectivityError(
                f"The following executors are unreachable from the start executor '{start_executor_id}': "
                f"{sorted(unreachable)}. This may indicate a disconnected workflow graph."
            )

        # Check for isolated executors (no edges)
        isolated_executors: list[str] = []
        for executor_id in all_executors:
            has_incoming = any(edge.target_id == executor_id for edge in self._edges)
            has_outgoing = any(edge.source_id == executor_id for edge in self._edges)

            if not has_incoming and not has_outgoing and executor_id != start_executor_id:
                isolated_executors.append(executor_id)

        if isolated_executors:
            raise GraphConnectivityError(
                f"The following executors are isolated (no incoming or outgoing edges): "
                f"{sorted(isolated_executors)}. Isolated executors will never be executed."
            )

    def _find_reachable_nodes(self, graph: dict[str, list[str]], start: str) -> set[str]:
        """Find all nodes reachable from the start node using DFS.

        Args:
            graph: Adjacency list representation of the graph
            start: Starting node ID

        Returns:
            Set of reachable node IDs
        """
        visited: set[str] = set()
        stack = [start]

        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                stack.extend(graph[node])

        return visited

    # endregion

    # region Additional Validation Scenarios
    def _validate_self_loops(self) -> None:
        """Detect and log self-loops (edges from executor to itself).

        Self-loops might indicate recursive processing which could be intentional
        but should be highlighted for review.
        """
        self_loops = [edge for edge in self._edges if edge.source_id == edge.target_id]

        for edge in self_loops:
            logger.warning(
                f"Self-loop detected: Executor '{edge.source_id}' connects to itself. "
                f"This may cause infinite recursion if not properly handled with conditions."
            )

    def _validate_handler_ambiguity(self) -> None:
        """Check for potential ambiguity in message handlers.

        Warns when executors have multiple handlers that could handle the same type,
        which might lead to unexpected behavior.
        """
        for executor_id, executor in self._executors.items():
            input_types = self._get_executor_input_types(executor)

            # Check for duplicate input types
            seen_types: set[type[Any]] = set()
            duplicate_types: set[type[Any]] = set()

            for input_type in input_types:
                if input_type in seen_types:
                    duplicate_types.add(input_type)
                seen_types.add(input_type)

            if duplicate_types:
                logger.warning(
                    f"Executor '{executor_id}' has multiple handlers for the same input types: "
                    f"{[str(t) for t in duplicate_types]}. This may lead to ambiguous message routing."
                )

    def _validate_dead_ends(self) -> None:
        """Identify executors that have no outgoing edges (potential dead ends).

        These might be intentional final nodes or could indicate missing connections.
        """
        executors_with_outgoing = {edge.source_id for edge in self._edges}
        all_executor_ids = set(self._executors.keys())
        dead_ends = all_executor_ids - executors_with_outgoing

        if dead_ends:
            logger.info(
                f"Dead-end executors detected (no outgoing edges): {sorted(dead_ends)}. "
                f"Verify these are intended as final nodes in the workflow."
            )

    def _validate_cycles(self) -> None:
        """Detect cycles in the workflow graph.

        Cycles might be intentional for iterative processing but should be flagged
        for review to ensure proper termination conditions exist.
        """
        # Build adjacency list
        graph: dict[str, list[str]] = defaultdict(list)
        for edge in self._edges:
            graph[edge.source_id].append(edge.target_id)

        # Use DFS to detect cycles
        white = set(self._executors.keys())  # Unvisited
        gray: set[str] = set()  # Currently being processed
        black: set[str] = set()  # Completely processed

        def has_cycle(node: str) -> bool:
            if node in gray:  # Back edge found - cycle detected
                return True
            if node in black:  # Already processed
                return False

            # Mark as being processed
            white.discard(node)
            gray.add(node)

            # Visit neighbors
            for neighbor in graph[node]:
                if has_cycle(neighbor):
                    return True

            # Mark as completely processed
            gray.discard(node)
            black.add(node)
            return False

        # Check for cycles starting from any unvisited node
        cycle_detected = False
        while white and not cycle_detected:
            start_node = next(iter(white))
            if has_cycle(start_node):
                cycle_detected = True

        if cycle_detected:
            logger.warning(
                "Cycle detected in the workflow graph. "
                "Ensure proper termination conditions exist to prevent infinite loops."
            )

    def _validate_interceptor_uniqueness(self) -> None:
        """Validate that only one executor intercepts a given request type from a specific sub-workflow.

        This prevents non-deterministic behavior where multiple executors could intercept
        the same request type from the same sub-workflow.
        """
        from ._executor import WorkflowExecutor

        # Find all WorkflowExecutor instances in the workflow
        workflow_executors: dict[str, WorkflowExecutor] = {}
        for executor_id, executor in self._executors.items():
            if isinstance(executor, WorkflowExecutor):
                workflow_executors[executor_id] = executor

        # For each WorkflowExecutor, check which executors can intercept its requests
        for workflow_id, _workflow_executor in workflow_executors.items():
            # Map of request_type -> list of intercepting executor IDs
            interceptors_by_type: dict[type | str, list[str]] = {}

            # Find all executors that have edges from this WorkflowExecutor
            # These are potential interceptors
            for edge in self._edges:
                if edge.source_id == workflow_id:
                    target_executor = self._executors.get(edge.target_id)
                    if target_executor and hasattr(target_executor, "_request_interceptors"):
                        # Check what request types this executor intercepts
                        for request_type, interceptor_list in target_executor._request_interceptors.items():
                            # Check if any interceptor is scoped to this workflow or unscoped
                            for interceptor_info in interceptor_list:
                                from_workflow = interceptor_info.get("from_workflow")
                                # If unscoped or specifically scoped to this workflow
                                if from_workflow is None or from_workflow == workflow_id:
                                    if request_type not in interceptors_by_type:
                                        interceptors_by_type[request_type] = []
                                    interceptors_by_type[request_type].append(edge.target_id)

            # Check for duplicates
            for request_type, executor_ids in interceptors_by_type.items():
                unique_executors = list(set(executor_ids))  # Remove duplicates from same executor
                if len(unique_executors) > 1:
                    type_name = request_type.__name__ if isinstance(request_type, type) else str(request_type)
                    raise InterceptorConflictError(
                        f"Multiple executors intercept the same request type '{type_name}' "
                        f"from sub-workflow '{workflow_id}': {', '.join(unique_executors)}. "
                        f"Only one executor should intercept a given request type from a specific sub-workflow "
                        f"to ensure deterministic behavior."
                    )

    # endregion

    # region Type Compatibility Utilities
    @staticmethod
    def _is_type_compatible(source_type: type[Any], target_type: type[Any]) -> bool:
        """Check if source_type is compatible with target_type."""
        # Handle Any type
        if source_type is Any or target_type is Any:
            return True

        # Handle exact match
        if source_type == target_type:
            return True

        # Handle inheritance
        try:
            if inspect.isclass(source_type) and inspect.isclass(target_type):
                return issubclass(source_type, target_type)
        except TypeError:
            # Handle generic types that can't be used with issubclass
            pass

        # Handle Union types
        source_origin = get_origin(source_type)
        target_origin = get_origin(target_type)

        if target_origin in (Union, UnionType):
            target_args = get_args(target_type)
            return any(WorkflowGraphValidator._is_type_compatible(source_type, arg) for arg in target_args)

        if source_origin in (Union, UnionType):
            source_args = get_args(source_type)
            return all(WorkflowGraphValidator._is_type_compatible(arg, target_type) for arg in source_args)

        # Handle generic types
        if source_origin is not None and target_origin is not None and source_origin == target_origin:
            source_args = get_args(source_type)
            target_args = get_args(target_type)
            if len(source_args) == len(target_args):
                return all(
                    WorkflowGraphValidator._is_type_compatible(s_arg, t_arg)
                    for s_arg, t_arg in zip(source_args, target_args, strict=True)
                )

        return False

    # endregion


# endregion


def validate_workflow_graph(
    edge_groups: Sequence[EdgeGroup], executors: dict[str, Executor], start_executor: Executor | str
) -> None:
    """Convenience function to validate a workflow graph.

    Args:
        edge_groups: list of edge groups in the workflow
        executors: Map of executor IDs to executor instances
        start_executor: The starting executor (can be instance or ID)

    Raises:
        WorkflowValidationError: If any validation fails
    """
    validator = WorkflowGraphValidator()
    validator.validate_workflow(edge_groups, executors, start_executor)
