"""AgentActor - bridges AI agents with the actor runtime"""

import logging
import os
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Union

# Framework agent types
sys.path.append(os.path.join(os.path.dirname(__file__), "../../packages/main"))

from pydantic import BaseModel

from agent_framework import AgentRunResponse, AgentThread, AIAgent, ChatMessage, ChatRole  # type: ignore


class AgentRunRequest(BaseModel):
    agent_name: str
    conversation_id: str | None = None
    messages: list[ChatMessage]


@dataclass(frozen=True)
class ActorId:
    """Unique identifier for an actor instance"""

    type_name: str
    instance_id: str

    def __str__(self) -> str:
        return f"{self.type_name}/{self.instance_id}"


class ActorMessageType(Enum):
    """Types of messages that can be sent to actors"""

    REQUEST = "request"
    RESPONSE = "response"


class RequestStatus(Enum):
    """Status of a request being processed by an actor"""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_FOUND = "not_found"


@dataclass
class _ActorMessage:
    """Base class for all actor system messages (not intended for direct use)."""

    message_id: str
    message_type: ActorMessageType
    timestamp: datetime = field(default_factory=lambda: datetime.now(datetime.timezone.utc))


@dataclass
class ActorRequestMessage(_ActorMessage):
    """Request message sent to an actor"""

    method: str = ""
    params: dict[str, Any] | None = None

    def __post_init__(self):
        self.message_type = ActorMessageType.REQUEST


@dataclass
class ActorResponseMessage(_ActorMessage):
    """Response message from an actor"""

    sender_id: ActorId | None = None
    status: RequestStatus = RequestStatus.PENDING
    data: Any = None

    def __post_init__(self):
        self.message_type = ActorMessageType.RESPONSE


# Type alias for the union of message types (public API)
ActorMessage = Union[ActorRequestMessage, ActorResponseMessage]


class ActorRuntimeContext(ABC):
    """Runtime context provided to actors (infrastructure services).

    This closely mirrors the .NET runtime abstractions but is intentionally
    slimmer for the initial Python foundation. Methods for batching state
    operations and fine‑grained progress streaming can be added incrementally.
    """

    @property
    @abstractmethod
    def actor_id(self) -> ActorId:
        """Get the actor's unique identifier"""
        pass

    @abstractmethod
    async def watch_messages(self) -> AsyncIterator[ActorMessage]:
        """Watch for incoming messages"""
        pass

    @abstractmethod
    async def read_state(self, key: str) -> Any | None:
        """Read state value by key"""
        pass

    @abstractmethod
    async def write_state(self, key: str, value: Any) -> bool:
        """Write state value by key"""
        pass

    @abstractmethod
    def complete_request(self, message_id: str, response: ActorResponseMessage) -> None:
        """Complete a request with a response"""
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
    """Interface for all actors in the system (runtime infrastructure)"""

    @abstractmethod
    async def run(self, context: ActorRuntimeContext) -> None:
        """Main actor execution loop"""
        pass

    async def dispose(self) -> None:
        """Cleanup resources when actor is shut down"""
        pass


logger = logging.getLogger(__name__)


class AgentActor(Actor):
    """Runtime actor that wraps framework AI agents"""

    THREAD_STATE_KEY = "agent_thread"

    def __init__(self, agent: AIAgent):
        """Initialize with framework agent"""
        self._agent = agent
        self._thread: AgentThread | None = None

    async def run(self, context: ActorRuntimeContext) -> None:
        """Main actor execution loop"""
        agent_name = getattr(self._agent, "name", None) or getattr(self._agent, "id", "unknown")
        logger.info(f"Agent actor started: {context.actor_id} (agent: {agent_name})")

        # Restore thread state
        await self._restore_thread_state(context)

        # Process messages
        async for message in context.watch_messages():
            if isinstance(message, ActorRequestMessage):
                await self._handle_agent_request(message, context)

    async def _restore_thread_state(self, context: ActorRuntimeContext):
        """Restore the agent thread state from storage"""
        thread_data = await context.read_state(self.THREAD_STATE_KEY)

        if thread_data:
            try:
                # For now, create new thread - full serialization would need framework support
                self._thread = self._agent.get_new_thread()
                logger.debug("Restored thread state (simplified)")
            except Exception as e:
                logger.error(f"Failed to restore thread state: {e}")
                self._thread = self._agent.get_new_thread()
        else:
            self._thread = self._agent.get_new_thread()
            logger.debug("Created new thread")

    async def _handle_agent_request(self, request: ActorRequestMessage, context: ActorRuntimeContext):
        """Handle agent run requests using framework types directly"""
        if request.method != "run":
            logger.warning(f"Unsupported method: {request.method}")
            await self._send_error_response(request, context, f"Unsupported method: {request.method}")
            return

        try:
            logger.info(f"Processing agent request: {request.message_id}")

            # Validate request format early
            if not request.params:
                raise ValueError("Request params are required")
            
            # Parse and validate the request
            run_request = AgentRunRequest.model_validate(request.params)
            
            # Extract messages directly - no conversion needed!
            framework_messages = run_request.messages

            # Ensure a thread exists (may be None if _restore_thread_state not yet called in some test paths)
            if self._thread is None:
                self._thread = self._agent.get_new_thread()

            # Don't manually append incoming messages; allow agent implementation to manage thread.

            # Call framework agent directly
            response = await self._agent.run(framework_messages, thread=self._thread)

            # Save updated thread state
            await self._save_thread_state(context)

            # Convert framework response to runtime format
            response_data = self._convert_framework_response(response)

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


    def _convert_framework_response(self, framework_response: AgentRunResponse) -> dict:
        """Convert framework AgentRunResponse to runtime data format using built-in serialization"""
        try:
            # Use framework's built-in serialization (like .NET does)
            # This preserves all content types including images, files, function calls, etc.
            return framework_response.model_dump()
            
        except Exception as e:
            logger.error(f"Error converting framework response: {e}")
            return {"messages": [{"role": "assistant", "text": f"Response conversion error: {e}"}], "status": "failed"}


    async def _save_thread_state(self, context: ActorRuntimeContext):
        """Save framework thread state to runtime storage"""
        try:
            if self._thread:
                # Serialize basic thread info plus messages for persistence tests
                thread_data = {
                    "thread_id": getattr(self._thread, "id", None),
                    "last_updated": str(context.actor_id),
                }
                if hasattr(self._thread, "messages"):
                    serialized_messages = []
                    for m in self._thread.messages:
                        try:
                            # Use framework's built-in serialization
                            serialized_messages.append(m.model_dump())
                        except Exception as e:
                            logger.debug(f"Failed to serialize message for state: {e}")
                    thread_data["messages"] = serialized_messages
                await context.write_state(self.THREAD_STATE_KEY, thread_data)
                logger.debug("Saved thread state (messages count=%s)", len(thread_data.get("messages", [])))
        except Exception as e:
            logger.error(f"Error saving thread state: {e}")

    async def _send_error_response(self, request: ActorRequestMessage, context: ActorRuntimeContext, error_msg: str):
        """Send error response"""
        error_response = ActorResponseMessage(
            message_id=request.message_id,
            message_type=ActorMessageType.RESPONSE,
            sender_id=context.actor_id,
            status=RequestStatus.FAILED,
            data={"error": error_msg},
        )
        context.complete_request(request.message_id, error_response)
