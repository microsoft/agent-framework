# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._workflow import Workflow

from ._const import GLOBAL_KWARGS_KEY, WORKFLOW_RUN_KWARGS_KEY
from ._events import (
    WorkflowEvent,
    WorkflowRunState,
    _framework_event_origin,  # type: ignore[reportPrivateUsage]
)
from ._executor import Executor, handler
from ._request_info_mixin import response_handler
from ._runner_context import WorkflowMessage
from ._typing_utils import is_instance_of
from ._workflow import WorkflowRunResult
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Legacy per-execution bookkeeping.

    Retained only to decode checkpoints written before the sub-workflow's own checkpoint was
    embedded (see ``WorkflowExecutor.on_checkpoint_restore``). It is no longer used at runtime -
    the wrapped sub-workflow is the single source of truth for its pending requests.
    """

    # The ID of the execution context
    execution_id: str

    # Responses that have been collected so far for requests that
    # were sent out in the previous iteration
    collected_responses: dict[str, Any]  # request_id -> response_data

    # Number of responses to be expected. If the WorkflowExecutor has
    # not received all responses, it won't run the sub workflow.
    expected_response_count: int

    # Pending requests to be fulfilled. This will get updated as the
    # WorkflowExecutor receives responses.
    pending_requests: dict[str, WorkflowEvent]  # request_id -> request_info_event


@dataclass
class SubWorkflowResponseMessage:
    """Message sent from a parent workflow to a sub-workflow via WorkflowExecutor to provide requested information.

    This message wraps the response data along with the original WorkflowEvent emitted by the sub-workflow executor.

    Attributes:
        data: The response data to the original request.
        source_event: The original WorkflowEvent emitted by the sub-workflow executor.
    """

    data: Any
    source_event: WorkflowEvent


@dataclass
class SubWorkflowRequestMessage:
    """Message sent from a sub-workflow to an executor in the parent workflow to request information.

    This message wraps a WorkflowEvent emitted by the executor in the sub-workflow.

    Attributes:
        source_event: The original WorkflowEvent emitted by the sub-workflow executor.
        executor_id: The ID of the WorkflowExecutor in the parent workflow that is
            responsible for this sub-workflow. This can be used to ensure that the response
            is sent back to the correct sub-workflow instance.
    """

    source_event: WorkflowEvent
    executor_id: str

    def create_response(self, data: Any) -> SubWorkflowResponseMessage:
        """Validate and wrap response data into a SubWorkflowResponseMessage.

        Validation ensures the response data type matches the expected type from the original request.
        """
        expected_data_type = self.source_event.response_type
        if not is_instance_of(data, expected_data_type):
            raise TypeError(
                f"Response data type {type(data)} does not match expected type {expected_data_type} "
                f"for request_id {self.source_event.request_id}"
            )

        return SubWorkflowResponseMessage(data=data, source_event=self.source_event)


class WorkflowExecutor(Executor):
    """An executor that wraps a workflow to enable hierarchical workflow composition.

    ## Overview
    WorkflowExecutor makes a workflow behave as a single executor within a parent workflow,
    enabling nested workflow architectures. It handles the complete lifecycle of sub-workflow
    execution including event processing, output forwarding, and request/response coordination
    between parent and child workflows.

    ## Execution Model
    When invoked, WorkflowExecutor:
    1. Starts the wrapped workflow with the input message
    2. Runs the sub-workflow to completion or until it needs external input
    3. Processes the sub-workflow's complete event stream after execution
    4. Forwards outputs to the parent workflow as messages
    5. Handles external requests by routing them to the parent workflow
    6. Accumulates responses and resumes sub-workflow execution

    ## Event Stream Processing
    WorkflowExecutor processes events after sub-workflow completion:

    ### Output Forwarding
    All outputs from the sub-workflow are automatically forwarded to the parent:

    #### When `allow_direct_output` is False (default):

    .. code-block:: python

        # An executor in the sub-workflow yields outputs
        await ctx.yield_output("sub-workflow result")

        # WorkflowExecutor forwards to parent via ctx.send_message()
        # Parent receives the output as a regular message

    #### When `allow_direct_output` is True:

    .. code-block:: python
        # An executor in the sub-workflow yields outputs
        await ctx.yield_output("sub-workflow result")

        # WorkflowExecutor yields output directly to parent workflow's event stream
        # The output of the sub-workflow is considered the output of the parent workflow
        # Caller of the parent workflow receives the output directly

    ### Request/Response Coordination
    When sub-workflows need external information:

    .. code-block:: python

        # An executor in the sub-workflow makes request
        request = MyDataRequest(query="user info")

        # WorkflowExecutor captures WorkflowEvent and wraps it in a SubWorkflowRequestMessage
        # then send it to the receiving executor in parent workflow. The executor in parent workflow
        # can handle the request locally or forward it to an external source.
        # The WorkflowExecutor tracks the pending request, and implements a response handler.
        # When the response is received, it executes the response handler to accumulate responses
        # and resume the sub-workflow when all expected responses are received.
        # The response handler expects a SubWorkflowResponseMessage wrapping the response data.

    ### State Management
    WorkflowExecutor keeps no request/response bookkeeping of its own. The wrapped sub-workflow
    is the single source of truth for its pending requests; responses are forwarded to it and
    validated against its own pending request_info events.

    ## Type System Integration
    WorkflowExecutor inherits its type signature from the wrapped workflow:

    ### Input Types
    Matches the wrapped workflow's start executor input types:

    .. code-block:: python

        # If sub-workflow accepts str, WorkflowExecutor accepts str
        workflow_executor = WorkflowExecutor(my_workflow, id="wrapper")
        assert workflow_executor.input_types == my_workflow.input_types

    ### Output Types
    Combines sub-workflow outputs with request coordination types:

    .. code-block:: python

        # Includes all sub-workflow output types
        # Plus SubWorkflowRequestMessage if sub-workflow can make requests
        output_types = workflow.output_types + [SubWorkflowRequestMessage]  # if applicable

    ## Error Handling
    WorkflowExecutor propagates sub-workflow failures:
    - Captures failed event (type='failed') from sub-workflow
    - Converts to error event in parent context
    - Provides detailed error information including sub-workflow ID

    ## Overlapping Executions
    A ``WorkflowExecutor`` wraps a single shared sub-workflow instance and keeps no per-execution
    state. If a new input arrives while the sub-workflow still has pending request_info events from
    an unfinished request/response cycle, the new input advances the shared sub-workflow state and
    can interfere with that cycle - a response arriving later may apply to a sub-workflow that has
    moved on. This is allowed but logs a warning, and is only safe when the wrapped workflow (and
    its executors) are stateless.

    .. code-block:: python

        # Avoid: stateful executor whose instance variables are shared across overlapping runs
        class StatefulExecutor(Executor):
            def __init__(self):
                super().__init__(id="stateful")
                self.data = []  # Shared across overlapping sub-workflow executions!

    ## Integration with Parent Workflows
    Parent workflows can intercept sub-workflow requests:

    .. code-block:: python
        class ParentExecutor(Executor):
            @handler
            async def handle_subworkflow_request(
                self,
                request: SubWorkflowRequestMessage,
                ctx: WorkflowContext[SubWorkflowResponseMessage],
            ) -> None:
                # Handle request locally or forward to external source
                if self.can_handle_locally(request):
                    # Send response back to sub-workflow
                    response = request.create_response(data="local response data")
                    await ctx.send_message(response, target_id=request.source_executor_id)
                else:
                    # Forward to external handler
                    await ctx.request_info(request.source_event, response_type=request.source_event.response_type)

    ## Implementation Notes
    - Sub-workflows run to completion (or to idle-with-pending-requests) before their results are processed
    - Event processing is ordered - outputs are forwarded before requests
    - Responses are forwarded to the sub-workflow as they arrive; the sub-workflow tracks its own
      pending requests and resumes when they are answered
    - The WorkflowExecutor keeps no per-execution bookkeeping; the sub-workflow is the single source
      of truth for its pending requests. Starting a new execution while the sub-workflow still has
      pending requests logs a warning and is only safe when the wrapped workflow is stateless
    """

    def __init__(
        self,
        workflow: "Workflow",
        id: str,
        allow_direct_output: bool = False,
        propagate_request: bool = False,
        **kwargs: Any,
    ):
        """Initialize the WorkflowExecutor.

        Args:
            workflow: The workflow to execute as a sub-workflow. This workflow instance (including
                the executor instances within it) must be unique. If the same instances are shared
                across multiple WorkflowExecutor instances, it may lead to incorrect behavior.
            id: Unique identifier for this executor.
            allow_direct_output: Whether to allow direct output from the sub-workflow. By default,
                outputs from the sub-workflow are sent to other executors in the parent workflow as
                messages. When this is set to true, the outputs are yielded directly from the
                WorkflowExecutor to the parent workflow's event stream.
            propagate_request: Whether to propagate requests from the sub-workflow to the parent
                workflow. If set to true, requests from the sub-workflow will be propagated as the
                original WorkflowEvent to the parent workflow. Otherwise, they will be wrapped in a
                SubWorkflowRequestMessage, which should be handled by an executor in the parent workflow.

        Keyword Args:
            **kwargs: Additional keyword arguments passed to the parent constructor.
        """
        super().__init__(id, **kwargs)
        self.workflow = workflow
        self.allow_direct_output = allow_direct_output
        self._propagate_request = propagate_request

    @property
    def input_types(self) -> list[type[Any] | types.UnionType]:
        """Get the input types based on the underlying workflow's input types plus WorkflowExecutor-specific types.

        Returns:
            A list of input types that the WorkflowExecutor can accept.
        """
        input_types: list[type[Any] | types.UnionType] = list(self.workflow.input_types)

        # WorkflowExecutor can also handle SubWorkflowResponseMessage for sub-workflow responses
        if SubWorkflowResponseMessage not in input_types:
            input_types.append(SubWorkflowResponseMessage)

        return input_types

    @property
    def output_types(self) -> list[type[Any] | types.UnionType]:
        """Get the output types based on the underlying workflow's output types.

        Returns:
            A list of output types that the underlying workflow can produce.
            Includes the SubWorkflowRequestMessage type if any executor in the
            sub-workflow is request-response capable.
        """
        output_types: list[type[Any] | types.UnionType] = list(self.workflow.output_types)

        is_request_response_capable = any(
            executor.is_request_response_capable for executor in self.workflow.executors.values()
        )

        if is_request_response_capable:
            output_types.append(SubWorkflowRequestMessage)

        return output_types

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["workflow"] = self.workflow.to_dict()
        return data

    def can_handle(self, message: WorkflowMessage) -> bool:
        """Override can_handle to only accept messages that the wrapped workflow can handle.

        This prevents the WorkflowExecutor from accepting messages that should go to other
        executors because the handler `process_workflow` has no type restrictions.
        """
        if isinstance(message.data, SubWorkflowResponseMessage):
            # Always handle SubWorkflowResponseMessage
            return True

        if message.original_request_info_event is not None:
            # A propagated response is target-routed back to the executor that issued the request,
            # so if one reaches this WorkflowExecutor it belongs to our sub-workflow. _handle_response
            # validates it against the sub-workflow's pending requests and ignores anything unknown.
            return True

        # For other messages, only handle if the wrapped workflow can accept them as input
        return any(is_instance_of(message.data, input_type) for input_type in self.workflow.input_types)

    @handler
    async def process_workflow(self, input_data: object, ctx: WorkflowContext[Any, Any]) -> None:
        """Execute the sub-workflow with raw input data.

        This handler starts a new sub-workflow execution. When the sub-workflow
        needs external information, it pauses and sends a request to the parent.

        Args:
            input_data: The input data to send to the sub-workflow.
            ctx: The workflow context from the parent.
        """
        # The sub-workflow is a single shared instance. If it still has pending request_info events
        # from an unfinished request/response cycle, a new input advances its shared state and can
        # interfere with that cycle - a response arriving later may apply to a sub-workflow that has
        # moved on. We allow it (the sub-workflow may be stateless) but warn so the risk is visible.
        pending_requests = await self.workflow._runner_context.get_pending_request_info_events()  # pyright: ignore[reportPrivateUsage]
        if pending_requests:
            logger.warning(
                f"WorkflowExecutor {self.id} received a new input message while its sub-workflow "
                f"({self.workflow.id}) still has {len(pending_requests)} pending request(s) from an "
                f"unfinished request/response cycle. The sub-workflow is a single shared instance, so the "
                f"new input advances shared state and can interfere with the in-flight cycle. Ensure the "
                f"sub-workflow is stateless, or complete the pending cycle before sending new input."
            )

        logger.debug(f"WorkflowExecutor {self.id} starting sub-workflow {self.workflow.id}")

        # Get kwargs from parent workflow's State to propagate to subworkflow
        parent_kwargs: dict[str, Any] = ctx.get_state(WORKFLOW_RUN_KWARGS_KEY, {})

        # Extract invocation kwargs recognised by Workflow.run()
        # The state stores resolved format (with __global__ wrapper for global kwargs).
        # Unwrap __global__ before passing to the subworkflow so it gets re-resolved
        # against the subworkflow's own executor IDs.
        fi_kwargs: dict[str, Any] | None = None
        ci_kwargs: dict[str, Any] | None = None
        for key in ("function_invocation_kwargs", "client_kwargs"):
            resolved = parent_kwargs.get(key)
            if isinstance(resolved, dict):
                # Unwrap global sentinel; pass per-executor dicts as-is
                unwrapped: dict[str, Any] = resolved.get(GLOBAL_KWARGS_KEY, resolved)  # type: ignore
                if key == "function_invocation_kwargs":
                    fi_kwargs = unwrapped  # type: ignore
                else:
                    ci_kwargs = unwrapped  # type: ignore

        # Run the sub-workflow and collect all events, passing parent kwargs
        result = await self.workflow.run(
            input_data,
            function_invocation_kwargs=fi_kwargs,  # type: ignore
            client_kwargs=ci_kwargs,  # type: ignore
        )

        logger.debug(f"WorkflowExecutor {self.id} sub-workflow {self.workflow.id} completed with {len(result)} events")

        # Process the workflow result using shared logic
        await self._process_workflow_result(result, ctx)

    @handler
    async def handle_message_wrapped_request_response(
        self,
        response: SubWorkflowResponseMessage,
        ctx: WorkflowContext[Any, Any],
    ) -> None:
        """Handle response from parent for a forwarded request.

        Forwards the response to the sub-workflow, which resumes and validates it against its
        own pending requests.

        Args:
            response: The response to a previous request.
            ctx: The workflow context.
        """
        request_id = response.source_event.request_id
        await self._handle_response(
            request_id=request_id,
            response=response.data,
            ctx=ctx,
        )

    @response_handler
    async def handle_propagated_request_response(
        self,
        original_request: Any,
        response: object,
        ctx: WorkflowContext[Any],
    ) -> None:
        """Handle response for a request that was propagated to the parent workflow.

        Args:
            original_request: The original WorkflowEvent.
            response: The response data.
            ctx: The workflow context.
        """
        if ctx.request_id is None:
            raise RuntimeError("WorkflowExecutor received a propagated response without a request ID in the context.")

        await self._handle_response(
            request_id=ctx.request_id,
            response=response,
            ctx=ctx,
        )

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Get the current state of the WorkflowExecutor for checkpointing purposes."""
        return {
            # The sub-workflow's own checkpoint carries everything needed to resume: shared state,
            # executor snapshots, in-flight messages, and pending request_info events. The
            # WorkflowExecutor keeps no separate request/response bookkeeping of its own. The
            # sub-workflow is quiescent here: it ran to idle within this parent superstep before
            # the parent checkpoints.
            "sub_workflow_checkpoint": await self.workflow._runner.capture_checkpoint_object(),  # pyright: ignore[reportPrivateUsage]
        }

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the WorkflowExecutor state from a checkpoint snapshot."""
        # The storage backend fully materializes the checkpoint on load (FileCheckpointStorage
        # decodes recursively; InMemoryCheckpointStorage deep-copies without encoding), so nested
        # executor state - including this embedded checkpoint - already arrives as a live object,
        # exactly as every other executor consumes its already-decoded on_checkpoint_restore state.
        sub_workflow_checkpoint = state.get("sub_workflow_checkpoint")
        if sub_workflow_checkpoint is not None:
            await self.workflow._runner.restore_from_checkpoint_object(sub_workflow_checkpoint)  # pyright: ignore[reportPrivateUsage]
            return

        # Backward-compatibility fallback for checkpoints written before the sub-workflow checkpoint
        # was embedded. Those stored per-execution bookkeeping; recover only the pending
        # request_info events so the sub-workflow re-emits its pending requests. The sub-workflow's
        # deeper executor/shared state cannot be restored from these older checkpoints.
        legacy_execution_contexts = state.get("execution_contexts")
        if not legacy_execution_contexts:
            return
        request_info_events: list[WorkflowEvent[Any]] = []
        for execution_context in legacy_execution_contexts.values():
            if isinstance(execution_context, ExecutionContext):
                request_info_events.extend(execution_context.pending_requests.values())
        await asyncio.gather(*[
            self.workflow._runner_context.add_request_info_event(event)  # pyright: ignore[reportPrivateUsage]
            for event in request_info_events
        ])

    async def _process_workflow_result(
        self,
        result: WorkflowRunResult,
        ctx: WorkflowContext[Any],
    ) -> None:
        """Process the result from a workflow execution.

        This method handles the common logic for processing outputs, request info events,
        and final states that is shared between process_workflow and handle_response.

        Args:
            result: The workflow execution result.
            ctx: The workflow context.
        """
        # Collect all events from the workflow
        request_info_events = result.get_request_info_events()
        outputs = result.get_outputs()
        intermediate_outputs = result.get_intermediate_outputs()
        workflow_run_state = result.get_final_state()
        logger.debug(
            f"WorkflowExecutor {self.id} processing workflow result with "
            f"{len(outputs)} outputs, {len(intermediate_outputs)} intermediate outputs, "
            f"and {len(request_info_events)} request info events. "
            f"Workflow run state: {workflow_run_state}"
        )

        # Process outputs
        if self.allow_direct_output:
            # Note that the executor is allowed to continue its own execution after yielding outputs.
            await asyncio.gather(*[ctx.yield_output(output) for output in outputs])
        else:
            await asyncio.gather(*[ctx.send_message(output) for output in outputs])

        # Pipe sub-workflow intermediate emissions up through the parent's event stream.
        # Bypasses the parent's yield-output classifier so the 'intermediate' label is preserved
        # across the encapsulation boundary; uses this WorkflowExecutor's id as the source
        # so outer callers don't need to know the sub-workflow's internal executor layout.
        if intermediate_outputs:

            async def _forward_intermediate_output(output: Any) -> None:
                with _framework_event_origin():
                    event = WorkflowEvent("intermediate", executor_id=self.id, data=output)
                await ctx.add_event(event)

            await asyncio.gather(*[_forward_intermediate_output(output) for output in intermediate_outputs])

        # Process request info events
        for event in request_info_events:
            request_id = event.request_id
            response_type = event.response_type
            if self._propagate_request:
                # In a workflow where the parent workflow does not handle the request, the request
                # should be propagated via the `request_info` mechanism to an external source. And
                # a @response_handler would be required in the WorkflowExecutor to handle the response.
                await ctx.request_info(event.data, response_type, request_id=request_id)
            else:
                # In a workflow where the parent workflow has an executor that may intercept the
                # request and handle it directly, a message should be sent.
                await ctx.send_message(SubWorkflowRequestMessage(source_event=event, executor_id=self.id))

        # Handle final state
        if workflow_run_state == WorkflowRunState.FAILED:
            # Find the failed event (type='failed').
            failed_events = [e for e in result if isinstance(e, WorkflowEvent) and e.type == "failed"]
            if failed_events:
                failed_event = failed_events[0]
                if failed_event.details is not None:
                    error_type = failed_event.details.error_type
                    error_message = failed_event.details.message
                    exception = Exception(
                        f"Sub-workflow {self.workflow.id} failed with error: {error_type} - {error_message}"
                    )
                else:
                    exception = Exception(f"Sub-workflow {self.workflow.id} failed with unknown error")
                error_event = WorkflowEvent.error(exception)
                await ctx.add_event(error_event)
        elif workflow_run_state == WorkflowRunState.IDLE:
            # Sub-workflow is idle - nothing more to do now
            logger.debug(f"Sub-workflow {self.workflow.id} is idle")
        elif workflow_run_state == WorkflowRunState.CANCELLED:
            # Sub-workflow was cancelled - treat as completion
            logger.debug(f"Sub-workflow {self.workflow.id} was cancelled")
        elif workflow_run_state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS:
            # Sub-workflow is still running with pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is still in progress with {len(request_info_events)} pending requests"
            )
        elif workflow_run_state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            # Sub-workflow is idle but has pending requests
            logger.debug(f"Sub-workflow {self.workflow.id} is idle with pending requests: {len(request_info_events)}")
        else:
            raise RuntimeError(f"Unexpected workflow run state: {workflow_run_state}")

    async def _handle_response(
        self,
        request_id: str,
        response: Any,
        ctx: WorkflowContext[Any],
    ) -> None:
        # The sub-workflow is the source of truth for what it is awaiting. Validate the response
        # against its pending requests and ignore anything unknown or already handled.
        pending_requests = await self.workflow._runner_context.get_pending_request_info_events()  # pyright: ignore[reportPrivateUsage]
        if request_id not in pending_requests:
            logger.warning(
                f"WorkflowExecutor {self.id} received a response for an unknown or already-handled "
                f"request_id: {request_id}. This response will be ignored."
            )
            return

        # Forward the response to the sub-workflow, which resumes and validates it against its own
        # pending requests, then process whatever the sub-workflow produces.
        result = await self.workflow.run(responses={request_id: response})
        await self._process_workflow_result(result, ctx)
