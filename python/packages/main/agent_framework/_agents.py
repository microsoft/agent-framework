# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import AsyncIterable, Callable, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager
from enum import Enum
from typing import Any, ClassVar, Literal, Protocol, TypeVar, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field

from ._clients import ChatClient
from ._pydantic import AFBaseModel
from ._tools import AITool
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    ChatToolMode,
)
from .exceptions import AgentExecutionException
from .telemetry import use_agent_telemetry

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

TThreadType = TypeVar("TThreadType", bound="AgentThread")

# region AgentThread

__all__ = [
    "AIAgent",
    "AgentBase",
    "AgentThread",
    "ChatClientAgent",
    "ChatClientAgentThread",
    "ChatClientAgentThreadType",
    "MessagesRetrievableThread",
]


class AgentThread(AFBaseModel):
    """Base class for agent threads."""

    id: str | None = None

    async def on_new_messages(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        await self._on_new_messages(new_messages=new_messages)

    async def _on_new_messages(
        self,
        new_messages: ChatMessage | Sequence[ChatMessage],
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any participant."""
        pass


# region MessagesRetrievableThread


@runtime_checkable
class MessagesRetrievableThread(Protocol):
    def get_messages(self) -> AsyncIterable[ChatMessage]:
        """Asynchronously retrieves all messages from thread."""
        ...


# region Agent Protocol


@runtime_checkable
class AIAgent(Protocol):
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
    def display_name(self) -> str:
        """Returns the display name of the agent."""
        ...

    @property
    def description(self) -> str | None:
        """Returns the description of the agent."""
        ...

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentRunResponse object. The caller is blocked until
        the final result is available.

        Note: For streaming responses, use the run_stream method, which returns
        intermediate steps and the final result as a stream of AgentRunResponseUpdate
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

    def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Run the agent as a stream.

        This method will return the intermediate steps and final results of the
        agent's execution as a stream of AgentRunResponseUpdate objects to the caller.

        Note: An AgentRunResponseUpdate object contains a chunk of a message.

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


# region AgentBase


class AgentBase(AFBaseModel):
    """Base class for all Agent Framework agents.

    Attributes:
       id: The unique identifier of the agent  If no id is provided,
           a new UUID will be generated.
       name: The name of the agent, can be None.
       description: The description of the agent.
       display_name: The display name of the agent, which is either the name or id.

    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str | None = None
    description: str | None = None

    async def _notify_thread_of_new_messages(
        self, thread: AgentThread, new_messages: ChatMessage | Sequence[ChatMessage]
    ) -> None:
        """Notify the thread of new messages."""
        if isinstance(new_messages, ChatMessage) or len(new_messages) > 0:
            await thread.on_new_messages(new_messages)

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent.

        This is the name if present, otherwise the id.
        """
        return self.name or self.id

    def _validate_or_create_thread_type(
        self,
        thread: AgentThread | None,
        construct_thread: Callable[[], TThreadType],
        expected_type: type[TThreadType],
    ) -> TThreadType:
        """Validate or create a AgentThread of the right type.

        Args:
            thread: The thread to validate or create.
            construct_thread: A callable that constructs a new thread if `thread` is None.
            expected_type: The expected type of the thread.

        Returns:
            The validated or newly created thread of the expected type.

        Raises:
            AgentExecutionException: If the thread is not of the expected type.
        """
        if thread is None:
            return construct_thread()

        if not isinstance(thread, expected_type):
            raise AgentExecutionException(
                f"{self.__class__.__name__} currently only supports agent threads of type {expected_type.__name__}."
            )

        return thread


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

    chat_messages: list[ChatMessage] | None = None
    storage_location: ChatClientAgentThreadType | None = None

    def __init__(
        self,
        id: str | None = None,
        messages: Sequence[ChatMessage] | None = None,
        **kwargs: Any,
    ):
        """Initialize the chat client agent thread.

        Args:
            id: Service thread identifier. If provided, thread is managed by the service and messages are
            not stored locally. Must not be empty or whitespace.
            messages: Initial messages for local storage. If provided, thread is managed
            locally in-memory.
            kwargs: Additional keyword arguments.

        Raises:
            ValueError: If both id and messages are provided, or if id is empty/whitespace.

        Notes:
            - If id is set, _id is assigned and _chat_messages is None (service-managed).
            - If messages is set, _chat_messages is populated and _id is None (local).
            - If neither is provided, creates an empty local thread.
        """
        processed_messages: list[ChatMessage] | None = None
        storage_location: ChatClientAgentThreadType | None = None

        if id and messages:
            raise ValueError("Cannot specify both id and messages")

        if id:
            if not id.strip():
                raise ValueError("ID cannot be empty or whitespace")
            storage_location = ChatClientAgentThreadType.CONVERSATION_ID
        elif messages:
            processed_messages = []
            processed_messages.extend(messages)
            storage_location = ChatClientAgentThreadType.IN_MEMORY_MESSAGES

        super().__init__(
            id=id,
            chat_messages=processed_messages,  # type: ignore[reportCallIssue]
            storage_location=storage_location,  # type: ignore[reportCallIssue]
            **kwargs,
        )

    async def get_messages(self) -> AsyncIterable[ChatMessage]:
        """Get all messages in the thread."""
        for message in self.chat_messages or []:
            yield message

    async def _on_new_messages(self, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Handle new messages."""
        if self.storage_location == ChatClientAgentThreadType.IN_MEMORY_MESSAGES:
            if self.chat_messages is None:
                self.chat_messages = []
            self.chat_messages.extend([new_messages] if isinstance(new_messages, ChatMessage) else new_messages)


# region ChatClientAgent


@use_agent_telemetry
class ChatClientAgent(AgentBase):
    """A Chat Client Agent."""

    AGENT_SYSTEM_NAME: ClassVar[str] = "microsoft.agent_framework"
    chat_client: ChatClient
    instructions: str | None = None
    chat_options: ChatOptions

    def __init__(
        self,
        chat_client: ChatClient,
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = "auto",
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a ChatClientAgent.

        Remarks:
            The set of attributes from frequency_penalty to additional_properties are used to
            call the chat client, they can also be passed to both run methods.
            When both are set, the ones passed to the run methods take precedence.

        Args:
            chat_client: The chat client to use for the agent.
            instructions: Optional instructions for the agent.
            These will be put into the messages sent to the chat client service as a system message.
            id: The unique identifier for the agent, will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            frequency_penalty: the frequency penalty to use.
            logit_bias: the logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            response_format: the format of the response.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request.
            kwargs: any additional keyword arguments.
                Unused, can be used by subclasses of this Agent.
        """
        kwargs.update(additional_properties or {})

        args: dict[str, Any] = {
            "chat_client": chat_client,
            "chat_options": ChatOptions(
                ai_model_id=model,
                frequency_penalty=frequency_penalty,
                logit_bias=logit_bias,
                max_tokens=max_tokens,
                metadata=metadata,
                presence_penalty=presence_penalty,
                response_format=response_format,
                seed=seed,
                stop=stop,
                store=store,
                temperature=temperature,
                tool_choice=tool_choice,
                tools=tools,  # type: ignore
                top_p=top_p,
                user=user,
                additional_properties=kwargs,
            ),
        }
        if instructions is not None:
            args["instructions"] = instructions
        if name is not None:
            args["name"] = name
        if description is not None:
            args["description"] = description
        if id is not None:
            args["id"] = id

        super().__init__(**args)
        self._update_agent_name()

    async def __aenter__(self) -> "Self":
        """Async context manager entry.

        If the chat_client supports async context management, enter its context.
        """
        if isinstance(self.chat_client, AbstractAsyncContextManager):
            await self.chat_client.__aenter__()  # type: ignore[reportUnknownMemberType]
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit.

        If the chat_client supports async context management, exit its context.
        """
        if isinstance(self.chat_client, AbstractAsyncContextManager):
            await self.chat_client.__aexit__(exc_type, exc_val, exc_tb)  # type: ignore[reportUnknownMemberType]

    def _update_agent_name(self) -> None:
        """Update the agent name in a chat client.

        Checks if there is a agent name, the implementation
        should check if there is already a agent name defined, and if not
        set it to this value.
        """
        if hasattr(self.chat_client, "_update_agent_name") and callable(self.chat_client._update_agent_name):  # type: ignore[reportAttributeAccessIssue]
            self.chat_client._update_agent_name(self.name)  # type: ignore[reportAttributeAccessIssue]

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Run the agent with the given messages and options.

        Remarks:
            Since you won't always call the agent.run directly, but it get's called
            through orchestration, it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.
            thread: The thread to use for the agent.
            frequency_penalty: the frequency penalty to use.
            logit_bias: the logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            response_format: the format of the response.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request.
            kwargs: Additional keyword arguments for the agent.
                will only be passed to functions that are called.
        """
        input_messages = self._normalize_messages(messages)
        thread, thread_messages = await self._prepare_thread_and_messages(thread=thread, input_messages=input_messages)
        agent_name = self._get_agent_name()

        response = await self.chat_client.get_response(
            messages=thread_messages,
            chat_options=self.chat_options
            & ChatOptions(
                ai_model_id=model,
                conversation_id=thread.id,
                frequency_penalty=frequency_penalty,
                logit_bias=logit_bias,
                max_tokens=max_tokens,
                metadata=metadata,
                presence_penalty=presence_penalty,
                response_format=response_format,
                seed=seed,
                stop=stop,
                store=store,
                temperature=temperature,
                tool_choice=tool_choice,
                tools=tools,  # type: ignore
                top_p=top_p,
                user=user,
                additional_properties=additional_properties or {},
            ),
            **kwargs,
        )

        self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Ensure that the author name is set for each message in the response.
        for message in response.messages:
            if message.author_name is None:
                message.author_name = agent_name

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

        return AgentRunResponse(
            messages=response.messages,
            response_id=response.response_id,
            created_at=response.created_at,
            usage_details=response.usage_details,
            raw_representation=response,
            additional_properties=response.additional_properties,
        )

    async def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        frequency_penalty: float | None = None,
        logit_bias: dict[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None,
        tools: AITool
        | list[AITool]
        | Callable[..., Any]
        | list[Callable[..., Any]]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream the agent with the given messages and options.

        Remarks:
            Since you won't always call the agent.run_streaming directly, but it get's called
            through orchestration, it is advised to set your default values for
            all the chat client parameters in the agent constructor.
            If both parameters are used, the ones passed to the run methods take precedence.

        Args:
            messages: The messages to process.
            thread: The thread to use for the agent.
            frequency_penalty: the frequency penalty to use.
            logit_bias: the logit bias to use.
            max_tokens: The maximum number of tokens to generate.
            metadata: additional metadata to include in the request.
            model: The model to use for the agent.
            presence_penalty: the presence penalty to use.
            response_format: the format of the response.
            seed: the random seed to use.
            stop: the stop sequence(s) for the request.
            store: whether to store the response.
            temperature: the sampling temperature to use.
            tool_choice: the tool choice for the request.
            tools: the tools to use for the request.
            top_p: the nucleus sampling probability to use.
            user: the user to associate with the request.
            additional_properties: additional properties to include in the request.
            kwargs: any additional keyword arguments.
                will only be passed to functions that are called.

        """
        input_messages = self._normalize_messages(messages)
        thread, thread_messages = await self._prepare_thread_and_messages(thread=thread, input_messages=input_messages)
        agent_name = self._get_agent_name()
        response_updates: list[ChatResponseUpdate] = []

        async for update in self.chat_client.get_streaming_response(
            messages=thread_messages,
            chat_options=self.chat_options
            & ChatOptions(
                conversation_id=thread.id,
                frequency_penalty=frequency_penalty,
                logit_bias=logit_bias,
                max_tokens=max_tokens,
                metadata=metadata,
                ai_model_id=model,
                presence_penalty=presence_penalty,
                response_format=response_format,
                seed=seed,
                stop=stop,
                store=store,
                temperature=temperature,
                tool_choice=tool_choice,
                tools=tools,  # type: ignore
                top_p=top_p,
                user=user,
                additional_properties=additional_properties or {},
            ),
            **kwargs,
        ):
            response_updates.append(update)

            if update.author_name is None:
                update.author_name = agent_name

            yield AgentRunResponseUpdate(
                contents=update.contents,
                role=update.role,
                author_name=update.author_name,
                response_id=update.response_id,
                message_id=update.message_id,
                created_at=update.created_at,
                additional_properties=update.additional_properties,
                raw_representation=update,
            )

        response = ChatResponse.from_chat_response_updates(response_updates)

        self._update_thread_with_type_and_conversation_id(thread, response.conversation_id)

        # Only notify the thread of new messages if the chatResponse was successful
        # to avoid inconsistent messages state in the thread.
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

    def get_new_thread(self) -> ChatClientAgentThread:
        return ChatClientAgentThread()

    def _update_thread_with_type_and_conversation_id(
        self, chat_client_thread: ChatClientAgentThread, responseConversationId: str | None
    ) -> None:
        """Update thread with storage type and conversation ID.

        Args:
            chat_client_thread: The thread to update.
            responseConversationId: The conversation ID from the response, if any.

        Raises:
            AgentExecutionException: If conversation ID is missing for service-managed thread.
        """
        # Set the thread's storage location, the first time that we use it.
        if chat_client_thread.storage_location is None:
            chat_client_thread.storage_location = (
                ChatClientAgentThreadType.CONVERSATION_ID
                if responseConversationId is not None
                else ChatClientAgentThreadType.IN_MEMORY_MESSAGES
            )

        # If we got a conversation id back from the chat client, it means that the service supports server side thread
        # storage so we should capture the id and update the thread with the new id.
        if chat_client_thread.storage_location == ChatClientAgentThreadType.CONVERSATION_ID:
            if responseConversationId is None:
                raise AgentExecutionException(
                    "Service did not return a valid conversation id when using a service managed thread."
                )
            chat_client_thread.id = responseConversationId

    async def _prepare_thread_and_messages(
        self,
        *,
        thread: AgentThread | None,
        input_messages: list[ChatMessage] | None = None,
    ) -> tuple[ChatClientAgentThread, list[ChatMessage]]:
        """Prepare the messages for agent execution.

        Args:
            thread: The conversation thread.
            input_messages: Messages to process.

        Returns:
            The validated thread and normalized messages.

        Raises:
            AgentExecutionException: If the thread is not of the expected type.
        """
        validated_thread: ChatClientAgentThread = self._validate_or_create_thread_type(  # type: ignore[reportAssignmentType]
            thread=thread,
            construct_thread=self.get_new_thread,
            expected_type=ChatClientAgentThread,
        )
        messages: list[ChatMessage] = []
        if self.instructions:
            messages.append(ChatMessage(role=ChatRole.SYSTEM, text=self.instructions))
        if isinstance(validated_thread, MessagesRetrievableThread):
            async for message in validated_thread.get_messages():
                messages.append(message)
        messages.extend(input_messages or [])
        return validated_thread, messages

    def _normalize_messages(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=ChatRole.USER, text=messages)]

        if isinstance(messages, ChatMessage):
            return [messages]

        return [ChatMessage(role=ChatRole.USER, text=msg) if isinstance(msg, str) else msg for msg in messages]

    def _get_agent_name(self) -> str:
        return self.name or "UnnamedAgent"
