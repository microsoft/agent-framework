# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, Iterable, List, Protocol, runtime_checkable

from ._types import ChatMessage, ChatResponse, ChatResponseUpdate

# region AgentThread


class AgentThread(ABC):
    """Base class for agent threads."""

    def __init__(self) -> None:
        """Initialize the agent thread."""
        self._id: str | None = None  # type: ignore

    @property
    def id(self) -> str | None:
        """Returns the ID of the current thread (if any)."""
        return self._id

    async def on_new_message(
        self,
        new_message: ChatMessage,
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        await self._on_new_message(new_message)

    @abstractmethod
    async def _on_new_message(
        self,
        new_message: ChatMessage,
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        raise NotImplementedError


# region Agent Protocol


@runtime_checkable
class Agent(Protocol):
    """A protocol for an agent that can be invoked."""

    async def run(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
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
            arguments: Additional arguments to pass to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        ...

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
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
            arguments: Additional arguments to pass to the agent.
            thread: The conversation thread associated with the message(s).
            on_intermediate_message: A callback function to handle intermediate steps of the
                                     agent's execution as fully formed messages.
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        ...

    def get_new_thread(self) -> AgentThread:
        """Get a new AgentThread instance compatible with the agent.

        Returns:
            A new AgentThread instance.

        Notes:
            - Returns the default thread type or configured thread type if multiple are supported.
            - Thread may be created via a service call on first use.
        """
        ...


# region ChatClientAgentThread


class ChatClientAgentThread(AgentThread):
    """Chat client agent thread.

    This class manages chat threads either locally (in-memory) or via a service based on initialization.
    """

    def __init__(self, id: str | None = None, messages: Iterable[ChatMessage] | None = None):
        """Initialize the chat client agent thread.

        Args:
            id (str | None): Service thread identifier. If provided, thread is managed by the service and messages are
            not stored locally. Must not be empty or whitespace.
            messages (Iterable[ChatMessage] | None): Initial messages for local storage. If provided, thread is managed
            locally in-memory.

        Raises:
            ValueError: If both id and messages are provided, or if id is empty/whitespace.

        Notes:
            - If id is set, _id is assigned and _chat_messages remains empty (service-managed).
            - If messages is set, _chat_messages is populated and _id is None (local).
            - If neither is provided, creates an empty local thread.
        """
        super().__init__()
        self._chat_messages: List[ChatMessage] = []

        if id and messages:
            raise ValueError("Cannot specify both id and messages")

        if id:
            if not id.strip():
                raise ValueError("ID cannot be empty or whitespace")
            self._id = id
        elif messages:
            self._chat_messages.extend(messages)

    async def get_messages(self) -> AsyncIterable[ChatMessage]:
        """Get all messages in the thread."""
        for message in self._chat_messages:
            yield message

    async def _on_new_message(self, new_message: ChatMessage) -> None:
        """Handle new message."""
        # If id is not initialized, it means that thread is local and messages are stored in-memory.
        if self._id is None:
            self._chat_messages.append(new_message)
