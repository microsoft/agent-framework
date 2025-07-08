# Copyright (c) Microsoft. All rights reserved.

from abc import abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable
from enum import Enum
from typing import Any, Iterable, List, Protocol, Sequence, TypeVar, runtime_checkable
from uuid import uuid4

from pydantic import Field

from agent_framework import ChatClient, ChatMessage, ChatResponse, ChatResponseUpdate

from ._pydantic import AFBaseModel
from .exceptions import AgentExecutionException

TThreadType = TypeVar("TThreadType", bound="AgentThread")

# region AgentThread


class AgentThread(AFBaseModel):
    """Base class for agent threads."""

    id: str | None = None

    async def on_new_messages(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        await self._on_new_messages(new_messages=new_messages)

    @abstractmethod
    async def _on_new_messages(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        ...


# region BaseAgent


class BaseAgent:
    """Base abstraction for all agents."""

    def _ensure_thread_exists_with_messages(
        self,
        *,
        messages: ChatMessage | Sequence[ChatMessage] | None = None,
        thread: AgentThread | None,
        construct_thread: Callable[[], TThreadType],
        expected_type: type[TThreadType],
    ) -> TThreadType:
        """Ensure the thread exists with the provided message(s)."""
        if messages is None:
            messages = []

        if isinstance(messages, ChatMessage):
            messages = [messages]

        if thread is None:
            thread = construct_thread()

        if not isinstance(thread, expected_type):
            raise AgentExecutionException(
                f"{self.__class__.__name__} currently only supports agent threads of type {expected_type.__name__}."
            )

        return thread

    async def _notify_thread_of_new_messages(
        self, thread: AgentThread, new_messages: ChatMessage | Sequence[ChatMessage]
    ) -> None:
        """Notify the thread of new messages."""
        if isinstance(new_messages, ChatMessage) or len(new_messages) > 0:
            await thread.on_new_messages(new_messages)


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
        messages: ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        on_intermediate_message: Callable[[ChatMessage], Awaitable[None]] | None = None,
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
            on_intermediate_message: A callback function to handle intermediate steps of the
                                     agent's execution as fully formed messages.
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        ...

    def run_stream(
        self,
        messages: ChatMessage | list[ChatMessage] | None = None,
        *,
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


class ChatClientAgentThreadType(Enum):
    """Defines the different supported storage locations for ChatClientAgentThread."""

    IN_MEMORY_MESSAGES = "InMemoryMessages"
    """Messages are stored in memory inside the thread object."""

    CONVERSATION_ID = "ConversationId"
    """Messages are stored in the service and the thread object just has an id reference to the service storage."""


class ChatClientAgentThread(AgentThread):
    """Chat client agent thread.

    This class manages chat threads either locally (in-memory) or via a service based on initialization.
    """

    _storage_location: ChatClientAgentThreadType | None = None

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
            self._storage_location = ChatClientAgentThreadType.CONVERSATION_ID
        elif messages:
            self._chat_messages.extend(messages)
            self._storage_location = ChatClientAgentThreadType.IN_MEMORY_MESSAGES

    async def get_messages(self) -> AsyncIterable[ChatMessage]:
        """Get all messages in the thread."""
        for message in self._chat_messages:
            yield message

    async def _on_new_messages(self, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Handle new messages."""
        if self._storage_location == ChatClientAgentThreadType.IN_MEMORY_MESSAGES:
            self._chat_messages.extend([new_messages] if isinstance(new_messages, ChatMessage) else new_messages)


# region ChatClientAgent


class ChatClientAgent(BaseAgent, Agent):
    """A Chat Client Agent based on ChatClient.

    Attributes:
       id: The unique identifier of the agent  If no id is provided,
           a new UUID will be generated.
       name: The name of the agent
       description: The description of the agent
       instructions: The instructions for the agent (optional)
    """

    _chat_client: ChatClient = Field(..., exclude=True)
    _id: str = Field(default_factory=lambda: str(uuid4()))
    _name: str = Field(default="UnnamedAgent")
    _description: str | None = None
    _instructions: str | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        return self._name

    @property
    def description(self) -> str | None:
        """Returns the description of the agent."""
        return self._description

    @property
    def instructions(self) -> str | None:
        """Returns the instructions for the agent."""
        return self._instructions

    def __init__(
        self,
        chat_client: ChatClient,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
    ) -> None:
        self._chat_client = chat_client

        if id is not None:
            self._id = id
        if name is not None:
            self._name = name

        self._description = description
        self._instructions = instructions

    async def run(
        self,
        messages: ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        thread = self._ensure_thread_exists_with_messages(
            messages=messages,
            thread=thread,
            construct_thread=lambda: ChatClientAgentThread(),
            expected_type=ChatClientAgentThread,
        )

        thread_messages: list[ChatMessage] = []

        async for message in thread.get_messages():
            thread_messages.append(message)

        response = await self._chat_client.get_response(thread_messages, **kwargs)

        self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, thread_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

        return response

    async def run_stream(
        self,
        messages: ChatMessage | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        thread = self._ensure_thread_exists_with_messages(
            messages=messages,
            thread=thread,
            construct_thread=lambda: ChatClientAgentThread(),
            expected_type=ChatClientAgentThread,
        )

        thread_messages: list[ChatMessage] = []

        async for message in thread.get_messages():
            thread_messages.append(message)

        response_updates: list[ChatResponseUpdate] = []

        async for update in self._chat_client.get_streaming_response(thread_messages):
            response_updates.append(update)
            yield update

        response = ChatResponse.from_chat_response_updates(response_updates)

        self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, thread_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

    def get_new_thread(self) -> AgentThread:
        return ChatClientAgentThread()

    def _update_thread_with_type_and_conversation_id(
        self, chatClientThread: ChatClientAgentThread, responseConversationId: str | None
    ) -> None:
        # Set the thread's storage location, the first time that we use it.
        if chatClientThread._storage_location is None:  # type: ignore[reportPrivateUsage]
            chatClientThread._storage_location = (  # type: ignore[reportPrivateUsage]
                ChatClientAgentThreadType.CONVERSATION_ID
                if responseConversationId is not None
                else ChatClientAgentThreadType.IN_MEMORY_MESSAGES
            )

        # If we got a conversation id back from the chat client, it means that the service supports server side thread
        # storage so we should capture the id and update the thread with the new id.

        if chatClientThread._storage_location == ChatClientAgentThreadType.CONVERSATION_ID:  # type: ignore[reportPrivateUsage]
            if responseConversationId is None:
                raise ValueError("Service did not return a valid conversation id when using a service managed thread.")
            chatClientThread.id = responseConversationId
