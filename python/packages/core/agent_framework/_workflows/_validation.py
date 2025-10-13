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
from ._request_info_executor import RequestInfoExecutor

logger = logging.getLogger(__name__)

# Track cycle signatures we've already reported to avoid spamming logs when workflows
# with intentional feedback loops are constructed multiple times in the same process.
_LOGGED_CYCLE_SIGNATURES: set[tuple[str, ...]] = set()


# region Enums and Base Classes
class ValidationTypeEnum(Enum):
    """Enumeration of workflow validation types."""

    EDGE_DUPLICATION = "EDGE_DUPLICATION"
    EXECUTOR_DUPLICATION = "EXECUTOR_DUPLICATION"
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


class ExecutorDuplicationError(WorkflowValidationError):
    """Exception raised when duplicate executor identifiers are detected."""

    def __init__(self, executor_id: str):
        super().__init__(
            message=(
                f"Duplicate executor id detected: '{executor_id}'. Executor ids must be globally unique within a "
                "workflow."
            ),
            validation_type=ValidationTypeEnum.EXECUTOR_DUPLICATION,
        )
        self.executor_id = executor_id


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
        self._duplicate_executor_ids: set[str] = set()
        self._start_executor_ref: Executor | str | None = None

    # region Core Validation Methods
    def validate_workflow(
        self,
        edge_groups: Sequence[EdgeGroup],
        executors: dict[str, Executor],
        start_executor: Executor | str,
        *,
        duplicate_executor_ids: Sequence[str] | None = None,
    ) -> None:
        """Validate the entire workflow graph.

        Args:
            edge_groups: list of edge groups in the workflow
            executors: Map of executor IDs to executor instances
            start_executor: The starting executor (can be instance or ID)

        Keyword Args:
            duplicate_executor_ids: Optional list of known duplicate executor IDs to pre-populate

        Raises:
            WorkflowValidationError: If any validation fails
        """
        self._executors = executors
        self._edges = [edge for group in edge_groups for edge in group.edges]
        self._edge_groups = edge_groups
        self._duplicate_executor_ids = set(duplicate_executor_ids or [])
        self._start_executor_ref = start_executor

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
        self._validate_executor_id_uniqueness(start_executor_id)
        self._validate_edge_duplication()
        self._validate_handler_output_annotations()
        self._validate_type_compatibility()
        self._validate_graph_connectivity(start_executor_id)
        self._validate_self_loops()
        self._validate_dead_ends()
        self._validate_cycles()

    def _validate_handler_output_annotations(self) -> None:
        """Validate that each handler's ctx parameter is annotated with WorkflowContext[T].

        Note: This validation is now primarily handled at handler registration time
        via the unified validation functions in _workflow_context.py when the @handler
        decorator is applied. This method is kept minimal for any edge cases.
        """
        # The comprehensive validation is already done during handler registration:
        # 1. @handler decorator calls validate_function_signature()
        # 2. FunctionExecutor constructor calls validate_function_signature()
        # 3. Both use validate_workflow_context_annotation() for WorkflowContext validation
        #
        # All executors in the workflow must have gone through one of these paths,
        # so redundant validation here is unnecessary and has been removed.
        pass

    # endregion

    def _validate_executor_id_uniqueness(self, start_executor_id: str) -> None:
        """Ensure executor identifiers are unique throughout the workflow graph."""
        duplicates: set[str] = set(self._duplicate_executor_ids)

        id_counts: defaultdict[str, int] = defaultdict(int)
        for key, executor in self._executors.items():
            id_counts[executor.id] += 1
            if key != executor.id:
                duplicates.add(executor.id)

        duplicates.update({executor_id for executor_id, count in id_counts.items() if count > 1})

        if isinstance(self._start_executor_ref, Executor):
            mapped = self._executors.get(start_executor_id)
            if mapped is not None and mapped is not self._start_executor_ref:
                duplicates.add(start_executor_id)

        if duplicates:
            raise ExecutorDuplicationError(sorted(duplicates)[0])

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
        source_output_types = list(source_executor.output_types)

        # Get input types from target executor
        target_input_types = target_executor.input_types

        # If either executor has no type information, log warning and skip validation
        # This allows for dynamic typing scenarios but warns about reduced validation coverage
        if not source_output_types or not target_input_types:
            # Suppress warnings for RequestInfoExecutor where dynamic typing is expected
            if not source_output_types and not isinstance(source_executor, RequestInfoExecutor):
                logger.warning(
                    f"Executor '{source_executor.id}' has no output type annotations. "
                    f"Type compatibility validation will be skipped for edges from this executor. "
                    f"Consider adding WorkflowContext[T] generics in handlers for better validation."
                )
            if not target_input_types and not isinstance(target_executor, RequestInfoExecutor):
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
        for review to ensure proper termination conditions exist. We surface each
        distinct cycle group only once per process to avoid noisy, repeated warnings
        when rebuilding the same workflow.
        """
        # Build adjacency list (ensure every executor appears even if it has no outgoing edges)
        graph: dict[str, list[str]] = defaultdict(list)
        for edge in self._edges:
            graph[edge.source_id].append(edge.target_id)
            graph.setdefault(edge.target_id, [])
        for executor_id in self._executors:
            graph.setdefault(executor_id, [])

        # Tarjan's algorithm to locate strongly-connected components that form cycles
        index: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        current_index = 0
        cycle_components: list[list[str]] = []

        def strongconnect(node: str) -> None:
            nonlocal current_index

            index[node] = current_index
            lowlink[node] = current_index
            current_index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in graph[node]:
                if neighbor not in index:
                    strongconnect(neighbor)
                    lowlink[node] = min(lowlink[node], lowlink[neighbor])
                elif neighbor in on_stack:
                    lowlink[node] = min(lowlink[node], index[neighbor])

            if lowlink[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break

                # A strongly connected component represents a cycle if it has more than one
                # node or if a single node references itself directly.
                if len(component) > 1 or any(member in graph[member] for member in component):
                    cycle_components.append(component)

        for executor_id in graph:
            if executor_id not in index:
                strongconnect(executor_id)

        if not cycle_components:
            return

        unseen_components: list[list[str]] = []
        for component in cycle_components:
            signature = tuple(sorted(component))
            if signature in _LOGGED_CYCLE_SIGNATURES:
                continue
            _LOGGED_CYCLE_SIGNATURES.add(signature)
            unseen_components.append(component)

        if not unseen_components:
            # All cycles already reported in this process; keep noise low but retain traceability.
            logger.debug(
                "Cycle detected in workflow graph but previously reported. Components: %s",
                [sorted(component) for component in cycle_components],
            )
            return

        def _format_cycle(component: list[str]) -> str:
            if not component:
                return ""
            ordered = list(component)
            ordered.append(component[0])
            return " -> ".join(ordered)

        formatted_cycles = ", ".join(_format_cycle(component) for component in unseen_components)
        logger.warning(
            "Cycle detected in the workflow graph involving: %s. Ensure termination or iteration limits exist.",
            formatted_cycles,
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

        # No other special compatibility cases
        return False

    # endregion


# endregion


def validate_workflow_graph(
    edge_groups: Sequence[EdgeGroup],
    executors: dict[str, Executor],
    start_executor: Executor | str,
    *,
    duplicate_executor_ids: Sequence[str] | None = None,
) -> None:
    """Convenience function to validate a workflow graph.

    Args:
        edge_groups: list of edge groups in the workflow
        executors: Map of executor IDs to executor instances
        start_executor: The starting executor (can be instance or ID)

    Keyword Args:
        duplicate_executor_ids: Optional list of known duplicate executor IDs to pre-populate

    Raises:
        WorkflowValidationError: If any validation fails
    """
    validator = WorkflowGraphValidator()
    validator.validate_workflow(
        edge_groups,
        executors,
        start_executor,
        duplicate_executor_ids=duplicate_executor_ids,
    )
