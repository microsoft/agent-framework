# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from collections.abc import MutableSequence
from typing import Any

from pydantic import Field

from ._pydantic import AFBaseModel
from ._tools import AIFunction
from ._types import ChatMessage


class AIContext(AFBaseModel):
    """A class containing any context that should be provided to the AI model as supplied by an AIContextProvider.

    Each AIContextProvider has the ability to provide its own context for each invocation.
    The AIContext class contains the additional context supplied by the AIContextProvider.
    This context will be combined with context supplied by other providers before being passed to the AI model.
    This context is per invocation, and will not be stored as part of the chat history.
    """

    instructions: str | None = Field(None)
    """
    Any instructions to pass to the AI model in addition to any other prompts
    that it may already have (in the case of an agent), or chat history that may already exist.
    """

    ai_functions: list[AIFunction[Any, Any]] = Field(default_factory=list[AIFunction[Any, Any]])
    """A list of functions/tools to make available to the AI model for the current invocation."""


class AIContextProvider(AFBaseModel, ABC):
    async def conversation_created(self, conversation_id: str | None) -> None:
        """Called just after a new conversation/thread is created.

        Implementers can use this method to do any operations required at the creation of a new conversation/thread.
        For example, checking long term storage for any data that is relevant
        to the current session based on the input text.

        Args:
            conversation_id: The ID of the new conversation/thread, if the conversation/thread has an ID.
        """
        pass

    async def message_adding(self, conversation_id: str | None, new_message: ChatMessage) -> None:
        """Called just before a message is added to the chat by any participant.

        Inheritors can use this method to update their context based on the new message.

        Args:
            conversation_id: The ID of the conversation/thread for the new message,
            if the conversation/thread has an ID.
            new_message: The new message.
        """
        pass

    async def conversation_deleting(self, conversation_id: str | None) -> None:
        """Called just before a conversation/thread is deleted.

        Implementers can use this method to do any operations required before a conversation/thread is deleted.
        For example, storing the context to long term storage.

        Args:
            conversation_id: The ID of the conversation/thread that will be deleted,
            if the conversation/thread has an ID.
        """
        pass

    @abstractmethod
    async def model_invoking(self, new_messages: MutableSequence[ChatMessage]) -> AIContext:
        """Called just before the Model/Agent/etc. is invoked.

        Implementers can load any additional context required at this time,
        and they should return any context that should be passed to the Model/Agent/etc.

        Args:
            new_messages: The most recent messages that the Model/Agent/etc. is being invoked with.
        """
        pass

    async def suspending(self, conversation_id: str | None) -> None:
        """Called when the current conversion is temporarily suspended and any state should be saved.

        In a service that hosts an agent, that is invoked via calls to the service,
        this might be at the end of each service call.
        In a client application, this might be when the user closes the chat window or the application.

        Args:
            conversation_id: The ID of the current conversation/thread, if the conversation/thread has an ID.
        """
        pass

    async def resuming(self, conversation_id: str | None) -> None:
        """Called when the current conversion is resumed and any state should be restored.

        In a service that hosts an agent, that is invoked via calls to the service, this might be
        at the start of each service call where a previous conversation is being continued.
        In a client application, this might be when the user re-opens the chat window to resume a conversation
        after having previously closed it.

        Args:
            conversation_id: The ID of the current conversation/thread, if the conversation/thread has an ID.
        """
        pass
