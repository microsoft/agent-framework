# Copyright (c) Microsoft. All rights reserved.

"""Message format conversion between AG-UI and Agent Framework."""

from typing import Any, cast

from agent_framework import (
    ChatMessage,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
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
        # Handle standard tool result messages early (role="tool") to preserve provider invariants
        # This path maps AG‑UI tool messages to FunctionResultContent with the correct tool_call_id
        role_str = msg.get("role", "user")
        if role_str == "tool":
            # Prefer explicit tool_call_id fields; fall back to backend fields only if necessary
            tool_call_id = msg.get("tool_call_id") or msg.get("toolCallId")

            # If no explicit tool_call_id, treat as backend tool rendering payloads where
            # AG‑UI may send actionExecutionId/actionName. This must still map to the
            # assistant's tool call id to satisfy provider requirements.
            if not tool_call_id:
                tool_call_id = msg.get("actionExecutionId") or ""

            # Extract raw content text
            result_content = msg.get("content")
            if result_content is None:
                result_content = msg.get("result", "")

            # Distinguish approval payloads from actual tool results
            is_approval = False
            if isinstance(result_content, str) and result_content:
                import json as _json

                try:
                    parsed = _json.loads(result_content)
                    is_approval = isinstance(parsed, dict) and "accepted" in parsed
                except Exception:
                    is_approval = False

            if is_approval:
                # Approval responses should be treated as user messages to trigger human-in-the-loop flow
                chat_msg = ChatMessage(
                    role=Role.USER,
                    contents=[TextContent(text=str(result_content))],
                    additional_properties={"is_tool_result": True, "tool_call_id": str(tool_call_id or "")},
                )
                if "id" in msg:
                    chat_msg.message_id = msg["id"]
                result.append(chat_msg)
                continue

            chat_msg = ChatMessage(
                role=Role.TOOL,
                contents=[FunctionResultContent(call_id=str(tool_call_id), result=result_content)],
            )
            if "id" in msg:
                chat_msg.message_id = msg["id"]
            result.append(chat_msg)
            continue

        # Backend tool rendering payloads without an explicit role
        # Prefer standard tool mapping above; this block only covers legacy/minimal payloads
        if "actionExecutionId" in msg or "actionName" in msg:
            # Prefer toolCallId if present; otherwise fall back to actionExecutionId
            tool_call_id = msg.get("toolCallId") or msg.get("tool_call_id") or msg.get("actionExecutionId", "")
            result_content = msg.get("result", msg.get("content", ""))

            chat_msg = ChatMessage(
                role=Role.TOOL,
                contents=[FunctionResultContent(call_id=str(tool_call_id), result=result_content)],
            )
            if "id" in msg:
                chat_msg.message_id = msg["id"]
            result.append(chat_msg)
            continue

        # If assistant message includes tool calls, convert to FunctionCallContent(s)
        tool_calls = msg.get("tool_calls") or msg.get("toolCalls")
        if tool_calls:
            contents: list[Any] = []
            # Include any assistant text content if present
            content_text = msg.get("content")
            if isinstance(content_text, str) and content_text:
                contents.append(TextContent(text=content_text))
            # Convert each tool call entry
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                # Cast to typed dict for proper type inference
                tc_dict = cast(dict[str, Any], tc)
                tc_type = tc_dict.get("type")
                if tc_type == "function":
                    func_data = tc_dict.get("function", {})
                    func_dict = cast(dict[str, Any], func_data) if isinstance(func_data, dict) else {}

                    call_id = str(tc_dict.get("id", ""))
                    name = str(func_dict.get("name", ""))
                    arguments = func_dict.get("arguments")

                    contents.append(
                        FunctionCallContent(
                            call_id=call_id,
                            name=name,
                            arguments=arguments,
                        )
                    )
            chat_msg = ChatMessage(role=Role.ASSISTANT, contents=contents)
            if "id" in msg:
                chat_msg.message_id = msg["id"]
            result.append(chat_msg)
            continue

        # No special handling required for assistant/plain messages here

        role = _AGUI_TO_FRAMEWORK_ROLE.get(role_str, Role.USER)

        # Check if this message contains function approvals
        if "function_approvals" in msg and msg["function_approvals"]:
            # Convert function approvals to FunctionApprovalResponseContent
            approval_contents: list[Any] = []
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
                approval_contents.append(approval_response)

            chat_msg = ChatMessage(role=role, contents=approval_contents)  # type: ignore[arg-type]
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


def agent_framework_messages_to_agui(messages: list[ChatMessage] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Agent Framework messages to AG-UI format.

    Args:
        messages: List of Agent Framework ChatMessage objects or AG-UI dicts (already converted)

    Returns:
        List of AG-UI message dictionaries
    """
    from ._utils import generate_event_id

    result: list[dict[str, Any]] = []
    for msg in messages:
        # If already a dict (AG-UI format), ensure it has an ID and normalize keys for Pydantic
        if isinstance(msg, dict):
            # Always work on a copy to avoid mutating input
            normalized_msg = msg.copy()
            # Ensure ID exists
            if "id" not in normalized_msg:
                normalized_msg["id"] = generate_event_id()
            # Normalize tool_call_id to toolCallId for Pydantic's alias_generator=to_camel
            if normalized_msg.get("role") == "tool":
                if "tool_call_id" in normalized_msg:
                    normalized_msg["toolCallId"] = normalized_msg["tool_call_id"]
                    del normalized_msg["tool_call_id"]
                elif "toolCallId" not in normalized_msg:
                    # Tool message missing toolCallId - add empty string to satisfy schema
                    normalized_msg["toolCallId"] = ""
            # Always append the normalized copy, not the original
            result.append(normalized_msg)
            continue

        # Convert ChatMessage to AG-UI format
        role = _FRAMEWORK_TO_AGUI_ROLE.get(msg.role, "user")

        content_text = ""
        tool_calls: list[dict[str, Any]] = []
        tool_result_call_id: str | None = None

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
            elif isinstance(content, FunctionResultContent):
                # Tool result content - extract call_id and result
                tool_result_call_id = content.call_id
                # Serialize result to string
                if isinstance(content.result, dict):
                    import json

                    content_text = json.dumps(content.result)  # type: ignore
                elif content.result is not None:
                    content_text = str(content.result)

        agui_msg: dict[str, Any] = {
            "id": msg.message_id if msg.message_id else generate_event_id(),  # Always include id
            "role": role,
            "content": content_text,
        }

        if tool_calls:
            agui_msg["tool_calls"] = tool_calls

        # If this is a tool result message, add toolCallId (using camelCase for Pydantic)
        if tool_result_call_id:
            agui_msg["toolCallId"] = tool_result_call_id
            # Tool result messages should have role="tool"
            agui_msg["role"] = "tool"

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
