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
    WorkflowCompletedEvent,
    WorkflowEvent,
)

if TYPE_CHECKING:
    from ._workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAgentThread(AgentThread):
    """Custom thread for workflow agents that tracks workflow execution state."""

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
        """Initialize the workflow agent thread.

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

    def __init__(
        self,
        workflow: "Workflow[list[ChatMessage]]",
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
        super().__init__(id=id, name=name, description=description, **kwargs)
        self._workflow = workflow
        self._active_runs: dict[str, Any] = {}  # Track running workflows by run_id
        self._pending_requests: dict[str, RequestInfoEvent] = {}  # Track pending request info events

    def _generate_run_id(self) -> str:
        """Generate a unique run ID for this workflow execution.

        Returns:
            A unique run ID string.
        """
        return f"{self.id}_{uuid.uuid4().hex[:8]}"

    def get_new_thread(self) -> WorkflowAgentThread:
        """Create a new workflow agent thread.

        Returns:
            A new WorkflowAgentThread instance.
        """
        run_id = self._generate_run_id()
        return WorkflowAgentThread(
            workflow_id=self.id,
            run_id=run_id,
            workflow_name=self.name,
        )

    async def _prepare_workflow_messages(
        self,
        input_messages: list[ChatMessage],
        thread: WorkflowAgentThread,
    ) -> list[ChatMessage]:
        """Prepare messages for workflow execution using bookmark system.

        Args:
            input_messages: New input messages to process.
            thread: The workflow agent thread.

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
    ) -> list[tuple[str, Any]]:
        """Extract function result responses from input messages.

        Args:
            messages: Input messages that may contain function results.

        Returns:
            List of (request_id, response_data) tuples for pending requests.
        """
        responses = []
        for message in messages:
            for content in message.contents:
                if isinstance(content, FunctionResultContent):
                    request_id = content.call_id

                    # Check if we have a pending request for this call_id
                    if request_id in self._pending_requests:
                        response_data = content.result if hasattr(content, "result") else str(content)
                        responses.append((request_id, response_data))

        return responses

    async def _convert_workflow_event_to_agent_update(
        self,
        event: WorkflowEvent,
        thread: WorkflowAgentThread,
    ) -> AgentRunResponseUpdate | None:
        """Convert workflow events to agent response updates.

        Args:
            event: The workflow event to convert.
            thread: The workflow agent thread.

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
                self._pending_requests[request_id] = event

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
        thread: WorkflowAgentThread,
        workflow_messages: list[ChatMessage],
    ) -> None:
        """Update the thread bookmark after workflow processing.

        Args:
            thread: The workflow agent thread.
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
            # Ensure we have a WorkflowAgentThread
            if thread is None:
                thread = self.get_new_thread()
            elif not isinstance(thread, WorkflowAgentThread):
                # Convert regular AgentThread to WorkflowAgentThread
                run_id = self._generate_run_id()
                workflow_thread = WorkflowAgentThread(
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

            # Prepare workflow messages using bookmark system
            workflow_messages = await self._prepare_workflow_messages(input_messages, thread)

            # Extract function result responses before starting/continuing workflow
            function_responses = await self._extract_function_result_responses(input_messages)

            # Track this workflow run
            self._active_runs[thread.run_id] = thread

            try:
                # Check if this is a continuation of existing workflow (has pending requests)
                if function_responses and thread.run_id in self._active_runs:
                    # This is a continuation - we need to resume existing workflow with responses
                    # For now, we'll send the workflow messages and let the workflow handle responses
                    # The proper approach would be to integrate with the workflow's request-response system
                    logger.info(f"Continuing workflow with {len(function_responses)} responses")

                    # Clear the pending requests that we're responding to
                    for request_id, _ in function_responses:
                        self._pending_requests.pop(request_id, None)

                # Execute workflow with streaming
                async for event in self._workflow.run_streaming(workflow_messages):
                    # Convert workflow event to agent update
                    update = await self._convert_workflow_event_to_agent_update(event, thread)
                    if update is not None:
                        yield update

                    # If this is a completed event, update thread bookmark
                    if isinstance(event, WorkflowCompletedEvent):
                        await self._update_thread_bookmark(thread, workflow_messages)
                        # Add final messages to thread if any
                        if (
                            hasattr(event, "data")
                            and isinstance(event.data, list)
                            and thread._message_store is not None
                        ):
                            await thread._message_store.add_messages(event.data)

            finally:
                # Clean up active run tracking
                self._active_runs.pop(thread.run_id, None)
                # Clean up any remaining pending requests for this thread
                pending_to_remove = list(self._pending_requests.keys())
                for req_id in pending_to_remove:
                    self._pending_requests.pop(req_id, None)

        except Exception as e:
            logger.error(f"Error in workflow agent execution: {e}", exc_info=True)
            raise AgentExecutionException(f"Workflow execution failed: {e}") from e
