# Copyright (c) Microsoft. All rights reserved.

import asyncio
import functools
import hashlib
import json
import logging
import sys
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any

from ..observability import OtelAttr, capture_exception, create_workflow_span
from ._agent import WorkflowAgent
from ._checkpoint import CheckpointStorage
from ._const import DEFAULT_MAX_ITERATIONS
from ._edge import (
    EdgeGroup,
    FanOutEdgeGroup,
)
from ._events import (
    RequestInfoEvent,
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowFailedEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
    _framework_event_origin,  # type: ignore
)
from ._executor import Executor
from ._model_utils import DictConvertible
from ._runner import Runner
from ._runner_context import RunnerContext
from ._shared_state import SharedState

if sys.version_info >= (3, 11):
    pass  # pragma: no cover
else:
    pass  # pragma: no cover


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

    def __init__(self, events: list[WorkflowEvent], status_events: list[WorkflowStatusEvent] | None = None) -> None:
        super().__init__(events)
        self._status_events: list[WorkflowStatusEvent] = status_events or []

    def get_outputs(self) -> list[Any]:
        """Get all outputs from the workflow run result.

        Returns:
            A list of outputs produced by the workflow during its execution.
        """
        return [event.data for event in self if isinstance(event, WorkflowOutputEvent)]

    def get_request_info_events(self) -> list[RequestInfoEvent]:
        """Get all request info events from the workflow run result.

        Returns:
            A list of RequestInfoEvent instances found in the workflow run result.
        """
        return [event for event in self if isinstance(event, RequestInfoEvent)]

    def get_final_state(self) -> WorkflowRunState:
        """Return the final run state based on explicit status events.

        Returns the last WorkflowStatusEvent.state observed. Raises if none were emitted.
        """
        if self._status_events:
            return self._status_events[-1].state  # type: ignore[return-value]
        raise RuntimeError(
            "Final state is unknown because no WorkflowStatusEvent was emitted. "
            "Ensure your workflow entry points are used (which emit status events) "
            "or handle the absence of status explicitly."
        )

    def status_timeline(self) -> list[WorkflowStatusEvent]:
        """Return the list of status events emitted during the run (control-plane)."""
        return list(self._status_events)


# region Workflow


class Workflow(DictConvertible):
    """A graph-based execution engine that orchestrates connected executors.

    ## Overview
    A workflow executes a directed graph of executors connected via edge groups using a Pregel-like model,
    running in supersteps until the graph becomes idle. Workflows are created using the
    WorkflowBuilder class - do not instantiate this class directly.

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
    - **run_stream()**: Returns async generator yielding events as they occur

    Both methods support:
    - Initial workflow runs: Provide `message` parameter
    - Checkpoint restoration: Provide `checkpoint_id` (and optionally `checkpoint_storage`)
    - HIL continuation: Provide `responses` to continue after RequestInfoExecutor requests
    - Runtime checkpointing: Provide `checkpoint_storage` to enable/override checkpointing for this run

    ## External Input Requests
    Executors within a workflow can request external input using `ctx.request_info()`:
    1. Executor calls `ctx.request_info()` to request input
    2. Executor implements `response_handler()` to process the response
    3. Requests are emitted as RequestInfoEvent instances in the event stream
    4. Workflow enters IDLE_WITH_PENDING_REQUESTS state
    5. Caller handles requests and provides responses via the `send_responses` or `send_responses_streaming` methods
    6. Responses are routed to the requesting executors and response handlers are invoked

    ## Checkpointing
    Checkpointing can be configured at build time or runtime:

    Build-time (via WorkflowBuilder):
        workflow = WorkflowBuilder().with_checkpointing(storage).build()

    Runtime (via run/run_stream parameters):
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
        start_executor: Executor | str,
        runner_context: RunnerContext,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ):
        """Initialize the workflow with a list of edges.

        Args:
            edge_groups: A list of EdgeGroup instances that define the workflow edges.
            executors: A dictionary mapping executor IDs to Executor instances.
            start_executor: The starting executor for the workflow, which can be an Executor instance or its ID.
            runner_context: The RunnerContext instance to be used during workflow execution.
            max_iterations: The maximum number of iterations the workflow will run for convergence.
            name: Optional human-readable name for the workflow.
            description: Optional description of what the workflow does.
            kwargs: Additional keyword arguments. Unused in this implementation.
        """
        # Convert start_executor to string ID if it's an Executor instance
        start_executor_id = start_executor.id if isinstance(start_executor, Executor) else start_executor

        self.edge_groups = list(edge_groups)
        self.executors = dict(executors)
        self.start_executor_id = start_executor_id
        self.max_iterations = max_iterations
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description

        # Store non-serializable runtime objects as private attributes
        self._runner_context = runner_context
        self._shared_state = SharedState()
        self._runner: Runner = Runner(
            self.edge_groups,
            self.executors,
            self._shared_state,
            runner_context,
            max_iterations=max_iterations,
            workflow_id=self.id,
        )

        # Flag to prevent concurrent workflow executions
        self._is_running = False

        # Capture a canonical fingerprint of the workflow graph so checkpoints
        # can assert they are resumed with an equivalent topology.
        self._graph_signature = self._compute_graph_signature()
        self._graph_signature_hash = self._hash_graph_signature(self._graph_signature)
        self._runner.graph_signature_hash = self._graph_signature_hash

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
            "id": self.id,
            "start_executor_id": self.start_executor_id,
            "max_iterations": self.max_iterations,
            "edge_groups": [group.to_dict() for group in self.edge_groups],
            "executors": {executor_id: executor.to_dict() for executor_id, executor in self.executors.items()},
        }

        # Add optional name and description if provided
        if self.name is not None:
            data["name"] = self.name
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

    def get_executors_list(self) -> list[Executor]:
        """Get the list of executors in the workflow."""
        return list(self.executors.values())

    async def _run_workflow_with_tracing(
        self,
        initial_executor_fn: Callable[[], Awaitable[None]] | None = None,
        reset_context: bool = True,
        streaming: bool = False,
    ) -> AsyncIterable[WorkflowEvent]:
        """Private method to run workflow with proper tracing.

        All workflow entry points create a NEW workflow span. It is the responsibility
        of external callers to maintain context across different workflow runs.

        Args:
            initial_executor_fn: Optional function to execute initial executor
            reset_context: Whether to reset the context for a new run
            streaming: Whether to enable streaming mode for agents

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
                    started = WorkflowStartedEvent()
                yield started
                with _framework_event_origin():
                    in_progress = WorkflowStatusEvent(WorkflowRunState.IN_PROGRESS)
                yield in_progress

                # Reset context for a new run if supported
                if reset_context:
                    self._runner.reset_iteration_count()
                    self._runner.context.reset_for_new_run()
                    await self._shared_state.clear()

                # Set streaming mode after reset
                self._runner_context.set_streaming(streaming)

                # Execute initial setup if provided
                if initial_executor_fn:
                    await initial_executor_fn()

                # All executor executions happen within workflow span
                async for event in self._runner.run_until_convergence():
                    # Track request events for final status determination
                    if isinstance(event, RequestInfoEvent):
                        saw_request = True
                    yield event

                    if isinstance(event, RequestInfoEvent) and not emitted_in_progress_pending:
                        emitted_in_progress_pending = True
                        with _framework_event_origin():
                            pending_status = WorkflowStatusEvent(WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS)
                        yield pending_status

                # Workflow runs until idle - emit final status based on whether requests are pending
                if saw_request:
                    with _framework_event_origin():
                        terminal_status = WorkflowStatusEvent(WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)
                    yield terminal_status
                else:
                    with _framework_event_origin():
                        terminal_status = WorkflowStatusEvent(WorkflowRunState.IDLE)
                    yield terminal_status

                span.add_event(OtelAttr.WORKFLOW_COMPLETED)
            except Exception as exc:
                # Surface structured failure details before propagating exception
                details = WorkflowErrorDetails.from_exception(exc)
                with _framework_event_origin():
                    failed_event = WorkflowFailedEvent(details)
                yield failed_event
                with _framework_event_origin():
                    failed_status = WorkflowStatusEvent(WorkflowRunState.FAILED)
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
                    "or build workflow with WorkflowBuilder.with_checkpointing(checkpoint_storage)."
                )

            restored = await self._runner.restore_from_checkpoint(checkpoint_id, checkpoint_storage)

            if not restored:
                raise RuntimeError(f"Failed to restore from checkpoint: {checkpoint_id}")

        # Handle initial message
        elif message is not None:
            executor = self.get_start_executor()
            await executor.execute(
                message,
                [self.__class__.__name__],
                self._shared_state,
                self._runner.context,
                trace_contexts=None,
                source_span_ids=None,
            )

    async def run_stream(
        self,
        message: Any | None = None,
        *,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow and stream events.

        Unified streaming interface supporting initial runs and checkpoint restoration.

        Args:
            message: Initial message for the start executor. Required for new workflow runs,
                    should be None when resuming from checkpoint.
            checkpoint_id: ID of checkpoint to restore from. If provided, the workflow resumes
                          from this checkpoint instead of starting fresh. When resuming, checkpoint_storage
                          must be provided (either at build time or runtime) to load the checkpoint.
            checkpoint_storage: Runtime checkpoint storage with two behaviors:
                               - With checkpoint_id: Used to load and restore the specified checkpoint
                               - Without checkpoint_id: Enables checkpointing for this run, overriding
                                 build-time configuration

        Yields:
            WorkflowEvent: Events generated during workflow execution.

        Raises:
            ValueError: If both message and checkpoint_id are provided, or if neither is provided.
            ValueError: If checkpoint_id is provided but no checkpoint storage is available
                       (neither at build time nor runtime).
            RuntimeError: If checkpoint restoration fails.

        Examples:
            Initial run:

            .. code-block:: python

                async for event in workflow.run_stream("start message"):
                    process(event)

            Enable checkpointing at runtime:

            .. code-block:: python

                storage = FileCheckpointStorage("./checkpoints")
                async for event in workflow.run_stream("start", checkpoint_storage=storage):
                    process(event)

            Resume from checkpoint (storage provided at build time):

            .. code-block:: python

                async for event in workflow.run_stream(checkpoint_id="cp_123"):
                    process(event)

            Resume from checkpoint (storage provided at runtime):

            .. code-block:: python

                storage = FileCheckpointStorage("./checkpoints")
                async for event in workflow.run_stream(checkpoint_id="cp_123", checkpoint_storage=storage):
                    process(event)
        """
        # Validate mutually exclusive parameters BEFORE setting running flag
        if message is not None and checkpoint_id is not None:
            raise ValueError("Cannot provide both 'message' and 'checkpoint_id'. Use one or the other.")

        if message is None and checkpoint_id is None:
            raise ValueError("Must provide either 'message' (new run) or 'checkpoint_id' (resume).")

        self._ensure_not_running()

        # Enable runtime checkpointing if storage provided
        # Two cases:
        # 1. checkpoint_storage + checkpoint_id: Load checkpoint from this storage and resume
        # 2. checkpoint_storage without checkpoint_id: Enable checkpointing for this run
        if checkpoint_storage is not None:
            self._runner.context.set_runtime_checkpoint_storage(checkpoint_storage)

        try:
            # Reset context only for new runs (not checkpoint restoration)
            reset_context = message is not None and checkpoint_id is None

            async for event in self._run_workflow_with_tracing(
                initial_executor_fn=functools.partial(
                    self._execute_with_message_or_checkpoint, message, checkpoint_id, checkpoint_storage
                ),
                reset_context=reset_context,
                streaming=True,
            ):
                yield event
        finally:
            if checkpoint_storage is not None:
                self._runner.context.clear_runtime_checkpoint_storage()
            self._reset_running_flag()

    async def send_responses_streaming(self, responses: dict[str, Any]) -> AsyncIterable[WorkflowEvent]:
        """Send responses back to the workflow and stream the events generated by the workflow.

        Args:
            responses: The responses to be sent back to the workflow, where keys are request IDs
                       and values are the corresponding response data.

        Yields:
            WorkflowEvent: The events generated during the workflow execution after sending the responses.
        """
        self._ensure_not_running()
        try:
            async for event in self._run_workflow_with_tracing(
                initial_executor_fn=functools.partial(self._send_responses_internal, responses),
                reset_context=False,  # Don't reset context when sending responses
                streaming=True,
            ):
                yield event
        finally:
            self._reset_running_flag()

    async def run(
        self,
        message: Any | None = None,
        *,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        include_status_events: bool = False,
    ) -> WorkflowRunResult:
        """Run the workflow to completion and return all events.

        Unified non-streaming interface supporting initial runs and checkpoint restoration.

        Args:
            message: Initial message for the start executor. Required for new workflow runs,
                    should be None when resuming from checkpoint.
            checkpoint_id: ID of checkpoint to restore from. If provided, the workflow resumes
                          from this checkpoint instead of starting fresh. When resuming, checkpoint_storage
                          must be provided (either at build time or runtime) to load the checkpoint.
            checkpoint_storage: Runtime checkpoint storage with two behaviors:
                               - With checkpoint_id: Used to load and restore the specified checkpoint
                               - Without checkpoint_id: Enables checkpointing for this run, overriding
                                 build-time configuration
            include_status_events: Whether to include WorkflowStatusEvent instances in the result list.

        Returns:
            A WorkflowRunResult instance containing events generated during workflow execution.

        Raises:
            ValueError: If both message and checkpoint_id are provided, or if neither is provided.
            ValueError: If checkpoint_id is provided but no checkpoint storage is available
                       (neither at build time nor runtime).
            RuntimeError: If checkpoint restoration fails.

        Examples:
            Initial run:

            .. code-block:: python

                result = await workflow.run("start message")
                outputs = result.get_outputs()

            Enable checkpointing at runtime:

            .. code-block:: python

                storage = FileCheckpointStorage("./checkpoints")
                result = await workflow.run("start", checkpoint_storage=storage)

            Resume from checkpoint (storage provided at build time):

            .. code-block:: python

                result = await workflow.run(checkpoint_id="cp_123")

            Resume from checkpoint (storage provided at runtime):

            .. code-block:: python

                storage = FileCheckpointStorage("./checkpoints")
                result = await workflow.run(checkpoint_id="cp_123", checkpoint_storage=storage)
        """
        # Validate mutually exclusive parameters BEFORE setting running flag
        if message is not None and checkpoint_id is not None:
            raise ValueError("Cannot provide both 'message' and 'checkpoint_id'. Use one or the other.")

        if message is None and checkpoint_id is None:
            raise ValueError("Must provide either 'message' (new run) or 'checkpoint_id' (resume).")

        self._ensure_not_running()

        # Enable runtime checkpointing if storage provided
        if checkpoint_storage is not None:
            self._runner.context.set_runtime_checkpoint_storage(checkpoint_storage)

        try:
            # Reset context only for new runs (not checkpoint restoration)
            reset_context = message is not None and checkpoint_id is None

            raw_events = [
                event
                async for event in self._run_workflow_with_tracing(
                    initial_executor_fn=functools.partial(
                        self._execute_with_message_or_checkpoint, message, checkpoint_id, checkpoint_storage
                    ),
                    reset_context=reset_context,
                )
            ]
        finally:
            if checkpoint_storage is not None:
                self._runner.context.clear_runtime_checkpoint_storage()
            self._reset_running_flag()

        # Filter events for non-streaming mode
        filtered: list[WorkflowEvent] = []
        status_events: list[WorkflowStatusEvent] = []

        for ev in raw_events:
            # Omit WorkflowStartedEvent from non-streaming (telemetry-only)
            if isinstance(ev, WorkflowStartedEvent):
                continue
            # Track status; include inline only if explicitly requested
            if isinstance(ev, WorkflowStatusEvent):
                status_events.append(ev)
                if include_status_events:
                    filtered.append(ev)
                continue
            filtered.append(ev)

        return WorkflowRunResult(filtered, status_events)

    async def send_responses(self, responses: dict[str, Any]) -> WorkflowRunResult:
        """Send responses back to the workflow.

        Args:
            responses: A dictionary where keys are request IDs and values are the corresponding response data.

        Returns:
            A WorkflowRunResult instance containing a list of events generated during the workflow execution.
        """
        self._ensure_not_running()
        try:
            events = [
                event
                async for event in self._run_workflow_with_tracing(
                    initial_executor_fn=functools.partial(self._send_responses_internal, responses),
                    reset_context=False,  # Don't reset context when sending responses
                )
            ]
            status_events = [e for e in events if isinstance(e, WorkflowStatusEvent)]
            filtered_events = [e for e in events if not isinstance(e, (WorkflowStatusEvent, WorkflowStartedEvent))]
            return WorkflowRunResult(filtered_events, status_events)
        finally:
            self._reset_running_flag()

    async def _send_responses_internal(self, responses: dict[str, Any]) -> None:
        """Internal method to validate and send responses to the executors."""
        pending_requests = await self._runner_context.get_pending_request_info_events()
        if not pending_requests:
            raise RuntimeError("No pending requests found in workflow context.")

        # Validate responses against pending requests
        for request_id, response in responses.items():
            if request_id not in pending_requests:
                raise ValueError(f"Response provided for unknown request ID: {request_id}")
            pending_request = pending_requests[request_id]
            if not isinstance(response, pending_request.response_type):
                raise ValueError(
                    f"Response type mismatch for request ID {request_id}: "
                    f"expected {pending_request.response_type}, got {type(response)}"
                )

        await asyncio.gather(*[
            self._runner_context.send_request_info_response(request_id, response)
            for request_id, response in responses.items()
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

    # Graph signature helpers

    def _compute_graph_signature(self) -> dict[str, Any]:
        """Build a canonical fingerprint of the workflow graph topology for checkpoint validation.

        This creates a minimal, stable representation that captures only the structural
        elements of the workflow (executor types, edge relationships, topology) while
        ignoring data/state changes. Used to verify that a workflow's structure hasn't
        changed when resuming from checkpoints.
        """
        executors_signature = {
            executor_id: f"{executor.__class__.__module__}.{executor.__class__.__name__}"
            for executor_id, executor in self.executors.items()
        }

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
            "max_iterations": self.max_iterations,
        }

    @staticmethod
    def _hash_graph_signature(signature: dict[str, Any]) -> str:
        canonical = json.dumps(signature, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def graph_signature_hash(self) -> str:
        return self._graph_signature_hash

    @property
    def input_types(self) -> list[type[Any]]:
        """Get the input types of the workflow.

        The input types are the list of input types of the start executor.

        Returns:
            A list of input types that the workflow can accept.
        """
        start_executor = self.get_start_executor()
        return start_executor.input_types

    @property
    def output_types(self) -> list[type[Any]]:
        """Get the output types of the workflow.

        The output types are the list of all workflow output types from executors
        that have workflow output types.

        Returns:
            A list of output types that the workflow can produce.
        """
        output_types: set[type[Any]] = set()

        for executor in self.executors.values():
            workflow_output_types = executor.workflow_output_types
            output_types.update(workflow_output_types)

        return list(output_types)

    def as_agent(self, name: str | None = None) -> WorkflowAgent:
        """Create a WorkflowAgent that wraps this workflow.

        The returned agent converts standard agent inputs (strings, ChatMessage, or lists of these)
        into a list[ChatMessage] that is passed to the workflow's start executor. This conversion
        happens in WorkflowAgent._normalize_messages() which transforms:
        - str -> [ChatMessage(role=USER, text=str)]
        - ChatMessage -> [ChatMessage]
        - list[str | ChatMessage] -> list[ChatMessage] (with string elements converted)

        The workflow's start executor must accept list[ChatMessage] as an input type, otherwise
        initialization will fail with a ValueError.

        Args:
            name: Optional name for the agent. If None, a default name will be generated.

        Returns:
            A WorkflowAgent instance that wraps this workflow.

        Raises:
            ValueError: If the workflow's start executor cannot handle list[ChatMessage] input.
        """
        # Import here to avoid circular imports
        from ._agent import WorkflowAgent

        return WorkflowAgent(workflow=self, name=name)
