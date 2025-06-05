from abc import ABC, abstractmethod

from ._message import Message


class AgentThread(ABC):
    """The base class for all threads.
    
    A thread is a data structure that holds a sequence of messages between an agent
    and a user, or between orchestrator and sub-agents.
    
    The `AgentThread` class defines the minimum interface for all threads in the framework.
    """

    # ---------- Message-handling ----------
    @abstractmethod
    async def on_new_messages(self, messages: list[Message]) -> None:
        """Handle a new message added to the thread."""
        ...

    # ---------- Lifecycle management ----------
    @classmethod
    @abstractmethod
    async def create(cls) -> "AgentThread":
        """Create a new thread of the same type."""
        ...

    # For delete and release resources, subclass should override built-in Python `del` method.