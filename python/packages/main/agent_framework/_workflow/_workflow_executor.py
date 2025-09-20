# Copyright (c) Microsoft. All rights reserved.

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._workflow import Workflow

from pydantic import Field

from ._events import (
    ExecutorEvent,
    RequestInfoEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from ._executor import Executor, RequestInfoMessage, SubWorkflowRequestInfo, SubWorkflowResponse, handler
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
        """
        return self.workflow.output_types

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
            return

        # Track this execution
        self._active_executions += 1

        try:
            # Run the sub-workflow and collect all events
            events = [event async for event in self.workflow.run_stream(input_data)]

            # Process events in single iteration
            request_count = 0
            workflow_completed = False

            for event in events:
                if isinstance(event, WorkflowOutputEvent):
                    # Sub-workflow yielded output - send it to parent
                    await ctx.send_message(event.output)

                elif isinstance(event, RequestInfoEvent):
                    # Sub-workflow needs external information
                    request_count += 1
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

                elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.COMPLETED:
                    # Check if workflow is completed
                    workflow_completed = True

            # Initialize response accumulation for this execution
            self._expected_response_count = request_count
            self._collected_responses = {}

            # Handle completion if workflow completed
            if workflow_completed:
                self._active_executions -= 1
                return  # Exit after completion

        except Exception as e:
            # Sub-workflow failed - create error event
            error_event = ExecutorEvent(executor_id=self.id, data={"error": str(e), "type": "sub_workflow_error"})
            await ctx.add_event(error_event)
            self._active_executions -= 1
            raise

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

        result_events = [event async for event in self.workflow.send_responses_streaming(responses_to_send)]

        # Process events in single iteration
        new_request_count = 0
        workflow_completed = False

        for event in result_events:
            if isinstance(event, WorkflowOutputEvent):
                # Sub-workflow yielded output - send it to parent
                await ctx.send_message(event.output)

            elif isinstance(event, RequestInfoEvent):
                # Sub-workflow sent more requests - prepare for next batch
                new_request_count += 1
                self._pending_requests[event.request_id] = event.data

                # Send the new request to parent
                if not isinstance(event.data, RequestInfoMessage):
                    raise TypeError(f"Expected RequestInfoMessage, got {type(event.data)}")
                wrapped_request = SubWorkflowRequestInfo(
                    request_id=event.request_id,
                    sub_workflow_id=self.id,
                    data=event.data,
                )
                await ctx.send_message(wrapped_request)

            elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.COMPLETED:
                # Check if workflow is completed
                workflow_completed = True

        # Handle completion if workflow completed
        if workflow_completed:
            self._active_executions -= 1
            return

        # Update expected count for next batch of requests
        self._expected_response_count = new_request_count
