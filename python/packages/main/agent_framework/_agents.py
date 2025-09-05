# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import AsyncIterable, Callable, MutableMapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from itertools import chain
from typing import Any, ClassVar, Literal, Protocol, TypeVar, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field, PrivateAttr

from ._clients import ChatClientProtocol
from ._mcp import MCPTool
from ._pydantic import AFBaseModel
from ._threads import AgentThread, ChatMessageStore, deserialize_thread_state, thread_on_new_messages
from ._tools import ToolProtocol
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatToolMode,
    Role,
)
from .exceptions import AgentExecutionException
from .telemetry import use_agent_telemetry

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

TThreadType = TypeVar("TThreadType", bound="AgentThread")

__all__ = ["AgentProtocol", "BaseAgent", "ChatAgent"]


# region Agent Protocol


@runtime_checkable
class AgentProtocol(Protocol):
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

    def run_stream(
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


# region BaseAgent


class BaseAgent(AFBaseModel):
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
            await thread_on_new_messages(thread, new_messages)

    @property
    def display_name(self) -> str:
        """Returns the display name of the agent.

        This is the name if present, otherwise the id.
        """
        return self.name or self.id

    def get_new_thread(self) -> AgentThread:
        """Returns AgentThread instance that is compatible with the agent."""
        return AgentThread()

    async def deserialize_thread(self, serialized_thread: Any, **kwargs: Any) -> AgentThread:
        """Deserializes the thread."""
        thread: AgentThread = self.get_new_thread()
        await deserialize_thread_state(thread, serialized_thread, **kwargs)
        return thread


# region ChatAgent


@use_agent_telemetry
class ChatAgent(BaseAgent):
    """A Chat Client Agent."""

    AGENT_SYSTEM_NAME: ClassVar[str] = "microsoft.agent_framework"
    chat_client: ChatClientProtocol
    instructions: str | None = None
    chat_options: ChatOptions
    chat_message_store_factory: Callable[[], ChatMessageStore] | None = None
    _local_mcp_tools: list[MCPTool] = PrivateAttr(default_factory=list)  # type: ignore[reportUnknownVariableType]
    _async_exit_stack: AsyncExitStack = PrivateAttr(default_factory=AsyncExitStack)

    def __init__(
        self,
        chat_client: ChatClientProtocol,
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
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        chat_message_store_factory: Callable[[], ChatMessageStore] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a ChatAgent.

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
            chat_message_store_factory: factory function to create an instance of ChatMessageStore. If not provided,
                the default in-memory store will be used.
            kwargs: any additional keyword arguments.
                Unused, can be used by subclasses of this Agent.
        """
        kwargs.update(additional_properties or {})

        # We ignore the MCP Servers here and store them separately,
        # we add their functions to the tools list at runtime
        normalized_tools = [] if tools is None else tools if isinstance(tools, list) else [tools]
        local_mcp_tools = [tool for tool in normalized_tools if isinstance(tool, MCPTool)]
        final_tools = [tool for tool in normalized_tools if not isinstance(tool, MCPTool)]
        args: dict[str, Any] = {
            "chat_client": chat_client,
            "chat_message_store_factory": chat_message_store_factory,
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
                tools=final_tools,  # type: ignore[reportArgumentType]
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
        self._local_mcp_tools = local_mcp_tools  # type: ignore[assignment]

    async def __aenter__(self) -> "Self":
        """Async context manager entry.

        If either the chat_client or the local_mcp_tools are context managers,
        they will be entered into the async exit stack to ensure proper cleanup.

        This list might be extended in the future.
        """
        for context_manager in chain([self.chat_client], self._local_mcp_tools):
            if isinstance(context_manager, AbstractAsyncContextManager):
                await self._async_exit_stack.enter_async_context(context_manager)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit.

        Close the async exit stack to ensure all context managers are exited properly.
        """
        await self._async_exit_stack.aclose()

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
        tools: ToolProtocol
        | list[ToolProtocol]
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

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | Callable[..., Any] | dict[str, Any]] = []
        # Normalize tools argument to a list without mutating the original parameter
        normalized_tools = [] if tools is None else tools if isinstance(tools, list) else [tools]
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)  # type: ignore

        for mcp_server in self._local_mcp_tools:
            final_tools.extend(mcp_server.functions)

        response = await self.chat_client.get_response(
            messages=thread_messages,
            chat_options=self.chat_options
            & ChatOptions(
                ai_model_id=model,
                conversation_id=thread.service_thread_id,
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
                tools=final_tools,  # type: ignore[reportArgumentType]
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

    async def run_stream(
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
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream the agent with the given messages and options.

        Remarks:
            Since you won't always call the agent.run_stream directly, but it get's called
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

        # Resolve final tool list (runtime provided tools + local MCP server tools)
        final_tools: list[ToolProtocol | MutableMapping[str, Any] | Callable[..., Any]] = []
        # Normalize tools argument to a list without mutating the original parameter
        normalized_tools = [] if tools is None else tools if isinstance(tools, list) else [tools]
        for tool in normalized_tools:
            if isinstance(tool, MCPTool):
                final_tools.extend(tool.functions)  # type: ignore
            else:
                final_tools.append(tool)

        for mcp_server in self._local_mcp_tools:
            final_tools.extend(mcp_server.functions)

        async for update in self.chat_client.get_streaming_response(
            messages=thread_messages,
            chat_options=self.chat_options
            & ChatOptions(
                conversation_id=thread.service_thread_id,
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
                tools=final_tools,  # type: ignore[reportArgumentType]
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

    def get_new_thread(self) -> AgentThread:
        message_store: ChatMessageStore | None = None

        if self.chat_message_store_factory:
            message_store = self.chat_message_store_factory()

        return AgentThread() if message_store is None else AgentThread(message_store=message_store)

    def _update_thread_with_type_and_conversation_id(
        self, thread: AgentThread, response_conversation_id: str | None
    ) -> None:
        """Update thread with storage type and conversation ID.

        Args:
            thread: The thread to update.
            response_conversation_id: The conversation ID from the response, if any.

        Raises:
            AgentExecutionException: If conversation ID is missing for service-managed thread.
        """
        if response_conversation_id is None and thread.service_thread_id is not None:
            # We were passed a thread that is service managed, but we got no conversation id back from the chat client,
            # meaning the service doesn't support service managed threads,
            # so the thread cannot be used with this service.
            raise AgentExecutionException(
                "Service did not return a valid conversation id when using a service managed thread."
            )

        if response_conversation_id is not None:
            # If we got a conversation id back from the chat client, it means that the service
            # supports server side thread storage so we should update the thread with the new id.
            thread.service_thread_id = response_conversation_id
        elif thread.message_store is None and self.chat_message_store_factory is not None:
            # If the service doesn't use service side thread storage (i.e. we got no id back from invocation), and
            # the thread has no message_store yet, and we have a custom messages store, we should update the thread
            # with the custom message_store so that it has somewhere to store the chat history.
            thread.message_store = self.chat_message_store_factory()

    async def _prepare_thread_and_messages(
        self,
        *,
        thread: AgentThread | None,
        input_messages: list[ChatMessage] | None = None,
    ) -> tuple[AgentThread, list[ChatMessage]]:
        """Prepare the messages for agent execution.

        Args:
            thread: The conversation thread.
            input_messages: Messages to process.

        Returns:
            The validated thread and normalized messages.

        Raises:
            AgentExecutionException: If the thread is not of the expected type.
        """
        thread = thread or self.get_new_thread()

        messages: list[ChatMessage] = []
        if self.instructions:
            messages.append(ChatMessage(role=Role.SYSTEM, text=self.instructions))
        if thread.message_store:
            messages.extend(await thread.message_store.list_messages() or [])
        messages.extend(input_messages or [])
        return thread, messages

    def _normalize_messages(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=Role.USER, text=messages)]

        if isinstance(messages, ChatMessage):
            return [messages]

        return [ChatMessage(role=Role.USER, text=msg) if isinstance(msg, str) else msg for msg in messages]

    def _get_agent_name(self) -> str:
        return self.name or "UnnamedAgent"
