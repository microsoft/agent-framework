# Copyright (c) Microsoft. All rights reserved.

from asyncio import CancelledError

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import FilePart, FileWithBytes, FileWithUri, Part, Task, TaskState, TextPart
from a2a.utils import new_task
from agent_framework import (
    AgentThread,
    AgentThreadStorage,
    ChatAgent,
    ChatMessage,
    DataContent,
    InMemoryAgentThreadStorage,
    Role,
    TextContent,
    UriContent,
    WorkflowAgent,
)
from typing_extensions import override


class A2AExecutor(AgentExecutor):
    """Execute AI agents using the A2A (Agent-to-Agent) protocol.

    The A2aExecutor bridges AI agents built with the agent_framework library and the A2A protocol,
    enabling structured agent execution with event-driven communication. It manages agent threads,
    handles execution contexts, and converts agent responses into A2A protocol events.

    The executor supports both ChatAgent and WorkflowAgent types, persists conversation threads
    using configurable storage, and provides comprehensive error handling with task status updates.
    It handles various content types including text, binary data, and URI-based content.

    Key Features:
        - Multi-turn conversation support with thread persistence
        - Support for ChatAgent and WorkflowAgent agent types
        - Configurable storage backend for agent threads
        - Comprehensive error handling with task state management
        - Support for multiple content types (text, binary data, URIs)
        - Metadata preservation through message processing

    Args:
        agent: The AI agent to execute. Can be a ChatAgent for conversational tasks
            or a WorkflowAgent for multistep agent workflows.
        agent_thread_storage: Optional storage backend for persisting agent conversation threads.
            If not provided, InMemoryAgentThreadStorage is used. For production systems,
            consider using persistent storage to maintain conversation state across restarts.

    Raises:
        ValueError: If context_id or message is not provided in RequestContext during execution.

    Example:
        Creating an executor and starting an A2A server:

        .. code-block:: python

            from agent_framework.openai import OpenAIResponsesClient
            from agent_framework.a2a import A2AExecutor
            from a2a.server.apps import A2AStarletteApplication
            from a2a.server.request_handlers import DefaultRequestHandler
            from a2a.server.tasks import InMemoryTaskStore
            from a2a.types import AgentCapabilities, AgentCard, AgentSkill
            import uvicorn

            # Create the agent
            agent = OpenAIResponsesClient().create_agent(
                name="Food Agent", instructions="A simple agent that provides food-related information."
            )

            # Create the executor
            executor = A2AExecutor(agent=agent)

            # Create agent metadata
            skill = AgentSkill(
                id="Food_Agent",
                name="Food Agent",
                description="A simple agent that provides food-related information.",
                tags=["food", "nutrition", "recipes"],
            )

            agent_card = AgentCard(
                name="Food Agent",
                description="A simple agent that provides food-related information.",
                url="http://localhost:9999/",
                version="1.0.0",
                capabilities=AgentCapabilities(streaming=True),
                skills=[skill],
            )

            # Set up the A2A server
            request_handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())

            server = A2AStarletteApplication(
                agent_card=agent_card,
                http_handler=request_handler,
            ).build()

            # Run the server
            uvicorn.run(server, host="0.0.0.0", port=9999)
    """

    def __init__(
        self,
        agent: ChatAgent | WorkflowAgent,
        agent_thread_storage: AgentThreadStorage | None = None,
    ):
        """Initialize the A2aExecutor.

        This constructor sets up the executor with the specified agent and optional storage backend.
        The storage backend is responsible for persisting and retrieving agent conversation threads,
        enabling multi-turn conversations across different execution contexts.

        Args:
            agent: The AI agent to execute. Can be a ChatAgent for conversational tasks
                or a WorkflowAgent for multistep agent workflows.
            agent_thread_storage: Optional storage backend for persisting agent conversation threads.
                If not provided, InMemoryAgentThreadStorage is used. For production systems,
                consider using persistent storage (e.g., database-backed storage) to maintain
                conversation state across restarts and enable thread recovery.

        Example:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient
                from agent_framework.a2a import A2AExecutor
                from a2a.server.request_handlers import DefaultRequestHandler
                from a2a.server.tasks import InMemoryTaskStore

                # Create the agent
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent", instructions="A simple agent that provides food-related information."
                )

                # Create executor with default storage
                executor = A2AExecutor(agent=agent)

                # Use with request handler
                request_handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
        """
        super().__init__()
        self._agent_thread_storage: AgentThreadStorage = (
            agent_thread_storage if agent_thread_storage else InMemoryAgentThreadStorage()
        )
        self._agent: ChatAgent | WorkflowAgent = agent

    async def get_agent_thread(self, task: Task) -> AgentThread:
        """Get or create the agent thread for the given context.

        This method retrieves an existing agent thread from storage based on the task's context_id,
        or creates a new thread if one doesn't exist. This enables multi-turn conversations where
        the same context_id maintains a persistent conversation state across multiple executions.

        Args:
            task: The task object containing the context_id that identifies the conversation thread.

        Returns:
            AgentThread: An existing or newly created agent thread for the given context.

        Example:
            .. code-block:: python

                from a2a.types import Task

                # Get or create a thread for a specific context
                task = Task(context_id="user-session-123", id="task-1")
                thread = await executor.get_agent_thread(task)

                # The same context_id will return the same thread on subsequent calls
                task2 = Task(context_id="user-session-123", id="task-2")
                thread2 = await executor.get_agent_thread(task2)
                # thread and thread2 refer to the same conversation
        """
        thread = await self._agent_thread_storage.load_thread(task.context_id)
        if not thread:
            thread = self._agent.get_new_thread()
            await self._agent_thread_storage.save_thread(task.context_id, thread)
        return thread

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel agent execution.

        Cancellation is primarily managed by the A2A protocol layer. This method ensures
        compliance with the AgentExecutor interface.

        Args:
            context: The request context containing execution information.
            event_queue: The event queue for publishing events.
        """
        # Cancellation handled at A2A protocol level
        pass

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent with the given context and event queue.

        Orchestrates the agent execution process: validates inputs, retrieves or creates an agent thread,
        executes the agent, processes response messages, and handles errors with appropriate task status updates.

        Args:
            context: The request context containing user input and context_id. Must have both
                context_id and message attributes.
            event_queue: The event queue where task and status update events are published.

        Raises:
            ValueError: If context_id or message is not provided in RequestContext.

        Status Updates published:
            - TaskState.working: Agent execution begins and progresses
            - TaskState.completed: Agent execution completes successfully
            - TaskState.canceled: Execution cancelled via CancelledError
            - TaskState.failed: Execution encounters an exception

        Example:
            Typically called by the A2A request handler. See agent_framework_to_a2a.py sample
            for integration with DefaultRequestHandler and A2AStarletteApplication.

            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient
                from agent_framework.a2a import A2AExecutor
                from a2a.server.request_handlers import DefaultRequestHandler
                from a2a.server.tasks import InMemoryTaskStore

                # Create executor
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent",
                    instructions="A simple agent that provides food-related information.",
                )
                executor = A2AExecutor(agent=agent)

                # Use with request handler (handles execute calls automatically)
                request_handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
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

        agent_thread = await self.get_agent_thread(task)
        agent = self._agent
        try:
            await updater.start_work()
            # Create a ChatMessage from the query
            user_message = ChatMessage(role=Role.USER, text=query)

            # Run the agent with the message
            response = await agent.run(user_message, thread=agent_thread)
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

    async def handle_events(self, message: ChatMessage, updater: TaskUpdater) -> None:
        """Convert agent response messages to A2A protocol events and update task status.

        Processes ChatMessage objects returned by the agent and converts them into A2A protocol format.
        Handles multiple content types (TextContent, DataContent, UriContent), preserves metadata,
        and publishes status updates. USER role messages are skipped.

        Args:
            message: The ChatMessage returned by agent execution. Can contain multiple content items.
            updater: The TaskUpdater used to publish status updates to the event queue.

        Content Types Supported:
            - TextContent: Plain text responses
            - DataContent: Binary data/files (converted to FilePart with bytes)
            - UriContent: External resource references (converted to FilePart with URI)

        Example:
            Typically called automatically by execute(). For text response processing:

            .. code-block:: python

                from agent_framework import ChatMessage, Role, TextContent

                response_message = ChatMessage(
                    role=Role.ASSISTANT, contents=[TextContent(text="Food information response here.")]
                )
                await executor.handle_events(response_message, updater)

        Example with multiple content types:

            .. code-block:: python

                from agent_framework import ChatMessage, Role, TextContent, UriContent

                response_message = ChatMessage(
                    role=Role.ASSISTANT,
                    contents=[
                        TextContent(text="Here is the document:"),
                        UriContent(uri="https://example.com/recipe.pdf", media_type="application/pdf"),
                    ],
                )

                await executor.handle_events(response_message, updater)

        Note:
            Unsupported content types are silently skipped. Only messages with at least one
            supported content type will result in a status update being published.
        """
        if message.role == Role.USER:
            # This is a user message, we can ignore it in the context of task updates
            return

        parts: list[Part] = []
        metadata = getattr(message, "additional_properties", None)

        for content in message.contents:
            if isinstance(content, TextContent):
                parts.append(Part(root=TextPart(text=content.text)))
            if isinstance(content, DataContent):
                parts.append(Part(root=FilePart(file=FileWithBytes(bytes=content.get_data_bytes_as_str()))))
            if isinstance(content, UriContent):
                # Handle URI content
                parts.append(Part(root=FilePart(file=FileWithUri(uri=content.uri, mime_type=content.media_type))))
            # Silently skip unsupported content types

        if parts:
            await updater.update_status(
                state=TaskState.working,
                message=updater.new_agent_message(parts=parts, metadata=metadata),
            )
