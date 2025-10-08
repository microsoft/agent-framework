# Copyright (c) Microsoft. All rights reserved.

import asyncio
import hashlib
import json
import logging
import sys
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any

from .._agents import AgentProtocol
from ..observability import OtelAttr, capture_exception, create_workflow_span
from ._agent import WorkflowAgent
from ._agent_executor import AgentExecutor
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
from ._request_info_executor import RequestInfoExecutor
from ._runner import Runner
from ._runner_context import InProcRunnerContext, RunnerContext
from ._shared_state import SharedState
from ._validation import validate_workflow_graph
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


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
    - run(): Execute to completion, returns WorkflowRunResult with all events
    - run_stream(): Returns async generator yielding events as they occur
    - run_from_checkpoint(): Resume from a saved checkpoint
    - run_stream_from_checkpoint(): Resume from checkpoint with streaming

    ## External Input Requests
    Workflows can request external input using a RequestInfoExecutor:
    1. Executor connects to RequestInfoExecutor via edge group and back to itself
    2. Executor sends RequestInfoMessage to RequestInfoExecutor
    3. RequestInfoExecutor emits RequestInfoEvent and workflow enters IDLE_WITH_PENDING_REQUESTS
    4. Caller handles requests and uses send_responses()/send_responses_streaming() to continue

    ## Checkpointing
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

        id = str(uuid.uuid4())

        self.edge_groups = list(edge_groups)
        self.executors = dict(executors)
        self.start_executor_id = start_executor_id
        self.max_iterations = max_iterations
        self.id = id
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
            workflow_id=id,
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
                    self._runner.context.reset_for_new_run(self._shared_state)

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

    async def run_stream(self, message: Any) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with a starting message and stream events.

        Args:
            message: The message to be sent to the starting executor.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        self._ensure_not_running()
        try:

            async def initial_execution() -> None:
                executor = self.get_start_executor()
                await executor.execute(
                    message,
                    [self.__class__.__name__],  # source_executor_ids
                    self._shared_state,  # shared_state
                    self._runner.context,  # runner_context
                    trace_contexts=None,  # No parent trace context for workflow start
                    source_span_ids=None,  # No source span for workflow start
                )

            async for event in self._run_workflow_with_tracing(
                initial_executor_fn=initial_execution, reset_context=True, streaming=True
            ):
                yield event
        finally:
            self._reset_running_flag()

    async def run_stream_from_checkpoint(
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
        self._ensure_not_running()
        try:

            async def checkpoint_restoration() -> None:
                has_checkpointing = self._runner.context.has_checkpointing()

                if not has_checkpointing and checkpoint_storage is None:
                    raise ValueError(
                        "Cannot restore from checkpoint: either provide checkpoint_storage parameter "
                        "or build workflow with WorkflowBuilder.with_checkpointing(checkpoint_storage)."
                    )

                restored = await self._runner.restore_from_checkpoint(checkpoint_id, checkpoint_storage)

                if not restored:
                    raise RuntimeError(f"Failed to restore from checkpoint: {checkpoint_id}")

                # Process any pending messages from the checkpoint first
                # This ensures that RequestInfoExecutor state is properly populated
                # before we try to handle responses
                if await self._runner.context.has_messages():
                    # Run one iteration to process pending messages
                    # This will populate RequestInfoExecutor._request_events properly
                    await self._runner._run_iteration()  # type: ignore

                if responses:
                    request_info_executor = self._find_request_info_executor()
                    if request_info_executor:
                        for request_id, response_data in responses.items():
                            ctx: WorkflowContext[Any] = WorkflowContext(
                                request_info_executor.id,
                                [self.__class__.__name__],
                                self._shared_state,
                                self._runner.context,
                                trace_contexts=None,  # No parent trace context for new workflow span
                                source_span_ids=None,  # No source span for response handling
                            )

                            if not await request_info_executor.has_pending_request(request_id, ctx):
                                logger.debug(
                                    f"Skipping pre-supplied response for request {request_id}; "
                                    f"no pending request found after checkpoint restoration."
                                )
                                continue

                            await request_info_executor.handle_response(
                                response_data,
                                request_id,
                                ctx,
                            )

            async for event in self._run_workflow_with_tracing(
                initial_executor_fn=checkpoint_restoration,
                reset_context=False,  # Don't reset context when resuming from checkpoint
                streaming=True,
            ):
                yield event
        finally:
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
                streaming=True,
            ):
                yield event
        finally:
            self._reset_running_flag()

    async def run(self, message: Any, *, include_status_events: bool = False) -> WorkflowRunResult:
        """Run the workflow with the given message.

        Args:
            message: The message to be processed by the workflow.
            include_status_events: Whether to include WorkflowStatusEvent instances in the result list.

        Returns:
            A WorkflowRunResult instance containing a list of events generated during the workflow execution.
        """
        self._ensure_not_running()
        try:

            async def initial_execution() -> None:
                executor = self.get_start_executor()
                await executor.execute(
                    message,
                    [self.__class__.__name__],  # source_executor_ids
                    self._shared_state,  # shared_state
                    self._runner.context,  # runner_context
                    trace_contexts=None,  # No parent trace context for workflow start
                    source_span_ids=None,  # No source span for workflow start
                )

            raw_events = [
                event
                async for event in self._run_workflow_with_tracing(
                    initial_executor_fn=initial_execution,
                    reset_context=True,
                )
            ]
        finally:
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
        self._ensure_not_running()
        try:

            async def checkpoint_restoration() -> None:
                has_checkpointing = self._runner.context.has_checkpointing()

                if not has_checkpointing and checkpoint_storage is None:
                    raise ValueError(
                        "Cannot restore from checkpoint: either provide checkpoint_storage parameter "
                        "or build workflow with WorkflowBuilder.with_checkpointing(checkpoint_storage)."
                    )

                restored = await self._runner.restore_from_checkpoint(checkpoint_id, checkpoint_storage)

                if not restored:
                    raise RuntimeError(f"Failed to restore from checkpoint: {checkpoint_id}")

                # Process any pending messages from the checkpoint first
                # This ensures that RequestInfoExecutor state is properly populated
                # before we try to handle responses
                if await self._runner.context.has_messages():
                    # Run one iteration to process pending messages
                    # This will populate RequestInfoExecutor._request_events properly
                    await self._runner._run_iteration()  # type: ignore

                if responses:
                    request_info_executor = self._find_request_info_executor()
                    if request_info_executor:
                        for request_id, response_data in responses.items():
                            ctx: WorkflowContext[Any] = WorkflowContext(
                                request_info_executor.id,
                                [self.__class__.__name__],
                                self._shared_state,
                                self._runner.context,
                                trace_contexts=None,  # No parent trace context for new workflow span
                                source_span_ids=None,  # No source span for response handling
                            )

                            if not await request_info_executor.has_pending_request(request_id, ctx):
                                logger.debug(
                                    f"Skipping pre-supplied response for request {request_id}; "
                                    f"no pending request found after checkpoint restoration."
                                )
                                continue

                            await request_info_executor.handle_response(
                                response_data,
                                request_id,
                                ctx,
                            )

            events = [
                event
                async for event in self._run_workflow_with_tracing(
                    initial_executor_fn=checkpoint_restoration,
                    reset_context=False,  # Don't reset context when resuming from checkpoint
                )
            ]
            status_events = [e for e in events if isinstance(e, WorkflowStatusEvent)]
            filtered_events = [e for e in events if not isinstance(e, (WorkflowStatusEvent, WorkflowStartedEvent))]
            return WorkflowRunResult(filtered_events, status_events)
        finally:
            self._reset_running_flag()

    async def send_responses(self, responses: dict[str, Any]) -> WorkflowRunResult:
        """Send responses back to the workflow.

        Args:
            responses: A dictionary where keys are request IDs and values are the corresponding response data.

        Returns:
            A WorkflowRunResult instance containing a list of events generated during the workflow execution.
        """
        self._ensure_not_running()
        try:

            async def send_responses_internal() -> None:
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

            events = [
                event
                async for event in self._run_workflow_with_tracing(
                    initial_executor_fn=send_responses_internal,
                    reset_context=False,  # Don't reset context when sending responses
                )
            ]
            status_events = [e for e in events if isinstance(e, WorkflowStatusEvent)]
            filtered_events = [e for e in events if not isinstance(e, (WorkflowStatusEvent, WorkflowStartedEvent))]
            return WorkflowRunResult(filtered_events, status_events)
        finally:
            self._reset_running_flag()

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

    def _find_request_info_executor(self) -> RequestInfoExecutor | None:
        """Find the RequestInfoExecutor instance in this workflow.

        Returns:
            The RequestInfoExecutor instance if found, None otherwise.
        """
        from ._request_info_executor import RequestInfoExecutor

        for executor in self.executors.values():
            if isinstance(executor, RequestInfoExecutor):
                return executor
        return None

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

    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        name: str | None = None,
        description: str | None = None,
    ):
        """Initialize the WorkflowBuilder with an empty list of edges and no starting executor.

        Args:
            max_iterations: Maximum number of iterations for workflow convergence.
            name: Optional human-readable name for the workflow.
            description: Optional description of what the workflow does.
        """
        self._edge_groups: list[EdgeGroup] = []
        self._executors: dict[str, Executor] = {}
        self._duplicate_executor_ids: set[str] = set()
        self._start_executor: Executor | str | None = None
        self._checkpoint_storage: CheckpointStorage | None = None
        self._max_iterations: int = max_iterations
        self._name: str | None = name
        self._description: str | None = description
        # Maps underlying AgentProtocol object id -> wrapped Executor so we reuse the same wrapper
        # across set_start_executor / add_edge calls. Without this, unnamed agents (which receive
        # random UUID based executor ids) end up wrapped multiple times, giving different ids for
        # the start node vs edge nodes and triggering a GraphConnectivityError during validation.
        self._agent_wrappers: dict[int, Executor] = {}

    # Agents auto-wrapped by builder now always stream incremental updates.

    def _add_executor(self, executor: Executor) -> str:
        """Add an executor to the map and return its ID."""
        existing = self._executors.get(executor.id)
        if existing is not None and existing is not executor:
            self._duplicate_executor_ids.add(executor.id)
        else:
            self._executors[executor.id] = executor
        return executor.id

    def _maybe_wrap_agent(
        self,
        candidate: Executor | AgentProtocol,
        agent_thread: Any | None = None,
        output_response: bool = False,
        executor_id: str | None = None,
    ) -> Executor:
        """If the provided object implements AgentProtocol, wrap it in an AgentExecutor.

        This allows fluent builder APIs to directly accept agents instead of
        requiring callers to manually instantiate AgentExecutor.

        Args:
            candidate: The executor or agent to wrap.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            output_response: Whether to yield an AgentRunResponse as a workflow output when the agent completes.
            executor_id: A unique identifier for the executor. If None, the agent's name will be used if available.
        """
        try:  # Local import to avoid hard dependency at import time
            from agent_framework import AgentProtocol  # type: ignore
        except Exception:  # pragma: no cover - defensive
            AgentProtocol = object  # type: ignore

        if isinstance(candidate, Executor):  # Already an executor
            return candidate
        if isinstance(candidate, AgentProtocol):  # type: ignore[arg-type]
            # Reuse existing wrapper for the same agent instance if present
            agent_instance_id = id(candidate)
            existing = self._agent_wrappers.get(agent_instance_id)
            if existing is not None:
                return existing
            # Use agent name if available and unique among current executors
            name = getattr(candidate, "name", None)
            proposed_id: str | None = executor_id
            if proposed_id is None and name:
                proposed_id = str(name)
                if proposed_id in self._executors:
                    raise ValueError(
                        f"Duplicate executor ID '{proposed_id}' from agent name. "
                        "Agent names must be unique within a workflow."
                    )
            wrapper = AgentExecutor(
                candidate,
                agent_thread=agent_thread,
                output_response=output_response,
                id=proposed_id,
            )
            self._agent_wrappers[agent_instance_id] = wrapper
            return wrapper
        raise TypeError(
            f"WorkflowBuilder expected an Executor or AgentProtocol instance; got {type(candidate).__name__}."
        )

    def add_agent(
        self,
        agent: AgentProtocol,
        agent_thread: Any | None = None,
        output_response: bool = False,
        id: str | None = None,
    ) -> Self:
        """Add an agent to the workflow by wrapping it in an AgentExecutor.

        This method creates an AgentExecutor that wraps the agent with the given parameters
        and ensures that subsequent uses of the same agent instance in other builder methods
        (like add_edge, set_start_executor, etc.) will reuse the same wrapped executor.

        Note: Agents adapt their behavior based on how the workflow is executed:
        - run_stream(): Agents emit incremental AgentRunUpdateEvent events as tokens are produced
        - run(): Agents emit a single AgentRunEvent containing the complete response

        Args:
            agent: The agent to add to the workflow.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            output_response: Whether to yield an AgentRunResponse as a workflow output when the agent completes.
            id: A unique identifier for the executor. If None, the agent's name will be used if available.

        Returns:
            The WorkflowBuilder instance (for method chaining).

        Raises:
            ValueError: If the provided id or agent name conflicts with an existing executor.
        """
        executor = self._maybe_wrap_agent(
            agent, agent_thread=agent_thread, output_response=output_response, executor_id=id
        )
        self._add_executor(executor)
        return self

    def add_edge(
        self,
        source: Executor | AgentProtocol,
        target: Executor | AgentProtocol,
        condition: Callable[[Any], bool] | None = None,
    ) -> Self:
        """Add a directed edge between two executors.

        The output types of the source and the input types of the target must be compatible.

        Args:
            source: The source executor of the edge.
            target: The target executor of the edge.
            condition: An optional condition function that determines whether the edge
                       should be traversed based on the message type.
        """
        # TODO(@taochen): Support executor factories for lazy initialization
        source_exec = self._maybe_wrap_agent(source)
        target_exec = self._maybe_wrap_agent(target)
        source_id = self._add_executor(source_exec)
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(SingleEdgeGroup(source_id, target_id, condition))  # type: ignore[call-arg]
        return self

    def add_fan_out_edges(
        self,
        source: Executor | AgentProtocol,
        targets: Sequence[Executor | AgentProtocol],
    ) -> Self:
        """Add multiple edges to the workflow where messages from the source will be sent to all target.

        The output types of the source and the input types of the targets must be compatible.

        Args:
            source: The source executor of the edges.
            targets: A list of target executors for the edges.
        """
        source_exec = self._maybe_wrap_agent(source)
        target_execs = [self._maybe_wrap_agent(t) for t in targets]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids))  # type: ignore[call-arg]

        return self

    def add_switch_case_edge_group(
        self,
        source: Executor | AgentProtocol,
        cases: Sequence[Case | Default],
    ) -> Self:
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
        source_exec = self._maybe_wrap_agent(source)
        source_id = self._add_executor(source_exec)
        # Convert case data types to internal types that only uses target_id.
        internal_cases: list[SwitchCaseEdgeGroupCase | SwitchCaseEdgeGroupDefault] = []
        for case in cases:
            # Allow case targets to be agents
            case.target = self._maybe_wrap_agent(case.target)  # type: ignore[attr-defined]
            self._add_executor(case.target)
            if isinstance(case, Default):
                internal_cases.append(SwitchCaseEdgeGroupDefault(target_id=case.target.id))
            else:
                internal_cases.append(SwitchCaseEdgeGroupCase(condition=case.condition, target_id=case.target.id))
        self._edge_groups.append(SwitchCaseEdgeGroup(source_id, internal_cases))  # type: ignore[call-arg]

        return self

    def add_multi_selection_edge_group(
        self,
        source: Executor | AgentProtocol,
        targets: Sequence[Executor | AgentProtocol],
        selection_func: Callable[[Any, list[str]], list[str]],
    ) -> Self:
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
        source_exec = self._maybe_wrap_agent(source)
        target_execs = [self._maybe_wrap_agent(t) for t in targets]
        source_id = self._add_executor(source_exec)
        target_ids = [self._add_executor(t) for t in target_execs]
        self._edge_groups.append(FanOutEdgeGroup(source_id, target_ids, selection_func))  # type: ignore[call-arg]

        return self

    def add_fan_in_edges(
        self,
        sources: Sequence[Executor | AgentProtocol],
        target: Executor | AgentProtocol,
    ) -> Self:
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
        source_execs = [self._maybe_wrap_agent(s) for s in sources]
        target_exec = self._maybe_wrap_agent(target)
        source_ids = [self._add_executor(s) for s in source_execs]
        target_id = self._add_executor(target_exec)
        self._edge_groups.append(FanInEdgeGroup(source_ids, target_id))  # type: ignore[call-arg]

        return self

    def add_chain(self, executors: Sequence[Executor | AgentProtocol]) -> Self:
        """Add a chain of executors to the workflow.

        The output of each executor in the chain will be sent to the next executor in the chain.
        The input types of each executor must be compatible with the output types of the previous executor.

        Circles in the chain are not allowed, meaning the chain cannot have two executors with the same ID.

        Args:
            executors: A list of executors to be added to the chain.
        """
        # Wrap each candidate first to ensure stable IDs before adding edges
        wrapped: list[Executor] = [self._maybe_wrap_agent(e) for e in executors]
        for i in range(len(wrapped) - 1):
            self.add_edge(wrapped[i], wrapped[i + 1])
        return self

    def set_start_executor(self, executor: Executor | AgentProtocol | str) -> Self:
        """Set the starting executor for the workflow.

        Args:
            executor: The starting executor, which can be an Executor instance or its ID.
        """
        if isinstance(executor, str):
            self._start_executor = executor
        else:
            wrapped = self._maybe_wrap_agent(executor)  # type: ignore[arg-type]
            self._start_executor = wrapped
            # Ensure the start executor is present in the executor map so validation succeeds
            # even if no edges are added yet, or before edges wrap the same agent again.
            existing = self._executors.get(wrapped.id)
            if existing is not wrapped:
                self._add_executor(wrapped)
        return self

    def set_max_iterations(self, max_iterations: int) -> Self:
        """Set the maximum number of iterations for the workflow.

        Args:
            max_iterations: The maximum number of iterations the workflow will run for convergence.
        """
        self._max_iterations = max_iterations
        return self

    # Removed explicit set_agent_streaming() API; agents always stream updates.

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> Self:
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
        # Create workflow build span that includes validation and workflow creation
        with create_workflow_span(OtelAttr.WORKFLOW_BUILD_SPAN) as span:
            try:
                # Add workflow build started event
                span.add_event(OtelAttr.BUILD_STARTED)

                if not self._start_executor:
                    raise ValueError(
                        "Starting executor must be set using set_start_executor before building the workflow."
                    )

                # Perform validation before creating the workflow
                validate_workflow_graph(
                    self._edge_groups,
                    self._executors,
                    self._start_executor,
                    duplicate_executor_ids=tuple(self._duplicate_executor_ids),
                )

                # Add validation completed event
                span.add_event(OtelAttr.BUILD_VALIDATION_COMPLETED)

                context = InProcRunnerContext(self._checkpoint_storage)

                # Create workflow instance after validation
                workflow = Workflow(
                    self._edge_groups,
                    self._executors,
                    self._start_executor,
                    context,
                    self._max_iterations,
                    name=self._name,
                    description=self._description,
                )
                build_attributes: dict[str, Any] = {
                    OtelAttr.WORKFLOW_ID: workflow.id,
                    OtelAttr.WORKFLOW_DEFINITION: workflow.to_json(),
                }
                if workflow.name:
                    build_attributes[OtelAttr.WORKFLOW_NAME] = workflow.name
                if workflow.description:
                    build_attributes[OtelAttr.WORKFLOW_DESCRIPTION] = workflow.description
                span.set_attributes(build_attributes)

                # Add workflow build completed event
                span.add_event(OtelAttr.BUILD_COMPLETED)

                return workflow

            except Exception as exc:
                attributes = {
                    OtelAttr.BUILD_ERROR_MESSAGE: str(exc),
                    OtelAttr.BUILD_ERROR_TYPE: type(exc).__name__,
                }
                span.add_event(OtelAttr.BUILD_ERROR, attributes)  # type: ignore[reportArgumentType, arg-type]
                capture_exception(span, exc)
                raise
