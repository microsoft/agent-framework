"""Core abstractions for the Python Agent Runtime"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import uuid
from datetime import datetime


# Actor System Types
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


@dataclass
class ActorMessage:
    """Base class for all actor messages"""
    message_id: str
    message_type: ActorMessageType
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ActorRequestMessage(ActorMessage):
    """Request message sent to an actor"""
    method: str = ""
    params: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        self.message_type = ActorMessageType.REQUEST


@dataclass
class ActorResponseMessage(ActorMessage):
    """Response message from an actor"""
    sender_id: Optional[ActorId] = None
    status: RequestStatus = RequestStatus.PENDING
    data: Any = None
    
    def __post_init__(self):
        self.message_type = ActorMessageType.RESPONSE


# Agent Abstractions
@dataclass 
class ChatMessage:
    """Represents a single message in a conversation"""
    role: str  # "user", "assistant", "system"
    content: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentRunResponse:
    """Response from running an agent"""
    messages: List[ChatMessage]
    status: str = "completed"
    

class AgentThread:
    """Manages conversation state for an agent"""
    
    def __init__(self, conversation_id: Optional[str] = None):
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.messages: List[ChatMessage] = []
    
    def add_message(self, message: ChatMessage) -> None:
        """Add a message to the thread"""
        self.messages.append(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize thread to dictionary"""
        return {
            "conversation_id": self.conversation_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content, 
                    "message_id": msg.message_id,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in self.messages
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentThread":
        """Deserialize thread from dictionary"""
        thread = cls(data["conversation_id"])
        for msg_data in data.get("messages", []):
            message = ChatMessage(
                role=msg_data["role"],
                content=msg_data["content"],
                message_id=msg_data["message_id"],
                timestamp=datetime.fromisoformat(msg_data["timestamp"])
            )
            thread.messages.append(message)
        return thread


class AIAgent(ABC):
    """Base class for all AI agents"""
    
    def __init__(self, name: str, agent_id: Optional[str] = None):
        self.id = agent_id or str(uuid.uuid4())
        self.name = name
    
    def get_new_thread(self) -> AgentThread:
        """Create a new conversation thread"""
        return AgentThread()
    
    @abstractmethod
    async def run_async(
        self, 
        messages: List[ChatMessage], 
        thread: Optional[AgentThread] = None
    ) -> AgentRunResponse:
        """Run the agent with the provided messages"""
        pass
    
    @abstractmethod
    async def run_streaming_async(
        self,
        messages: List[ChatMessage],
        thread: Optional[AgentThread] = None
    ) -> AsyncIterator[ChatMessage]:
        """Run the agent and yield streaming responses"""
        pass


# Actor Runtime Interfaces
class IActorRuntimeContext(ABC):
    """Runtime context provided to actors"""
    
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
    async def read_state(self, key: str) -> Optional[Any]:
        """Read state value by key"""
        pass
    
    @abstractmethod  
    async def write_state(self, key: str, value: Any) -> bool:
        """Write state value by key"""
        pass


class IActor(ABC):
    """Interface for all actors in the system"""
    
    @abstractmethod
    async def run(self, context: IActorRuntimeContext) -> None:
        """Main actor execution loop"""
        pass
    
    async def dispose(self) -> None:
        """Cleanup resources when actor is shut down"""
        pass


class IActorClient(ABC):
    """Interface for sending requests to actors"""
    
    @abstractmethod
    async def send_request(
        self, 
        actor_id: ActorId, 
        method: str,
        params: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None
    ) -> "ActorResponseHandle":
        """Send a request to an actor"""
        pass


class ActorResponseHandle(ABC):
    """Handle for tracking actor responses"""
    
    @abstractmethod
    async def get_response(self) -> ActorResponseMessage:
        """Get the final response"""
        pass
    
    @abstractmethod
    async def watch_updates(self) -> AsyncIterator[ActorResponseMessage]:
        """Watch for streaming updates"""
        pass


# State Storage
class IActorStateStorage(ABC):
    """Interface for actor state persistence"""
    
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
        """Delete state for an actor"""
        pass