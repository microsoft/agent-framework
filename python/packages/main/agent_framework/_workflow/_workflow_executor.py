# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._workflow import Workflow

from pydantic import Field

from ._events import (
    WorkflowErrorEvent,
    WorkflowFailedEvent,
    WorkflowRunState,
)
from ._executor import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    SubWorkflowRequestInfo,
    SubWorkflowResponse,
    handler,
)
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for tracking a single sub-workflow execution."""

    execution_id: str
    collected_responses: dict[str, Any]  # request_id -> response_data
    expected_response_count: int
    pending_requests: dict[str, Any]  # request_id -> original request data


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
    4. Forwards outputs to the parent workflow's event stream
    5. Handles external requests by routing them to the parent workflow
    6. Accumulates responses and resumes sub-workflow execution

    ## Event Stream Processing
    WorkflowExecutor processes events after sub-workflow completion:

    ### Output Forwarding
    All outputs from the sub-workflow are automatically forwarded to the parent:
    ```python
    # Sub-workflow yields outputs
    await ctx.yield_output("sub-workflow result")

    # WorkflowExecutor forwards to parent via ctx.send_message()
    # Parent receives the output as a regular message
    ```

    ### Request/Response Coordination
    When sub-workflows need external information:
    ```python
    # Sub-workflow makes request
    request = MyDataRequest(query="user info")
    # RequestInfoExecutor emits RequestInfoEvent

    # WorkflowExecutor wraps and forwards to parent
    wrapped = SubWorkflowRequestInfo(request_id="...", sub_workflow_id="child_workflow", data=request)
    # Parent workflow can intercept via @intercepts_request
    ```

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
    ```python
    # If sub-workflow accepts str, WorkflowExecutor accepts str
    workflow_executor = WorkflowExecutor(my_workflow, id="wrapper")
    assert workflow_executor.input_types == my_workflow.input_types
    ```

    ### Output Types
    Combines sub-workflow outputs with request coordination types:
    ```python
    # Includes all sub-workflow output types
    # Plus SubWorkflowRequestInfo if sub-workflow can make requests
    output_types = workflow.output_types + [SubWorkflowRequestInfo]  # if applicable
    ```

    ## Error Handling
    WorkflowExecutor propagates sub-workflow failures:
    - Captures WorkflowFailedEvent from sub-workflow
    - Converts to WorkflowErrorEvent in parent context
    - Provides detailed error information including sub-workflow ID

    ## Concurrent Execution Support
    WorkflowExecutor fully supports multiple concurrent sub-workflow executions:

    ### Per-Execution State Isolation
    Each sub-workflow invocation creates an isolated ExecutionContext:
    ```python
    # Multiple concurrent invocations are supported
    workflow_executor = WorkflowExecutor(my_workflow, id="concurrent_executor")

    # Each invocation gets its own execution context
    # Execution 1: processes input_1 independently
    # Execution 2: processes input_2 independently
    # No state interference between executions
    ```

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
    For proper isolation, ensure that:
    - The wrapped workflow and its executors are stateless
    - Executors use WorkflowContext state management instead of instance variables
    - Any shared state is managed through WorkflowContext.get_shared_state/set_shared_state
    ```python
    # Good: Stateless executor using context state
    class StatelessExecutor(Executor):
        @handler
        async def process(self, data: str, ctx: WorkflowContext[str]) -> None:
            # Use context state instead of instance variables
            state = await ctx.get_state() or {}
            state["processed"] = data
            await ctx.set_state(state)


    # Avoid: Stateful executor with instance variables
    class StatefulExecutor(Executor):
        def __init__(self):
            super().__init__(id="stateful")
            self.data = []  # This will be shared across concurrent executions!
    ```

    ## Integration with Parent Workflows
    Parent workflows can intercept sub-workflow requests:
    ```python
    class ParentExecutor(Executor):
        @intercepts_request
        async def handle_child_request(
            self, request: MyDataRequest, ctx: WorkflowContext[Any]
        ) -> RequestResponse[MyDataRequest, str]:
            # Handle request locally or forward to external source
            if self.can_handle_locally(request):
                return RequestResponse.handled("local result")
            return RequestResponse.forward()  # Send to external handler
    ```

    ## Implementation Notes
    - Sub-workflows run to completion before processing their results
    - Event processing is atomic - all outputs are forwarded before requests
    - Response accumulation ensures sub-workflows receive complete response batches
    - Execution state is maintained for proper resumption after external requests
    - Concurrent executions are fully isolated and do not interfere with each other
    """

    workflow: "Workflow" = Field(description="The workflow to execute as a sub-workflow")

    def __init__(self, workflow: "Workflow", id: str, **kwargs: Any):
        """Initialize the WorkflowExecutor.

        Args:
            workflow: The workflow to execute as a sub-workflow.
            id: Unique identifier for this executor.
            **kwargs: Additional keyword arguments passed to the parent constructor.
        """
        kwargs.update({"workflow": workflow})
        super().__init__(id, **kwargs)

        # Track execution contexts for concurrent sub-workflow executions
        self._execution_contexts: dict[str, ExecutionContext] = {}  # execution_id -> ExecutionContext
        # Map request_id to execution_id for response routing
        self._request_to_execution: dict[str, str] = {}  # request_id -> execution_id
        self._active_executions: int = 0  # Count of active sub-workflow executions

    @property
    def input_types(self) -> list[type[Any]]:
        """Get the input types based on the underlying workflow's input types.

        Returns:
            A list of input types that the underlying workflow can accept.
        """
        return self.workflow.input_types

    @property
    def output_types(self) -> list[type[Any]]:
        """Get the output types based on the underlying workflow's output types.

        Returns:
            A list of output types that the underlying workflow can produce.
            Includes SubWorkflowRequestInfo if the sub-workflow contains RequestInfoExecutor.
        """
        output_types = list(self.workflow.output_types)

        # Check if the sub-workflow contains a RequestInfoExecutor
        # If so, this WorkflowExecutor can also output SubWorkflowRequestInfo messages
        for executor in self.workflow.executors.values():
            if isinstance(executor, RequestInfoExecutor):
                if SubWorkflowRequestInfo not in output_types:
                    output_types.append(SubWorkflowRequestInfo)
                break

        return output_types

    @handler  # No output_types - can send any completion data type
    async def process_workflow(self, input_data: object, ctx: WorkflowContext[Any]) -> None:
        """Execute the sub-workflow with raw input data.

        This handler starts a new sub-workflow execution. When the sub-workflow
        needs external information, it pauses and sends a request to the parent.

        Args:
            input_data: The input data to send to the sub-workflow.
            ctx: The workflow context from the parent.
        """
        # Skip SubWorkflowResponse and SubWorkflowRequestInfo - they have specific handlers
        if isinstance(input_data, (SubWorkflowResponse, SubWorkflowRequestInfo)):
            logger.debug(f"WorkflowExecutor {self.id} ignoring input of type {type(input_data)}")
            return

        # Create execution context for this sub-workflow run
        execution_id = str(uuid.uuid4())
        execution_context = ExecutionContext(
            execution_id=execution_id,
            collected_responses={},
            expected_response_count=0,
            pending_requests={},
        )
        self._execution_contexts[execution_id] = execution_context

        # Track this execution
        self._active_executions += 1

        logger.debug(f"WorkflowExecutor {self.id} starting sub-workflow {self.workflow.id} execution {execution_id}")

        try:
            # Run the sub-workflow and collect all events
            result = await self.workflow.run(input_data)

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
                    self._active_executions -= 1

    async def _process_workflow_result(
        self, result: Any, execution_context: ExecutionContext, ctx: WorkflowContext[Any]
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
        final_state = result.get_final_state()
        logger.debug(
            f"WorkflowExecutor {self.id} processing workflow result with "
            f"{len(outputs)} outputs and {len(request_info_events)} request info events, "
            f"final state: {final_state}"
        )

        # Process outputs
        for output in outputs:
            await ctx.send_message(output)

        # Process request info events
        for event in request_info_events:
            # Track the pending request in execution context
            execution_context.pending_requests[event.request_id] = event.data
            # Map request to execution for response routing
            self._request_to_execution[event.request_id] = execution_context.execution_id
            # Wrap request with routing context and send to parent
            if not isinstance(event.data, RequestInfoMessage):
                raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
            wrapped_request = SubWorkflowRequestInfo(
                request_id=event.request_id,
                sub_workflow_id=self.id,
                data=event.data,
            )
            await ctx.send_message(wrapped_request)

        # Update expected response count for this execution
        execution_context.expected_response_count = len(request_info_events)

        # Handle final state
        if final_state == WorkflowRunState.FAILED:
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
                self._active_executions -= 1
        elif final_state == WorkflowRunState.IDLE:
            # Sub-workflow is idle - nothing more to do now
            logger.debug(f"Sub-workflow {self.workflow.id} is idle with {self._active_executions} active executions")
            self._active_executions -= 1  # Treat idle as completion for now
        elif final_state == WorkflowRunState.CANCELLED:
            # Sub-workflow was cancelled - treat as completion
            logger.debug(
                f"Sub-workflow {self.workflow.id} was cancelled with {self._active_executions} active executions"
            )
            self._active_executions -= 1
        elif final_state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS:
            # Sub-workflow is still running with pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is still in progress with {len(request_info_events)} "
                f"pending requests with {self._active_executions} active executions"
            )
        elif final_state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
            # Sub-workflow is idle but has pending requests
            logger.debug(
                f"Sub-workflow {self.workflow.id} is idle with pending requests: "
                f"{len(request_info_events)} with {self._active_executions} active executions"
            )
        else:
            raise RuntimeError(f"Unexpected final state: {final_state}")

    @handler
    async def handle_response(
        self,
        response: SubWorkflowResponse,
        ctx: WorkflowContext[Any],
    ) -> None:
        """Handle response from parent for a forwarded request.

        This handler accumulates responses and only resumes the sub-workflow
        when all expected responses have been received for that execution.

        Args:
            response: The response to a previous request.
            ctx: The workflow context.
        """
        # Find the execution context for this request
        execution_id = self._request_to_execution.get(response.request_id)
        if not execution_id or execution_id not in self._execution_contexts:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: {response.request_id}, ignoring"
            )
            return

        execution_context = self._execution_contexts[execution_id]

        # Check if we have this pending request in the execution context
        if response.request_id not in execution_context.pending_requests:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: "
                f"{response.request_id} in execution {execution_id}, ignoring"
            )
            return

        # Remove the request from pending list and request mapping
        execution_context.pending_requests.pop(response.request_id, None)
        self._request_to_execution.pop(response.request_id, None)

        # Accumulate the response in this execution's context
        execution_context.collected_responses[response.request_id] = response.data

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
                self._active_executions -= 1
