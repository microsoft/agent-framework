# type: ignore

from tau2.environment.tool import Tool
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ToolMessage,
    ToolCall,
)
from agent_framework._tools import AIFunction
from agent_framework import ChatMessage


def convert_tau2_tool_to_ai_function(tau2_tool: Tool) -> AIFunction:
    """Convert a tau2 Tool to an AIFunction using its existing params BaseModel."""

    # Create a wrapper function that calls the tau2 tool
    def wrapped_func(**kwargs):
        return tau2_tool(**kwargs)

    # Use the existing params BaseModel from tau2 tool
    return AIFunction(
        name=tau2_tool.name,
        description=tau2_tool._get_description(),
        func=wrapped_func,
        input_model=tau2_tool.params,
    )


def convert_agent_framework_messages_to_tau2_messages(messages: list[ChatMessage]) -> list[APICompatibleMessage]:
    """Convert agent framework ChatMessages to tau2 APICompatibleMessage objects."""

    tau2_messages = []

    for msg in messages:
        role_str = str(msg.role)  # Convert Role to string

        # Extract text content
        text_content = None
        text_contents = [c for c in msg.contents if hasattr(c, "text") and hasattr(c, "type") and c.type == "text"]
        if text_contents:
            text_content = " ".join(c.text for c in text_contents)

        # Extract function calls
        function_calls = [c for c in msg.contents if hasattr(c, "type") and c.type == "function_call"]
        tool_calls = None
        if function_calls:
            tool_calls = []
            for fc in function_calls:
                # Parse arguments
                arguments = fc.parse_arguments() or {}
                tool_call = ToolCall(
                    id=fc.call_id,
                    name=fc.name,
                    arguments=arguments,
                    requestor="assistant" if role_str == "assistant" else "user",
                )
                tool_calls.append(tool_call)

        # Extract function results - these become separate ToolMessage instances
        function_results = [c for c in msg.contents if hasattr(c, "type") and c.type == "function_result"]

        # Create the main message (system, user, or assistant)
        if role_str == "system":
            tau2_messages.append(SystemMessage(role="system", content=text_content))
        elif role_str == "user":
            tau2_messages.append(UserMessage(role="user", content=text_content, tool_calls=tool_calls))
        elif role_str == "assistant":
            tau2_messages.append(AssistantMessage(role="assistant", content=text_content, tool_calls=tool_calls))
        elif role_str == "tool":
            # Tool role messages in agent framework should be handled as function results
            # Skip creating a participant message for these, they'll be handled below
            pass

        # Handle function results as separate ToolMessage instances
        for fr in function_results:
            tool_msg = ToolMessage(
                id=fr.call_id,
                role="tool",
                content=str(fr.result) if fr.result is not None else None,
                requestor="assistant",  # Most tool calls come from assistant
                error=fr.exception is not None,
            )
            tau2_messages.append(tool_msg)

    return tau2_messages
