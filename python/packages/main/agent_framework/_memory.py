# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from abc import ABC, abstractmethod
from collections.abc import MutableSequence, Sequence
from contextlib import AsyncExitStack
from types import TracebackType
from typing import ClassVar

from ._pydantic import AFBaseModel
from ._types import ChatMessage, Contents

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

# region Context

__all__ = ["AggregateContextProvider", "Context", "ContextProvider"]


class Context(AFBaseModel):
    """A class containing any context that should be provided to the AI model as supplied by an ContextProvider.

    Each ContextProvider has the ability to provide its own context for each invocation.
    The Context class contains the additional context supplied by the ContextProvider.
    This context will be combined with context supplied by other providers before being passed to the AI model.
    This context is per invocation, and will not be stored as part of the chat history.
    """

    contents: list[Contents] | None = None
    """
    Any content to pass to the AI model in addition to any other prompts
    that it may already have (in the case of an agent), or chat history that may already exist.
    """


# region ContextProvider


class ContextProvider(AFBaseModel, ABC):
    """Base class for all context providers.

    A context provider is a component that can be used to enhance the AI's context management.
    It can listen to changes in the conversation and provide additional context to the AI model
    just before invocation.
    """

    # Default prompt to be used by all context providers when assembling memories/instructions
    DEFAULT_CONTEXT_PROMPT: ClassVar[str] = (
        "## Memories\nConsider the following memories when answering user questions:"
    )

    async def thread_created(self, thread_id: str | None) -> None:
        """Called just after a new thread is created.

        Implementers can use this method to do any operations required at the creation of a new thread.
        For example, checking long term storage for any data that is relevant
        to the current session based on the input text.

        Args:
            thread_id: The ID of the new thread.
        """
        pass

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Called just before messages are added to the chat by any participant.

        Inheritors can use this method to update their context based on new messages.

        Args:
            thread_id: The ID of the thread for the new message.
            new_messages: New messages to add.
        """
        pass

    @abstractmethod
    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Called just before the Model/Agent/etc. is invoked.

        Implementers can load any additional context required at this time,
        and they should return any context that should be passed to the agent.

        Args:
            messages: The most recent messages that the agent is being invoked with.
        """
        pass

    async def __aenter__(self) -> "Self":
        """Async context manager entry.

        Override this method to perform any setup operations when the context provider is entered.

        Returns:
            Self for chaining.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit.

        Override this method to perform any cleanup operations when the context provider is exited.

        Args:
            exc_type: Exception type if an exception occurred, None otherwise.
            exc_val: Exception value if an exception occurred, None otherwise.
            exc_tb: Exception traceback if an exception occurred, None otherwise.
        """
        pass


# region AggregateContextProvider


class AggregateContextProvider(ContextProvider):
    """A ContextProvider that contains multiple context providers.

    It delegates events to multiple context providers and aggregates responses from those events before returning.
    """

    providers: list[ContextProvider]
    """List of registered context providers."""

    def __init__(self, context_providers: Sequence[ContextProvider] | None = None) -> None:
        """Initialize AggregateContextProvider with context providers.

        Args:
            context_providers: Context providers to add.
        """
        super().__init__(providers=list(context_providers or []))  # type: ignore
        self._exit_stack: AsyncExitStack | None = None

    def add(self, context_provider: ContextProvider) -> None:
        """Adds new context provider.

        Args:
            context_provider: Context provider to add.
        """
        self.providers.append(context_provider)

    async def thread_created(self, thread_id: str | None = None) -> None:
        await asyncio.gather(*[x.thread_created(thread_id) for x in self.providers])

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        await asyncio.gather(*[x.messages_adding(thread_id, new_messages) for x in self.providers])

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        sub_contexts = await asyncio.gather(*[x.model_invoking(messages) for x in self.providers])
        combined_context = Context()
        # Flatten the list of lists and filter out None values
        all_contents = []
        for ctx in sub_contexts:
            if ctx.contents:
                all_contents.extend(ctx.contents)

        combined_context.contents = all_contents if all_contents else None
        return combined_context

    async def __aenter__(self) -> "Self":
        """Enter async context manager and set up all providers.

        Returns:
            Self for chaining.
        """
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        # Enter all context providers
        for provider in self.providers:
            await self._exit_stack.enter_async_context(provider)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager and clean up all providers.

        Args:
            exc_type: Exception type if an exception occurred, None otherwise.
            exc_val: Exception value if an exception occurred, None otherwise.
            exc_tb: Exception traceback if an exception occurred, None otherwise.
        """
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None
