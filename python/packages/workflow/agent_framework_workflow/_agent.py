# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Any

from agent_framework import (
    AgentBase,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    AIContents,
    ChatMessage,
    ChatMessageList,
    ChatRole,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)
from agent_framework.exceptions import AgentExecutionException
from pydantic import Field

from ._events import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    RequestInfoEvent,
    WorkflowEvent,
)

if TYPE_CHECKING:
    from ._workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowThread(AgentThread):
    """Custom thread for workflows that tracks workflow execution state."""

    workflow_id: str = Field(default="", description="The unique identifier for the workflow")
    run_id: str = Field(default="", description="The unique identifier for this workflow run")
    workflow_name: str | None = Field(default=None, description="Optional name of the workflow")
    message_bookmark: int = Field(default=0, description="Track processed messages")

    def __init__(
        self,
        workflow_id: str,
        run_id: str,
        workflow_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the workflow thread.

        Args:
            workflow_id: The unique identifier for the workflow.
            run_id: The unique identifier for this workflow run.
            workflow_name: Optional name of the workflow.
            **kwargs: Additional keyword arguments passed to AgentThread.
        """
        # Initialize with an in-memory message store
        if "message_store" not in kwargs:
            kwargs["message_store"] = ChatMessageList()

        # Extract AgentThread parameters only
        service_thread_id = kwargs.get("service_thread_id")
        message_store = kwargs.get("message_store")

        # Initialize parent class first
        if service_thread_id is not None and message_store is not None:
            # Both parameters provided - this violates the constraint, use service_thread_id only
            super().__init__(service_thread_id)
        elif service_thread_id is not None:
            super().__init__(service_thread_id)
        elif message_store is not None:
            super().__init__(message_store=message_store)
        else:
            super().__init__()

        # Set our specific fields
        self.workflow_id = workflow_id
        self.run_id = run_id
        self.workflow_name = workflow_name
        self.message_bookmark = 0


class WorkflowAgent(AgentBase):
    """Python implementation of WorkflowHostAgent that wraps workflows as AIAgents.

    This agent allows workflows to participate in the agent ecosystem by implementing
    the AIAgent protocol, enabling seamless integration with orchestration and other
    agent-based systems.
    """

    workflow: "Workflow | None" = Field(default=None, description="The workflow to wrap as an agent")
    active_runs: dict[str, Any] = Field(default_factory=dict, description="Track running workflows by run_id")
    pending_requests: dict[str, RequestInfoEvent] = Field(
        default_factory=dict, description="Track pending request info events"
    )

    def __init__(
        self,
        workflow: "Workflow",
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the WorkflowAgent.

        Args:
            workflow: The workflow to wrap as an agent.
            id: Unique identifier for the agent. If None, will be generated.
            name: Optional name for the agent.
            description: Optional description of the agent.
            **kwargs: Additional keyword arguments passed to AgentBase.
        """
        if id is None:
            id = f"WorkflowAgent_{uuid.uuid4().hex[:8]}"
        # Initialize with standard AgentBase parameters first
        super().__init__(id=id, name=name, description=description, **kwargs)

        # Set additional fields directly
        object.__setattr__(self, "workflow", workflow)
        object.__setattr__(self, "active_runs", {})
        object.__setattr__(self, "pending_requests", {})

    def _generate_run_id(self) -> str:
        """Generate a unique run ID for this workflow execution.

        Returns:
            A unique run ID string.
        """
        return f"{self.id}_{uuid.uuid4().hex[:8]}"

    def get_new_thread(self) -> WorkflowThread:
        """Create a new workflow thread.

        Returns:
            A new WorkflowThread instance.
        """
        run_id = self._generate_run_id()
        return WorkflowThread(
            workflow_id=self.id,
            run_id=run_id,
            workflow_name=self.name,
        )

    async def _prepare_workflow_messages(
        self,
        input_messages: list[ChatMessage],
        thread: WorkflowThread,
    ) -> list[ChatMessage]:
        """Prepare messages for workflow execution using bookmark system.

        Args:
            input_messages: New input messages to process.
            thread: The workflow thread.

        Returns:
            List of messages to send to the workflow.
        """
        # Add input messages to thread
        if input_messages:
            if thread._message_store is not None:
                await thread._message_store.add_messages(input_messages)
            else:
                # If no message store, create one with the input messages
                thread._message_store = ChatMessageList(messages=input_messages)

        # Get messages from bookmark position (unprocessed messages)
        all_messages = await thread.list_messages() or []
        return all_messages[thread.message_bookmark :]

    async def _extract_function_result_responses(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[tuple[str, Any]], list[ChatMessage]]:
        """Extract function result responses from input messages and separate other messages.

        Args:
            messages: Input messages that may contain function results.

        Returns:
            Tuple of:
            - List of (request_id, response_data) tuples for pending requests
            - List of non-function-result messages that should be preserved for next run
        """
        responses = []
        other_messages = []

        for message in messages:
            non_function_contents: list[AIContents] = []

            for content in message.contents:
                if isinstance(content, FunctionResultContent):
                    request_id = content.call_id
                    # Check if we have a pending request for this call_id
                    if request_id in self.pending_requests:
                        response_data = content.result if hasattr(content, "result") else str(content)
                        responses.append((request_id, response_data))
                    else:
                        # Function result for unknown request - treat as non-function content
                        non_function_contents.append(content)
                else:
                    non_function_contents.append(content)

            # If message has non-function contents, preserve it for next run
            if non_function_contents:
                preserved_message = ChatMessage(
                    role=message.role,
                    contents=non_function_contents,
                    author_name=message.author_name,
                    message_id=message.message_id,
                )
                other_messages.append(preserved_message)

        return responses, other_messages

    async def _convert_workflow_event_to_agent_update(
        self,
        event: WorkflowEvent,
        thread: WorkflowThread,
    ) -> AgentRunResponseUpdate | None:
        """Convert workflow events to agent response updates.

        Args:
            event: The workflow event to convert.
            thread: The workflow thread.

        Returns:
            An AgentRunResponseUpdate if the event should be converted, None otherwise.
        """
        match event:
            case AgentRunStreamingEvent(data=update):
                # Direct pass-through of agent streaming events
                return update

            case AgentRunEvent(data=response):
                # Convert completed agent response to update
                if response and response.messages:
                    # Use the first message for the update
                    first_message = response.messages[0]
                    return AgentRunResponseUpdate(
                        contents=first_message.contents,
                        role=first_message.role,
                        author_name=first_message.author_name,
                        message_id=first_message.message_id,
                        response_id=response.response_id,
                        created_at=response.created_at,
                    )

            case RequestInfoEvent(request_id=request_id):
                # Store the pending request for later correlation
                self.pending_requests[request_id] = event

                # Convert to function call content
                function_call = FunctionCallContent(
                    call_id=request_id,
                    name="request_info",
                    arguments={"request_id": request_id, "data": str(event.data)},
                )
                return AgentRunResponseUpdate(
                    contents=[function_call],
                    role=ChatRole.ASSISTANT,
                )

        return None

    async def _update_thread_bookmark(
        self,
        thread: WorkflowThread,
        workflow_messages: list[ChatMessage],
    ) -> None:
        """Update the thread bookmark after workflow processing.

        Args:
            thread: The workflow thread.
            workflow_messages: Messages that were sent to the workflow.
        """
        # Update bookmark to mark messages as processed
        thread.message_bookmark += len(workflow_messages)

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Get a response from the workflow agent (non-streaming).

        This method collects all streaming updates and merges them into a single response.

        Args:
            messages: The message(s) to send to the workflow.
            thread: The conversation thread. If None, a new thread will be created.
            **kwargs: Additional keyword arguments.

        Returns:
            The final workflow response as an AgentRunResponse.
        """
        # Collect all streaming updates
        response_messages: list[ChatMessage] = []
        final_response_id: str | None = None
        final_created_at: str | None = None

        async for update in self.run_streaming(messages=messages, thread=thread, **kwargs):
            if update.contents:
                # Create a ChatMessage from the update
                message = ChatMessage(
                    role=update.role or ChatRole.ASSISTANT,
                    contents=update.contents,
                    author_name=update.author_name,
                    message_id=update.message_id,
                )
                response_messages.append(message)

            # Capture final response metadata
            if update.response_id:
                final_response_id = update.response_id
            if update.created_at:
                final_created_at = update.created_at

        return AgentRunResponse(
            messages=response_messages,
            response_id=final_response_id,
            created_at=final_created_at,
        )

    def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream response updates from the workflow agent.

        Args:
            messages: The message(s) to send to the workflow.
            thread: The conversation thread. If None, a new thread will be created.
            **kwargs: Additional keyword arguments.

        Yields:
            AgentRunResponseUpdate objects representing the workflow execution progress.
        """
        return self._run_streaming_impl(messages, thread, **kwargs)

    async def _run_streaming_impl(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None,
        thread: AgentThread | None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Internal implementation of streaming execution.

        Args:
            messages: The message(s) to send to the workflow.
            thread: The conversation thread. If None, a new thread will be created.
            **kwargs: Additional keyword arguments.

        Yields:
            AgentRunResponseUpdate objects representing the workflow execution progress.
        """
        try:
            # Ensure we have a WorkflowThread
            if thread is None:
                thread = self.get_new_thread()
            elif not isinstance(thread, WorkflowThread):
                # Convert regular AgentThread to WorkflowThread
                run_id = self._generate_run_id()
                workflow_thread = WorkflowThread(
                    workflow_id=self.id,
                    run_id=run_id,
                    workflow_name=self.name,
                )
                # Copy messages from original thread if any exist
                existing_messages = await thread.list_messages()
                if existing_messages and workflow_thread._message_store is not None:
                    await workflow_thread._message_store.add_messages(existing_messages)
                thread = workflow_thread

            # Convert input to list of ChatMessage
            input_messages: list[ChatMessage] = []
            if messages is not None:
                if isinstance(messages, str):
                    input_messages = [ChatMessage(role=ChatRole.USER, contents=[TextContent(text=messages)])]
                elif isinstance(messages, ChatMessage):
                    input_messages = [messages]
                elif isinstance(messages, list):
                    input_messages = []
                    for msg in messages:
                        if isinstance(msg, str):
                            input_messages.append(ChatMessage(role=ChatRole.USER, contents=[TextContent(text=msg)]))
                        elif isinstance(msg, ChatMessage):
                            input_messages.append(msg)

            # Extract function result responses and separate other messages first
            function_responses, other_messages = await self._extract_function_result_responses(input_messages)

            # Prepare workflow messages using bookmark system
            # For continuation runs with function responses, we don't send new workflow messages
            workflow_messages = []
            if not (function_responses and thread.run_id in self.active_runs):
                workflow_messages = await self._prepare_workflow_messages(input_messages, thread)

            # Track this workflow run
            self.active_runs[thread.run_id] = thread

            try:
                # Ensure workflow is not None
                if self.workflow is None:
                    raise ValueError("Workflow not initialized")

                # Determine the event stream based on whether we have function responses
                if function_responses and thread.run_id in self.active_runs:
                    # This is a continuation - use send_responses_streaming to send function responses back
                    logger.info(f"Continuing workflow with {len(function_responses)} responses")

                    # Warn about other messages that will be ignored during continuation
                    if other_messages:
                        logger.warning(
                            f"During workflow continuation, {len(other_messages)} non-function-result messages "
                            f"are being ignored and will need to be sent in the next run. "
                            f"Consider sending function responses separately from other messages."
                        )

                    # Convert function responses to dict format expected by send_responses_streaming
                    response_dict = {request_id: response_data for request_id, response_data in function_responses}
                    # Clear the pending requests that we're responding to
                    for request_id, _ in function_responses:
                        self.pending_requests.pop(request_id, None)

                    event_stream = self.workflow.send_responses_streaming(response_dict)
                else:
                    # Execute workflow with streaming (initial run or no function responses)
                    event_stream = self.workflow.run_streaming(workflow_messages)

                # Process events from the stream
                async for event in event_stream:
                    # Convert workflow event to agent update
                    update = await self._convert_workflow_event_to_agent_update(event, thread)
                    if update is not None:
                        yield update

                # Update thread bookmark after workflow processing completes
                await self._update_thread_bookmark(thread, workflow_messages)

                # If we had other messages during continuation, add them to thread for next run
                if other_messages and function_responses and thread._message_store is not None:
                    logger.info(f"Adding {len(other_messages)} preserved messages to thread for next run")
                    await thread._message_store.add_messages(other_messages)

            finally:
                # Clean up active run tracking
                self.active_runs.pop(thread.run_id, None)
                # Note: Don't clean up pending_requests here as they may be needed for continuation

        except Exception as e:
            logger.error(f"Error in workflow agent execution: {e}", exc_info=True)
            raise AgentExecutionException(f"Workflow execution failed: {e}") from e
