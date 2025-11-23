# Copyright (c) Microsoft. All rights reserved.

from asyncio import CancelledError
from typing import Awaitable, Callable, Optional, Union

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TextPart
from a2a.utils import new_task
from agent_framework import ChatMessage, Role, BaseAgent, AgentThread, AgentThreadStorage, InMemoryAgentThreadStorage, \
    ChatAgent, WorkflowAgent

from ._a2a_event_adapter import A2aEventAdapter, BaseA2aEventAdapter
from ._a2a_execution_context import A2aExecutionContext

SyncGetAgentFuncType = Callable[[A2aExecutionContext], BaseAgent]
AsyncGetAgentFuncType = Callable[[A2aExecutionContext], Awaitable[BaseAgent]]
GetAgentFuncType = Union[SyncGetAgentFuncType, AsyncGetAgentFuncType]


class A2aExecutor(AgentExecutor):
    """Execute AI agents using the A2A (Agent-to-Agent) protocol.

    The A2aExecutor bridges AI agents built with the agent_framework library and the A2A protocol,
    enabling structured agent execution with event-driven communication. It manages agent threads,
    handles execution contexts, and converts agent responses into A2A protocol events.

    The executor supports both ChatAgent and WorkflowAgent types, persists conversation threads
    using configurable storage, and provides comprehensive error handling with task status updates.

    Args:
        agent_thread_storage (AgentThreadStorage): Storage backend for persisting agent conversation threads.
            Defaults to InMemoryAgentThreadStorage if not provided.
        agent (Union[ChatAgent, WorkflowAgent]): The AI agent to execute.
        event_adapter (A2aEventAdapter): Adapter for converting agent responses to A2A protocol events.
            Defaults to BaseA2aEventAdapter if not provided.

    Example:
        Basic usage with a ChatAgent:

        >>> from agent_framework import ChatAgent
        >>> from agent_framework.openai import OpenAIResponsesClient
        >>> from a2a.server.events import EventQueue
        >>> from a2a.server.agent_execution import RequestContext
        >>>
        >>> # Initialize the AI client and agent
        >>> agent = OpenAIResponsesClient().create_agent(
        ...     name="WeatherBot",
        ...     instructions="You are a helpful weather assistant.",
        ... )
        >>>
        >>> # Create the executor with default event adapter and storage
        >>> executor = A2aExecutor(agent=agent)
        >>>
        >>> # Execute an agent within an async context
        >>> async def run_example():
        ...     event_queue = EventQueue()
        ...     request_context = RequestContext(
        ...         user_input="What is the weather today?",
        ...         context_id="user-123"
        ...     )
        ...     await executor.execute(request_context, event_queue)
        ...     # Events are queued in event_queue for processing

        Custom event adapter and persistent storage:

        >>> from agent_framework import InMemoryAgentThreadStorage
        >>> from agent_framework.a2a import BaseA2aEventAdapter
        >>>
        >>> custom_adapter = BaseA2aEventAdapter()
        >>> storage = InMemoryAgentThreadStorage()
        >>>
        >>> executor = A2aExecutor(
        ...     agent=agent,
        ...     event_adapter=custom_adapter,
        ...     agent_thread_storage=storage
        ... )
        >>>
        >>> # The same context_id will reuse the same conversation thread
        >>> async def run_multi_turn():
        ...     event_queue = EventQueue()
        ...     context_id = "conversation-session-1"
        ...
        ...     # First turn
        ...     request1 = RequestContext(
        ...         user_input="Hello, who are you?",
        ...         context_id=context_id
        ...     )
        ...     await executor.execute(request1, event_queue)
        ...
        ...     # Second turn (same conversation thread)
        ...     request2 = RequestContext(
        ...         user_input="What did I just ask?",
        ...         context_id=context_id
        ...     )
        ...     await executor.execute(request2, event_queue)
    """

    def __init__(
        self,
        agent: Union[ChatAgent, WorkflowAgent],
        event_adapter: Optional[A2aEventAdapter] = None,
        agent_thread_storage: Optional[AgentThreadStorage] = None,
    ):
        """Initialize the A2aExecutor.

        Args:
            agent: The AI agent to execute. Can be a ChatAgent for conversational tasks
                or a WorkflowAgent for multistep agent workflows.
            event_adapter: Optional adapter for converting agent responses to A2A protocol events.
                If not provided, BaseA2aEventAdapter is used.
            agent_thread_storage: Optional storage backend for persisting agent conversation threads.
                If not provided, InMemoryAgentThreadStorage is used. For production systems,
                consider using persistent storage to maintain conversation state across restarts.
        """
        super().__init__()
        self._agent_thread_storage: AgentThreadStorage = agent_thread_storage if agent_thread_storage else InMemoryAgentThreadStorage()
        self._agent: Union[ChatAgent, WorkflowAgent] = agent
        self._event_adapter: A2aEventAdapter = event_adapter if event_adapter else BaseA2aEventAdapter()

    def build_context(
        self,
        request_context: RequestContext,
        task: Task,
        updater: TaskUpdater
    ) -> A2aExecutionContext:
        """Build the execution context for the agent."""
        return A2aExecutionContext(request_context, task, updater)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Cancellation handled at A2A protocol level
        pass

    async def get_agent_thread(self, context: A2aExecutionContext) -> AgentThread:
        """Get or create the agent thread for the given context."""
        thread = await self._agent_thread_storage.load_thread(context.task.context_id)
        if not thread:
            thread = self._agent.get_new_thread()
            await self._agent_thread_storage.save_thread(context.task.context_id, thread)
        return thread

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent with the given context and event queue."""
        query = context.get_user_input()
        task = context.current_task
        if not task:
            assert context.message
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        assert context.context_id

        updater = TaskUpdater(event_queue, task.id, context.context_id)
        await updater.submit()

        execution_context = self.build_context(context, task, updater)
        agent_thread = await self.get_agent_thread(execution_context)
        agent = self._agent
        try:
            await updater.start_work()
            # Create a ChatMessage from the query
            user_message = ChatMessage(role=Role.USER, text=query)

            # Run the agent with the message
            # Note: agent_framework's ChatAgent.run_stream returns AgentRunResponseUpdate objects
            async for response_update in agent.run_stream(user_message, thread=agent_thread):
                # Convert response updates to A2A protocol events
                if response_update.contents:
                    await self._event_adapter.handle_events(response_update, execution_context)
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