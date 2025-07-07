# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import Field

from ._pydantic import AFBaseModel
from ._types import ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole, TextContent
from .exceptions import AgentExecutionException

TThreadType = TypeVar("TThreadType", bound="AgentThread")


class AgentThread(ABC):
    """Base class for agent threads."""

    def __init__(self) -> None:
        """Initialize the agent thread."""
        self._is_deleted: bool = False  # type: ignore
        self._id: str | None = None  # type: ignore

    @property
    def id(self) -> str | None:
        """Returns the ID of the current thread (if any)."""
        if self._is_deleted:
            raise RuntimeError(
                "Thread has been deleted; Create a new AgentThread instance and call `create()` to recreate it."
            )
        return self._id

    async def create(self) -> str | None:
        """Starts the thread and returns the thread ID."""
        # A thread should not be recreated after it has been deleted.
        if self._is_deleted:
            raise RuntimeError("Thread has already been deleted. For new thread, create a new AgentThread instance.")

        # If the thread ID is already set, we're done, just return the Id.
        if self.id is not None:
            return self.id

        # Otherwise, create the thread.
        self._id = await self._create()
        return self.id

    async def delete(self) -> None:
        """Ends the current thread."""
        # A thread should not be deleted if it has already been deleted.
        if self._is_deleted:
            return

        # If the thread ID is not set, we're done, just return.
        if self.id is None:
            self._is_deleted = True
            return

        # Otherwise, delete the thread.
        await self._delete()
        self._id = None
        self._is_deleted = True

    async def on_new_message(
        self,
        new_message: ChatMessage,
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        # If the thread is not created yet, create it.
        if self.id is None:
            await self.create()

        await self._on_new_message(new_message)

    @abstractmethod
    async def _create(self) -> str:
        """Starts the thread and returns the thread ID."""
        raise NotImplementedError

    @abstractmethod
    async def _delete(self) -> None:
        """Ends the current thread."""
        raise NotImplementedError

    @abstractmethod
    async def _on_new_message(
        self,
        new_message: ChatMessage,
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        raise NotImplementedError


class Agent(AFBaseModel, ABC):
    """Base abstraction for all agents.

    An agent instance may participate in one or more conversations.
    A conversation may include one or more agents.
    In addition to identity and descriptive meta-data, an Agent
    must define its communication protocol.

    Attributes:
        arguments: The arguments for the agent
        description: The description of the agent
        id: The unique identifier of the agent  If no id is provided,
            a new UUID will be generated.
        instructions: The instructions for the agent (optional)
        name: The name of the agent
    """

    arguments: dict[str, Any] | None = None
    description: str | None = None
    id: str = Field(default_factory=lambda: str(uuid4()))
    instructions: str | None = None
    name: str = "UnnamedAgent"

    # region Invocation Methods

    @abstractmethod
    def get_response(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse]:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single ChatResponse object. The caller is blocked until
        the final result is available.

        Note: For streaming responses, use the invoke_stream method, which returns
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
        pass

    @abstractmethod
    def invoke(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponse]:
        """Invoke the agent.

        This invocation method will return the final results of the agent's execution as a
        stream of ChatResponse objects to the caller. The reason for returning a stream
        is to allow for future extensions to the agent's capabilities, such as multi-modality.

        To get the intermediate steps of the agent's execution, use the on_intermediate_message callback
        to handle those messages.

        Note: A ChatResponse object contains an entire message.

        Args:
            messages: The message(s) to send to the agent.
            arguments: Additional arguments to pass to the agent.
            thread: The conversation thread associated with the message(s).
            on_intermediate_message: A callback function to handle intermediate steps of the agent's execution.
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        pass

    @abstractmethod
    def invoke_stream(
        self,
        messages: str | ChatMessage | list[str | ChatMessage] | None = None,
        *,
        arguments: dict[str, Any] | None = None,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Invoke the agent as a stream.

        This invocation method will return the intermediate steps and final results of the
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
        pass

    async def _ensure_thread_exists_with_messages(
        self,
        *,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        thread: TThreadType | None,
        construct_thread: Callable[[], TThreadType],
        expected_type: type[TThreadType],
    ) -> TThreadType:
        """Ensure the thread exists with the provided message(s)."""
        if messages is None:
            messages = []

        if isinstance(messages, (str, ChatMessage)):
            messages = [messages]

        normalized_messages = [
            ChatMessage(role=ChatRole.USER, contents=[TextContent(msg)]) if isinstance(msg, str) else msg
            for msg in messages
        ]

        if thread is None:
            thread = construct_thread()
            await thread.create()

        if not isinstance(thread, expected_type):
            raise AgentExecutionException(
                f"{self.__class__.__name__} currently only supports agent threads of type {expected_type.__name__}."
            )

        # Notify the thread that new messages are available.
        for msg in normalized_messages:
            await self._notify_thread_of_new_message(thread, msg)

        return thread

    async def _notify_thread_of_new_message(
        self,
        thread: AgentThread,
        new_message: ChatMessage,
    ) -> None:
        """Notify the thread of a new message."""
        await thread.on_new_message(new_message)

    def __eq__(self, other: Any) -> bool:
        """Check if two agents are equal."""
        if isinstance(other, Agent):
            return (
                self.id == other.id
                and self.name == other.name
                and self.description == other.description
                and self.instructions == other.instructions
            )
        return False

    def __hash__(self) -> int:
        """Get the hash of the agent."""
        return hash((self.id, self.name, self.description, self.instructions))
