# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import List, AsyncIterator, Optional, Dict, Any
import logging
from openai import AsyncOpenAI, AsyncAzureOpenAI

from .chat_client import ChatClient
from ..common import ChatMessage, ChatResponse, ChatResponseUpdate, ChatRole

class OpenAIChatClient(ChatClient):
    """
    Implementation of ChatClient for OpenAI's API.
    """
    
    def __init__(self, client):
        """
        Initialize a new instance of the OpenAIChatClient class.
        
        Args:
            client: The OpenAI client instance (AsyncOpenAI or AsyncAzureOpenAI).
        """
        self._client = client
        self._logger = logging.getLogger(__name__)
    
    async def get_response_async(self, 
                           messages: List[ChatMessage], 
                           options=None, 
                           cancellation_token=None) -> ChatResponse:
        """
        Gets a response from the chat client.
        
        Args:
            messages (List[ChatMessage]): The messages to send to the chat client.
            options: The options for the chat client.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            ChatResponse: The response from the chat client.
        """
        try:
            # Convert our ChatMessage objects to OpenAI format
            openai_messages = self._convert_to_openai_messages(messages)
            
            # Create the completion
            response = await self._client.chat.completions.create(
                messages=openai_messages,
                **self._get_openai_options(options)
            )
            
            # Convert the response to our format
            chat_response = self._convert_from_openai_response(response)
            
            return chat_response
            
        except Exception as e:
            self._logger.error(f"Error in get_response_async: {str(e)}")
            raise
    
    async def get_streaming_response_async(self, 
                                     messages: List[ChatMessage], 
                                     options=None, 
                                     cancellation_token=None) -> AsyncIterator[ChatResponseUpdate]:
        """
        Gets a streaming response from the chat client.
        
        Args:
            messages (List[ChatMessage]): The messages to send to the chat client.
            options: The options for the chat client.
            cancellation_token: The token to monitor for cancellation requests.
            
        Returns:
            AsyncIterator[ChatResponseUpdate]: An asynchronous iterator of response updates.
        """
        try:
            # Convert our ChatMessage objects to OpenAI format
            openai_messages = self._convert_to_openai_messages(messages)
            
            # Create the completion with streaming
            stream = await self._client.chat.completions.create(
                messages=openai_messages,
                stream=True,
                **self._get_openai_options(options)
            )
            
            # Yield updates as they come in
            current_role = None
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if choice and choice.delta:
                    # For the first chunk, set the role
                    if current_role is None and hasattr(choice.delta, "role"):
                        current_role = ChatRole(choice.delta.role)
                    
                    # For content chunks, yield an update
                    if hasattr(choice.delta, "content") and choice.delta.content:
                        update = ChatResponseUpdate(current_role or ChatRole.ASSISTANT, choice.delta.content)
                        yield update
                        
        except Exception as e:
            self._logger.error(f"Error in get_streaming_response_async: {str(e)}")
            raise
    
    def _convert_to_openai_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """
        Converts our ChatMessage objects to OpenAI format.
        
        Args:
            messages: The messages to convert.
            
        Returns:
            List[Dict[str, Any]]: The messages in OpenAI format.
        """
        openai_messages = []
        
        for message in messages:
            openai_message = {
                "role": message.role.value,
                "content": message.content
            }
            
            if message.name:
                openai_message["name"] = message.name
                
            if message.function_call:
                openai_message["function_call"] = message.function_call
                
            # Handle tool_calls if needed
            # This is simplified and would need more work for a complete implementation
            
            openai_messages.append(openai_message)
            
        return openai_messages
    
    def _convert_from_openai_response(self, response) -> ChatResponse:
        """
        Converts an OpenAI response to our ChatResponse format.
        
        Args:
            response: The OpenAI response.
            
        Returns:
            ChatResponse: The converted response.
        """
        chat_response = ChatResponse()
        
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message"):
                message = ChatMessage(
                    ChatRole(choice.message.role),
                    choice.message.content or ""
                )
                
                # Handle function_call if present
                if hasattr(choice.message, "function_call") and choice.message.function_call:
                    message.function_call = {
                        "name": choice.message.function_call.name,
                        "arguments": choice.message.function_call.arguments
                    }
                    
                # Handle tool_calls if present
                # This is simplified and would need more work for a complete implementation
                
                chat_response.messages.append(message)
                
        # Set conversation ID if available
        if hasattr(response, "id"):
            chat_response.conversation_id = response.id
            
        return chat_response
    
    def _get_openai_options(self, options) -> Dict[str, Any]:
        """
        Converts our options to OpenAI API options.
        
        Args:
            options: Our chat options.
            
        Returns:
            Dict[str, Any]: Options for the OpenAI API.
        """
        if not options:
            return {}
            
        openai_options = {}
        
        if options.model_id:
            openai_options["model"] = options.model_id
            
        if options.temperature is not None:
            openai_options["temperature"] = options.temperature
            
        if options.max_output_tokens is not None:
            openai_options["max_tokens"] = options.max_output_tokens
            
        if options.top_p is not None:
            openai_options["top_p"] = options.top_p
            
        if options.frequency_penalty is not None:
            openai_options["frequency_penalty"] = options.frequency_penalty
            
        if options.presence_penalty is not None:
            openai_options["presence_penalty"] = options.presence_penalty
            
        if options.stop_sequences:
            openai_options["stop"] = options.stop_sequences
            
        # Handle more options as needed
        # This is simplified and would need more work for a complete implementation
        
        return openai_options
