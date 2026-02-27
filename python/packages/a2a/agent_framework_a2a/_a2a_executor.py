# Copyright (c) Microsoft. All rights reserved.

from asyncio import CancelledError

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import FilePart, FileWithBytes, FileWithUri, Part, TaskState, TextPart
from a2a.utils import new_task
from typing_extensions import override

from agent_framework import (
    Message,
    Content,
    Agent,
    WorkflowAgent,
)


class A2AExecutor(AgentExecutor):
    """Execute AI agents using the A2A (Agent-to-Agent) protocol.

    The A2aExecutor bridges AI agents built with the agent_framework library and the A2A protocol,
    enabling structured agent execution with event-driven communication. It manages agent history,
    handles execution contexts, and converts agent responses into A2A protocol events.

    The executor supports any agent implementing SupportsAgentRun, persists conversation history
    using a configurable history provider, and provides comprehensive error handling with task status updates.
    It handles various content types including text, binary data, and URI-based content.

    Args:
        agent: The AI agent to execute.
    """

    def __init__(
            self,
            agent: Agent | WorkflowAgent
    ):
        """Initialize the A2aExecutor with the specified agent.

        Sets up the executor with in-memory thread storage by default.

        Args:
            agent: The AI agent to execute.
        """
        super().__init__()
        self._agent: Agent | WorkflowAgent = agent

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel agent execution.

        Cancellation is primarily managed by the A2A protocol layer.
        """
        pass

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent with the given context and event queue.

        Orchestrates the agent execution process: retrieves conversation history,
        executes the agent, processes response messages, and handles errors with appropriate task status updates.
        """
        if context.context_id is None:
            raise ValueError("Context ID must be provided in the RequestContext")
        if context.message is None:
            raise ValueError("Message must be provided in the RequestContext")

        query = context.get_user_input()
        task = context.current_task

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, context.context_id)
        await updater.submit()

        try:
            await updater.start_work()

            session = self._agent.create_session(session_id=task.context_id)

            # Create a Message from the user query
            user_message = Message(role="user", contents=[Content.from_text(text=query)])

            # Run the agent with the message list
            response = await self._agent.run(user_message, session=session)

            response_messages = response.messages
            if not isinstance(response_messages, list):
                response_messages = [response_messages]

            for message in response_messages:
                await self.handle_events(message, updater)

            # Mark as complete
            await updater.complete()
        except CancelledError:
            await updater.update_status(state=TaskState.canceled, final=True)
        except Exception as e:
            await updater.update_status(
                state=TaskState.failed,
                final=True,
                message=updater.new_agent_message([Part(root=TextPart(text=str(e.args)))]),
            )

    async def handle_events(self, message: Message, updater: TaskUpdater) -> None:
        """Convert agent response messages to A2A protocol events and update task status.

        Processes Message objects returned by the agent and converts them into A2A protocol format.
        Handles text, data, and URI content. USER role messages are skipped.
        """
        if message.role == "user":
            # This is a user message, we can ignore it in the context of task updates
            return

        parts: list[Part] = []
        metadata = getattr(message, "additional_properties", None)

        for content in message.contents:
            if content.type == "text" and content.text:
                parts.append(Part(root=TextPart(text=content.text)))
            elif content.type == "data":
                base64_str = content.uri
                parts.append(Part(root=FilePart(file=FileWithBytes(bytes=base64_str, mime_type=content.media_type))))
            elif content.type == "uri":
                parts.append(Part(root=FilePart(file=FileWithUri(uri=content.uri, mime_type=content.media_type))))
            # Silently skip unsupported content types

        if parts:
            await updater.update_status(
                state=TaskState.working,
                message=updater.new_agent_message(parts=parts, metadata=metadata),
            )
