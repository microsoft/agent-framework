# Copyright (c) Microsoft. All rights reserved.

import sys
from abc import ABC, abstractmethod
from collections.abc import MutableSequence, Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final

from ._types import ChatMessage

if TYPE_CHECKING:
    from ._tools import ToolProtocol

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

# region Context

__all__ = ["Context", "ContextProvider"]


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
        tools: Sequence["ToolProtocol"] | None = None,
    ):
        """Create a new Context object.

        Args:
            instructions: The instructions to provide to the AI model.
            messages: The list of messages to include in the context.
            tools: The list of tools to provide to this run.
        """
        self.instructions = instructions
        self.messages: Sequence[ChatMessage] = messages or []
        self.tools: Sequence["ToolProtocol"] = tools or []


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
                agent = ChatAgent(chat_client=client, name="assistant", context_provider=provider)
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
