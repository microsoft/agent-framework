# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import Optional, Any, Dict
from .chat_role import ChatRole

class ChatMessage:
    """
    Represents a message in a chat conversation.
    """
    
    def __init__(self, role: ChatRole, content: str, author_name: Optional[str] = None):
        """
        Initialize a new instance of the ChatMessage class.
        
        Args:
            role (ChatRole): The role of the message author.
            content (str): The content of the message.
            author_name (Optional[str]): The name of the author of the message, if available.
        """
        self._role = role
        self._content = content
        self._author_name = author_name
        self._tool_calls: list = []
        self._function_call: Optional[Dict[str, Any]] = None
        self._name: Optional[str] = None

    @property
    def role(self) -> ChatRole:
        """
        Gets the role of the message author.
        
        Returns:
            ChatRole: The role of the message author.
        """
        return self._role

    @property
    def content(self) -> str:
        """
        Gets the content of the message.
        
        Returns:
            str: The content of the message.
        """
        return self._content

    @property
    def author_name(self) -> Optional[str]:
        """
        Gets the name of the author of the message, if available.
        
        Returns:
            Optional[str]: The name of the author or None.
        """
        return self._author_name

    @author_name.setter
    def author_name(self, value: Optional[str]) -> None:
        """
        Sets the name of the author of the message.
        
        Args:
            value (Optional[str]): The name of the author or None.
        """
        self._author_name = value

    @property
    def tool_calls(self) -> list:
        """
        Gets the tool calls made in this message, if any.
        
        Returns:
            list: A list of tool calls made in this message.
        """
        return self._tool_calls

    @tool_calls.setter
    def tool_calls(self, value: list) -> None:
        """
        Sets the tool calls made in this message.
        
        Args:
            value (list): A list of tool calls.
        """
        self._tool_calls = value

    @property
    def function_call(self) -> Optional[Dict[str, Any]]:
        """
        Gets the function call made in this message, if any.
        
        Returns:
            Optional[Dict[str, Any]]: The function call or None.
        """
        return self._function_call

    @function_call.setter
    def function_call(self, value: Optional[Dict[str, Any]]) -> None:
        """
        Sets the function call made in this message.
        
        Args:
            value (Optional[Dict[str, Any]]): The function call or None.
        """
        self._function_call = value

    @property
    def name(self) -> Optional[str]:
        """
        Gets the name associated with this message, if any.
        Used primarily for function/tool response messages.
        
        Returns:
            Optional[str]: The name or None.
        """
        return self._name

    @name.setter
    def name(self, value: Optional[str]) -> None:
        """
        Sets the name associated with this message.
        Used primarily for function/tool response messages.
        
        Args:
            value (Optional[str]): The name or None.
        """
        self._name = value
