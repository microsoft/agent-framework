# Copyright (c) Microsoft. All rights reserved.

"""Message format conversion between AG-UI and Agent Framework."""

from typing import Any

from agent_framework import (
    ChatMessage,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    Role,
    TextContent,
)

# Role mapping constants
_AGUI_TO_FRAMEWORK_ROLE = {
    "user": Role.USER,
    "assistant": Role.ASSISTANT,
    "system": Role.SYSTEM,
}

_FRAMEWORK_TO_AGUI_ROLE = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "system",
}


def agui_messages_to_agent_framework(messages: list[dict[str, Any]]) -> list[ChatMessage]:
    """Convert AG-UI messages to Agent Framework format.

    Args:
        messages: List of AG-UI messages

    Returns:
        List of Agent Framework ChatMessage objects
    """
    result: list[ChatMessage] = []
    for msg in messages:
        # Check for backend tool rendering results FIRST (may not have role field)
        if "actionExecutionId" in msg or "actionName" in msg:
            # Backend tool rendering - convert to FunctionResultContent
            from agent_framework import FunctionResultContent

            tool_call_id = msg.get("actionExecutionId", "")
            result_content = msg.get("result", msg.get("content", ""))

            chat_msg = ChatMessage(
                role=Role.ASSISTANT,  # Tool results are assistant messages
                contents=[FunctionResultContent(call_id=tool_call_id, result=result_content)],
            )

            if "id" in msg:
                chat_msg.message_id = msg["id"]

            result.append(chat_msg)
            continue

        role_str = msg.get("role", "user")

        # Handle tool result messages (with role="tool")
        if role_str == "tool":
            # Check if this is a standard tool result (has tool_call_id or toolCallId)
            tool_call_id = msg.get("tool_call_id") or msg.get("toolCallId")
            result_content = msg.get("content", "")

            # Distinguish between backend tool results and approval responses
            # Approval responses have {"accepted": ...} structure
            is_approval = False
            if result_content:
                import json

                try:
                    parsed_content = json.loads(result_content)
                    is_approval = "accepted" in parsed_content
                except (json.JSONDecodeError, TypeError):
                    is_approval = False

            # Backend tool results have non-empty content WITHOUT "accepted" field
            if tool_call_id and result_content and not is_approval:
                # Backend tool execution - convert to FunctionResultContent
                from agent_framework import FunctionResultContent

                chat_msg = ChatMessage(
                    role=Role.ASSISTANT,  # Tool results are assistant messages
                    contents=[FunctionResultContent(call_id=tool_call_id, result=result_content)],
                )

                if "id" in msg:
                    chat_msg.message_id = msg["id"]

                result.append(chat_msg)
                continue
            else:
                # Human-in-the-loop approval response - mark for special handling
                content = msg.get("content", "")
                chat_msg = ChatMessage(
                    role=Role.USER,  # Approval responses are user messages
                    contents=[TextContent(text=content)],
                )
                # Mark this as a tool result so we can detect it later
                chat_msg.metadata = {"is_tool_result": True, "tool_call_id": msg.get("toolCallId", "")}  # type: ignore[attr-defined]

                if "id" in msg:
                    chat_msg.message_id = msg["id"]

                result.append(chat_msg)
                continue

        role = _AGUI_TO_FRAMEWORK_ROLE.get(role_str, Role.USER)

        # Check if this message contains function approvals
        if "function_approvals" in msg and msg["function_approvals"]:
            # Convert function approvals to FunctionApprovalResponseContent
            contents: list[Any] = []
            for approval in msg["function_approvals"]:
                # Create FunctionCallContent with the modified arguments
                func_call = FunctionCallContent(
                    call_id=approval.get("call_id", ""),
                    name=approval.get("name", ""),
                    arguments=approval.get("arguments", {}),
                )

                # Create the approval response
                approval_response = FunctionApprovalResponseContent(
                    approved=approval.get("approved", True),
                    id=approval.get("id", ""),
                    function_call=func_call,
                )
                contents.append(approval_response)

            chat_msg = ChatMessage(role=role, contents=contents)  # type: ignore[arg-type]
        else:
            # Regular text message
            content = msg.get("content", "")
            if isinstance(content, str):
                chat_msg = ChatMessage(role=role, contents=[TextContent(text=content)])
            else:
                chat_msg = ChatMessage(role=role, contents=[TextContent(text=str(content))])

        if "id" in msg:
            chat_msg.message_id = msg["id"]

        result.append(chat_msg)

    return result


def agent_framework_messages_to_agui(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Convert Agent Framework messages to AG-UI format.

    Args:
        messages: List of Agent Framework ChatMessage objects

    Returns:
        List of AG-UI message dictionaries
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = _FRAMEWORK_TO_AGUI_ROLE.get(msg.role, "user")

        content_text = ""
        tool_calls: list[dict[str, Any]] = []

        for content in msg.contents:
            if isinstance(content, TextContent):
                content_text += content.text
            elif isinstance(content, FunctionCallContent):
                tool_calls.append(
                    {
                        "id": content.call_id,
                        "type": "function",
                        "function": {
                            "name": content.name,
                            "arguments": content.arguments,
                        },
                    }
                )

        agui_msg: dict[str, Any] = {
            "role": role,
            "content": content_text,
        }

        if msg.message_id:
            agui_msg["id"] = msg.message_id

        if tool_calls:
            agui_msg["tool_calls"] = tool_calls

        result.append(agui_msg)

    return result


def extract_text_from_contents(contents: list[Any]) -> str:
    """Extract text from Agent Framework contents.

    Args:
        contents: List of content objects

    Returns:
        Concatenated text
    """
    text_parts: list[str] = []
    for content in contents:
        if isinstance(content, TextContent):
            text_parts.append(content.text)
        elif hasattr(content, "text"):
            text_parts.append(content.text)
    return "".join(text_parts)


__all__ = [
    "agui_messages_to_agent_framework",
    "agent_framework_messages_to_agui",
    "extract_text_from_contents",
]
