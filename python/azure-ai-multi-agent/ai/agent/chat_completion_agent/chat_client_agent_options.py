# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import Optional, Dict, Any, List

class ChatOptions:
    """
    Options for a chat completion request.
    """
    
    def __init__(self):
        """
        Initialize a new instance of the ChatOptions class.
        """
        self.allow_multiple_tool_calls: Optional[bool] = None
        self.conversation_id: Optional[str] = None
        self.frequency_penalty: Optional[float] = None
        self.max_output_tokens: Optional[int] = None
        self.model_id: Optional[str] = None
        self.presence_penalty: Optional[float] = None
        self.response_format: Optional[str] = None
        self.seed: Optional[int] = None
        self.temperature: Optional[float] = None
        self.top_p: Optional[float] = None
        self.top_k: Optional[int] = None
        self.tool_mode: Optional[str] = None
        self.additional_properties: Optional[Dict[str, Any]] = None
        self.tools: List = []
        self.stop_sequences: List[str] = []
        self.raw_representation_factory = None  # This would need a more specific type
        
    def clone(self):
        """
        Creates a clone of the current options.
        
        Returns:
            ChatOptions: A new instance with the same properties.
        """
        cloned = ChatOptions()
        cloned.allow_multiple_tool_calls = self.allow_multiple_tool_calls
        cloned.conversation_id = self.conversation_id
        cloned.frequency_penalty = self.frequency_penalty
        cloned.max_output_tokens = self.max_output_tokens
        cloned.model_id = self.model_id
        cloned.presence_penalty = self.presence_penalty
        cloned.response_format = self.response_format
        cloned.seed = self.seed
        cloned.temperature = self.temperature
        cloned.top_p = self.top_p
        cloned.top_k = self.top_k
        cloned.tool_mode = self.tool_mode
        
        if self.additional_properties:
            cloned.additional_properties = self.additional_properties.copy()
            
        if self.tools:
            cloned.tools = self.tools.copy()
            
        if self.stop_sequences:
            cloned.stop_sequences = self.stop_sequences.copy()
            
        cloned.raw_representation_factory = self.raw_representation_factory
        
        return cloned

class ChatClientAgentOptions:
    """
    Options for a chat client agent.
    """
    
    def __init__(self):
        """
        Initialize a new instance of the ChatClientAgentOptions class.
        """
        self._id: Optional[str] = None
        self._name: Optional[str] = None
        self._description: Optional[str] = None
        self._instructions: Optional[str] = None
        self._chat_options = ChatOptions()
        
    @property
    def id(self) -> Optional[str]:
        """
        Gets the ID of the agent.
        
        Returns:
            Optional[str]: The ID of the agent or None.
        """
        return self._id
    
    @id.setter
    def id(self, value: Optional[str]) -> None:
        """
        Sets the ID of the agent.
        
        Args:
            value (Optional[str]): The ID of the agent or None.
        """
        self._id = value
        
    @property
    def name(self) -> Optional[str]:
        """
        Gets the name of the agent.
        
        Returns:
            Optional[str]: The name of the agent or None.
        """
        return self._name
    
    @name.setter
    def name(self, value: Optional[str]) -> None:
        """
        Sets the name of the agent.
        
        Args:
            value (Optional[str]): The name of the agent or None.
        """
        self._name = value
        
    @property
    def description(self) -> Optional[str]:
        """
        Gets the description of the agent.
        
        Returns:
            Optional[str]: The description of the agent or None.
        """
        return self._description
    
    @description.setter
    def description(self, value: Optional[str]) -> None:
        """
        Sets the description of the agent.
        
        Args:
            value (Optional[str]): The description of the agent or None.
        """
        self._description = value
        
    @property
    def instructions(self) -> Optional[str]:
        """
        Gets the instructions for the agent.
        
        Returns:
            Optional[str]: The instructions for the agent or None.
        """
        return self._instructions
    
    @instructions.setter
    def instructions(self, value: Optional[str]) -> None:
        """
        Sets the instructions for the agent.
        
        Args:
            value (Optional[str]): The instructions for the agent or None.
        """
        self._instructions = value
        
    @property
    def chat_options(self) -> ChatOptions:
        """
        Gets the chat options for the agent.
        
        Returns:
            ChatOptions: The chat options for the agent.
        """
        return self._chat_options
    
    @chat_options.setter
    def chat_options(self, value: ChatOptions) -> None:
        """
        Sets the chat options for the agent.
        
        Args:
            value (ChatOptions): The chat options for the agent.
        """
        self._chat_options = value
        
    def clone(self):
        """
        Creates a clone of the current options.
        
        Returns:
            ChatClientAgentOptions: A new instance with the same properties.
        """
        cloned = ChatClientAgentOptions()
        cloned.id = self.id
        cloned.name = self.name
        cloned.description = self.description
        cloned.instructions = self.instructions
        cloned.chat_options = self.chat_options.clone()
        return cloned
