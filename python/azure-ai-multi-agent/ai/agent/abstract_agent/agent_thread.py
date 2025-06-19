# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import typing
import asyncio
from typing import List, Optional, Collection

from ..common import ChatMessage

class AgentThread:
    """
    Base abstraction for all agent threads.
    A thread represents a specific conversation with an agent.
    """

    def __init__(self):
        """
        Initialize a new instance of the AgentThread class.
        """
        self._id: Optional[str] = None

    @property
    def id(self) -> Optional[str]:
        """
        Gets the id of the current thread.
        
        This id may be None if the thread has no id, or if it represents 
        a service-owned thread but the service has not yet been called to create the thread.
        
        The id may also change over time where the AgentThread is a proxy to 
        a service owned thread that forks on each agent invocation.
        
        Returns:
            Optional[str]: The thread id or None
        """
        return self._id

    @id.setter
    def id(self, value: Optional[str]) -> None:
        """
        Sets the id of the current thread.
        
        Args:
            value (Optional[str]): The thread id or None
        """
        self._id = value

    async def on_new_messages_async(self, messages: Collection[ChatMessage], cancellation_token=None) -> None:
        """
        This method is called when new messages have been contributed to the chat by any participant.
        
        Inheritors can use this method to update their context based on the new messages.
        
        Args:
            messages (Collection[ChatMessage]): The messages that were added to the chat
            cancellation_token: The token to monitor for cancellation requests
        """
        # Base implementation does nothing
        pass
