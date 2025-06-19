# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import asyncio
from typing import List, Collection, AsyncIterator, Optional

from .agent_thread import AgentThread
from .messages_retrievable_thread import MessagesRetrievableThread
from ..common import ChatMessage

class MemoryAgentThread(AgentThread, MessagesRetrievableThread):
    """
    A thread implementation that stores messages in memory.
    
    This implementation is suitable for agents that need to access the full message history
    when making requests or for local conversations that don't require persistence.
    """
    
    def __init__(self, thread_id: Optional[str] = None):
        """
        Initialize a new instance of the MemoryAgentThread class.
        
        Args:
            thread_id (Optional[str]): An optional thread ID to initialize the thread with.
        """
        super().__init__()
        self.id = thread_id
        self._messages: List[ChatMessage] = []
        
    async def on_new_messages_async(self, messages: Collection[ChatMessage], cancellation_token=None) -> None:
        """
        This method is called when new messages have been contributed to the chat by any participant.
        
        Updates the internal message store with the new messages.
        
        Args:
            messages (Collection[ChatMessage]): The messages that were added to the chat
            cancellation_token: The token to monitor for cancellation requests
        """
        for message in messages:
            self._messages.append(message)
            
    async def get_messages_async(self, cancellation_token=None) -> AsyncIterator[ChatMessage]:
        """
        Gets the messages in the thread for agent invocation.
        
        Yields the messages stored in this thread's memory.
        
        Args:
            cancellation_token: The token to monitor for cancellation requests

        Yields:
            ChatMessage: The messages in the thread
        """
        for message in self._messages:
            yield message
            
    @property
    def messages(self) -> List[ChatMessage]:
        """
        Gets a copy of all messages stored in this thread.
        
        Returns:
            List[ChatMessage]: A copy of the messages list
        """
        return self._messages.copy()
    
    def clear_messages(self) -> None:
        """
        Clears all messages stored in this thread.
        """
        self._messages.clear()
    
    def add_message(self, message: ChatMessage) -> None:
        """
        Adds a single message to this thread.
        
        Args:
            message (ChatMessage): The message to add
        """
        if message is None:
            raise ValueError("message cannot be None")
        
        self._messages.append(message)
    
    def add_messages(self, messages: Collection[ChatMessage]) -> None:
        """
        Adds multiple messages to this thread.
        
        Args:
            messages (Collection[ChatMessage]): The messages to add
        """
        if messages is None:
            raise ValueError("messages cannot be None")
        
        for message in messages:
            self.add_message(message)
