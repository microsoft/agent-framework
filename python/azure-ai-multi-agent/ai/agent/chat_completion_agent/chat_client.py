# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from abc import ABC, abstractmethod
from typing import List, AsyncIterator, Optional

from ..common import ChatMessage, ChatResponse, ChatResponseUpdate
from .chat_client_agent_options import ChatOptions

class ChatClient(ABC):
    """
    Interface for a chat client that can be used to invoke chat completions.
    """
    
    @abstractmethod
    async def get_response_async(self, 
                           messages: List[ChatMessage], 
                           options: Optional[ChatOptions] = None, 
                           cancellation_token=None) -> ChatResponse:
        """
        Gets a response from the chat client.
        
        Args:
            messages (List[ChatMessage]): The messages to send to the chat client.
            options (Optional[ChatOptions]): The options for the chat client.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            ChatResponse: The response from the chat client.
        """
        pass
        
    @abstractmethod
    async def get_streaming_response_async(self, 
                                     messages: List[ChatMessage], 
                                     options: Optional[ChatOptions] = None, 
                                     cancellation_token=None) -> AsyncIterator[ChatResponseUpdate]:
        """
        Gets a streaming response from the chat client.
        
        Args:
            messages (List[ChatMessage]): The messages to send to the chat client.
            options (Optional[ChatOptions]): The options for the chat client.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            AsyncIterator[ChatResponseUpdate]: An asynchronous iterator of response updates.
        """
        pass
        
    def get_service(self, service_type):
        """
        Gets a service from the chat client by type.
        
        Args:
            service_type: The type of service to get.
            
        Returns:
            The requested service or None if not available.
        """
        return None
