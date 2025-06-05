from abc import ABC, abstractmethod

from ._thread import AgentThread


class UserInputSource(ABC):
    """The base class for user input sources."""

    @abstractmethod
    async def request_input(self, prompt: str, thread: AgentThread) -> str:
        """Request input from the user with a given prompt and the current thread for context."""
        ...
    
    @abstractmethod
    async def request_confirmation(self, prompt: str, thread: AgentThread) -> bool:
        """Request confirmation from the user with a given prompt and the current thread for context."""
        ...
