# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from abc import ABC, abstractmethod
from collections.abc import MutableSequence, Sequence
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Final, cast

from ._tools import ToolProtocol
from ._types import ChatMessage

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

# region Context

__all__ = ["AggregateContextProvider", "Context", "ContextProvider"]


class Context:
    """A class containing any context that should be provided to the AI model as supplied by a ContextProvider.

    Each ContextProvider has the ability to provide its own context for each invocation.
    The Context class contains the additional context supplied by the ContextProvider.
    This context will be combined with context supplied by other providers before being passed to the AI model.
    This context is per invocation, and will not be stored as part of the chat history.

    Examples:
        .. code-block:: python

            from agent_framework import Context, ChatMessage

            # Create context with instructions
            context = Context(
                instructions="Use a professional tone when responding.",
                messages=[ChatMessage(content="Previous context", role="user")],
                tools=[my_tool],
            )

            # Access context properties
            print(context.instructions)
            print(len(context.messages))
    """

    def __init__(
        self,
        instructions: str | None = None,
        messages: Sequence[ChatMessage] | None = None,
        tools: Sequence[ToolProtocol] | None = None,
    ):
        """Create a new Context object.

        Args:
            instructions: The instructions to provide to the AI model.
            messages: The list of messages to include in the context.
            tools: The list of tools to provide to this run.
        """
        self.instructions = instructions
        self.messages: Sequence[ChatMessage] = messages or []
        self.tools: Sequence[ToolProtocol] = tools or []


# region ContextProvider


class ContextProvider(ABC):
    """Base class for all context providers.

    A context provider is a component that can be used to enhance the AI's context management.
    It can listen to changes in the conversation and provide additional context to the AI model
    just before invocation.

    Note:
        ContextProvider is an abstract base class. You must subclass it and implement
        the ``invoking()`` method to create a custom context provider. Ideally, you should
        also implement the ``invoked()`` and ``thread_created()`` methods to track conversation
        state, but these are optional.

    Examples:
        .. code-block:: python

            from agent_framework import ContextProvider, Context, ChatMessage


            class CustomContextProvider(ContextProvider):
                async def invoking(self, messages, **kwargs):
                    # Add custom instructions before each invocation
                    return Context(instructions="Always be concise and helpful.", messages=[], tools=[])


            # Use with a chat agent
            async with CustomContextProvider() as provider:
                agent = ChatAgent(chat_client=client, name="assistant", context_providers=provider)
    """

    # Default prompt to be used by all context providers when assembling memories/instructions
    DEFAULT_CONTEXT_PROMPT: Final[str] = "## Memories\nConsider the following memories when answering user questions:"

    async def thread_created(self, thread_id: str | None) -> None:
        """Called just after a new thread is created.

        Implementers can use this method to perform any operations required at the creation
        of a new thread. For example, checking long-term storage for any data that is relevant
        to the current session.

        Args:
            thread_id: The ID of the new thread.
        """
        pass

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after the agent has received a response from the underlying inference service.

        You can inspect the request and response messages, and update the state of the context provider.

        Args:
            request_messages: The messages that were sent to the model/agent.
            response_messages: The messages that were returned by the model/agent.
            invoke_exception: The exception that was thrown, if any.

        Keyword Args:
            kwargs: Additional keyword arguments (not used at present).
        """
        pass

    @abstractmethod
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called just before the model/agent is invoked.

        Implementers can load any additional context required at this time,
        and they should return any context that should be passed to the agent.

        Args:
            messages: The most recent messages that the agent is being invoked with.

        Keyword Args:
            kwargs: Additional keyword arguments (not used at present).

        Returns:
            A Context object containing instructions, messages, and tools to include.
        """
        pass

    async def __aenter__(self) -> "Self":
        """Enter the async context manager.

        Override this method to perform any setup operations when the context provider is entered.

        Returns:
            The ContextProvider instance for chaining.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager.

        Override this method to perform any cleanup operations when the context provider is exited.

        Args:
            exc_type: The exception type if an exception occurred, None otherwise.
            exc_val: The exception value if an exception occurred, None otherwise.
            exc_tb: The exception traceback if an exception occurred, None otherwise.
        """
        pass


# region AggregateContextProvider


class AggregateContextProvider(ContextProvider):
    """A ContextProvider that contains multiple context providers.

    It delegates events to multiple context providers and aggregates responses from those
    events before returning. This allows you to combine multiple context providers into a
    single provider.

    Note:
        An AggregateContextProvider is created automatically when you pass a single context
        provider or a sequence of context providers to the agent constructor.

    Examples:
        .. code-block:: python

            from agent_framework import AggregateContextProvider, ChatAgent

            # Create multiple context providers
            provider1 = CustomContextProvider1()
            provider2 = CustomContextProvider2()
            provider3 = CustomContextProvider3()

            # Pass them to the agent - AggregateContextProvider is created automatically
            agent = ChatAgent(chat_client=client, name="assistant", context_providers=[provider1, provider2, provider3])

            # Verify that an AggregateContextProvider was created
            assert isinstance(agent.context_providers, AggregateContextProvider)

            # Add additional providers to the agent
            provider4 = CustomContextProvider4()
            agent.context_providers.add(provider4)
    """

    def __init__(self, context_providers: ContextProvider | Sequence[ContextProvider] | None = None) -> None:
        """Initialize the AggregateContextProvider with context providers.

        Args:
            context_providers: The context provider(s) to add.
        """
        if isinstance(context_providers, ContextProvider):
            self.providers = [context_providers]
        else:
            self.providers = cast(list[ContextProvider], context_providers) or []
        self._exit_stack: AsyncExitStack | None = None

    def add(self, context_provider: ContextProvider) -> None:
        """Add a new context provider.

        Args:
            context_provider: The context provider to add.
        """
        self.providers.append(context_provider)

    @override
    async def thread_created(self, thread_id: str | None = None) -> None:
        await asyncio.gather(*[x.thread_created(thread_id) for x in self.providers])

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        contexts = await asyncio.gather(*[provider.invoking(messages, **kwargs) for provider in self.providers])
        instructions: str = ""
        return_messages: list[ChatMessage] = []
        tools: list[ToolProtocol] = []
        for ctx in contexts:
            if ctx.instructions:
                instructions += ctx.instructions
            if ctx.messages:
                return_messages.extend(ctx.messages)
            if ctx.tools:
                tools.extend(ctx.tools)
        return Context(instructions=instructions, messages=return_messages, tools=tools)

    @override
    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        await asyncio.gather(*[
            x.invoked(
                request_messages=request_messages,
                response_messages=response_messages,
                invoke_exception=invoke_exception,
                **kwargs,
            )
            for x in self.providers
        ])

    @override
    async def __aenter__(self) -> "Self":
        """Enter the async context manager and set up all providers.

        Returns:
            The AggregateContextProvider instance for chaining.
        """
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        # Enter all context providers
        for provider in self.providers:
            await self._exit_stack.enter_async_context(provider)

        return self

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and clean up all providers.

        Args:
            exc_type: The exception type if an exception occurred, None otherwise.
            exc_val: The exception value if an exception occurred, None otherwise.
            exc_tb: The exception traceback if an exception occurred, None otherwise.
        """
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None
