# Copyright (c) Microsoft. All rights reserved.

"""Message conversion utilities for DevUI.

Handles conversion between frontend message formats and Agent Framework ChatMessage objects.
"""

from typing import Any, Dict, List, Union, Optional
import logging

try:
    from agent_framework import ChatMessage
    from agent_framework._types import DataContent, TextContent, UriContent, Role
    AGENT_FRAMEWORK_AVAILABLE = True
except ImportError:
    # Fallback when agent_framework is not available
    AGENT_FRAMEWORK_AVAILABLE = False
    ChatMessage = None
    DataContent = None
    TextContent = None
    UriContent = None
    Role = None

logger = logging.getLogger(__name__)

def frontend_messages_to_chat_messages(
    frontend_messages: Union[str, List[Dict[str, Any]]]
) -> Union[str, List[Any]]:
    """Convert frontend message format to Agent Framework compatible format.
    
    Args:
        frontend_messages: Either a simple string or list of rich message objects
        
    Returns:
        str for simple messages, List[ChatMessage] for rich messages
        
    Frontend message format:
    {
        "role": "user" | "assistant" | "system" | "tool",
        "contents": [
            {"type": "text", "text": "Hello"},
            {"type": "data", "uri": "data:image/png;base64,...", "media_type": "image/png"},
            {"type": "uri", "uri": "https://example.com/file.pdf", "media_type": "application/pdf"}
        ]
    }
    """
    if not AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError("Agent Framework is not available")
        
    if isinstance(frontend_messages, str):
        return frontend_messages
    
    if not isinstance(frontend_messages, list):
        raise ValueError("frontend_messages must be str or list")
    
    chat_messages = []
    
    for msg_dict in frontend_messages:
        if not isinstance(msg_dict, dict):
            raise ValueError("Each message must be a dictionary")
            
        # Extract role
        role_str = msg_dict.get('role', 'user')
        try:
            if Role is not None:
                role = Role(value=role_str)
            else:
                raise RuntimeError("Role class not available")
        except Exception as e:
            logger.warning(f"Invalid role '{role_str}', defaulting to 'user': {e}")
            if Role is not None:
                role = Role.USER
            else:
                raise RuntimeError("Role class not available")
            
        # Convert contents
        contents = []
        content_list = msg_dict.get('contents', [])
        
        if not isinstance(content_list, list):
            raise ValueError("Message contents must be a list")
            
        for content_dict in content_list:
            if not isinstance(content_dict, dict):
                raise ValueError("Each content item must be a dictionary")
                
            content_type = content_dict.get('type')
            
            try:
                if content_type == 'text':
                    text = content_dict.get('text', '')
                    if text and TextContent is not None:  # Only add non-empty text content
                        contents.append(TextContent(text=text))
                        
                elif content_type == 'data':
                    uri = content_dict.get('uri')
                    if uri and DataContent is not None:
                        media_type = content_dict.get('media_type')
                        contents.append(DataContent(
                            uri=uri,
                            media_type=media_type
                        ))
                        
                elif content_type == 'uri':
                    uri = content_dict.get('uri')
                    media_type = content_dict.get('media_type', 'application/octet-stream')
                    if uri and UriContent is not None:
                        contents.append(UriContent(
                            uri=uri,
                            media_type=media_type
                        ))
                        
                else:
                    logger.warning(f"Unsupported content type: {content_type}")
                    
            except Exception as e:
                logger.error(f"Error creating content of type {content_type}: {e}")
                continue
        
        # Only create message if we have valid contents
        if contents and ChatMessage is not None:
            try:
                chat_message = ChatMessage(
                    role=role,
                    contents=contents,
                    author_name=msg_dict.get('author_name'),
                    message_id=msg_dict.get('message_id')
                )
                chat_messages.append(chat_message)
            except Exception as e:
                logger.error(f"Error creating ChatMessage: {e}")
                continue
    
    return chat_messages

def validate_frontend_message_content(content_dict: Dict[str, Any]) -> bool:
    """Validate a single content item from frontend.
    
    Args:
        content_dict: Content dictionary to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(content_dict, dict):
        return False
        
    content_type = content_dict.get('type')
    
    if content_type == 'text':
        return isinstance(content_dict.get('text'), str)
        
    elif content_type == 'data':
        uri = content_dict.get('uri', '')
        # Basic data URI validation
        return isinstance(uri, str) and uri.startswith('data:')
        
    elif content_type == 'uri':
        uri = content_dict.get('uri', '')
        return isinstance(uri, str) and (uri.startswith('http://') or uri.startswith('https://'))
        
    return False

def validate_frontend_message(msg_dict: Dict[str, Any], max_content_size: int = 50 * 1024 * 1024) -> tuple[bool, Optional[str]]:
    """Validate a complete frontend message.
    
    Args:
        msg_dict: Message dictionary to validate
        max_content_size: Maximum size for data content in bytes
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(msg_dict, dict):
        return False, "Message must be a dictionary"
        
    # Validate role
    role = msg_dict.get('role')
    if role not in ['user', 'assistant', 'system', 'tool']:
        return False, f"Invalid role: {role}"
        
    # Validate contents
    contents = msg_dict.get('contents', [])
    if not isinstance(contents, list):
        return False, "Contents must be a list"
        
    for i, content in enumerate(contents):
        if not validate_frontend_message_content(content):
            return False, f"Invalid content at index {i}"
            
        # Check data URI size for data content
        if content.get('type') == 'data':
            uri = content.get('uri', '')
            if len(uri) > max_content_size:
                return False, f"Content at index {i} exceeds size limit"
                
    return True, None

def extract_text_from_chat_message(message: Any) -> str:
    """Extract text content from a ChatMessage for simple display.
    
    Args:
        message: ChatMessage object
        
    Returns:
        Combined text from all TextContent items
    """
    if not hasattr(message, 'contents'):
        return str(message)
        
    text_parts = []
    for content in message.contents:
        if hasattr(content, 'text') and hasattr(content, 'type') and content.type == 'text':
            text_parts.append(content.text)
            
    return ' '.join(text_parts)