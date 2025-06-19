# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import logging
import asyncio
from typing import List, Collection, AsyncIterator, Optional, Type, Dict, Any
import uuid

from ..abstract_agent.agent import Agent
from ..abstract_agent.agent_thread import AgentThread
from ..abstract_agent.agent_run_options import AgentRunOptions
from ..common import ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole, chat_response_updates_to_chat_response
from .chat_client import ChatClient
from .chat_client_agent_thread import ChatClientAgentThread, ChatClientAgentThreadType
from .chat_client_agent_options import ChatClientAgentOptions, ChatOptions
from .chat_client_agent_run_options import ChatClientAgentRunOptions

class ChatClientAgent(Agent):
    """
    Represents an agent that can be invoked using a chat client.
    """
    
    def __init__(self, chat_client: ChatClient, options: Optional[ChatClientAgentOptions] = None, logger=None):
        """
        Initialize a new instance of the ChatClientAgent class.
        
        Args:
            chat_client (ChatClient): The chat client to use for invoking the agent.
            options (Optional[ChatClientAgentOptions]): Optional agent options to configure the agent.
            logger: Optional logger to use for logging.
        """
        if chat_client is None:
            raise ValueError("chat_client cannot be None")
            
        # Options must be cloned since ChatClientAgentOptions is mutable
        self._agent_options = options.clone() if options is not None else None
        
        # Get the type of the chat client
        self._chat_client_type = type(chat_client)
        
        # For simplicity, we're not implementing the agent_invoking_chat_client wrapper here
        self._chat_client = chat_client
        
        # Get a logger
        self._logger = logger or logging.getLogger(__name__)
    
    @property
    def chat_client(self) -> ChatClient:
        """
        The underlying chat client used by the agent to invoke chat completions.
        
        Returns:
            ChatClient: The chat client.
        """
        return self._chat_client
    
    @property
    def id(self) -> str:
        """
        Gets the identifier of the agent.
        
        Returns:
            str: The identifier of the agent.
        """
        return self._agent_options.id if self._agent_options and self._agent_options.id else super().id
    
    @property
    def name(self) -> Optional[str]:
        """
        Gets the name of the agent.
        
        Returns:
            Optional[str]: The name of the agent or None.
        """
        return self._agent_options.name if self._agent_options else None
    
    @property
    def description(self) -> Optional[str]:
        """
        Gets the description of the agent.
        
        Returns:
            Optional[str]: The description of the agent or None.
        """
        return self._agent_options.description if self._agent_options else None
    
    @property
    def instructions(self) -> Optional[str]:
        """
        Gets the instructions for the agent.
        
        Returns:
            Optional[str]: The instructions for the agent or None.
        """
        return self._agent_options.instructions if self._agent_options else None
    
    @property
    def chat_options(self) -> Optional[ChatOptions]:
        """
        Gets of the default chat options used by the agent.
        
        Returns:
            Optional[ChatOptions]: The chat options or None.
        """
        return self._agent_options.chat_options if self._agent_options else None
    
    def get_new_thread(self) -> AgentThread:
        """
        Get a new AgentThread instance that is compatible with the agent.
        
        Returns:
            AgentThread: A new ChatClientAgentThread instance.
        """
        return ChatClientAgentThread()
    
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
            
        chat_client_thread, chat_options, thread_messages = await self._prepare_thread_and_messages_async(
            thread, messages, options, cancellation_token
        )
        
        agent_name = self._get_agent_name()
        
        self._logger.debug(f"[run_async_with_messages] Agent {self.id}/{agent_name} Invoking client {self._chat_client_type.__name__}")
        
        chat_response = await self.chat_client.get_response_async(thread_messages, chat_options, cancellation_token)
        
        self._logger.info(f"[run_async_with_messages] Agent {self.id}/{agent_name} Invoked client {self._chat_client_type.__name__} with message count: {len(messages)}")
        
        # Update the thread with the conversation ID
        self._update_thread_with_type_and_conversation_id(chat_client_thread, chat_response.conversation_id)
        
        # Only notify the thread of new messages if the response was successful
        await self.notify_thread_of_new_messages_async(chat_client_thread, messages, cancellation_token)
        
        # Ensure that the author name is set for each message in the response
        for chat_response_message in chat_response.messages:
            if not chat_response_message.author_name:
                chat_response_message.author_name = agent_name
                
        # Convert the chat response messages to a valid collection for notification
        chat_response_messages = list(chat_response.messages)
        
        await self.notify_thread_of_new_messages_async(chat_client_thread, chat_response_messages, cancellation_token)
        
        if options and options.on_intermediate_messages:
            await options.on_intermediate_messages(chat_response_messages)
            
        return chat_response
    
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
            AsyncIterator[ChatResponseUpdate]: An async list of response items that each contain a ChatResponseUpdate
        """
        if messages is None:
            raise ValueError("messages cannot be None")
            
        input_messages = list(messages)
        
        chat_client_thread, chat_options, thread_messages = await self._prepare_thread_and_messages_async(
            thread, input_messages, options, cancellation_token
        )
        
        message_count = len(thread_messages)
        agent_name = self._get_agent_name()
        
        self._logger.debug(f"[run_streaming_async_with_messages] Agent {self.id}/{agent_name} Invoking client {self._chat_client_type.__name__}")
        
        # Get the streaming response
        response_updates_iterator = self.chat_client.get_streaming_response_async(
            thread_messages, chat_options, cancellation_token
        )
        
        self._logger.info(f"[run_streaming_async_with_messages] Agent {self.id}/{agent_name} Invoked client {self._chat_client_type.__name__}")
        
        # Collect the updates to convert to a ChatResponse at the end
        response_updates = []
        
        # Yield the updates as they come in
        async for update in response_updates_iterator:
            if update:
                response_updates.append(update)
                update.author_name = update.author_name or agent_name
                yield update
                
        # Convert the updates to a ChatResponse
        chat_response = chat_response_updates_to_chat_response(response_updates)
        chat_response_messages = list(chat_response.messages)
        
        # Update the thread with the conversation ID
        self._update_thread_with_type_and_conversation_id(chat_client_thread, chat_response.conversation_id)
        
        # To avoid inconsistent state, only notify the thread of the input messages if no error occurs
        await self.notify_thread_of_new_messages_async(chat_client_thread, input_messages, cancellation_token)
        await self.notify_thread_of_new_messages_async(chat_client_thread, chat_response_messages, cancellation_token)
        
        if options and options.on_intermediate_messages:
            await options.on_intermediate_messages(chat_response_messages)
    
    async def _prepare_thread_and_messages_async(self,
                                         thread: Optional[AgentThread],
                                         input_messages: Collection[ChatMessage],
                                         run_options: Optional[AgentRunOptions],
                                         cancellation_token) -> tuple:
        """
        Prepares the thread and messages for a chat client invocation.
        
        Args:
            thread: The thread to use or None to create a new one.
            input_messages: The input messages to send.
            run_options: Optional run options.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            tuple: A tuple containing the chat client thread, chat options, and the thread messages.
        """
        chat_options = self._create_configured_chat_options(run_options)
        
        chat_client_thread = self.validate_or_create_thread_type(thread, lambda: ChatClientAgentThread())
        
        # Add any existing messages from the thread to the messages to be sent
        thread_messages = []
        
        # If the thread supports message retrieval, get the messages
        if hasattr(chat_client_thread, "get_messages_async"):
            async for message in chat_client_thread.get_messages_async(cancellation_token):
                thread_messages.append(message)
                
        # Update the messages with agent instructions
        self._update_thread_messages_with_agent_instructions(thread_messages, run_options)
        
        # Add the input messages to the end of thread messages
        thread_messages.extend(input_messages)
        
        # If a user provided two different thread ids, via the thread object and options, we should throw
        # since we don't know which one to use
        if (chat_client_thread.id and chat_options and chat_options.conversation_id and 
            chat_client_thread.id != chat_options.conversation_id):
            raise ValueError(
                f"The conversation_id provided via ChatOptions is different to the id of the provided AgentThread. Only one thread id can be used for a run."
            )
            
        # Only clone and update ChatOptions if we have an id on the thread and we don't have the same one already in ChatOptions
        if chat_client_thread.id and (not chat_options or chat_client_thread.id != chat_options.conversation_id):
            if not chat_options:
                chat_options = ChatOptions()
            chat_options.conversation_id = chat_client_thread.id
            
        return chat_client_thread, chat_options, thread_messages
    
    def _create_configured_chat_options(self, run_options: Optional[AgentRunOptions]) -> Optional[ChatOptions]:
        """
        Configures and returns chat options by merging the provided run options with the agent's default chat options.
        
        Args:
            run_options: The run options containing chat options to merge.
            
        Returns:
            Optional[ChatOptions]: The configured chat options or None.
        """
        request_chat_options = None
        if isinstance(run_options, ChatClientAgentRunOptions) and run_options.chat_options:
            request_chat_options = run_options.chat_options.clone()
            
        # If no agent chat options were provided, return the request chat options as is
        if not self._agent_options or not self._agent_options.chat_options:
            return request_chat_options
            
        # If no request chat options were provided, use the agent's chat options clone
        if not request_chat_options:
            return self._agent_options.chat_options.clone() if self._agent_options.chat_options else None
            
        # If both are present, we need to merge them
        # The merge strategy will prioritize the request options over the agent options,
        # and will fill the blanks with agent options where the request options were not set
        if request_chat_options.allow_multiple_tool_calls is None:
            request_chat_options.allow_multiple_tool_calls = self._agent_options.chat_options.allow_multiple_tool_calls
            
        if request_chat_options.conversation_id is None:
            request_chat_options.conversation_id = self._agent_options.chat_options.conversation_id
            
        if request_chat_options.frequency_penalty is None:
            request_chat_options.frequency_penalty = self._agent_options.chat_options.frequency_penalty
            
        if request_chat_options.max_output_tokens is None:
            request_chat_options.max_output_tokens = self._agent_options.chat_options.max_output_tokens
            
        if request_chat_options.model_id is None:
            request_chat_options.model_id = self._agent_options.chat_options.model_id
            
        if request_chat_options.presence_penalty is None:
            request_chat_options.presence_penalty = self._agent_options.chat_options.presence_penalty
            
        if request_chat_options.response_format is None:
            request_chat_options.response_format = self._agent_options.chat_options.response_format
            
        if request_chat_options.seed is None:
            request_chat_options.seed = self._agent_options.chat_options.seed
            
        if request_chat_options.temperature is None:
            request_chat_options.temperature = self._agent_options.chat_options.temperature
            
        if request_chat_options.top_p is None:
            request_chat_options.top_p = self._agent_options.chat_options.top_p
            
        if request_chat_options.top_k is None:
            request_chat_options.top_k = self._agent_options.chat_options.top_k
            
        if request_chat_options.tool_mode is None:
            request_chat_options.tool_mode = self._agent_options.chat_options.tool_mode
            
        # Merge additional properties
        if (request_chat_options.additional_properties is not None and 
            self._agent_options.chat_options.additional_properties is not None):
            for key, value in self._agent_options.chat_options.additional_properties.items():
                if key not in request_chat_options.additional_properties:
                    request_chat_options.additional_properties[key] = value
        elif self._agent_options.chat_options.additional_properties is not None:
            request_chat_options.additional_properties = self._agent_options.chat_options.additional_properties.copy()
            
        # Handle raw_representation_factory (simplified)
        if self._agent_options.chat_options.raw_representation_factory:
            request_chat_options.raw_representation_factory = self._agent_options.chat_options.raw_representation_factory
            
        # Handle stop sequences
        if self._agent_options.chat_options.stop_sequences:
            if not request_chat_options.stop_sequences:
                request_chat_options.stop_sequences = self._agent_options.chat_options.stop_sequences.copy()
            elif isinstance(request_chat_options.stop_sequences, list):
                request_chat_options.stop_sequences.extend(self._agent_options.chat_options.stop_sequences)
                
        # Handle tools
        if self._agent_options.chat_options.tools:
            if not request_chat_options.tools:
                request_chat_options.tools = self._agent_options.chat_options.tools.copy()
            elif isinstance(request_chat_options.tools, list):
                request_chat_options.tools.extend(self._agent_options.chat_options.tools)
                
        return request_chat_options
    
    def _update_thread_with_type_and_conversation_id(self, 
                                            chat_client_thread: ChatClientAgentThread, 
                                            response_conversation_id: Optional[str]) -> None:
        """
        Updates the thread's storage location and ID based on the conversation ID from the response.
        
        Args:
            chat_client_thread: The thread to update.
            response_conversation_id: The conversation ID from the response.
        """
        # Set the thread's storage location, the first time that we use it
        if not chat_client_thread.storage_location:
            chat_client_thread.storage_location = (
                ChatClientAgentThreadType.IN_MEMORY_MESSAGES if not response_conversation_id 
                else ChatClientAgentThreadType.CONVERSATION_ID
            )
            
        # If we got a conversation id back from the chat client, it means that the service supports server side thread storage
        # so we should capture the id and update the thread with the new id
        if chat_client_thread.storage_location == ChatClientAgentThreadType.CONVERSATION_ID:
            if not response_conversation_id:
                raise ValueError("Service did not return a valid conversation id when using a service managed thread.")
            chat_client_thread.id = response_conversation_id
    
    def _update_thread_messages_with_agent_instructions(self, 
                                               thread_messages: List[ChatMessage], 
                                               options: Optional[AgentRunOptions]) -> None:
        """
        Updates the thread messages with agent instructions.
        
        Args:
            thread_messages: The messages to update.
            options: The run options containing additional instructions.
        """
        # Add additional instructions from options if provided
        if options and options.additional_instructions:
            thread_messages.insert(0, ChatMessage(ChatRole.SYSTEM, options.additional_instructions, self.name))
            
        # Add agent instructions if provided
        if self.instructions:
            thread_messages.insert(0, ChatMessage(ChatRole.SYSTEM, self.instructions, self.name))
    
    def _get_agent_name(self) -> str:
        """
        Gets the agent name or a default if not set.
        
        Returns:
            str: The agent name or 'UnnamedAgent' if not set.
        """
        return self.name or "UnnamedAgent"
