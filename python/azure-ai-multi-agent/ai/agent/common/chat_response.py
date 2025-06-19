# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import Optional, List, Iterable
from .chat_message import ChatMessage

class ChatResponse:
    """
    Represents a response from a chat completion.
    """
    
    def __init__(self, message: Optional[ChatMessage] = None):
        """
        Initialize a new instance of the ChatResponse class.
        
        Args:
            message (Optional[ChatMessage]): A single message to initialize the response with, if provided.
        """
        self._messages: List[ChatMessage] = []
        self._conversation_id: Optional[str] = None
        
        if message is not None:
            self._messages.append(message)

    @property
    def messages(self) -> List[ChatMessage]:
        """
        Gets the messages in the response.
        
        Returns:
            List[ChatMessage]: The messages in the response.
        """
        return self._messages

    @messages.setter
    def messages(self, value: List[ChatMessage]) -> None:
        """
        Sets the messages in the response.
        
        Args:
            value (List[ChatMessage]): The messages to set.
        """
        self._messages = value

    @property
    def conversation_id(self) -> Optional[str]:
        """
        Gets the conversation ID associated with this response, if available.
        
        Returns:
            Optional[str]: The conversation ID or None.
        """
        return self._conversation_id

    @conversation_id.setter
    def conversation_id(self, value: Optional[str]) -> None:
        """
        Sets the conversation ID associated with this response.
        
        Args:
            value (Optional[str]): The conversation ID or None.
        """
        self._conversation_id = value
