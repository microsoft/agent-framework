# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from agent_framework._pydantic import AFBaseModel
from pydantic import Field

from ._checkpoint import CheckpointStorage
from ._const import DEFAULT_MAX_ITERATIONS
from ._edge import (
    Case,
    Default,
    EdgeGroup,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
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

if TYPE_CHECKING:  # Avoid runtime import cycles; enables proper type checking of as_agent return type
    from ._agent import WorkflowAgent


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


class Workflow(AFBaseModel):
    """A class representing a workflow that can be executed.

    This class is a placeholder for the workflow logic and does not implement any specific functionality.
    It serves as a base class for more complex workflows that can be defined in subclasses.
    """

    edge_groups: list[EdgeGroup] = Field(
        default_factory=list, description="List of edge groups that define the workflow edges"
    )
    executors: dict[str, Executor] = Field(
        default_factory=dict, description="Dictionary mapping executor IDs to Executor instances"
    )
    start_executor_id: str = Field(min_length=1, description="The ID of the starting executor for the workflow")
    max_iterations: int = Field(
        default=DEFAULT_MAX_ITERATIONS, description="Maximum number of iterations the workflow will run"
    )
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for this workflow instance"
    )

    def __init__(
        self,
        edge_groups: list[EdgeGroup],
        executors: dict[str, Executor],
        start_executor: Executor | str,
        runner_context: RunnerContext,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        **kwargs: Any,
    ):
        """Initialize the workflow with a list of edges.

        Args:
            edge_groups: A list of EdgeGroup instances that define the workflow edges.
            executors: A dictionary mapping executor IDs to Executor instances.
            start_executor: The starting executor for the workflow, which can be an Executor instance or its ID.
            runner_context: The RunnerContext instance to be used during workflow execution.
            max_iterations: The maximum number of iterations the workflow will run for convergence.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        # Convert start_executor to string ID if it's an Executor instance
        start_executor_id = start_executor.id if isinstance(start_executor, Executor) else start_executor

        id = str(uuid.uuid4())

        kwargs.update({
            "edge_groups": edge_groups,
            "executors": executors,
            "start_executor_id": start_executor_id,
            "max_iterations": max_iterations,
            "id": id,
        })

        super().__init__(**kwargs)

        # Store non-serializable runtime objects as private attributes
        self._runner_context = runner_context
        self._shared_state = SharedState()
        self._runner = Runner(
            self.edge_groups,
            self.executors,
            self._shared_state,
            runner_context,
            max_iterations=max_iterations,
            workflow_id=id,
        )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Custom serialization that properly handles WorkflowExecutor nested workflows."""
        data = super().model_dump(**kwargs)

        # Ensure WorkflowExecutor instances have their workflow field serialized
        if "executors" in data:
            executors_data = data["executors"]
            for executor_id, executor_data in executors_data.items():
                # Check if this is a WorkflowExecutor that might be missing its workflow field
                if (
                    isinstance(executor_data, dict)
                    and executor_data.get("type") == "WorkflowExecutor"
                    and "workflow" not in executor_data
                ):
                    # Get the original executor object and serialize its workflow
                    original_executor = self.executors.get(executor_id)
                    if original_executor and hasattr(original_executor, "workflow"):
                        from ._executor import WorkflowExecutor

                        if isinstance(original_executor, WorkflowExecutor):
                            executor_data["workflow"] = original_executor.workflow.model_dump(**kwargs)

        return data

    def model_dump_json(self, **kwargs: Any) -> str:
        """Custom JSON serialization that properly handles WorkflowExecutor nested workflows."""
        import json

        return json.dumps(self.model_dump(**kwargs))

    def get_start_executor(self) -> Executor:
        """Get the starting executor of the workflow.

        Returns:
            The starting executor instance.
        """
        return self.executors[self.start_executor_id]

    def get_executors_list(self) -> list[Executor]:
        """Get the list of executors in the workflow."""
        return list(self.executors.values())

    async def _run_workflow_with_tracing(
        self, initial_executor_fn: Callable[[], Awaitable[None]] | None = None, reset_context: bool = True
    ) -> AsyncIterable[WorkflowEvent]:
        """Private method to run workflow with proper tracing.

        All workflow entry points create a NEW workflow span. It is the responsibility
        of external callers to maintain context across different workflow runs.

        Args:
            initial_executor_fn: Optional function to execute initial executor
            reset_context: Whether to reset the context for a new run

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        # Import here to avoid circular imports
        from ._telemetry import workflow_tracer

        # Create workflow span that encompasses the entire execution
        with workflow_tracer.create_workflow_run_span(self):
            try:
                # Add workflow started event
                workflow_tracer.add_workflow_event("workflow.started")

                # Reset context for a new run if supported
                if reset_context:
                    self._runner.context.reset_for_new_run(self._shared_state)

                # Execute initial setup if provided
                if initial_executor_fn:
                    await initial_executor_fn()

                # All executor executions happen within workflow span
                async for event in self._runner.run_until_convergence():
                    yield event

                # Success
                workflow_tracer.add_workflow_event("workflow.completed")
            except Exception as e:
                workflow_tracer.add_workflow_error_event(e)
                raise

    async def run_streaming(self, message: Any) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with a starting message and stream events.

        Args:
            message: The message to be sent to the starting executor.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """

        async def initial_execution() -> None:
            executor = self.get_start_executor()
            await executor.execute(
                message,
                WorkflowContext(
                    executor.id,
                    [self.__class__.__name__],
                    self._shared_state,
                    self._runner.context,
                    trace_contexts=None,  # No parent trace context for workflow start
                    source_span_ids=None,  # No source span for workflow start
                ),
            )

        async for event in self._run_workflow_with_tracing(initial_executor_fn=initial_execution, reset_context=True):
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

        async def checkpoint_restoration() -> None:
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
                request_info_executor = self._find_request_info_executor()
                if request_info_executor:
                    for request_id, response_data in responses.items():
                        await request_info_executor.handle_response(
                            response_data,
                            request_id,
                            WorkflowContext(
                                request_info_executor.id,
                                [self.__class__.__name__],
                                self._shared_state,
                                self._runner.context,
                                trace_contexts=None,  # No parent trace context for new workflow span
                                source_span_ids=None,  # No source span for response handling
                            ),
                        )

        async for event in self._run_workflow_with_tracing(
            initial_executor_fn=checkpoint_restoration,
            reset_context=False,  # Don't reset context when resuming from checkpoint
        ):
            yield event

    async def send_responses_streaming(self, responses: dict[str, Any]) -> AsyncIterable[WorkflowEvent]:
        """Send responses back to the workflow and stream the events generated by the workflow.

        Args:
            responses: The responses to be sent back to the workflow, where keys are request IDs
                       and values are the corresponding response data.

        Yields:
            WorkflowEvent: The events generated during the workflow execution after sending the responses.
        """

        async def send_responses() -> None:
            request_info_executor = self._find_request_info_executor()
            if not request_info_executor:
                raise ValueError("No RequestInfoExecutor found in workflow.")

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
                        trace_contexts=None,  # No parent trace context for new workflow span
                        source_span_ids=None,  # No source span for response handling
                    ),
                )

            await asyncio.gather(*[
                _handle_response(response, request_id) for request_id, response in responses.items()
            ])

        async for event in self._run_workflow_with_tracing(
            initial_executor_fn=send_responses,
            reset_context=False,  # Don't reset context when sending responses
        ):
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
        if executor_id not in self.executors:
            raise ValueError(f"Executor with ID {executor_id} not found.")
        return self.executors[executor_id]

    def _find_request_info_executor(self) -> "RequestInfoExecutor | None":
        """Find the RequestInfoExecutor instance in this workflow.

        Returns:
            The RequestInfoExecutor instance if found, None otherwise.
        """
        from ._executor import RequestInfoExecutor

        for executor in self.executors.values():
            if isinstance(executor, RequestInfoExecutor):
                return executor
        return None

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
                    _Msg(
                        data=msg_data.get("data"),
                        source_id=source_id,
                        target_id=target_id,
                        trace_contexts=msg_data.get("trace_contexts"),
                        source_span_ids=msg_data.get("source_span_ids"),
                    )
                )

    def as_agent(self, name: str | None = None) -> "WorkflowAgent":
        """Create a WorkflowAgent that wraps this workflow.

        Args:
            name: Optional name for the agent. If None, a default name will be generated.

        Returns:
            A WorkflowAgent instance that wraps this workflow.
        """
        # Import here to avoid circular imports
        from ._agent import WorkflowAgent

        return WorkflowAgent(workflow=self, name=name)


# region WorkflowBuilder


class WorkflowBuilder:
    """A builder class for constructing workflows.

    This class provides methods to add edges and set the starting executor for the workflow.
    """

    def __init__(self, max_iterations: int = DEFAULT_MAX_ITERATIONS):
        """Initialize the WorkflowBuilder with an empty list of edges and no starting executor."""
        self._edge_groups: list[EdgeGroup] = []
        self._executors: dict[str, Executor] = {}
        self._start_executor: Executor | str | None = None
        self._checkpoint_storage: CheckpointStorage | None = None
        self._max_iterations: int = max_iterations

    def _add_executor(self, executor: Executor) -> str:
        """Add an executor to the map and return its ID."""
        self._executors[executor.id] = executor
        return executor.id

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
        source_id = self._add_executor(source)
        target_id = self._add_executor(target)
        self._edge_groups.append(SingleEdgeGroup(source_id, target_id, condition))
        return self

    def add_fan_out_edges(self, source: Executor, targets: Sequence[Executor]) -> "Self":
        """Add multiple edges to the workflow where messages from the source will be sent to all target.

        The output types of the source and the input types of the targets must be compatible.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.
        """
        source_id = self._add_executor(source)
        target_ids = [self._add_executor(target) for target in targets]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids))

        return self

    def add_switch_case_edge_group(self, source: Executor, cases: Sequence[Case | Default]) -> "Self":
        """Add an edge group that represents a switch-case statement.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to one of the target executors based on
        the provided conditions.

        Think of this as a switch statement where each target executor corresponds to a case.
        Each condition function will be evaluated in order, and the first one that returns True
        will determine which target executor receives the message.

        The last case (the default case) will receive messages that fall through all conditions
        (i.e., no condition matched).

        Args:
            source: The source executor of the edges.
            cases: A list of case objects that determine the target executor for each message.
        """
        source_id = self._add_executor(source)
        # Convert case data types to internal types that only uses target_id.
        internal_cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
        for case in cases:
            self._add_executor(case.target)
            if isinstance(case, Default):
                internal_cases.append(SwitchCaseEdgeGroupDefault(target_id=case.target.id))
            else:
                internal_cases.append(SwitchCaseEdgeGroupCase(condition=case.condition, target_id=case.target.id))
        self._edge_groups.append(SwitchCaseEdgeGroup(source_id, internal_cases))

        return self

    def add_multi_selection_edge_group(
        self,
        source: Executor,
        targets: Sequence[Executor],
        selection_func: Callable[[Any, list[str]], list[str]],
    ) -> "Self":
        """Add an edge group that represents a multi-selection execution model.

        The output types of the source and the input types of the targets must be compatible.
        Messages from the source executor will be sent to multiple target executors based on
        the provided selection function.

        The selection function should take a message and the name of the target executors,
        and return a list of indices indicating which target executors should receive the message.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.
            selection_func: A function that selects target executors for messages.
        """
        source_id = self._add_executor(source)
        target_ids = [self._add_executor(target) for target in targets]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids, selection_func))

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
        source_ids = [self._add_executor(source) for source in sources]
        target_id = self._add_executor(target)
        self._edge_groups.append(FanInEdgeGroup(source_ids, target_id))

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
        # Import here to avoid circular imports
        from ._telemetry import workflow_tracer

        # Create workflow build span that includes validation and workflow creation
        with workflow_tracer.create_workflow_build_span():
            try:
                # Add workflow build started event
                workflow_tracer.add_build_event("build.started")

                if not self._start_executor:
                    raise ValueError(
                        "Starting executor must be set using set_start_executor before building the workflow."
                    )

                # Perform validation before creating the workflow
                validate_workflow_graph(self._edge_groups, self._executors, self._start_executor)

                # Add validation completed event
                workflow_tracer.add_build_event("build.validation_completed")

                context = InProcRunnerContext(self._checkpoint_storage)

                # Create workflow instance after validation
                workflow = Workflow(
                    self._edge_groups, self._executors, self._start_executor, context, self._max_iterations
                )

                # Set workflow attributes on the span
                workflow_tracer.set_workflow_build_span_attributes(workflow)

                # Add workflow build completed event
                workflow_tracer.add_build_event("build.completed")

                return workflow

            except Exception as e:
                # The method already includes sufficient error info (error.message, error.type)
                workflow_tracer.add_build_error_event(e)
                raise
