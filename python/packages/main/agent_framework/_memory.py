# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import Iterable, MutableSequence, Sequence

from ._pydantic import AFBaseModel
from ._types import ChatMessage

# region AIContext


class AIContext(AFBaseModel):
    """A class containing any context that should be provided to the AI model as supplied by an AIContextProvider.

    Each AIContextProvider has the ability to provide its own context for each invocation.
    The AIContext class contains the additional context supplied by the AIContextProvider.
    This context will be combined with context supplied by other providers before being passed to the AI model.
    This context is per invocation, and will not be stored as part of the chat history.
    """

    instructions: str | None = None
    """
    Any instructions to pass to the AI model in addition to any other prompts
    that it may already have (in the case of an agent), or chat history that may already exist.
    """


# region AIContextProvider


class AIContextProvider(AFBaseModel, ABC):
    async def thread_created(self, thread_id: str | None) -> None:
        """Called just after a new thread is created.

        Implementers can use this method to do any operations required at the creation of a new thread.
        For example, checking long term storage for any data that is relevant
        to the current session based on the input text.

        Args:
            thread_id: The ID of the new thread, if the thread has an ID.
        """
        pass

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Called just before messages are added to the chat by any participant.

        Inheritors can use this method to update their context based on new messages.

        Args:
            thread_id: The ID of the thread for the new message, if the thread has an ID.
            new_messages: New messages to add.
        """
        pass

    @abstractmethod
    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> AIContext:
        """Called just before the Model/Agent/etc. is invoked.

        Implementers can load any additional context required at this time,
        and they should return any context that should be passed to the Model/Agent/etc.

        Args:
            messages: The most recent messages that the Model/Agent/etc. is being invoked with.
        """
        pass


class AggregateAIContextProvider(AIContextProvider):
    def __init__(self, ai_context_providers: Iterable[AIContextProvider] | None = None) -> None:
        """Initialize AggregateAIContextProvider with context providers.

        Args:
            ai_context_providers: Context providers to add.
        """
        self._providers: list[AIContextProvider] = list(ai_context_providers or [])

    @property
    def providers(self) -> list[AIContextProvider]:
        """Returns the list of registered context providers."""
        return self._providers

    def add(self, ai_context_provider: AIContextProvider) -> None:
        """Adds new context provider.

        Args:
            ai_context_provider: Context provider to add.
        """
        self._providers.append(ai_context_provider)

    async def thread_created(self, thread_id: str | None = None) -> None:
        for x in self._providers:
            await x.thread_created(thread_id)

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        for x in self._providers:
            await x.messages_adding(thread_id, new_messages)

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> AIContext:
        sub_contexts = [await x.model_invoking(messages) for x in self._providers]
        combined_context = AIContext()
        combined_context.instructions = "\n".join([
            ctx.instructions for ctx in sub_contexts if ctx.instructions and ctx.instructions.strip()
        ])
        return combined_context
