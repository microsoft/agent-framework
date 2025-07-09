# Copyright (c) Microsoft. All rights reserved.

from abc import abstractmethod
from collections.abc import AsyncIterable, Sequence
from typing import Any, Protocol, runtime_checkable

from ._pydantic import AFBaseModel
from ._types import ChatMessage, ChatResponse, ChatResponseUpdate

# region AgentThread


class AgentThread(AFBaseModel):
    """Base class for agent threads."""

    id: str | None = None

    async def create(self) -> str | None:
        """Starts the thread and returns the thread ID."""
        # If the thread ID is already set, we're done, just return the Id.
        if self.id is not None:
            return self.id

        # Otherwise, create the thread.
        self.id = await self._create()
        return self.id

    async def delete(self) -> None:
        """Ends the current thread."""
        await self._delete()
        self.id = None

    async def on_new_message(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        # If the thread is not created yet, create it.
        if self.id is None:
            await self.create()

        await self._on_new_message(new_messages=new_messages)

    @abstractmethod
    async def _create(self) -> str:
        """Starts the thread and returns the thread ID."""
        ...

    @abstractmethod
    async def _delete(self) -> None:
        """Ends the current thread."""
        ...

    @abstractmethod
    async def _on_new_message(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        ...


# region Agent Protocol


@runtime_checkable
class Agent(Protocol):
    """A protocol for an agent that can be invoked."""

    @property
    def id(self) -> str:
        """Returns the ID of the agent."""
        ...

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        ...

    @property
    def description(self) -> str | None:
        """Returns the description of the agent."""
        ...

    @property
    def instructions(self) -> str | None:
        """Returns the instructions for the agent."""
        ...

    async def run(
        self,
        messages: str | ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single ChatResponse object. The caller is blocked until
        the final result is available.

        Note: For streaming responses, use the run_stream method, which returns
        intermediate steps and the final result as a stream of ChatResponseUpdate
        objects. Streaming only the final result is not feasible because the timing of
        the final result's availability is unknown, and blocking the caller until then
        is undesirable in streaming scenarios.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        ...

    def run_stream(
        self,
        messages: str | ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Run the agent as a stream.

        This method will return the intermediate steps and final results of the
        agent's execution as a stream of ChatResponseUpdate objects to the caller.

        To get the intermediate steps of the agent's execution as fully formed messages,
        use the on_intermediate_message callback.

        Note: A ChatResponseUpdate object contains a chunk of a message.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        ...

    def get_new_thread(self) -> AgentThread:
        """Creates a new conversation thread for the agent."""
        ...
