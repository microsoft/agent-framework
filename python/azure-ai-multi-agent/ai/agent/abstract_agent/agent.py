# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import uuid
import typing
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, Collection, AsyncIterator, Callable, TypeVar, Type, Union, Awaitable

# Import local components
from .agent_thread import AgentThread
from .agent_run_options import AgentRunOptions
from ..common import ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole

# Type variable for thread type in validate_or_create_thread_type method
TThreadType = TypeVar('TThreadType', bound=AgentThread)

class Agent(ABC):
    """
    Base abstraction for all agents. An agent instance may participate in one or more conversations.
    A conversation may include one or more agents.
    """

    @property
    def id(self) -> str:
        """
        Gets the identifier of the agent (optional).
        
        The default is a random UUID value, but for service agents, it will match the id of the agent in the service.
        
        Returns:
            str: The identifier of the agent
        """
        return str(uuid.uuid4())

    @property
    def name(self) -> Optional[str]:
        """
        Gets the name of the agent (optional).
        
        Returns:
            Optional[str]: The name of the agent or None
        """
        return None

    @property
    def description(self) -> Optional[str]:
        """
        Gets the description of the agent (optional).
        
        Returns:
            Optional[str]: The description of the agent or None
        """
        return None

    @property
    def instructions(self) -> Optional[str]:
        """
        Gets the instructions for the agent (optional).
        
        Returns:
            Optional[str]: The instructions for the agent or None
        """
        return None

    @abstractmethod
    def get_new_thread(self) -> AgentThread:
        """
        Get a new AgentThread instance that is compatible with the agent.
        
        If an agent supports multiple thread types, this method should return the default thread
        type for the agent or whatever the agent was configured to use.
        
        If the thread needs to be created via a service call it would be created on first use.
        
        Returns:
            AgentThread: A new AgentThread instance
        """
        pass

    async def run_async(self, 
                   thread: Optional[AgentThread] = None, 
                   options: Optional[AgentRunOptions] = None,
                   cancellation_token = None) -> ChatResponse:
        """
        Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
        
        Args:
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            ChatResponse: A ChatResponse containing the list of ChatMessage items
        """
        return await self.run_async_with_messages([], thread, options, cancellation_token)

    async def run_async_with_message(self, 
                              message: str,
                              thread: Optional[AgentThread] = None, 
                              options: Optional[AgentRunOptions] = None,
                              cancellation_token = None) -> ChatResponse:
        """
        Run the agent with the provided message and arguments.
        
        The provided message string will be treated as a user message.
        
        Args:
            message (str): The message to pass to the agent.
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            ChatResponse: A ChatResponse containing the list of ChatMessage items
        """
        if message is None or message.strip() == "":
            raise ValueError("message cannot be None or empty")
        
        # Create a user message
        # We'll need to implement a ChatMessage class and ChatRole enum
        chat_message = ChatMessage(ChatRole.User, message)
        
        return await self.run_async_with_chat_message(chat_message, thread, options, cancellation_token)

    async def run_async_with_chat_message(self,
                                    message: ChatMessage,
                                    thread: Optional[AgentThread] = None, 
                                    options: Optional[AgentRunOptions] = None,
                                    cancellation_token = None) -> ChatResponse:
        """
        Run the agent with the provided message and arguments.
        
        Args:
            message (ChatMessage): The message to pass to the agent.
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            ChatResponse: A ChatResponse containing the list of ChatMessage items
        """
        if message is None:
            raise ValueError("message cannot be None")
            
        return await self.run_async_with_messages([message], thread, options, cancellation_token)

    @abstractmethod
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
        pass

    async def run_streaming_async(self,
                            thread: Optional[AgentThread] = None, 
                            options: Optional[AgentRunOptions] = None,
                            cancellation_token = None) -> AsyncIterator[ChatResponseUpdate]:
        """
        Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
        
        Args:
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            AsyncIterator[ChatResponseUpdate]: An async list of response items that each contain a ChatResponseUpdate
        """
        return self.run_streaming_async_with_messages([], thread, options, cancellation_token)

    async def run_streaming_async_with_message(self,
                                       message: str,
                                       thread: Optional[AgentThread] = None, 
                                       options: Optional[AgentRunOptions] = None,
                                       cancellation_token = None) -> AsyncIterator[ChatResponseUpdate]:
        """
        Run the agent with the provided message and arguments.
        
        The provided message string will be treated as a user message.
        
        Args:
            message (str): The message to pass to the agent.
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            AsyncIterator[ChatResponseUpdate]: An async list of response items that each contain a ChatResponseUpdate
        """
        if message is None or message.strip() == "":
            raise ValueError("message cannot be None or empty")
        
        # Create a user message
        chat_message = ChatMessage(ChatRole.User, message)
        
        return await self.run_streaming_async_with_chat_message(chat_message, thread, options, cancellation_token)

    async def run_streaming_async_with_chat_message(self,
                                             message: ChatMessage,
                                             thread: Optional[AgentThread] = None, 
                                             options: Optional[AgentRunOptions] = None,
                                             cancellation_token = None) -> AsyncIterator[ChatResponseUpdate]:
        """
        Run the agent with the provided message and arguments.
        
        Args:
            message (ChatMessage): The message to pass to the agent.
            thread (Optional[AgentThread]): The conversation thread to continue with this invocation. 
                                            If not provided, creates a new thread. The thread will be mutated 
                                            with the provided messages and agent response.
            options (Optional[AgentRunOptions]): Optional parameters for agent invocation.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            AsyncIterator[ChatResponseUpdate]: An async list of response items that each contain a ChatResponseUpdate
        """
        if message is None:
            raise ValueError("message cannot be None")
            
        return await self.run_streaming_async_with_messages([message], thread, options, cancellation_token)

    @abstractmethod
    async def run_streaming_async_with_messages(self,
                                         messages: Collection[ChatMessage],
                                         thread: Optional[AgentThread] = None, 
                                         options: Optional[AgentRunOptions] = None,
                                         cancellation_token = None) -> AsyncIterator[ChatResponseUpdate]:
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
            AsyncIterator[ChatResponseUpdate]: An async list of response items that each contain a ChatResponseUpdate
        """
        pass

    def validate_or_create_thread_type(self,
                                      thread: Optional[AgentThread],
                                      construct_thread: Callable[[], TThreadType]) -> TThreadType:
        """
        Checks that the thread is of the expected type, or if None, creates the default thread type.
        
        Args:
            thread (Optional[AgentThread]): The thread to create if it's None and validate its type if not None.
            construct_thread (Callable[[], TThreadType]): A callback to use to construct the thread if it's None.
            
        Returns:
            TThreadType: The validated or newly created thread
            
        Raises:
            NotSupportedError: If the thread is not of the expected type
        """
        if thread is None:
            if construct_thread is None:
                raise ValueError("construct_thread cannot be None when thread is None")
            thread = construct_thread()
            
        # Check if thread is of the expected type
        # In Python we can't get the type parameter at runtime like in C#
        # So we'll rely on isinstance check in the derived class
        
        return thread  # Type will be checked by the caller

    async def notify_thread_of_new_messages_async(self,
                                           thread: AgentThread,
                                           messages: Collection[ChatMessage],
                                           cancellation_token = None) -> None:
        """
        Notify the given thread that new messages are available.
        
        Note that while all agents should notify their threads of new messages,
        not all threads will necessarily take action. For some threads, this may be
        the only way that they would know that a new message is available to be added
        to their history.
        
        For other thread types, where history is managed by the service, the thread may
        not need to take any action.
        
        Where threads manage other memory components that need access to new messages,
        notifying the thread will be important, even if the thread itself does not
        require the message.
        
        Args:
            thread (AgentThread): The thread to notify of the new messages.
            messages (Collection[ChatMessage]): The messages to pass to the thread.
            cancellation_token: The token to monitor for cancellation requests.
        """
        if len(messages) > 0:
            await thread.on_new_messages_async(messages, cancellation_token)
