# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._workflow import Workflow

from ._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from ._const import WORKFLOW_RUN_KWARGS_KEY
from ._events import (
    RequestInfoEvent,
    WorkflowErrorEvent,
    WorkflowFailedEvent,
    WorkflowRunState,
)
from ._executor import Executor, handler
from ._request_info_mixin import response_handler
from ._runner_context import Message
from ._typing_utils import is_instance_of
from ._workflow import WorkflowRunResult
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover


logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for tracking a single sub-workflow execution."""

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
    pending_requests: dict[str, RequestInfoEvent]  # request_id -> request_info_event


@dataclass
class SubWorkflowResponseMessage:
    """Message sent from a parent workflow to a sub-workflow via WorkflowExecutor to provide requested information.

    This message wraps the response data along with the original RequestInfoEvent emitted by the sub-workflow executor.

    Attributes:
        data: The response data to the original request.
        source_event: The original RequestInfoEvent emitted by the sub-workflow executor.
    """

    data: Any
    source_event: RequestInfoEvent


@dataclass
class SubWorkflowRequestMessage:
    """Message sent from a sub-workflow to an executor in the parent workflow to request information.

    This message wraps a RequestInfoEvent emitted by the executor in the sub-workflow.

    Attributes:
        source_event: The original RequestInfoEvent emitted by the sub-workflow executor.
        executor_id: The ID of the WorkflowExecutor in the parent workflow that is
            responsible for this sub-workflow. This can be used to ensure that the response
            is sent back to the correct sub-workflow instance.
    """

    source_event: RequestInfoEvent
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

        # WorkflowExecutor captures RequestInfoEvent and wraps it in a SubWorkflowRequestMessage
        # then send it to the receiving executor in parent workflow. The executor in parent workflow
        # can handle the request locally or forward it to an external source.
        # The WorkflowExecutor tracks the pending request, and implements a response handler.
        # When the response is received, it executes the response handler to accumulate responses
        # and resume the sub-workflow when all expected responses are received.
        # The response handler expects a SubWorkflowResponseMessage wrapping the response data.

    ### State Management
    WorkflowExecutor maintains execution state across request/response cycles:
    - Tracks pending requests by request_id
    - Accumulates responses until all expected responses are received
    - Resumes sub-workflow execution with complete response batch
    - Handles concurrent executions and multiple pending requests

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
    - Captures WorkflowFailedEvent from sub-workflow
    - Converts to WorkflowErrorEvent in parent context
    - Provides detailed error information including sub-workflow ID

    ## Concurrent Execution Support
    WorkflowExecutor fully supports multiple concurrent sub-workflow executions:

    ### Per-Execution State Isolation
    Each sub-workflow invocation creates an isolated ExecutionContext:

    .. code-block:: python

        # Multiple concurrent invocations are supported
        workflow_executor = WorkflowExecutor(my_workflow, id="concurrent_executor")

        # Each invocation gets its own execution context
        # Execution 1: processes input_1 independently
        # Execution 2: processes input_2 independently
        # No state interference between executions

    ### Request/Response Coordination
    Responses are correctly routed to the originating execution:
    - Each execution tracks its own pending requests and expected responses
    - Request-to-execution mapping ensures responses reach the correct sub-workflow
    - Response accumulation is isolated per execution
    - Automatic cleanup when execution completes

    ### Memory Management
    - Unlimited concurrent executions supported
    - Each execution has unique UUID-based identification
    - Cleanup of completed execution contexts
    - Thread-safe state management for concurrent access

    ### Important Considerations
    **Shared Workflow Instance**: All concurrent executions use the same underlying workflow instance.
    For proper isolation, ensure that the wrapped workflow and its executors are stateless.

    .. code-block:: python

        # Avoid: Stateful executor with instance variables
        class StatefulExecutor(Executor):
            def __init__(self):
                super().__init__(id="stateful")
                self.data = []  # This will be shared across concurrent executions!

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
    - Sub-workflows run to completion before processing their results
    - Event processing is atomic - all outputs are forwarded before requests
    - Response accumulation ensures sub-workflows receive complete response batches
    - Execution state is maintained for proper resumption after external requests
    - Concurrent executions are fully isolated and do not interfere with each other
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
            workflow: The workflow to execute as a sub-workflow.
            id: Unique identifier for this executor.
            allow_direct_output: Whether to allow direct output from the sub-workflow.
                                 By default, outputs from the sub-workflow are sent to
                                 other executors in the parent workflow as messages.
                                 When this is set to true, the outputs are yielded
                                 directly from the WorkflowExecutor to the parent
                                 workflow's event stream.
            propagate_request: Whether to propagate requests from the sub-workflow to the
                               parent workflow. If set to true, requests from the sub-workflow
                               will be propagated as the original RequestInfoEvent to the parent
                               workflow. Otherwise, they will be wrapped in a SubWorkflowRequestMessage,
                               which should be handled by an executor in the parent workflow.

        Keyword Args:
            **kwargs: Additional keyword arguments passed to the parent constructor.
        """
        super().__init__(id, **kwargs)
        self.workflow = workflow
        self.allow_direct_output = allow_direct_output

        # Track execution contexts for concurrent sub-workflow executions
        self._execution_contexts: dict[str, ExecutionContext] = {}  # execution_id -> ExecutionContext
        # Map request_id to execution_id for response routing
        self._request_to_execution: dict[str, str] = {}  # request_id -> execution_id
        self._propagate_request = propagate_request

    @property
    def input_types(self) -> list[type[Any]]:
        """Get the input types based on the underlying workflow's input types plus WorkflowExecutor-specific types.

        Returns:
            A list of input types that the WorkflowExecutor can accept.
        """
        input_types = list(self.workflow.input_types)

        # WorkflowExecutor can also handle SubWorkflowResponseMessage for sub-workflow responses
        if SubWorkflowResponseMessage not in input_types:
            input_types.append(SubWorkflowResponseMessage)

        return input_types

    @property
    def output_types(self) -> list[type[Any]]:
        """Get the output types based on the underlying workflow's output types.

        Returns:
            A list of output types that the underlying workflow can produce.
            Includes the SubWorkflowRequestMessage type if any executor in the
            sub-workflow is request-response capable.
        """
        output_types = list(self.workflow.output_types)

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

    def can_handle(self, message: Message) -> bool:
        """Override can_handle to only accept messages that the wrapped workflow can handle.

        This prevents the WorkflowExecutor from accepting messages that should go to other
        executors because the handler `process_workflow` has no type restrictions.
        """
        if isinstance(message.data, SubWorkflowResponseMessage):
            # Always handle SubWorkflowResponseMessage
            return True

        if (
            message.original_request_info_event is not None
            and message.original_request_info_event.request_id in self._request_to_execution
        ):
            # Handle propagated responses for known requests
            return True

        # For other messages, only handle if the wrapped workflow can accept them as input
        return any(is_instance_of(message.data, input_type) for input_type in self.workflow.input_types)

    @handler
    async def process_workflow(self, input_data: object, ctx: WorkflowContext[Any]) -> None:
        """Execute the sub-workflow with raw input data.

        This handler starts a new sub-workflow execution. When the sub-workflow
        needs external information, it pauses and sends a request to the parent.

        Args:
            input_data: The input data to send to the sub-workflow.
            ctx: The workflow context from the parent.
        """
        # Create execution context for this sub-workflow run
        execution_id = str(uuid.uuid4())
        execution_context = ExecutionContext(
            execution_id=execution_id,
            collected_responses={},
            expected_response_count=0,
            pending_requests={},
        )
        self._execution_contexts[execution_id] = execution_context

        logger.debug(f"WorkflowExecutor {self.id} starting sub-workflow {self.workflow.id} execution {execution_id}")

        try:
            # Get kwargs from parent workflow's SharedState to propagate to subworkflow
            parent_kwargs: dict[str, Any] = await ctx.get_shared_state(WORKFLOW_RUN_KWARGS_KEY) or {}

            # Run the sub-workflow and collect all events, passing parent kwargs
            result = await self.workflow.run(input_data, **parent_kwargs)

            logger.debug(
                f"WorkflowExecutor {self.id} sub-workflow {self.workflow.id} "
                f"execution {execution_id} completed with {len(result)} events"
            )

            # Process the workflow result using shared logic
            await self._process_workflow_result(result, execution_context, ctx)
        finally:
            # Clean up execution context if it's completed (no pending requests)
            if execution_id in self._execution_contexts:
                exec_ctx = self._execution_contexts[execution_id]
                if not exec_ctx.pending_requests:
                    del self._execution_contexts[execution_id]

    @handler
    async def handle_message_wrapped_request_response(
        self,
        response: SubWorkflowResponseMessage,
        ctx: WorkflowContext[Any],
    ) -> None:
        """Handle response from parent for a forwarded request.

        This handler accumulates responses and only resumes the sub-workflow
        when all expected responses have been received for that execution.

        Args:
            response: The response to a previous request.
            ctx: The workflow context.
        """
        await self._handle_response(
            request_id=response.source_event.request_id,
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
            original_request: The original RequestInfoEvent.
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
            "execution_contexts": {
                execution_id: encode_checkpoint_value(execution_context)
                for execution_id, execution_context in self._execution_contexts.items()
            },
            "request_to_execution": dict(self._request_to_execution),
        }

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore the WorkflowExecutor state from a checkpoint snapshot."""
        # Validate the state contains the right keys
        if "execution_contexts" not in state:
            raise KeyError("Missing 'execution_contexts' in WorkflowExecutor state.")
        if "request_to_execution" not in state:
            raise KeyError("Missing 'request_to_execution' in WorkflowExecutor state.")

        # Validate the execution contexts stored in the state have the right keys and values
        execution_contexts: dict[str, ExecutionContext] | None = None
        try:
            execution_contexts = {
                key: decode_checkpoint_value(value) for key, value in state["execution_contexts"].items()
            }
        except Exception as ex:
            raise RuntimeError("Failed to deserialize execution context.") from ex

        if not all(
            isinstance(key, str) and isinstance(value, ExecutionContext) for key, value in execution_contexts.items()
        ):
            raise ValueError("Execution contexts must have 'str' as key and 'ExecutionContext' as value.")
        if not all(key == value.execution_id for key, value in execution_contexts.items()):
            raise ValueError("Execution contexts must have matching keys and IDs.")

        # Validate the request_to_execution map contain the right data
        request_to_execution = state["request_to_execution"]
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in request_to_execution.items()):
            raise ValueError("Request to execution map must have 'str' as key and 'str' as value.")
        if not all(value in execution_contexts for value in request_to_execution.values()):
            raise ValueError(
                "'request_to_execution` contains unknown execution ID that is not part of the execution contexts."
            )

        self._execution_contexts = execution_contexts
        self._request_to_execution = request_to_execution

        # Add the `request_info_event`s back to the sub workflow.
        # This is only a temporary solution to rehydrate the sub workflow with the requests.
        # The proper way would be to rehydrate the workflow from a checkpoint on a Workflow
        # API instead of the '_runner_context' object that should be hidden. And the sub workflow
        # should be rehydrated from a checkpoint object instead of from a subset of the state.
        # TODO(@taochen): Issue #1614 - how to handle the case when the parent workflow has checkpointing
        # set up but not the sub workflow?
        request_info_events = [
            request_info_event
            for execution_context in self._execution_contexts.values()
            for request_info_event in execution_context.pending_requests.values()
        ]
        await asyncio.gather(*[
            self.workflow._runner_context.add_request_info_event(event)  # pyright: ignore[reportPrivateUsage]
            for event in request_info_events
        ])

    async def _process_workflow_result(
        self,
        result: WorkflowRunResult,
        execution_context: ExecutionContext,
        ctx: WorkflowContext[Any],
    ) -> None:
        """Process the result from a workflow execution.

        This method handles the common logic for processing outputs, request info events,
        and final states that is shared between process_workflow and handle_response.

        Args:
            result: The workflow execution result.
            execution_context: The execution context for this sub-workflow run.
            ctx: The workflow context.
        """
        # Collect all events from the workflow
        request_info_events = result.get_request_info_events()
        outputs = result.get_outputs()
        workflow_run_state = result.get_final_state()
        logger.debug(
            f"WorkflowExecutor {self.id} processing workflow result with "
            f"{len(outputs)} outputs and {len(request_info_events)} request info events. "
            f"Workflow run state: {workflow_run_state}"
        )

        # Process outputs
        if self.allow_direct_output:
            # Note that the executor is allowed to continue its own execution after yielding outputs.
            await asyncio.gather(*[ctx.yield_output(output) for output in outputs])
        else:
            await asyncio.gather(*[ctx.send_message(output) for output in outputs])

        # Process request info events
        for event in request_info_events:
            # Track the pending request in execution context
            execution_context.pending_requests[event.request_id] = event
            # Map request to execution for response routing
            self._request_to_execution[event.request_id] = execution_context.execution_id
            if self._propagate_request:
                # In a workflow where the parent workflow does not handle the request, the request
                # should be propagated via the `request_info` mechanism to an external source. And
                # a @response_handler would be required in the WorkflowExecutor to handle the response.
                await ctx.request_info(event.data, event.response_type, request_id=event.request_id)
            else:
                # In a workflow where the parent workflow has an executor that may intercept the
                # request and handle it directly, a message should be sent.
                await ctx.send_message(SubWorkflowRequestMessage(source_event=event, executor_id=self.id))

        # Update expected response count for this execution
        execution_context.expected_response_count = len(request_info_events)

        # Handle final state
        if workflow_run_state == WorkflowRunState.FAILED:
            # Find the WorkflowFailedEvent.
            failed_events = [e for e in result if isinstance(e, WorkflowFailedEvent)]
            if failed_events:
                failed_event = failed_events[0]
                error_type = failed_event.details.error_type
                error_message = failed_event.details.message
                exception = Exception(
                    f"Sub-workflow {self.workflow.id} failed with error: {error_type} - {error_message}"
                )
                error_event = WorkflowErrorEvent(
                    data=exception,
                )
                await ctx.add_event(error_event)
        elif workflow_run_state == WorkflowRunState.IDLE:
            # Sub-workflow is idle - nothing more to do now
            logger.debug(
                f"Sub-workflow {self.workflow.id} is idle with {len(self._execution_contexts)} active executions"
            )
        elif workflow_run_state == WorkflowRunState.CANCELLED:
            # Sub-workflow was cancelled - treat as completion
            logger.debug(
                f"Sub-workflow {self.workflow.id} was cancelled with {len(self._execution_contexts)} active executions"
            )
        elif workflow_run_state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS:
            # Sub-workflow is still running with pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is still in progress with {len(request_info_events)} "
                f"pending requests with {len(self._execution_contexts)} active executions"
            )
        elif workflow_run_state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            # Sub-workflow is idle but has pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is idle with pending requests: "
                f"{len(request_info_events)} with {len(self._execution_contexts)} active executions"
            )
        else:
            raise RuntimeError(f"Unexpected workflow run state: {workflow_run_state}")

    async def _handle_response(
        self,
        request_id: str,
        response: Any,
        ctx: WorkflowContext[Any],
    ) -> None:
        execution_id = self._request_to_execution.get(request_id)
        if not execution_id or execution_id not in self._execution_contexts:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: {request_id}. "
                "This response will be ignored."
            )
            return

        execution_context = self._execution_contexts[execution_id]

        # Check if we have this pending request in the execution context
        if request_id not in execution_context.pending_requests:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: "
                f"{request_id} in execution {execution_id}, ignoring"
            )
            return

        # Remove the request from pending list and request mapping
        execution_context.pending_requests.pop(request_id, None)
        self._request_to_execution.pop(request_id, None)

        # Accumulate the response in this execution's context
        execution_context.collected_responses[request_id] = response
        # Check if we have all expected responses for this execution
        if len(execution_context.collected_responses) < execution_context.expected_response_count:
            logger.debug(
                f"WorkflowExecutor {self.id} execution {execution_id} waiting for more responses: "
                f"{len(execution_context.collected_responses)}/{execution_context.expected_response_count} received"
            )
            return  # Wait for more responses

        # Send all collected responses to the sub-workflow
        responses_to_send = dict(execution_context.collected_responses)
        execution_context.collected_responses.clear()  # Clear for next batch

        try:
            # Resume the sub-workflow with all collected responses
            result = await self.workflow.send_responses(responses_to_send)

            # Process the workflow result using shared logic
            await self._process_workflow_result(result, execution_context, ctx)
        finally:
            # Clean up execution context if it's completed (no pending requests)
            if not execution_context.pending_requests:
                del self._execution_contexts[execution_id]
