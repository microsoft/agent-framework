from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

from ._thread import AgentThread
from ._message import Message
from ._run_config import RunConfig


class Result(BaseModel):
    """The result of running an agent."""
    response: Message
    ... # Other fields, could be extended to include more for application-specific needs.


TInThread = TypeVar("TInThread", bound=AgentThread, contravariant=True)
TNewThread = TypeVar("TNewThread", bound=AgentThread, covariant=True)

class Agent(ABC, Generic[TInThread, TNewThread]):
    """The base class for all agents in the framework."""

    @abstractmethod
    async def run(
        self, 
        messages: list["Message"],
        thread: TInThread,
        config: RunConfig,
    ) -> Result:
        """The method to run the agent on a thread of messages, and return the result.

        Args:
            messages: The list of new messages to process that have not been added
                to the thread yet. The agent may use these messages and append
                new messages to the thread as part of its processing.
            thread: The thread of messages to process: it may be a local thread
                or a stub thread that is backed by a remote service.
            config: The configuration for the run, which includes the event handler
                for handling events emitted by the agent, and the user input source
                for requesting user input during the run.
        
        Returns:
            The result of running the agent, which includes the final response.
        """
        ...
    
    @classmethod
    @abstractmethod
    async def create_thread(cls) -> TNewThread:
        """Create a new thread for the agent to use.

        Returns:
            A new thread that is compatible with the agent.
        """
        ...

