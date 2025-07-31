# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import AsyncIterable, Callable, Sequence
from typing import Any

from ._edge import Edge
from ._events import WorkflowEvent
from ._executor import Executor
from ._runner import Runner
from ._runner_context import InProcRunnerContext, RunnerContext
from ._shared_state import SharedState
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


class Workflow:
    """A class representing a workflow that can be executed.

    This class is a placeholder for the workflow logic and does not implement any specific functionality.
    It serves as a base class for more complex workflows that can be defined in subclasses.
    """

    def __init__(
        self,
        edges: list[Edge],
        start_executor: Executor[Any] | str,
        runner_context: RunnerContext,
    ):
        """Initialize the workflow with a list of edges.

        Args:
            edges: A list of directed edges representing the connections between nodes in the workflow.
            start_executor: The starting executor for the workflow, which can be an Executor instance or its ID.
            runner_context: The RunnerContext instance to be used during workflow execution.
        """
        self._edges = edges
        self._start_executor = start_executor
        self._executors = {edge.source_id: edge.source for edge in edges} | {
            edge.target_id: edge.target for edge in edges
        }

        self._shared_state = SharedState()
        self._runner = Runner(self._edges, self._shared_state, runner_context)

    async def run_stream(
        self,
        message: Any,
        executor: Executor[Any] | str | None = None,
    ) -> AsyncIterable[WorkflowEvent]:
        """Send a message to the starting executor of the workflow.

        Args:
            message: The message to be sent to the starting executor.
            executor: The executor to which the message should be sent. If None, the starting executor is used.
        """
        if not executor:
            executor = self._start_executor

        if isinstance(executor, str):
            executor = self._get_executor_by_id(executor)

        await executor.execute(
            message,
            WorkflowContext(
                executor.id,
                self._shared_state,
                self._runner.context,
            ),
        )
        async for event in self._runner.run_until_convergence():
            yield event

    def _get_executor_by_id(self, executor_id: str) -> Executor[Any]:
        """Get an executor by its ID.

        Args:
            executor_id: The ID of the executor to retrieve.

        Returns:
            The Executor instance corresponding to the given ID.
        """
        if executor_id not in self._executors:
            raise ValueError(f"Executor with ID {executor_id} not found.")
        return self._executors[executor_id]


class WorkflowBuilder:
    """A builder class for constructing workflows.

    This class provides methods to add edges and set the starting executor for the workflow.
    """

    def __init__(self):
        """Initialize the WorkflowBuilder with an empty list of edges and no starting executor."""
        self._edges: list[Edge] = []
        self._start_executor: Executor[Any] | str | None = None
        self._runner_context: RunnerContext | None = None

    def add_edge(
        self,
        source: Executor[Any],
        target: Executor[Any],
        condition: Callable[[Any], bool] | None = None,
    ) -> "Self":
        """Add a directed edge between two executors.

        Args:
            source: The source executor of the edge.
            target: The target executor of the edge.
            condition: An optional condition function that determines whether the edge
                       should be traversed based on the message type.
        """
        # TODO(@taochen): Support executor factories for lazy initialization
        self._edges.append(Edge(source, target, condition))
        return self

    def add_fan_out_edges(self, source: Executor[Any], targets: Sequence[Executor[Any]]) -> "Self":
        """Add multiple edges to the workflow.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.
        """
        for target in targets:
            self._edges.append(Edge(source, target))
        return self

    def add_fan_in_edges(
        self,
        sources: Sequence[Executor[Any]],
        target: Executor[Any],
    ) -> "Self":
        """Add multiple edges from sources to a single target executor.

        The edges will be grouped together for synchronized processing, meaning
        the target executor will only be executed once all source executors have completed.

        Args:
            sources: A list of source executors for the edges.
            target: The target executor for the edges.
        """
        edges = [Edge(source, target) for source in sources]

        # Set the edge groups for the edges to ensure they are processed together.
        for i, edge in enumerate(edges):
            group_ids: list[str] = []
            group_ids.extend([e.id for e in edges[0:i]])
            group_ids.extend([e.id for e in edges[i + 1 :]])
            edge.set_edge_group(group_ids)

        self._edges.extend(edges)

        return self

    def add_chain(
        self,
        executors: Sequence[Executor[Any]],
    ) -> "Self":
        """Add a chain of executors to the workflow.

        Args:
            executors: A list of executors to be added to the chain.
        """
        for i in range(len(executors) - 1):
            self.add_edge(executors[i], executors[i + 1])
        return self

    def set_start_executor(self, executor: Executor[Any] | str) -> "Self":
        """Set the starting executor for the workflow.

        Args:
            executor: The starting executor, which can be an Executor instance or its ID.
        """
        self._start_executor = executor
        return self

    def set_runner_context(self, runner_context: RunnerContext) -> "Self":
        """Set the runner context for the workflow.

        Args:
            runner_context: The RunnerContext instance to be used during workflow execution.
        """
        self._runner_context = runner_context
        return self

    def build(self) -> Workflow:
        """Build and return the constructed workflow.

        Returns:
            A Workflow instance with the defined edges and starting executor.
        """
        if not self._start_executor:
            raise ValueError("Starting executor must be set before building the workflow.")

        runner_context = self._runner_context or InProcRunnerContext()

        return Workflow(self._edges, self._start_executor, runner_context)
