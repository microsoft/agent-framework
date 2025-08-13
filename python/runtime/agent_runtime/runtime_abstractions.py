"""Runtime infrastructure abstractions (actor system only)"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
from datetime import datetime


# Actor System Infrastructure Types
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
class ActorMessage:
    """Base class for all actor system messages.

    NOTE: timestamp must use default_factory to avoid all instances sharing the
    same datetime value at import time (bug fix for initial implementation).
    """
    message_id: str
    message_type: ActorMessageType
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ActorRequestMessage(ActorMessage):
    """Request message sent to an actor"""
    method: str = ""
    params: Dict[str, Any] | None = None
    
    def __post_init__(self):
        self.message_type = ActorMessageType.REQUEST


@dataclass
class ActorResponseMessage(ActorMessage):
    """Response message from an actor"""
    sender_id: ActorId | None = None
    status: RequestStatus = RequestStatus.PENDING
    data: Any = None
    
    def __post_init__(self):
        self.message_type = ActorMessageType.RESPONSE


# Runtime Infrastructure Interfaces
class IActorRuntimeContext(ABC):
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

    # --- Progress / streaming (parity scaffolding) ---------------------------------
    def on_progress_update(self, message_id: str, sequence_number: int, data: Any) -> None:  # pragma: no cover - default no-op
        """Report a progress / streaming update.

        Provided as a non-abstract hook so existing simple runtimes do not need
        to implement immediately. Future iterations can make this abstract once
        a concrete progress model is finalized.
        """
        return


class IActor(ABC):
    """Interface for all actors in the system (runtime infrastructure)"""
    
    @abstractmethod
    async def run(self, context: IActorRuntimeContext) -> None:
        """Main actor execution loop"""
        pass
    
    async def dispose(self) -> None:
        """Cleanup resources when actor is shut down"""
        pass


class IActorClient(ABC):
    """Interface for sending requests to actors (runtime infrastructure)"""
    
    @abstractmethod
    async def send_request(
        self, 
        actor_id: ActorId, 
        method: str, 
        params: Dict[str, Any] | None = None,
        message_id: str | None = None
    ) -> "ActorResponseHandle":
        """Send a request to an actor"""
        pass


class ActorResponseHandle(ABC):
    """Handle for async actor responses (runtime infrastructure)"""
    
    @abstractmethod
    async def get_response(self) -> ActorResponseMessage:
        """Get the final response (blocking until complete)"""
        pass
    
    @abstractmethod
    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        """Watch for streaming updates"""
        pass


class IActorStateStorage(ABC):
    """Interface for actor state persistence (runtime infrastructure)"""
    
    @abstractmethod
    async def read_state(self, actor_id: ActorId) -> Dict[str, Any]:
        """Read all state for an actor"""
        pass
    
    @abstractmethod
    async def write_state(self, actor_id: ActorId, state: Dict[str, Any]) -> bool:
        """Write state for an actor"""
        pass
    
    @abstractmethod
    async def delete_state(self, actor_id: ActorId) -> bool:
        """Delete all state for an actor"""
        pass