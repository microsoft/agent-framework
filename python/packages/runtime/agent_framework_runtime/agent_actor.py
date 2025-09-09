# Copyright (c) Microsoft. All rights reserved.

"""Core actor abstractions for the Python actor runtime."""

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Union

from agent_framework import AgentProtocol, AgentThread, ChatMessage
from pydantic import BaseModel


@dataclass(frozen=True, kw_only=True)
class ActorId:
    """Unique identifier for an actor instance."""

    type_name: str
    instance_id: str

    def __str__(self) -> str:
        """Return the string representation of the actor ID."""
        return f"{self.type_name}/{self.instance_id}"


class ActorMessageType(Enum):
    """Types of messages that can be sent to actors."""

    REQUEST = "request"
    RESPONSE = "response"


class RequestStatus(Enum):
    """Status of a request being processed by an actor."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_FOUND = "not_found"


@dataclass
class _ActorMessage:
    """Base class for all actor system messages (not intended for direct use)."""

    message_id: str
    message_type: ActorMessageType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(kw_only=True)
class ActorRequestMessage(_ActorMessage):
    """Request message sent to an actor."""

    method: str = ""
    params: dict[str, Any] | None = None
    sender_id: ActorId | None = None

    def __post_init__(self):
        """Initialize the message type after dataclass creation."""
        self.message_type = ActorMessageType.REQUEST


@dataclass(kw_only=True)
class ActorResponseMessage(_ActorMessage):
    """Response message from an actor."""

    sender_id: ActorId
    status: RequestStatus
    data: Any = None

    def __post_init__(self):
        """Initialize the message type after dataclass creation."""
        self.message_type = ActorMessageType.RESPONSE


# Type alias for the union of message types (public API)
ActorMessage = Union[ActorRequestMessage, ActorResponseMessage]


class ActorRuntimeContext(ABC):
    """Runtime context provided to actors."""

    @property
    @abstractmethod
    def actor_id(self) -> ActorId:
        """Get the actor's unique identifier."""
        pass

    @abstractmethod
    def watch_messages(self) -> AsyncIterator[ActorMessage]:
        """Watch for incoming messages.

        Implementations should be async generators that yield ActorMessage
        instances as they arrive from the underlying message transport.

        Example implementation:
            async def watch_messages(self) -> AsyncIterator[ActorMessage]:
                while True:
                    message = await self._message_queue.get()
                    if message is None:  # Shutdown signal
                        break
                    yield message
        """
        raise NotImplementedError

    @abstractmethod
    async def read_state(self, key: str) -> Any | None:
        """Read state value by key."""
        pass

    @abstractmethod
    async def write_state(self, key: str, value: Any) -> bool:
        """Write state value by key."""
        pass

    @abstractmethod
    def complete_request(self, message_id: str, response: ActorResponseMessage) -> None:
        """Complete a request with a response."""
        pass

    def on_progress_update(
        self, message_id: str, sequence_number: int, data: Any
    ) -> None:  # pragma: no cover - default no-op
        """Report a progress / streaming update.

        Provided as a non-abstract hook so existing simple runtimes do not need
        to implement immediately. Future iterations can make this abstract once
        a concrete progress model is finalized.
        """
        return


class Actor(ABC):
    """Interface for all actors in the system (runtime infrastructure)."""

    @abstractmethod
    async def run(self, context: ActorRuntimeContext) -> None:
        """Main actor execution loop."""
        pass


class AgentRunRequest(BaseModel):
    """Request model for running an agent."""

    agent_name: str
    conversation_id: str | None = None
    messages: list[ChatMessage]


logger = logging.getLogger(__name__)


class AgentActor(Actor):
    """Runtime actor that wraps framework AI agents."""

    THREAD_STATE_KEY = "agent_thread"

    def __init__(self, agent: AgentProtocol):
        """Initialize with framework agent."""
        self._agent = agent
        self._thread: AgentThread | None = None

    async def run(self, context: ActorRuntimeContext) -> None:
        """Main actor execution loop."""
        agent_name = getattr(self._agent, "name", None) or getattr(self._agent, "id", "unknown")
        logger.info(f"Agent actor started: {context.actor_id} (agent: {agent_name})")

        # Restore thread state
        await self._restore_thread_state(context)

        # Process messages
        async for message in context.watch_messages():
            if isinstance(message, ActorRequestMessage):
                await self._handle_agent_request(message, context)

    async def _restore_thread_state(self, context: ActorRuntimeContext):
        """Restore the agent thread state from storage."""
        thread_data = await context.read_state(self.THREAD_STATE_KEY)

        if thread_data:
            try:
                if hasattr(self._agent, "deserialize_thread"):
                    self._thread = await self._agent.deserialize_thread(thread_data)  # type: ignore[attr-defined]
                else:
                    # Fallback for agents that only implement AgentProtocol
                    self._thread = self._agent.get_new_thread()
                    logger.debug("Agent doesn't support deserialization, created new thread")
            except Exception as e:
                logger.error(f"Failed to restore thread state: {e}")
                self._thread = self._agent.get_new_thread()
        else:
            self._thread = self._agent.get_new_thread()
            logger.debug("Created new thread")

    async def _handle_agent_request(self, request: ActorRequestMessage, context: ActorRuntimeContext):
        """Handle agent run requests using framework types directly."""
        if request.method != "run":
            logger.warning(f"Unsupported method: {request.method}")
            await self._send_error_response(request, context, f"Unsupported method: {request.method}")
            return

        try:
            logger.info(f"Processing agent request: {request.message_id}")

            if not request.params:
                raise ValueError("Request params are required")

            run_request = AgentRunRequest.model_validate(request.params)

            # Ensure a thread exists (may be None if _restore_thread_state not yet called in some test paths)
            if self._thread is None:
                self._thread = self._agent.get_new_thread()

            response = await self._agent.run(run_request.messages, thread=self._thread)
            await self._save_thread_state(context)

            # Convert framework response to runtime format
            response_data = response.model_dump()

            # Send success response
            actor_response = ActorResponseMessage(
                message_id=request.message_id,
                message_type=ActorMessageType.RESPONSE,
                sender_id=context.actor_id,
                status=RequestStatus.COMPLETED,
                data=response_data,
            )

            context.complete_request(request.message_id, actor_response)
            logger.info(f"Agent request completed: {request.message_id}")

        except Exception as e:
            logger.error(f"Agent request failed: {e}")
            await self._send_error_response(request, context, str(e))

    async def _save_thread_state(self, context: ActorRuntimeContext):
        """Save framework thread state to runtime storage."""
        try:
            if self._thread:
                serialized_thread = self._thread.serialize()
                await context.write_state(self.THREAD_STATE_KEY, serialized_thread)
        except Exception as e:
            logger.error(f"Error saving thread state: {e}")

    async def _send_error_response(self, request: ActorRequestMessage, context: ActorRuntimeContext, error_msg: str):
        """Send error response."""
        error_response = ActorResponseMessage(
            message_id=request.message_id,
            message_type=ActorMessageType.RESPONSE,
            sender_id=context.actor_id,
            status=RequestStatus.FAILED,
            data={"error": error_msg},
        )
        context.complete_request(request.message_id, error_response)
