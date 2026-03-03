# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import types
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any, Literal, overload

from .._types import ResponseStream
from ..observability import OtelAttr, capture_exception, create_workflow_span
from ._agent import WorkflowAgent
from ._checkpoint import CheckpointStorage
from ._const import DEFAULT_MAX_ITERATIONS, WORKFLOW_RUN_KWARGS_KEY
from ._edge import (
    EdgeGroup,
    FanOutEdgeGroup,
)
from ._events import (
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowRunState,
    _framework_event_origin,  # type: ignore
)
from ._executor import Executor
from ._model_utils import DictConvertible
from ._runner import Runner
from ._runner_context import RunnerContext
from ._state import State
from ._typing_utils import is_instance_of, try_coerce_to_type

logger = logging.getLogger(__name__)


class WorkflowRunResult(list[WorkflowEvent]):
    """Container for events generated during non-streaming workflow execution.

    ## Overview
    Represents the complete execution results of a workflow run, containing all events
    generated from start to idle state. Workflows produce outputs incrementally through
    ctx.yield_output() calls during execution.

    ## Event Structure
    Maintains separation between data-plane and control-plane events:
    - Data-plane events: Executor invocations, completions, outputs, and requests (in main list)
    - Control-plane events: Status timeline accessible via status_timeline() method

    ## Key Methods
    - get_outputs(): Extract all workflow outputs from the execution
    - get_request_info_events(): Retrieve external input requests made during execution
    - get_final_state(): Get the final workflow state (IDLE, IDLE_WITH_PENDING_REQUESTS, etc.)
    - status_timeline(): Access the complete status event history
    """

    def __init__(self, events: list[WorkflowEvent[Any]], status_events: list[WorkflowEvent[Any]] | None = None) -> None:
        super().__init__(events)
        self._status_events: list[WorkflowEvent[Any]] = status_events or []

    def get_outputs(self) -> list[Any]:
        """Get all outputs from the workflow run result.

        Returns:
            A list of outputs produced by the workflow during its execution.
        """
        return [event.data for event in self if event.type == "output"]

    def get_request_info_events(self) -> list[WorkflowEvent[Any]]:
        """Get all request info events from the workflow run result.

        Returns:
            A list of WorkflowEvent instances with type='request_info' found in the workflow run result.
        """
        return [event for event in self if event.type == "request_info"]

    def get_final_state(self) -> WorkflowRunState:
        """Return the final run state based on explicit status events.

        Returns the last status event's state observed. Raises if none were emitted.
        """
        if self._status_events:
            return self._status_events[-1].state  # type: ignore[return-value]
        raise RuntimeError(
            "Final state is unknown because no status event was emitted. "
            "Ensure your workflow entry points are used (which emit status events) "
            "or handle the absence of status explicitly."
        )

    def status_timeline(self) -> list[WorkflowEvent[Any]]:
        """Return the list of status events emitted during the run (control-plane)."""
        return list(self._status_events)


# region Workflow


class Workflow(DictConvertible):
    """A graph-based execution engine that orchestrates connected executors.

    ## Overview
    A workflow executes a directed graph of executors connected via edge groups using a
    Pregel-like model, running in supersteps until the graph becomes idle. Workflows
    are created using the WorkflowBuilder class - do not instantiate this class directly.

    ## Execution Model
    Executors run in synchronized supersteps where each executor:
    - Is invoked when it receives messages from connected edge groups
    - Can send messages to downstream executors via ctx.send_message()
    - Can yield workflow-level outputs via ctx.yield_output()
    - Can emit custom events via ctx.add_event()

    Messages between executors are delivered at the end of each superstep and are not
    visible in the event stream. Only workflow-level events (outputs, custom events)
    and status events are observable to callers.

    ## Input/Output Types
    Workflow types are discovered at runtime by inspecting:
    - Input types: From the start executor's input types
    - Output types: Union of all executors' workflow output types
    Access these via the input_types and output_types properties.

    ## Execution Methods
    The workflow provides two primary execution APIs, each supporting multiple scenarios:

    - **run()**: Execute to completion, returns WorkflowRunResult with all events
    - **run(..., stream=True)**: Returns ResponseStream yielding events as they occur

    Both methods support:
    - Initial workflow runs: Provide `message` parameter
    - Checkpoint restoration: Provide `checkpoint_id` (and optionally `checkpoint_storage`)
    - HIL continuation: Provide `responses` to continue after RequestInfoExecutor requests
    - Runtime checkpointing: Provide `checkpoint_storage` to enable/override checkpointing for this run

    ## State Management
    Workflow instances contain states and states are preserved across calls to `run`.
    To execute multiple independent runs, create separate Workflow instances via WorkflowBuilder.

    ## External Input Requests
    Executors within a workflow can request external input using `ctx.request_info()`:
    1. Executor calls `ctx.request_info()` to request input
    2. Executor implements `response_handler()` to process the response
    3. Requests are emitted as request_info events (WorkflowEvent with type='request_info') in the event stream
    4. Workflow enters IDLE_WITH_PENDING_REQUESTS state
    5. Caller handles requests and provides responses via `run(responses=...)` or `run(responses=..., stream=True)`
    6. Responses are routed to the requesting executors and response handlers are invoked

    ## Checkpointing
    Checkpointing can be configured at build time or runtime:

    Build-time (via WorkflowBuilder):
        workflow = WorkflowBuilder(checkpoint_storage=storage).build()

    Runtime (via run parameters):
        result = await workflow.run(message, checkpoint_storage=runtime_storage)

    When enabled, checkpoints are created at the end of each superstep, capturing:
    - Executor states
    - Messages in transit
    - Shared state
    Workflows can be paused and resumed across process restarts using checkpoint storage.

    ## Composition
    Workflows can be nested using WorkflowExecutor, which wraps a child workflow as an executor.
    The nested workflow's input/output types become part of the WorkflowExecutor's types.
    When invoked, the WorkflowExecutor runs the nested workflow to completion and processes its outputs.
    """

    def __init__(
        self,
        edge_groups: list[EdgeGroup],
        executors: dict[str, Executor],
        start_executor: Executor,
        runner_context: RunnerContext,
        name: str,
        description: str | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        output_executors: list[str] | None = None,
        **kwargs: Any,
    ):
        """Initialize the workflow with a list of edges.

        Args:
            edge_groups: A list of EdgeGroup instances that define the workflow edges.
            executors: A dictionary mapping executor IDs to Executor instances.
            start_executor: The starting executor for the workflow.
            runner_context: The RunnerContext instance to be used during workflow execution.
            max_iterations: The maximum number of iterations the workflow will run for convergence.
            name: A human-readable name for the workflow. This can be used to identify the workflow in
                checkpoints, and telemetry. If the workflow is built using WorkflowBuilder, this will be the
                name of the builder. This name should be unique across different workflow definitions for
                better observability and management.
            description: Optional description of what the workflow does. If the workflow is built using
                WorkflowBuilder, this will be the description of the builder.
            output_executors: Optional list of executor IDs whose outputs will be considered workflow outputs.
                              If None or empty, all executor outputs are treated as workflow outputs.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        self.edge_groups = list(edge_groups)
        self.executors = dict(executors)
        self.start_executor_id = start_executor.id
        self.max_iterations = max_iterations
        self.name = name
        self.description = description
        # Generate a unique ID for the workflow instance for monitoring purposes. This is not intended to be a
        # stable identifier across instances created from the same builder, for that, use the name field.
        self.id = str(uuid.uuid4())
        # Capture a canonical fingerprint of the workflow graph so checkpoints can assert they are resumed with
        # an equivalent topology.
        self.graph_signature = self._compute_graph_signature()
        self.graph_signature_hash = self._hash_graph_signature(self.graph_signature)

        # Output events (WorkflowEvent with type='output') from these executors are treated as workflow outputs.
        # If None or empty, all executor outputs are considered workflow outputs.
        self._output_executors = list(output_executors) if output_executors else list(self.executors.keys())

        # Store non-serializable runtime objects as private attributes
        self._runner_context = runner_context
        self._state = State()
        self._runner: Runner = Runner(
            self.edge_groups,
            self.executors,
            self._state,
            runner_context,
            self.name,
            self.graph_signature_hash,
            max_iterations=max_iterations,
        )

        # Flag to prevent concurrent workflow executions
        self._is_running = False

    def _ensure_not_running(self) -> None:
        """Ensure the workflow is not already running."""
        if self._is_running:
            raise RuntimeError("Workflow is already running. Concurrent executions are not allowed.")
        self._is_running = True

    def _reset_running_flag(self) -> None:
        """Reset the running flag."""
        self._is_running = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow definition into a JSON-ready dictionary."""
        data: dict[str, Any] = {
            "name": self.name,
            "id": self.id,
            "start_executor_id": self.start_executor_id,
            "max_iterations": self.max_iterations,
            "edge_groups": [group.to_dict() for group in self.edge_groups],
            "executors": {executor_id: executor.to_dict() for executor_id, executor in self.executors.items()},
            "output_executors": self._output_executors,
        }

        if self.description is not None:
            data["description"] = self.description

        executors_data: dict[str, dict[str, Any]] = data.get("executors", {})
        for executor_id, executor_payload in executors_data.items():
            if (
                isinstance(executor_payload, dict)
                and executor_payload.get("type") == "WorkflowExecutor"
                and "workflow" not in executor_payload
            ):
                original_executor = self.executors.get(executor_id)
                if original_executor and hasattr(original_executor, "workflow"):
                    from ._workflow_executor import WorkflowExecutor

                    if isinstance(original_executor, WorkflowExecutor):
                        executor_payload["workflow"] = original_executor.workflow.to_dict()

        return data

    def to_json(self) -> str:
        """Serialize the workflow definition to JSON."""
        return json.dumps(self.to_dict())

    def get_start_executor(self) -> Executor:
        """Get the starting executor of the workflow.

        Returns:
            The starting executor instance.
        """
        return self.executors[self.start_executor_id]

    def get_output_executors(self) -> list[Executor]:
        """Get the list of output executors in the workflow."""
        return [self.executors[executor_id] for executor_id in self._output_executors]

    def get_executors_list(self) -> list[Executor]:
        """Get the list of executors in the workflow."""
        return list(self.executors.values())

    async def _run_workflow_with_tracing(
        self,
        initial_executor_fn: Callable[[], Awaitable[None]] | None = None,
        reset_context: bool = True,
        streaming: bool = False,
        run_kwargs: dict[str, Any] | None = None,
    ) -> AsyncIterable[WorkflowEvent]:
        """Private method to run workflow with proper tracing.

        All workflow entry points create a NEW workflow span. It is the responsibility
        of external callers to maintain context across different workflow runs.

        Args:
            initial_executor_fn: Optional function to execute initial executor
            reset_context: Whether to reset the context for a new run
            streaming: Whether to enable streaming mode for agents
            run_kwargs: Optional kwargs to store in State for agent invocations

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        # Create workflow span that encompasses the entire execution
        attributes: dict[str, Any] = {OtelAttr.WORKFLOW_ID: self.id}
        if self.name:
            attributes[OtelAttr.WORKFLOW_NAME] = self.name
        if self.description:
            attributes[OtelAttr.WORKFLOW_DESCRIPTION] = self.description

        with create_workflow_span(
            OtelAttr.WORKFLOW_RUN_SPAN,
            attributes,
        ) as span:
            saw_request = False
            emitted_in_progress_pending = False
            try:
                # Add workflow started event (telemetry + surface state to consumers)
                span.add_event(OtelAttr.WORKFLOW_STARTED)
                # Emit explicit start/status events to the stream
                with _framework_event_origin():
                    started = WorkflowEvent.started()
                yield started
                with _framework_event_origin():
                    in_progress = WorkflowEvent.status(WorkflowRunState.IN_PROGRESS)
                yield in_progress

                # Reset context for a new run if supported
                if reset_context:
                    self._runner.reset_iteration_count()
                    self._runner.context.reset_for_new_run()
                    self._state.clear()

                # Store run kwargs in State so executors can access them.
                # Only overwrite when new kwargs are explicitly provided or state was
                # just cleared (fresh run). On continuation (reset_context=False) with
                # no new kwargs, preserve the kwargs from the original run.
                if run_kwargs is not None:
                    self._state.set(WORKFLOW_RUN_KWARGS_KEY, run_kwargs)
                elif reset_context:
                    self._state.set(WORKFLOW_RUN_KWARGS_KEY, {})
                self._state.commit()  # Commit immediately so kwargs are available

                # Set streaming mode after reset
                self._runner_context.set_streaming(streaming)

                # Execute initial setup if provided
                if initial_executor_fn:
                    await initial_executor_fn()

                # All executor executions happen within workflow span
                async for event in self._runner.run_until_convergence():
                    # Track request events for final status determination
                    if event.type == "request_info":
                        saw_request = True
                    yield event

                    if event.type == "request_info" and not emitted_in_progress_pending:
                        emitted_in_progress_pending = True
                        with _framework_event_origin():
                            pending_status = WorkflowEvent.status(WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS)
                        yield pending_status
                # Workflow runs until idle - emit final status based on whether requests are pending
                if saw_request:
                    with _framework_event_origin():
                        terminal_status = WorkflowEvent.status(WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)
                    yield terminal_status
                else:
                    with _framework_event_origin():
                        terminal_status = WorkflowEvent.status(WorkflowRunState.IDLE)
                    yield terminal_status

                span.add_event(OtelAttr.WORKFLOW_COMPLETED)
            except Exception as exc:
                # Drain any pending events (for example, executor_failed) before yielding failed event
                for event in await self._runner.context.drain_events():
                    yield event

                # Surface structured failure details before propagating exception
                details = WorkflowErrorDetails.from_exception(exc)
                with _framework_event_origin():
                    failed_event = WorkflowEvent.failed(details)
                yield failed_event
                with _framework_event_origin():
                    failed_status = WorkflowEvent.status(WorkflowRunState.FAILED)
                yield failed_status
                span.add_event(
                    name=OtelAttr.WORKFLOW_ERROR,
                    attributes={
                        "error.message": str(exc),
                        "error.type": type(exc).__name__,
                    },
                )
                capture_exception(span, exception=exc)
                raise

    async def _execute_with_message_or_checkpoint(
        self,
        message: Any | None,
        checkpoint_id: str | None,
        checkpoint_storage: CheckpointStorage | None,
    ) -> None:
        """Internal handler for executing workflow with either initial message or checkpoint restoration.

        Args:
            message: Initial message for the start executor (for new runs).
            checkpoint_id: ID of checkpoint to restore from (for resuming runs).
            checkpoint_storage: Runtime checkpoint storage.

        Raises:
            ValueError: If both message and checkpoint_id are None (nothing to execute).
        """
        # Validate that we have something to execute
        if message is None and checkpoint_id is None:
            raise ValueError("Must provide either 'message' or 'checkpoint_id'")

        # Handle checkpoint restoration
        if checkpoint_id is not None:
            has_checkpointing = self._runner.context.has_checkpointing()

            if not has_checkpointing and checkpoint_storage is None:
                raise ValueError(
                    "Cannot restore from checkpoint: either provide checkpoint_storage parameter "
                    "or build workflow with WorkflowBuilder(checkpoint_storage=checkpoint_storage)."
                )

            await self._runner.restore_from_checkpoint(checkpoint_id, checkpoint_storage)

        # Handle initial message
        elif message is not None:
            executor = self.get_start_executor()
            await executor.execute(
                message,
                [self.__class__.__name__],
                self._state,
                self._runner.context,
                trace_contexts=None,
                source_span_ids=None,
            )

    @overload
    def run(
        self,
        message: Any | None = None,
        *,
        stream: Literal[True],
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[WorkflowEvent, WorkflowRunResult]: ...

    @overload
    def run(
        self,
        message: Any | None = None,
        *,
        stream: Literal[False] = ...,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        include_status_events: bool = False,
        **kwargs: Any,
    ) -> Awaitable[WorkflowRunResult]: ...

    def run(
        self,
        message: Any | None = None,
        *,
        stream: bool = False,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        include_status_events: bool = False,
        **kwargs: Any,
    ) -> ResponseStream[WorkflowEvent, WorkflowRunResult] | Awaitable[WorkflowRunResult]:
        """Run the workflow, optionally streaming events.

        Unified interface supporting initial runs, checkpoint restoration, and
        sending responses to pending requests.

        Args:
            message: Initial message for the start executor. Required for new workflow runs.
                Mutually exclusive with responses.
            stream: If True, returns a ResponseStream of events with
                ``get_final_response()`` for the final WorkflowRunResult. If False
                (default), returns an awaitable WorkflowRunResult.
            responses: Responses to send for pending request info events, where keys are
                request IDs and values are the corresponding response data. Mutually
                exclusive with message. Can be combined with checkpoint_id to restore
                a checkpoint and send responses in a single call.
            checkpoint_id: ID of checkpoint to restore from. Can be used alone (resume
                from checkpoint), with message (not allowed), or with responses
                (restore then send responses).
            checkpoint_storage: Runtime checkpoint storage.
            include_status_events: Whether to include status events (non-streaming only).
            **kwargs: Additional keyword arguments to pass through to agent invocations.

        Returns:
            When stream=True: A ResponseStream[WorkflowEvent, WorkflowRunResult] for
                streaming events. Iterate for events, call get_final_response() for result.
            When stream=False: An Awaitable[WorkflowRunResult] with all events.

        Raises:
            ValueError: If parameter combination is invalid.
        """
        # Validate parameters and set running flag eagerly (before any async work)
        self._validate_run_params(message, responses, checkpoint_id)
        self._ensure_not_running()

        response_stream = ResponseStream[WorkflowEvent, WorkflowRunResult](
            self._run_core(
                message=message,
                responses=responses,
                checkpoint_id=checkpoint_id,
                checkpoint_storage=checkpoint_storage,
                streaming=stream,
                **kwargs,
            ),
            finalizer=functools.partial(self._finalize_events, include_status_events=include_status_events),
            cleanup_hooks=[
                functools.partial(self._run_cleanup, checkpoint_storage),
            ],
        )

        if stream:
            return response_stream
        return response_stream.get_final_response()

    async def _run_core(
        self,
        message: Any | None = None,
        *,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        streaming: bool = False,
        **kwargs: Any,
    ) -> AsyncIterable[WorkflowEvent]:
        """Single core execution path for both streaming and non-streaming modes.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        # Enable runtime checkpointing if storage provided
        if checkpoint_storage is not None:
            self._runner.context.set_runtime_checkpoint_storage(checkpoint_storage)

        initial_executor_fn, reset_context = self._resolve_execution_mode(
            message, responses, checkpoint_id, checkpoint_storage
        )

        async for event in self._run_workflow_with_tracing(
            initial_executor_fn=initial_executor_fn,
            reset_context=reset_context,
            streaming=streaming,
            # Empty **kwargs (no caller-provided kwargs) is collapsed to None so that
            # continuation calls without explicit kwargs preserve the original run's kwargs.
            # A non-empty kwargs dict (even one with empty values like {"key": {}})
            # is passed through and will overwrite stored kwargs.
            run_kwargs=kwargs if kwargs else None,
        ):
            if event.type == "output" and not self._should_yield_output_event(event):
                continue
            if event.type == "request_info" and event.request_id in (responses or {}):
                # Don't yield request_info events for which we have responses to send -
                # these are considered "handled". This prevents the caller from seeing
                # events for requests they are already responding to.
                # This usually happens when responses are provided with a checkpoint
                # (restore then send), because the request_info events are stored in the
                # checkpoint and would be emitted on restoration by the runner regardless
                # of if a response is provided or not.
                continue
            yield event

    async def _run_cleanup(self, checkpoint_storage: CheckpointStorage | None) -> None:
        """Cleanup hook called after stream consumption."""
        if checkpoint_storage is not None:
            self._runner.context.clear_runtime_checkpoint_storage()
        self._reset_running_flag()

    @staticmethod
    def _finalize_events(
        events: Sequence[WorkflowEvent],
        *,
        include_status_events: bool = False,
    ) -> WorkflowRunResult:
        """Convert collected workflow events into a WorkflowRunResult.

        Filters out internal events for non-streaming callers.
        """
        filtered: list[WorkflowEvent] = []
        status_events: list[WorkflowEvent] = []

        for ev in events:
            # Omit started events from result (telemetry-only)
            if ev.type == "started":
                continue
            # Track status; include inline only if explicitly requested
            if ev.type == "status":
                status_events.append(ev)
                if include_status_events:
                    filtered.append(ev)
                continue
            filtered.append(ev)

        return WorkflowRunResult(filtered, status_events)

    @staticmethod
    def _validate_run_params(
        message: Any | None,
        responses: dict[str, Any] | None,
        checkpoint_id: str | None,
    ) -> None:
        """Validate parameter combinations for run().

        Rules:
        - message and responses are mutually exclusive
        - message and checkpoint_id are mutually exclusive
        - At least one of message, responses, or checkpoint_id must be provided
        - responses + checkpoint_id is allowed (restore then send)
        """
        if message is not None and responses is not None:
            raise ValueError("Cannot provide both 'message' and 'responses'. Use one or the other.")

        if message is not None and checkpoint_id is not None:
            raise ValueError("Cannot provide both 'message' and 'checkpoint_id'. Use one or the other.")

        if message is None and responses is None and checkpoint_id is None:
            raise ValueError(
                "Must provide at least one of: 'message' (new run), 'responses' (send responses), "
                "or 'checkpoint_id' (resume from checkpoint)."
            )

    def _resolve_execution_mode(
        self,
        message: Any | None,
        responses: dict[str, Any] | None,
        checkpoint_id: str | None,
        checkpoint_storage: CheckpointStorage | None,
    ) -> tuple[Callable[[], Awaitable[None]], bool]:
        """Determine the initial executor function and reset_context flag based on parameters.

        Returns:
            A tuple of (initial_executor_fn, reset_context).
        """
        if responses is not None:
            if checkpoint_id is not None:
                # Combined: restore checkpoint then send responses
                initial_executor_fn = functools.partial(
                    self._restore_and_send_responses, checkpoint_id, checkpoint_storage, responses
                )
            else:
                # Send responses only (requires pending requests in workflow state)
                initial_executor_fn = functools.partial(self._send_responses_internal, responses)
            return initial_executor_fn, False
        # Regular run or checkpoint restoration
        initial_executor_fn = functools.partial(
            self._execute_with_message_or_checkpoint, message, checkpoint_id, checkpoint_storage
        )
        reset_context = message is not None and checkpoint_id is None
        return initial_executor_fn, reset_context

    async def _restore_and_send_responses(
        self,
        checkpoint_id: str,
        checkpoint_storage: CheckpointStorage | None,
        responses: dict[str, Any],
    ) -> None:
        """Restore from a checkpoint then send responses to pending requests.

        Args:
            checkpoint_id: ID of checkpoint to restore from.
            checkpoint_storage: Runtime checkpoint storage.
            responses: Responses to send after restoration.
        """
        has_checkpointing = self._runner.context.has_checkpointing()

        if not has_checkpointing and checkpoint_storage is None:
            raise ValueError(
                "Cannot restore from checkpoint: either provide checkpoint_storage parameter "
                "or build workflow with WorkflowBuilder.with_checkpointing(checkpoint_storage)."
            )

        await self._runner.restore_from_checkpoint(checkpoint_id, checkpoint_storage)
        await self._send_responses_internal(responses)

    async def _send_responses_internal(self, responses: dict[str, Any]) -> None:
        """Internal method to validate and send responses to the executors."""
        pending_requests = await self._runner_context.get_pending_request_info_events()
        if not pending_requests:
            raise RuntimeError("No pending requests found in workflow context.")

        # Validate and coerce responses against pending requests
        coerced_responses: dict[str, Any] = {}
        for request_id, response in responses.items():
            if request_id not in pending_requests:
                raise ValueError(f"Response provided for unknown request ID: {request_id}")
            pending_request = pending_requests[request_id]
            # Try to coerce raw values (e.g., dicts from JSON) to the expected type
            response = try_coerce_to_type(response, pending_request.response_type)
            if not is_instance_of(response, pending_request.response_type):
                raise ValueError(
                    f"Response type mismatch for request ID {request_id}: "
                    f"expected {pending_request.response_type}, got {type(response)}"
                )
            coerced_responses[request_id] = response

        await asyncio.gather(*[
            self._runner_context.send_request_info_response(request_id, response)
            for request_id, response in coerced_responses.items()
        ])

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

    def _should_yield_output_event(self, event: WorkflowEvent[Any]) -> bool:
        """Determine if an output event should be yielded as a workflow output.

        Args:
            event: The WorkflowEvent with type='output' to evaluate.

        Returns:
            True if the event should be yielded as a workflow output, False otherwise.
        """
        # If no specific output executors are defined, yield all outputs
        if not self._output_executors:
            return True

        # Check if the event's source executor is in the list of output executors
        return event.executor_id in self._output_executors

    # Graph signature helpers

    def _compute_graph_signature(self) -> dict[str, Any]:
        """Build a canonical fingerprint of the workflow graph topology for checkpoint validation.

        This creates a minimal, stable representation that captures only the structural
        elements of the workflow (executor types, edge relationships, topology) while
        ignoring data/state changes. Used to verify that a workflow's structure hasn't
        changed when resuming from checkpoints.
        """
        from ._workflow_executor import WorkflowExecutor

        executors_signature = {}
        for executor_id, executor in self.executors.items():
            executor_sig: Any = f"{executor.__class__.__module__}.{executor.__class__.__name__}"

            if isinstance(executor, WorkflowExecutor):
                executor_sig = {
                    "type": executor_sig,
                    "sub_workflow": executor.workflow.graph_signature,
                }

            executors_signature[executor_id] = executor_sig

        edge_groups_signature: list[dict[str, Any]] = []
        for group in self.edge_groups:
            edges = [
                {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "condition": getattr(edge, "condition_name", None),
                }
                for edge in group.edges
            ]
            edges.sort(key=lambda e: (e["source"], e["target"], e["condition"] or ""))

            group_info: dict[str, Any] = {
                "group_type": group.__class__.__name__,
                "sources": sorted(group.source_executor_ids),
                "targets": sorted(group.target_executor_ids),
                "edges": edges,
            }

            if isinstance(group, FanOutEdgeGroup):
                group_info["selection_func"] = getattr(group, "selection_func_name", None)

            edge_groups_signature.append(group_info)

        edge_groups_signature.sort(
            key=lambda info: (
                info["group_type"],
                tuple(info["sources"]),
                tuple(info["targets"]),
                json.dumps(info["edges"], sort_keys=True),
                json.dumps(info.get("selection_func")),
            )
        )

        return {
            "start_executor": self.start_executor_id,
            "executors": executors_signature,
            "edge_groups": edge_groups_signature,
        }

    @staticmethod
    def _hash_graph_signature(signature: dict[str, Any]) -> str:
        canonical = json.dumps(signature, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def input_types(self) -> list[type[Any] | types.UnionType]:
        """Get the input types of the workflow.

        The input types are the list of input types of the start executor.

        Returns:
            A list of input types that the workflow can accept.
        """
        start_executor = self.get_start_executor()
        return start_executor.input_types

    @property
    def output_types(self) -> list[type[Any] | types.UnionType]:
        """Get the output types of the workflow.

        The output types are the list of all workflow output types from executors
        that have workflow output types.

        Returns:
            A list of output types that the workflow can produce.
        """
        output_types: set[type[Any] | types.UnionType] = set()

        for executor in self.executors.values():
            workflow_output_types = executor.workflow_output_types
            output_types.update(workflow_output_types)

        return list(output_types)

    def as_agent(self, name: str | None = None) -> WorkflowAgent:
        """Create a WorkflowAgent that wraps this workflow.

        The returned agent converts standard agent inputs (strings, Message, or lists of these)
        into a list[Message] that is passed to the workflow's start executor. This conversion
        happens in WorkflowAgent._normalize_messages() which transforms:
        - str -> [Message(USER, [str])]
        - Message -> [Message]
        - list[str | Message] -> list[Message] (with string elements converted)

        The workflow's start executor must accept list[Message] as an input type, otherwise
        initialization will fail with a ValueError.

        Args:
            name: Optional name for the agent. If None, a default name will be generated.

        Returns:
            A WorkflowAgent instance that wraps this workflow.

        Raises:
            ValueError: If the workflow's start executor cannot handle list[Message] input.
        """
        # Import here to avoid circular imports
        from ._agent import WorkflowAgent

        return WorkflowAgent(workflow=self, name=name)
