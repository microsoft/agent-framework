# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from typing import List
from .chat_response_update import ChatResponseUpdate
from .chat_response import ChatResponse
from .chat_message import ChatMessage

def chat_response_updates_to_chat_response(updates: List[ChatResponseUpdate]) -> ChatResponse:
    """
    Converts a list of ChatResponseUpdate to a ChatResponse.
    
    Args:
        updates (List[ChatResponseUpdate]): The list of response updates to convert.
        
    Returns:
        ChatResponse: The converted chat response.
    """
    response = ChatResponse()
    
    # Create a new ChatMessage from the updates
    if updates:
        message = ChatMessage(updates[0].role, "")
        message.author_name = updates[0].author_name
        
        for update in updates:
            if update.content:
                message.content += update.content
                
        response.messages.append(message)
    
    return response
