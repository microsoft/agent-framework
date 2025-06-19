# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import logging
from typing import Collection, AsyncIterator, Optional, List
import asyncio

from ..abstract_agent.agent import Agent
from ..abstract_agent.agent_thread import AgentThread
from ..abstract_agent.memory_agent_thread import MemoryAgentThread
from ..abstract_agent.agent_run_options import AgentRunOptions
from ..common import ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole

class SimpleAgent(Agent):
    """
    A simple agent implementation for demonstrating the agent framework.
    
    This agent responds with a pre-configured message to any user message.
    """
    
    def __init__(self, response_text: str = "I am a simple agent.", name: str = None, description: str = None, instructions: str = None, logger=None):
        """
        Initialize a new instance of the SimpleAgent class.
        
        Args:
            response_text (str): The text to respond with.
            name (Optional[str]): The name of the agent.
            description (Optional[str]): The description of the agent.
            instructions (Optional[str]): The instructions for the agent.
            logger: Optional logger to use for logging.
        """
        self._response_text = response_text
        self._name = name
        self._description = description
        self._instructions = instructions
        self._logger = logger or logging.getLogger(__name__)
    
    @property
    def name(self) -> Optional[str]:
        """
        Gets the name of the agent.
        
        Returns:
            Optional[str]: The name of the agent or None.
        """
        return self._name
    
    @property
    def description(self) -> Optional[str]:
        """
        Gets the description of the agent.
        
        Returns:
            Optional[str]: The description of the agent or None.
        """
        return self._description
    
    @property
    def instructions(self) -> Optional[str]:
        """
        Gets the instructions for the agent.
        
        Returns:
            Optional[str]: The instructions for the agent or None.
        """
        return self._instructions
    
    def get_new_thread(self) -> AgentThread:
        """
        Get a new AgentThread instance that is compatible with the agent.
        
        Returns:
            AgentThread: A new MemoryAgentThread instance.
        """
        return MemoryAgentThread()
    
    async def run_async_with_messages(self,
                                messages: Collection[ChatMessage],
                                thread: Optional[AgentThread] = None, 
                                options: Optional[AgentRunOptions] = None,
                                cancellation_token = None) -> ChatResponse:
        """
        Run the agent with the provided messages and arguments.
        
        Args:
            messages (Collection[ChatMessage]): The messages to pass to the agent.
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            ChatResponse: A ChatResponse containing the list of ChatMessage items
        """
        if messages is None:
            raise ValueError("messages cannot be None")
        
        # Validate or create the thread
        memory_thread = self.validate_or_create_thread_type(thread, self.get_new_thread)
        
        if not isinstance(memory_thread, MemoryAgentThread):
            raise TypeError(f"Thread must be of type MemoryAgentThread, but was {type(memory_thread)}")
        
        # Add the new messages to the thread
        await self.notify_thread_of_new_messages_async(memory_thread, messages, cancellation_token)
        
        # Create the response message
        response_message = ChatMessage(ChatRole.ASSISTANT, self._response_text)
        if self.name:
            response_message.author_name = self.name
        
        # Notify the thread of the response message
        await self.notify_thread_of_new_messages_async(memory_thread, [response_message], cancellation_token)
        
        # Create a response
        response = ChatResponse([response_message])
        
        return response
    
    async def run_streaming_async_with_messages(self,
                                         messages: Collection[ChatMessage],
                                         thread: Optional[AgentThread] = None, 
                                         options: Optional[AgentRunOptions] = None,
                                         cancellation_token = None) -> AsyncIterator[ChatResponseUpdate]:
        """
        Run the agent with the provided messages and arguments in streaming mode.
        
        Args:
            messages (Collection[ChatMessage]): The messages to pass to the agent.
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            AsyncIterator[ChatResponseUpdate]: An async iterator of response items that each contain a ChatResponseUpdate
        """
        if messages is None:
            raise ValueError("messages cannot be None")
        
        # Validate or create the thread
        memory_thread = self.validate_or_create_thread_type(thread, self.get_new_thread)
        
        if not isinstance(memory_thread, MemoryAgentThread):
            raise TypeError(f"Thread must be of type MemoryAgentThread, but was {type(memory_thread)}")
        
        # Add the new messages to the thread
        await self.notify_thread_of_new_messages_async(memory_thread, messages, cancellation_token)
        
        # For streaming, split the response into characters to simulate streaming
        response_text = self._response_text
        
        # Create the response message with no content initially
        response_message = ChatMessage(ChatRole.ASSISTANT, "")
        if self.name:
            response_message.author_name = self.name
        
        # Create initial update with empty content
        update = ChatResponseUpdate(response_message)
        
        # Return the first update
        yield update
        
        # Simulate streaming by adding one character at a time with a small delay
        for i in range(len(response_text)):
            # Update the message content
            response_message.content = response_text[:i+1]
            
            # Create update with the new content
            update = ChatResponseUpdate(response_message)
            
            yield update
            
            # Add a small delay to simulate streaming
            await asyncio.sleep(0.05)
        
        # Complete the response
        response_message.content = response_text
        
        # Notify the thread of the response message
        await self.notify_thread_of_new_messages_async(memory_thread, [response_message], cancellation_token)
