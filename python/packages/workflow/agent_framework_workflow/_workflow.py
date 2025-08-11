# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
import uuid
from collections.abc import AsyncIterable, Callable, Sequence
from typing import Any

from ._checkpoint import CheckpointStorage
from ._const import DEFAULT_MAX_ITERATIONS
from ._edge import Edge
from ._events import RequestInfoEvent, WorkflowCompletedEvent, WorkflowEvent
from ._executor import Executor, RequestInfoExecutor
from ._runner import Runner
from ._runner_context import CheckpointState, InProcRunnerContext, RunnerContext
from ._shared_state import SharedState
from ._validation import validate_workflow_graph
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = logging.getLogger(__name__)


class WorkflowRunResult(list[WorkflowEvent]):
    """A list of events generated during the workflow execution in non-streaming mode."""

    def get_completed_event(self) -> WorkflowCompletedEvent | None:
        """Get the completed event from the workflow run result.

        Returns:
            A completed WorkflowEvent instance if the workflow has a completed event, otherwise None.

        Raises:
            ValueError: If there are multiple completed events in the workflow run result.
        """
        completed_events = [event for event in self if isinstance(event, WorkflowCompletedEvent)]
        if not completed_events:
            return None
        if len(completed_events) > 1:
            raise ValueError("Multiple completed events found.")
        return completed_events[0]

    def get_request_info_events(self) -> list[RequestInfoEvent]:
        """Get all request info events from the workflow run result.

        Returns:
            A list of RequestInfoEvent instances found in the workflow run result.
        """
        return [event for event in self if isinstance(event, RequestInfoEvent)]


# region Workflow


class Workflow:
    """A class representing a workflow that can be executed.

    This class is a placeholder for the workflow logic and does not implement any specific functionality.
    It serves as a base class for more complex workflows that can be defined in subclasses.
    """

    def __init__(
        self,
        edges: list[Edge],
        start_executor: Executor | str,
        runner_context: RunnerContext,
        max_iterations: int,
    ):
        """Initialize the workflow with a list of edges.

        Args:
            edges: A list of directed edges representing the connections between nodes in the workflow.
            start_executor: The starting executor for the workflow, which can be an Executor instance or its ID.
            runner_context: The RunnerContext instance to be used during workflow execution.
            max_iterations: The maximum number of iterations the workflow will run for convergence.
        """
        self._edges = edges
        self._start_executor = start_executor
        self._executors = {edge.source_id: edge.source for edge in edges} | {
            edge.target_id: edge.target for edge in edges
        }

        self._shared_state = SharedState()

        workflow_id = str(uuid.uuid4())
        self._runner = Runner(
            self._edges, self._shared_state, runner_context, max_iterations=max_iterations, workflow_id=workflow_id
        )

    @property
    def edges(self) -> list[Edge]:
        """Get the list of edges in the workflow."""
        return self._edges

    @property
    def start_executor(self) -> Executor:
        """Get the starting executor of the workflow.

        Returns:
            The starting executor, which can be an Executor instance or its ID.
        """
        if isinstance(self._start_executor, str):
            return self._get_executor_by_id(self._start_executor)
        return self._start_executor

    @property
    def executors(self) -> list[Executor]:
        """Get the list of executors in the workflow."""
        return list(self._executors.values())

    async def run_streaming(self, message: Any) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with a starting message and stream events.

        Args:
            message: The message to be sent to the starting executor.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        # Reset context for a new run if supported
        self._runner.context.reset_for_new_run(self._shared_state)

        executor = self._start_executor
        if isinstance(executor, str):
            executor = self._get_executor_by_id(executor)

        await executor.execute(
            message,
            WorkflowContext(
                executor.id,
                [self.__class__.__name__],
                self._shared_state,
                self._runner.context,
            ),
        )

        async for event in self._runner.run_until_convergence():
            yield event

    async def run_streaming_from_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_storage: CheckpointStorage | None = None,
        responses: dict[str, Any] | None = None,
    ) -> AsyncIterable[WorkflowEvent]:
        """Resume workflow execution from a checkpoint and stream events.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from.
            checkpoint_storage: Optional checkpoint storage to use for restoration.
                              If not provided, the workflow must have been built with checkpointing enabled.
            responses: Optional dictionary of responses to inject into the workflow
                      after restoration. Keys are request IDs, values are response data.

        Yields:
            WorkflowEvent: Events generated during workflow execution.

        Raises:
            ValueError: If neither checkpoint_storage is provided nor checkpointing is enabled.
            RuntimeError: If checkpoint restoration fails.
        """
        has_checkpointing = self._runner.context.has_checkpointing()

        if not has_checkpointing and not checkpoint_storage:
            raise ValueError(
                "Cannot restore from checkpoint: either provide checkpoint_storage parameter "
                "or build workflow with WorkflowBuilder.with_checkpointing(checkpoint_storage)."
            )

        if has_checkpointing:
            # restore via Runner so shared state and iteration are synchronized
            restored = await self._runner.restore_from_checkpoint(checkpoint_id)
        else:
            if checkpoint_storage is None:
                raise ValueError("checkpoint_storage cannot be None.")
            restored = await self._restore_from_external_checkpoint(checkpoint_id, checkpoint_storage)

        if not restored:
            raise RuntimeError(f"Failed to restore from checkpoint: {checkpoint_id}")

        if responses:
            request_info_executor = self._get_executor_by_id(RequestInfoExecutor.EXECUTOR_ID)
            if isinstance(request_info_executor, RequestInfoExecutor):
                for request_id, response_data in responses.items():
                    await request_info_executor.handle_response(
                        response_data,
                        request_id,
                        WorkflowContext(
                            request_info_executor.id,
                            [self.__class__.__name__],
                            self._shared_state,
                            self._runner.context,
                        ),
                    )

        async for event in self._runner.run_until_convergence():
            yield event

    async def send_responses_streaming(self, responses: dict[str, Any]) -> AsyncIterable[WorkflowEvent]:
        """Send responses back to the workflow and stream the events generated by the workflow.

        Args:
            responses: The responses to be sent back to the workflow, where keys are request IDs
                       and values are the corresponding response data.

        Yields:
            WorkflowEvent: The events generated during the workflow execution after sending the responses.
        """
        request_info_executor = self._get_executor_by_id(RequestInfoExecutor.EXECUTOR_ID)
        if not isinstance(request_info_executor, RequestInfoExecutor):
            raise ValueError(f"Executor with ID {RequestInfoExecutor.EXECUTOR_ID} is not a RequestInfoExecutor.")

        async def _handle_response(response: Any, request_id: str) -> None:
            """Handle the response from the RequestInfoExecutor."""
            await request_info_executor.handle_response(
                response,
                request_id,
                WorkflowContext(
                    request_info_executor.id,
                    [self.__class__.__name__],
                    self._shared_state,
                    self._runner.context,
                ),
            )

        await asyncio.gather(*[_handle_response(response, request_id) for request_id, response in responses.items()])

        async for event in self._runner.run_until_convergence():
            yield event

    async def run(self, message: Any) -> WorkflowRunResult:
        """Run the workflow with the given message.

        Args:
            message: The message to be processed by the workflow.

        Returns:
            A WorkflowRunResult instance containing a list of events generated during the workflow execution.
        """
        events = [event async for event in self.run_streaming(message)]
        return WorkflowRunResult(events)

    async def run_from_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_storage: CheckpointStorage | None = None,
        responses: dict[str, Any] | None = None,
    ) -> WorkflowRunResult:
        """Resume workflow execution from a checkpoint.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from.
            checkpoint_storage: Optional checkpoint storage to use for restoration.
                              If not provided, the workflow must have been built with checkpointing enabled.
            responses: Optional dictionary of responses to inject into the workflow
                      after restoration. Keys are request IDs, values are response data.

        Returns:
            A WorkflowRunResult instance containing a list of events generated during the workflow execution.

        Raises:
            ValueError: If neither checkpoint_storage is provided nor checkpointing is enabled.
            RuntimeError: If checkpoint restoration fails.
        """
        events = [
            event async for event in self.run_streaming_from_checkpoint(checkpoint_id, checkpoint_storage, responses)
        ]
        return WorkflowRunResult(events)

    async def send_responses(self, responses: dict[str, Any]) -> WorkflowRunResult:
        """Send responses back to the workflow.

        Args:
            responses: A dictionary where keys are request IDs and values are the corresponding response data.

        Returns:
            A WorkflowRunResult instance containing a list of events generated during the workflow execution.
        """
        events = [event async for event in self.send_responses_streaming(responses)]
        return WorkflowRunResult(events)

    def _get_executor_by_id(self, executor_id: str) -> Executor:
        """Get an executor by its ID.

        Args:
            executor_id: The ID of the executor to retrieve.

        Returns:
            The Executor instance corresponding to the given ID.
        """
        if executor_id not in self._executors:
            raise ValueError(f"Executor with ID {executor_id} not found.")
        return self._executors[executor_id]

    async def _restore_from_external_checkpoint(
        self, checkpoint_id: str, checkpoint_storage: CheckpointStorage
    ) -> bool:
        """Restore workflow state from an external checkpoint storage.

        This method implements the state transfer pattern: load checkpoint data
        from external storage and transfer it to the current workflow context.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from.
            checkpoint_storage: The checkpoint storage to load from.

        Returns:
            True if restoration was successful, False otherwise.
        """
        try:
            checkpoint = await checkpoint_storage.load_checkpoint(checkpoint_id)
            if not checkpoint:
                return False

            temp_context = InProcRunnerContext(checkpoint_storage)
            state: CheckpointState = {
                "messages": checkpoint.messages,
                "shared_state": checkpoint.shared_state,
                "executor_states": checkpoint.executor_states,
                "iteration_count": checkpoint.iteration_count,
                "max_iterations": checkpoint.max_iterations,
            }

            await temp_context.set_checkpoint_state(state)
            restored_state = await temp_context.get_checkpoint_state()
            await self._transfer_state_to_context(restored_state)

            # Also set runner iteration/max so superstep numbering continues
            self._runner.mark_resumed(iteration=checkpoint.iteration_count, max_iterations=checkpoint.max_iterations)

            return True

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to restore from external checkpoint {checkpoint_id}: {e}")
            return False

    async def _transfer_state_to_context(self, restored_state: CheckpointState) -> None:
        """Transfer restored checkpoint state into the current workflow runtime.

        This transfers:
        - messages -> into the current RunnerContext so delivery can continue
        - executor_states -> into the current RunnerContext so ctx.get_state() works after resume
        - shared_state -> into the Workflow's SharedState so executors can read values set before the checkpoint
        """
        # Best-effort restoration
        # Restore shared state so downstream executors can read values (e.g., original_input)
        try:
            shared_state_data = restored_state.get("shared_state", {})
            if shared_state_data and hasattr(self._shared_state, "_state"):
                async with self._shared_state.hold():
                    self._shared_state._state.clear()  # type: ignore[attr-defined]
                    self._shared_state._state.update(shared_state_data)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to restore shared_state during external restore: %s", exc)

        # Restore executor states into the context so ctx.get_state() calls after resume succeed
        try:
            executor_states = restored_state.get("executor_states", {})
            for exec_id, state in executor_states.items():
                try:
                    await self._runner.context.set_state(exec_id, state)
                except Exception as exc:  # pragma: no cover - ignore per-executor failures
                    logger.debug("Failed to restore executor state for %s during external restore: %s", exec_id, exc)
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to iterate executor_states during external restore: %s", exc)

        # Transfer pending messages into the context for delivery in the next superstep
        messages_data = restored_state["messages"]
        for _, message_list in messages_data.items():
            for msg_data in message_list:
                source_any = msg_data.get("source_id", "")
                source_id: str = source_any if isinstance(source_any, str) else str(source_any)
                if not source_id:
                    source_id = ""
                target_raw = msg_data.get("target_id")
                target_id: str | None = (
                    target_raw if target_raw is None or isinstance(target_raw, str) else str(target_raw)
                )

                # Build and send Message via runner context
                from ._runner_context import Message as _Msg

                await self._runner.context.send_message(
                    _Msg(data=msg_data.get("data"), source_id=source_id, target_id=target_id)
                )


# region WorkflowBuilder


class WorkflowBuilder:
    """A builder class for constructing workflows.

    This class provides methods to add edges and set the starting executor for the workflow.
    """

    def __init__(self, max_iterations: int = DEFAULT_MAX_ITERATIONS):
        """Initialize the WorkflowBuilder with an empty list of edges and no starting executor."""
        self._edges: list[Edge] = []
        self._start_executor: Executor | str | None = None
        self._checkpoint_storage: CheckpointStorage | None = None
        self._max_iterations: int = max_iterations

    def add_edge(
        self,
        source: Executor,
        target: Executor,
        condition: Callable[[Any], bool] | None = None,
    ) -> "Self":
        """Add a directed edge between two executors.

        The output types of the source and the input types of the target must be compatible.

        Args:
            source: The source executor of the edge.
            target: The target executor of the edge.
            condition: An optional condition function that determines whether the edge
                       should be traversed based on the message type.
        """
        # TODO(@taochen): Support executor factories for lazy initialization
        self._edges.append(Edge(source, target, condition))
        return self

    def add_fan_out_edges(self, source: Executor, targets: Sequence[Executor]) -> "Self":
        """Add multiple edges to the workflow.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to all target executors.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.
        """
        for target in targets:
            self._edges.append(Edge(source, target))
        return self

    def add_fan_in_edges(self, sources: Sequence[Executor], target: Executor) -> "Self":
        """Add multiple edges from sources to a single target executor.

        The edges will be grouped together for synchronized processing, meaning
        the target executor will only be executed once all source executors have completed.

        The target executor will receive a list of messages aggregated from all source executors.
        Thus the input types of the target executor must be compatible with a list of the output
        types of the source executors. For example:

            class Target(Executor):
                @handler
                def handle_messages(self, messages: list[Message]) -> None:
                    # Process the aggregated messages from all sources

            class Source(Executor):
                @handler(output_type=[Message])
                def handle_message(self, message: Message) -> None:
                    # Send a message to the target executor
                    self.send_message(message)

            workflow = (
                WorkflowBuilder()
                .add_fan_in_edges(
                    [Source(id="source1"), Source(id="source2")],
                    Target(id="target")
                )
                .build()
            )

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

    def add_chain(self, executors: Sequence[Executor]) -> "Self":
        """Add a chain of executors to the workflow.

        The output of each executor in the chain will be sent to the next executor in the chain.
        The input types of each executor must be compatible with the output types of the previous executor.

        Circles in the chain are not allowed, meaning the chain cannot have two executors with the same ID.

        Args:
            executors: A list of executors to be added to the chain.
        """
        for i in range(len(executors) - 1):
            self.add_edge(executors[i], executors[i + 1])
        return self

    def set_start_executor(self, executor: Executor | str) -> "Self":
        """Set the starting executor for the workflow.

        Args:
            executor: The starting executor, which can be an Executor instance or its ID.
        """
        self._start_executor = executor
        return self

    def set_max_iterations(self, max_iterations: int) -> "Self":
        """Set the maximum number of iterations for the workflow.

        Args:
            max_iterations: The maximum number of iterations the workflow will run for convergence.
        """
        self._max_iterations = max_iterations
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "Self":
        """Enable checkpointing with the specified storage.

        Args:
            checkpoint_storage: The checkpoint storage to use.
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def build(self) -> Workflow:
        """Build and return the constructed workflow.

        This method performs validation before building the workflow.

        Returns:
            A Workflow instance with the defined edges and starting executor.

        Raises:
            ValueError: If starting executor is not set.
            WorkflowValidationError: If workflow validation fails (includes EdgeDuplicationError,
                TypeCompatibilityError, and GraphConnectivityError subclasses).
        """
        if not self._start_executor:
            raise ValueError("Starting executor must be set before building the workflow.")

        validate_workflow_graph(self._edges, self._start_executor)

        context = InProcRunnerContext(self._checkpoint_storage)

        return Workflow(self._edges, self._start_executor, context, self._max_iterations)


# endregion
