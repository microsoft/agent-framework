# Copyright (c) Microsoft. All rights reserved.

import logging
from asyncio import CancelledError
from collections.abc import Mapping
from functools import partial
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import FilePart, FileWithBytes, FileWithUri, Part, TaskState, TextPart
from a2a.utils import new_task
from agent_framework import (
    AgentResponseUpdate,
    AgentSession,
    Message,
    SupportsAgentRun,
)
from typing_extensions import override

from agent_framework_a2a._utils import get_uri_data

logger = logging.getLogger("agent_framework.a2a")


class A2AExecutor(AgentExecutor):
    """Execute AI agents using the A2A (Agent-to-Agent) protocol.

    The A2AExecutor bridges AI agents built with the agent_framework library and the A2A protocol,
    enabling structured agent execution with event-driven communication. It handles execution
    contexts, delegates history management to the agent's session, and converts agent
    responses into A2A protocol events.

    The executor supports executing an Agent or WorkflowAgent. It provides comprehensive
    error handling with task status updates and supports various content types including text,
    binary data, and URI-based content.

    Example:
        .. code-block:: python

            from a2a.server.apps import A2AStarletteApplication
            from a2a.server.request_handlers import DefaultRequestHandler
            from a2a.server.tasks import InMemoryTaskStore
            from a2a.types import AgentCapabilities, AgentCard
            from agent_framework.a2a import A2AExecutor
            from agent_framework.openai import OpenAIResponsesClient

            public_agent_card = AgentCard(
                name="Food Agent",
                description="A simple agent that provides food-related information.",
                url="http://localhost:9999/",
                version="1.0.0",
                defaultInputModes=["text"],
                defaultOutputModes=["text"],
                capabilities=AgentCapabilities(streaming=True),
                skills=[],
            )

            # Create an agent
            agent = OpenAIResponsesClient().as_agent(
                name="Food Agent",
                instructions="A simple agent that provides food-related information.",
            )

            # Set up the A2A server with the A2AExecutor enabled for streaming
            # and passing custom keyword arguments to the agent's run method.
            request_handler = DefaultRequestHandler(
                agent_executor=A2AExecutor(agent, stream=True, run_kwargs={"client_kwargs": {"max_tokens": 500}}),
                task_store=InMemoryTaskStore(),
            )

            server = A2AStarletteApplication(
                agent_card=public_agent_card,
                http_handler=request_handler,
            ).build()

    Args:
        agent: The AI agent to execute.
        stream: Whether to stream the agent response. Defaults to False.
        run_kwargs: Additional keyword arguments to pass to the agent's run method.
    """

    def __init__(self, agent: SupportsAgentRun, stream: bool = False, run_kwargs: Mapping[str, Any] | None = None):
        """Initialize the A2AExecutor with the specified agent.

        Args:
            agent: The AI agent or workflow to execute.
            stream: Whether to stream the agent response. Defaults to False.
            run_kwargs: Additional keyword arguments to pass to the agent's run method.
                Cannot contain 'session' or 'stream' as these are managed by the executor.

        Raises:
            ValueError: If run_kwargs contains 'session' or 'stream'.
        """
        super().__init__()
        self._agent: SupportsAgentRun = agent
        self._stream: bool = stream
        if run_kwargs:
            if "session" in run_kwargs:
                raise ValueError("run_kwargs cannot contain 'session' as it is managed by the executor.")
            if "stream" in run_kwargs:
                raise ValueError("run_kwargs cannot contain 'stream' as it is managed by the executor.")
        self._run_kwargs: Mapping[str, Any] = run_kwargs or {}

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel agent execution for the given request context.

        Uses a TaskUpdater to send a cancellation event through the provided event queue.

        Args:
            context: The request context identifying the task to cancel.
            event_queue: The event queue to publish the cancellation event to.

        Raises:
            ValueError: If context_id is not provided in the RequestContext.
        """
        if context.context_id is None:
            raise ValueError("Context ID must be provided in the RequestContext")

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=context.task_id or "",
            context_id=context.context_id,
        )

        await updater.cancel()

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent with the given context and event queue.

        Orchestrates the agent execution process: sets up the agent session,
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

            if self._stream:
                await self._run_stream(query, session, updater)
            else:
                await self._run(query, session, updater)

            # Mark as complete
            await updater.complete()
        except CancelledError:
            await updater.update_status(state=TaskState.canceled, final=True)
        except Exception as e:
            logger.exception("A2AExecutor encountered an error during execution.", exc_info=e)
            await updater.update_status(
                state=TaskState.failed,
                final=True,
                message=updater.new_agent_message([Part(root=TextPart(text=str(e)))]),
            )

    async def _run_stream(self, query: Any, session: AgentSession, updater: TaskUpdater) -> None:
        """Run the agent in streaming mode and publish updates to the task updater."""
        response_stream = self._agent.run(query, session=session, stream=True, **self._run_kwargs)
        streamed_artifact_ids: set[str] = set()
        await (
            response_stream.with_transform_hook(
                partial(self.handle_events, updater=updater, streamed_artifact_ids=streamed_artifact_ids)
            )
        ).get_final_response()

    async def _run(self, query: Any, session: AgentSession, updater: TaskUpdater) -> None:
        """Run the agent in non-streaming mode and publish messages to the task updater."""
        response = await self._agent.run(query, session=session, stream=False, **self._run_kwargs)
        response_messages = response.messages

        if not isinstance(response_messages, list):
            response_messages = [response_messages]

        for message in response_messages:
            await self.handle_events(message, updater)

    async def handle_events(
        self, item: Message | AgentResponseUpdate, updater: TaskUpdater, streamed_artifact_ids: set[str] | None = None
    ) -> None:
        """Convert agent response items (Messages or Updates) to A2A protocol events.

        Processes Message or AgentResponseUpdate objects and converts them into A2A protocol format.
        Handles text, data, and URI content. USER role messages are skipped.

        Users can override this method in a subclass to implement custom transformations
        from their agent's output format to A2A protocol events.

        Args:
            item: The agent response item (Message or AgentResponseUpdate) to process.
            updater: The task updater to publish events to.
            streamed_artifact_ids: A set of artifact IDs that have already been streamed.
                Used to prevent duplicate updates for the same artifact.

        Example:
            .. code-block:: python

                class CustomA2AExecutor(A2AExecutor):
                    async def handle_events(
                        self,
                        item: Message | AgentResponseUpdate,
                        updater: TaskUpdater,
                        streamed_artifact_ids: set[str] | None = None,
                    ) -> None:
                        # Custom logic to transform item contents
                        if item.role == "assistant" and item.contents:
                            parts = [Part(root=TextPart(text=f"Custom: {item.contents[0].text}"))]
                            await updater.update_status(
                                state=TaskState.working,
                                message=updater.new_agent_message(parts=parts),
                            )
                        else:
                            await super().handle_events(item, updater)
        """
        role = getattr(item, "role", None)
        if role == "user":
            # This is a user message, we can ignore it in the context of task updates
            return

        parts: list[Part] = []
        metadata = getattr(item, "additional_properties", None)

        # AgentResponseUpdate uses 'contents', Message uses 'contents'
        contents = getattr(item, "contents", [])

        for content in contents:
            if content.type == "text" and content.text:
                parts.append(Part(root=TextPart(text=content.text)))
            elif content.type == "data" and content.uri:
                base64_str = get_uri_data(content.uri)
                parts.append(Part(root=FilePart(file=FileWithBytes(bytes=base64_str, mime_type=content.media_type))))
            elif content.type == "uri" and content.uri:
                parts.append(Part(root=FilePart(file=FileWithUri(uri=content.uri, mime_type=content.media_type))))
            else:
                # Silently skip unsupported content types
                logger.warning("A2AExecutor does not yet support content type: %s. Omitted.", content.type)

        if parts:
            if isinstance(item, AgentResponseUpdate):
                # For streaming updates, we send TaskArtifactUpdateEvent via add_artifact
                await updater.add_artifact(
                    parts=parts,
                    artifact_id=item.message_id,
                    metadata=metadata,
                    append=(
                        True
                        if streamed_artifact_ids is not None and item.message_id in (streamed_artifact_ids or set())
                        else None
                    ),
                )
                if item.message_id and streamed_artifact_ids is not None:
                    streamed_artifact_ids.add(item.message_id)
            else:
                # For final messages, we send TaskStatusUpdateEvent with 'working' state
                await updater.update_status(
                    state=TaskState.working,
                    message=updater.new_agent_message(parts=parts, metadata=metadata),
                )
