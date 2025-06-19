# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import typing
from abc import ABC, abstractmethod
from typing import AsyncIterator

from ..common import ChatMessage

class MessagesRetrievableThread(ABC):
    """
    An interface for agent threads that allow retrieval of messages in the thread for agent invocation.

    Some agents need to be invoked with all relevant chat history messages in order to produce a result, 
    while some must be invoked with the id of a server side thread that contains the chat history.

    This interface can be implemented by all thread types that support the case where the agent is invoked 
    with the chat history. Implementations must consider the size of the messages provided, so that they do 
    not exceed the maximum size of the context window of the agent they are used with. Where appropriate, 
    implementations should truncate or summarize messages so that the size of messages are constrained.
    """

    @abstractmethod
    def get_messages_async(self, cancellation_token=None) -> AsyncIterator[ChatMessage]:
        """
        Gets the messages in the thread for agent invocation.
        
        Args:
            cancellation_token: The token to monitor for cancellation requests

        Returns:
            AsyncIterator[ChatMessage]: An asynchronous iterator of messages
        """
        pass
