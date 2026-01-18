# Copyright (c) Microsoft. All rights reserved.

"""Shared orchestrator utilities for group chat patterns.

This module provides simple, reusable functions for common orchestration tasks.
No inheritance required - just import and call.
"""

import logging

from .._types import ChatMessage, Role

logger = logging.getLogger(__name__)


def clean_conversation_for_handoff(conversation: list[ChatMessage]) -> list[ChatMessage]:
    """Remove tool-related content from conversation for clean handoffs.

    During handoffs, tool calls can cause API errors because:
    1. Assistant messages with tool_calls must be followed by tool responses
    2. Tool response messages must follow an assistant message with tool_calls

    This creates a cleaned copy removing ALL tool-related content.

    Removes:
    - FunctionApprovalRequestContent and FunctionCallContent from assistant messages
    - Tool response messages (Role.TOOL)
    - Messages with only tool calls and no text

    Preserves:
    - User messages
    - Assistant messages with text content

    Args:
        conversation: Original conversation with potential tool content

    Returns:
        Cleaned conversation safe for handoff routing
    """
    cleaned: list[ChatMessage] = []
    for msg in conversation:
        # Skip tool response messages entirely
        if msg.role == Role.TOOL:
            continue

        # Check for tool-related content
        has_tool_content = False
        if msg.contents:
            has_tool_content = any(
                content.type in ("function_approval_request", "function_call") for content in msg.contents
            )

        # If no tool content, keep original
        if not has_tool_content:
            cleaned.append(msg)
            continue

        # Has tool content - only keep if it also has text
        if msg.text and msg.text.strip():
            # Create fresh text-only message while preserving additional_properties
            msg_copy = ChatMessage(
                role=msg.role,
                text=msg.text,
                author_name=msg.author_name,
                additional_properties=dict(msg.additional_properties) if msg.additional_properties else None,
            )
            cleaned.append(msg_copy)

    return cleaned


def create_completion_message(
    *,
    text: str | None = None,
    author_name: str,
    reason: str = "completed",
) -> ChatMessage:
    """Create a standardized completion message.

    Simple helper to avoid duplicating completion message creation.

    Args:
        text: Message text, or None to generate default
        author_name: Author/orchestrator name
        reason: Reason for completion (for default text generation)

    Returns:
        ChatMessage with ASSISTANT role
    """
    message_text = text or f"Conversation {reason}."
    return ChatMessage(
        role=Role.ASSISTANT,
        text=message_text,
        author_name=author_name,
    )
