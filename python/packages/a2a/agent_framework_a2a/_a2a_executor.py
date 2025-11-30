# Copyright (c) Microsoft. All rights reserved.

from asyncio import CancelledError

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import FilePart, FileWithBytes, FileWithUri, Part, Task, TaskState, TextPart
from a2a.utils import new_task
from agent_framework import (
    AgentThread,
    ChatAgent,
    ChatMessage,
    DataContent,
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
        - Customizable event transformation and storage

    Overrideable Methods:
        The following methods can be overridden in subclasses to customize behavior:

        - save_thread(context_id, thread): Override to implement custom persistent storage backends
          (e.g., database, file system, cloud storage). Called after each agent execution to persist
          conversation state.

        - get_thread(context_id): Override to retrieve threads from custom persistent storage backends.
          Called before agent execution to restore conversation history.

        - handle_events(message, updater): Override to implement custom event transformation logic.
          This allows you to customize how agent responses are converted to A2A protocol format.

    Args:
        agent: The AI agent to execute. Can be a ChatAgent for conversational tasks
            or a WorkflowAgent for multistep agent workflows.

    Raises:
        ValueError: If context_id or message is not provided in RequestContext during execution.

    Example:
        Creating an executor and starting an A2A server:

        .. code-block:: python

            import uvicorn
            from dotenv import load_dotenv
            from a2a.server.apps import A2AStarletteApplication
            from a2a.server.request_handlers import DefaultRequestHandler
            from a2a.server.tasks import InMemoryTaskStore
            from a2a.types import AgentCapabilities, AgentCard, AgentSkill
            from agent_framework.a2a import A2AExecutor
            from agent_framework.openai import OpenAIResponsesClient

            load_dotenv()

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

    Example with custom storage backend:

        .. code-block:: python

            from agent_framework import AgentThread
            from agent_framework.a2a import A2AExecutor
            from agent_framework.openai import OpenAIResponsesClient

            class DatabaseBackedA2AExecutor(A2AExecutor):
                '''Executor with custom database storage for agent threads.'''

                def __init__(self, agent, db_connection):
                    super().__init__(agent)
                    self.db = db_connection

                async def save_thread(self, context_id: str, thread: AgentThread) -> None:
                    '''Save thread to database instead of memory.'''
                    serialized = serialize_thread(thread)
                    await self.db.save(context_id, serialized)

                async def get_thread(self, context_id: str) -> AgentThread | None:
                    '''Retrieve thread from database.'''
                    serialized = await self.db.get(context_id)
                    if serialized:
                        return deserialize_thread(serialized)
                    return None

            # Create executor with custom storage
            agent = OpenAIResponsesClient().create_agent(
                name="Food Agent",
                instructions="A simple agent that provides food-related information."
            )
            executor = DatabaseBackedA2AExecutor(agent=agent, db_connection=my_db)
    """

    def __init__(
        self,
        agent: ChatAgent | WorkflowAgent,
    ):
        """Initialize the A2aExecutor with the specified agent.

        Sets up the executor with in-memory thread storage by default. For custom persistent storage
        implementations, override the save_thread() and get_thread() methods.

        Args:
            agent: The AI agent to execute (ChatAgent or WorkflowAgent).
        """
        super().__init__()
        self._agent_thread_storage: dict[str, AgentThread] = dict()
        self._agent: ChatAgent | WorkflowAgent = agent

    async def save_thread(self, context_id: str, thread: AgentThread) -> None:
        """Save the agent thread for the given context ID.

        This method persists the agent thread in the storage backend, associating it with the provided
        context_id. This enables multi-turn conversations where the same context_id maintains a persistent
        conversation state across multiple executions.

        By default, this method uses an in-memory dictionary for storage. For production deployments with
        data persistence requirements, you can override this method to implement custom storage backends.

        Args:
            context_id: The unique identifier for the conversation context. This typically represents
                a user session, conversation thread, or execution context.
            thread: The agent thread object containing the conversation state and history to be persisted.

        Custom Storage Implementation:
            Override this method in a subclass to implement custom storage:

            .. code-block:: python

                class DatabaseBackedA2AExecutor(A2AExecutor):
                    async def save_thread(self, context_id: str, thread: AgentThread) -> None:
                        # Serialize the thread to your preferred format
                        serialized_thread = serialize(thread)
                        # Save to database, cloud storage, etc.
                        await self.db.save_conversation(context_id, serialized_thread)

        Example:
            .. code-block:: python

                from agent_framework import ChatAgent, ChatMessage, Role
                from agent_framework.openai import OpenAIResponsesClient
                from agent_framework.a2a import A2AExecutor

                # Create agent and executor
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent",
                    instructions="A simple agent that provides food-related information."
                )
                executor = A2AExecutor(agent=agent)

                # Create and save a new thread
                context_id = "user-session-123"
                thread = agent.get_new_thread()
                await executor.save_thread(context_id, thread)

                # The thread is now persisted and can be retrieved later
                retrieved_thread = await executor.get_thread(context_id)
        """
        self._agent_thread_storage[context_id] = thread

    async def get_thread(self, context_id: str) -> AgentThread | None:
        """Retrieve the agent thread for the given context ID.

        This method retrieves an existing agent thread from storage based on the provided context_id.
        If no thread exists for the context_id, it returns None. This enables stateful multi-turn
        conversations where consecutive requests with the same context_id access the same conversation history.

        By default, this method uses an in-memory dictionary for storage. For production deployments with
        data persistence requirements, you can override this method to implement custom storage backends.

        Args:
            context_id: The unique identifier for the conversation context. This typically represents
                a user session, conversation thread, or execution context.

        Returns:
            AgentThread | None: The agent thread associated with the context_id, or None if not found.

        Custom Storage Implementation:
            Override this method in a subclass to implement custom storage:

            .. code-block:: python

                class DatabaseBackedA2AExecutor(A2AExecutor):
                    async def get_thread(self, context_id: str) -> AgentThread | None:
                        # Retrieve from database, cloud storage, etc.
                        serialized_thread = await self.db.get_conversation(context_id)
                        if serialized_thread:
                            # Deserialize back to AgentThread
                            return deserialize(serialized_thread)
                        return None

        Example:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient
                from agent_framework.a2a import A2AExecutor

                # Create agent and executor
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent",
                    instructions="A simple agent that provides food-related information."
                )
                executor = A2AExecutor(agent=agent)

                # Retrieve a thread for a specific context
                context_id = "user-session-123"
                thread = await executor.get_thread(context_id)

                if thread:
                    # Thread exists, proceed with conversation using this existing thread
                    pass
                else:
                    # No thread found for this context_id, a new one will be created
                    pass
        """
        return self._agent_thread_storage.get(context_id, None)

    async def get_agent_thread(self, task: Task) -> AgentThread:
        """Get or create the agent thread for the given context.

        This method retrieves an existing agent thread from storage based on the task's context_id,
        or creates a new thread if one doesn't exist. This enables multi-turn conversations where
        the same context_id maintains a persistent conversation state across multiple executions.

        This method is the primary way to obtain conversation threads and is called automatically
        by the execute() method during agent execution.

        Args:
            task: The task object containing the context_id that identifies the conversation thread.

        Returns:
            AgentThread: An existing or newly created agent thread for the given context.

        Example:
            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient
                from agent_framework.a2a import A2AExecutor
                from a2a.types import Task

                # Create agent and executor
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent",
                    instructions="A simple agent that provides food-related information."
                )
                executor = A2AExecutor(agent=agent)

                # Get or create a thread for a specific context
                task1 = Task(context_id="user-session-123", id="task-1")
                thread1 = await executor.get_agent_thread(task1)

                # The same context_id will return the same thread on subsequent calls
                task2 = Task(context_id="user-session-123", id="task-2")
                thread2 = await executor.get_agent_thread(task2)

                # thread1 and thread2 refer to the same conversation
                # and maintain conversation history across both executions
        """
        thread = await self.get_thread(task.context_id)
        if not thread:
            thread = self._agent.get_new_thread()
            await self.save_thread(task.context_id, thread)
        return thread

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel agent execution.

        Cancellation is primarily managed by the A2A protocol layer. This method ensures
        compliance with the AgentExecutor interface. When called, it signals that the current
        agent execution should be terminated gracefully.

        This base implementation does not perform any cancellation logic, as cancellation is
        handled by the A2A protocol infrastructure. Subclasses can override this method to
        implement custom cancellation behavior if needed.

        Args:
            context: The request context containing execution information about the agent being cancelled.
            event_queue: The event queue for publishing cancellation events and status updates.

        Example:
            Typically managed automatically by the A2A request handler:

            .. code-block:: python

                from agent_framework.openai import OpenAIResponsesClient
                from agent_framework.a2a import A2AExecutor
                from a2a.server.request_handlers import DefaultRequestHandler
                from a2a.server.tasks import InMemoryTaskStore

                # Create executor
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent",
                    instructions="A simple agent that provides food-related information."
                )
                executor = A2AExecutor(agent=agent)

                # Use with request handler (handles cancellation automatically)
                request_handler = DefaultRequestHandler(
                    agent_executor=executor,
                    task_store=InMemoryTaskStore()
                )
        """
        # Cancellation handled at A2A protocol level
        pass

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent with the given context and event queue.

        Orchestrates the agent execution process: validates inputs, retrieves or creates an agent thread,
        executes the agent, processes response messages, and handles errors with appropriate task status updates.

        This method manages the complete lifecycle of a single agent execution, including:
        1. Validating that context_id and message are provided
        2. Creating a Task object if one doesn't exist
        3. Submitting the task to the event queue
        4. Retrieving or creating an agent thread for the context
        5. Creating a ChatMessage from user input
        6. Running the agent and processing response messages
        7. Converting agent responses to A2A protocol format via handle_events()
        8. Handling errors and updating task status appropriately
        9. Persisting the agent thread for future multi-turn conversations

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

        Thread Persistence:
            The agent thread is automatically saved at the end of execution (in the finally block),
            ensuring that conversation history is preserved for subsequent calls with the same context_id.
            To customize how threads are stored, override the save_thread() method.

        Example:
            Typically called by the A2A request handler. Here's a complete setup using the
            agent_framework_to_a2a.py sample pattern:

            .. code-block:: python

                import uvicorn
                from dotenv import load_dotenv
                from a2a.server.apps import A2AStarletteApplication
                from a2a.server.request_handlers import DefaultRequestHandler
                from a2a.server.tasks import InMemoryTaskStore
                from a2a.types import AgentCapabilities, AgentCard, AgentSkill
                from agent_framework.a2a import A2AExecutor
                from agent_framework.openai import OpenAIResponsesClient

                load_dotenv()

                # Create the agent
                agent = OpenAIResponsesClient().create_agent(
                    name="Food Agent",
                    instructions="A simple agent that provides food-related information."
                )

                # Create the executor
                executor = A2AExecutor(agent=agent)

                # Define agent metadata
                skill = AgentSkill(
                    id="Food_Agent",
                    name="Food Agent",
                    description="A simple agent that provides food-related information.",
                    tags=["food", "nutrition", "recipes"],
                    examples=[],
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
                request_handler = DefaultRequestHandler(
                    agent_executor=executor,
                    task_store=InMemoryTaskStore(),
                )

                server = A2AStarletteApplication(
                    agent_card=agent_card,
                    http_handler=request_handler,
                ).build()

                # Run the server
                uvicorn.run(server, host="0.0.0.0", port=9999)

        Custom Storage and Event Handling:
            For production use cases, you can customize storage and event handling:

            .. code-block:: python

                class ProductionA2AExecutor(A2AExecutor):
                    async def save_thread(self, context_id: str, thread: AgentThread) -> None:
                        # Save to persistent database
                        await self.db.save_conversation(context_id, thread)

                    async def get_thread(self, context_id: str) -> AgentThread | None:
                        # Retrieve from persistent database
                        return await self.db.get_conversation(context_id)

                    async def handle_events(self, message: ChatMessage, updater: TaskUpdater) -> None:
                        # Custom event transformation logic
                        await super().handle_events(message, updater)
                        # Add custom processing here

                # Use with your custom storage
                executor = ProductionA2AExecutor(agent=agent)
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
        finally:
            await self.save_thread(task.context_id, agent_thread)

    async def handle_events(self, message: ChatMessage, updater: TaskUpdater) -> None:
        """Convert agent response messages to A2A protocol events and update task status.

        Processes ChatMessage objects returned by the agent and converts them into A2A protocol format.
        Handles multiple content types (TextContent, DataContent, UriContent), preserves metadata,
        and publishes status updates. USER role messages are skipped.

        This method is called automatically by execute() for each response message from the agent.
        It serves as the bridge between the agent framework's ChatMessage format and the A2A protocol's
        Part format, enabling seamless integration between agent responses and A2A clients.

        Args:
            message: The ChatMessage returned by agent execution. Can contain multiple content items.
            updater: The TaskUpdater used to publish status updates to the event queue.

        Content Types Supported:
            - TextContent: Plain text responses converted to TextPart
            - DataContent: Binary data/files converted to FilePart with bytes
            - UriContent: External resource references converted to FilePart with URI

        Metadata Handling:
            Additional message properties are preserved and passed through to the A2A protocol
            via the metadata parameter in update_status() calls.

        Example:
            Typically called automatically by execute(). For text response processing:

            .. code-block:: python

                from agent_framework import ChatMessage, Role, TextContent
                from a2a.server.tasks import TaskUpdater

                response_message = ChatMessage(
                    role=Role.ASSISTANT,
                    contents=[TextContent(text="Food information response here.")]
                )
                await executor.handle_events(response_message, updater)

        Example with multiple content types:

            .. code-block:: python

                from agent_framework import ChatMessage, Role, TextContent, UriContent
                from a2a.server.tasks import TaskUpdater

                response_message = ChatMessage(
                    role=Role.ASSISTANT,
                    contents=[
                        TextContent(text="Here is the document:"),
                        UriContent(uri="https://example.com/recipe.pdf", media_type="application/pdf"),
                    ],
                )
                await executor.handle_events(response_message, updater)

        Custom Event Transformation:
            You can override this method to implement custom event transformation logic:

            .. code-block:: python

                class CustomA2AExecutor(A2AExecutor):
                    async def handle_events(self, message: ChatMessage, updater: TaskUpdater) -> None:
                        # Call parent implementation
                        await super().handle_events(message, updater)

                        # Add custom transformation logic
                        if message.role == Role.ASSISTANT:
                            # Custom processing for assistant messages
                            custom_metadata = {"custom_field": "custom_value"}
                            await updater.update_status(
                                state=TaskState.working,
                                message=updater.new_agent_message(
                                    parts=parts,
                                    metadata=custom_metadata
                                ),
                            )

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
