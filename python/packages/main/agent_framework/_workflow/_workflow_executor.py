# Copyright (c) Microsoft. All rights reserved.

import logging
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


class WorkflowExecutor(Executor):
    """An executor that runs another workflow as its execution logic.

    This executor wraps a workflow to make it behave as an executor, enabling
    hierarchical workflow composition. Sub-workflows can send requests that
    are intercepted by parent workflows.
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

        # Track pending external responses by request_id
        self._pending_responses: dict[str, Any] = {}  # request_id -> response_data
        # Track workflow state for proper resumption - support multiple concurrent requests
        self._pending_requests: dict[str, Any] = {}  # request_id -> original request data
        self._active_executions: int = 0  # Count of active sub-workflow executions
        # Response accumulation for multiple concurrent responses
        self._collected_responses: dict[str, Any] = {}  # Accumulate responses
        self._expected_response_count: int = 0  # Track how many responses we're waiting for

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

        # Track this execution
        self._active_executions += 1

        logger.debug(f"WorkflowExecutor {self.id} starting sub-workflow {self.workflow.id} execution")

        # Run the sub-workflow and collect all events
        result = await self.workflow.run(input_data)

        logger.debug(
            f"WorkflowExecutor {self.id} sub-workflow {self.workflow.id} execution completed with {len(result)} events"
        )

        # Initialize response accumulation for this execution
        self._collected_responses = {}

        # Process the workflow result using shared logic
        await self._process_workflow_result(result, ctx)

    async def _process_workflow_result(self, result: Any, ctx: WorkflowContext[Any]) -> None:
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
            # Track the pending request
            self._pending_requests[event.request_id] = event.data
            # Wrap request with routing context and send to parent
            if not isinstance(event.data, RequestInfoMessage):
                raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
            wrapped_request = SubWorkflowRequestInfo(
                request_id=event.request_id,
                sub_workflow_id=self.id,
                data=event.data,
            )
            await ctx.send_message(wrapped_request)

        # Update expected response count for next batch of requests
        self._expected_response_count = len(request_info_events)

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
        when all expected responses have been received.

        Args:
            response: The response to a previous request.
            ctx: The workflow context.
        """
        # Check if we have this pending request
        pending_requests = getattr(self, "_pending_requests", {})
        if response.request_id not in pending_requests:
            logger.warning(
                f"WorkflowExecutor {self.id} received response for unknown request_id: {response.request_id}, ignoring"
            )
            return

        # Remove the request from pending list
        pending_requests.pop(response.request_id, None)

        # Accumulate the response
        self._collected_responses[response.request_id] = response.data

        # Check if we have all expected responses for current batch
        if len(self._collected_responses) < self._expected_response_count:
            logger.debug(
                f"WorkflowExecutor {self.id} waiting for more responses: "
                f"{len(self._collected_responses)}/{self._expected_response_count} received"
            )
            return  # Wait for more responses

        # Send all collected responses to the sub-workflow
        responses_to_send = dict(self._collected_responses)
        self._collected_responses.clear()  # Clear for next batch

        # Resume the sub-workflow with all collected responses
        result = await self.workflow.send_responses(responses_to_send)

        # Process the workflow result using shared logic
        await self._process_workflow_result(result, ctx)
