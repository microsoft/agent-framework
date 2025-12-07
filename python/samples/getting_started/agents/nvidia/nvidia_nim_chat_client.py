# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from collections.abc import Sequence

from agent_framework.openai import OpenAIChatClient
from agent_framework._types import (
    ChatMessage, 
    Contents, 
    TextContent,
    Role,
    FunctionCallContent,
    FunctionResultContent,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    prepare_function_call_results,
)


class NVIDIANIMChatClient(OpenAIChatClient):
    """Custom OpenAI Chat Client for NVIDIA NIM models.
    
    NVIDIA NIM models expect the 'content' field in messages to be a simple string,
    not an array of content objects like standard OpenAI API. This client handles
    the conversion from the agent framework's content format to NVIDIA NIM's expected format.
    """
    
    def _openai_chat_message_parser(self, message: ChatMessage) -> list[dict[str, Any]]:
        """Parse a chat message into the NVIDIA NIM format.
        
        NVIDIA NIM expects:
        - content: string (not array of objects)
        - role: string
        """
        all_messages: list[dict[str, Any]] = []
        
        for content in message.contents:
            # Skip approval content - it's internal framework state, not for the LLM
            if isinstance(content, (FunctionApprovalRequestContent, FunctionApprovalResponseContent)):
                continue

            args: dict[str, Any] = {
                "role": message.role.value if isinstance(message.role, Role) else message.role,
            }
            
            if message.additional_properties:
                args["metadata"] = message.additional_properties
                
            if isinstance(content, FunctionCallContent):
                if all_messages and "tool_calls" in all_messages[-1]:
                    # If the last message already has tool calls, append to it
                    all_messages[-1]["tool_calls"].append(self._openai_content_parser(content))
                else:
                    args["tool_calls"] = [self._openai_content_parser(content)]  # type: ignore
            elif isinstance(content, FunctionResultContent):
                args["tool_call_id"] = content.call_id
                if content.result is not None:
                    args["content"] = prepare_function_call_results(content.result)
                elif content.exception is not None:
                    # Send the exception message to the model
                    args["content"] = "Error: " + str(content.exception)
            elif isinstance(content, TextContent):
                # For NVIDIA NIM, content should be a simple string, not an array
                if "content" not in args:
                    args["content"] = content.text
                else:
                    # If there's already content, append to it
                    args["content"] += content.text
            else:
                # For other content types, convert to string representation
                if "content" not in args:
                    args["content"] = str(content)
                else:
                    args["content"] += str(content)
                        
            if "content" in args or "tool_calls" in args:
                all_messages.append(args)
                
        return all_messages
