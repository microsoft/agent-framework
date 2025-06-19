# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import Optional

from ..abstract_agent.agent_run_options import AgentRunOptions
from .chat_client_agent_options import ChatOptions

class ChatClientAgentRunOptions(AgentRunOptions):
    """
    Options for running a chat client agent.
    """
    
    def __init__(self, options=None):
        """
        Initialize a new instance of the ChatClientAgentRunOptions class.
        
        Args:
            options (Optional[AgentRunOptions]): The base options to copy from.
        """
        super().__init__(options)
        self._chat_options: Optional[ChatOptions] = None
        
    @property
    def chat_options(self) -> Optional[ChatOptions]:
        """
        Gets the chat options for the agent invocation.
        
        Returns:
            Optional[ChatOptions]: The chat options or None.
        """
        return self._chat_options
    
    @chat_options.setter
    def chat_options(self, value: Optional[ChatOptions]) -> None:
        """
        Sets the chat options for the agent invocation.
        
        Args:
            value (Optional[ChatOptions]): The chat options or None.
        """
        self._chat_options = value
