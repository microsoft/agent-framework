# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import asyncio
from typing import AsyncIterator, List, Optional, Dict, Any

from ..abstract_agent.agent_thread import AgentThread
from ..abstract_agent.messages_retrievable_thread import MessagesRetrievableThread
from ..common import ChatMessage

class ChatClientAgentThreadType:
    """
    Defines the type of storage location for the thread.
    """
    IN_MEMORY_MESSAGES = "InMemoryMessages"
    CONVERSATION_ID = "ConversationId"

class ChatClientAgentThread(AgentThread, MessagesRetrievableThread):
    """
    Chat client agent thread.
    """
    
    def __init__(self):
        """
        Initialize a new instance of the ChatClientAgentThread class.
        """
        super().__init__()
        self._messages: List[ChatMessage] = []
        self._storage_location: Optional[str] = None
        
    @property
    def storage_location(self) -> Optional[str]:
        """
        Gets the storage location for the thread.
        
        Returns:
            Optional[str]: The storage location or None.
        """
        return self._storage_location
        
    @storage_location.setter
    def storage_location(self, value: Optional[str]) -> None:
        """
        Sets the storage location for the thread.
        
        Args:
            value (Optional[str]): The storage location or None.
        """
        self._storage_location = value
        
    async def on_new_messages_async(self, messages, cancellation_token=None) -> None:
        """
        Called when new messages are added to the thread.
        Stores the messages if the thread is using InMemoryMessages storage.
        
        Args:
            messages: The new messages to add.
            cancellation_token: The token to monitor for cancellation requests.
        """
        if self.storage_location == ChatClientAgentThreadType.IN_MEMORY_MESSAGES:
            for message in messages:
                self._messages.append(message)
                
    async def get_messages_async(self, cancellation_token=None) -> AsyncIterator[ChatMessage]:
        """
        Gets the messages in the thread.
        For in-memory messages, returns the stored messages.
        For conversation ID, no messages are returned since they're stored on the server.
        
        Args:
            cancellation_token: The token to monitor for cancellation requests.
            
        Yields:
            ChatMessage: The messages in the thread.
        """
        if self.storage_location == ChatClientAgentThreadType.IN_MEMORY_MESSAGES:
            for message in self._messages:
                yield message
