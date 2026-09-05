# Copyright (c) Microsoft. All rights reserved.

"""Shared orchestrator utilities for group chat patterns.

This module provides simple, reusable functions for common orchestration tasks.
No inheritance required - just import and call.
"""

import logging

from agent_framework._types import Message

logger = logging.getLogger(__name__)


def clean_conversation_for_handoff(conversation: list[Message]) -> list[Message]:
    """Clean conversation history for handoff routing.

    Handoff executors must not replay prior tool-control artifacts (function calls,
    tool outputs, approval payloads) into future model turns, or providers may reject
    the next request due to unmatched tool-call state.

    This helper preserves semantic content:
    - For `user` messages, preserves text and multimodal content (data, uri, hosted_file, hosted_vector_store).
    - For non-user messages (assistant, system, etc.), preserves only text content to avoid serializing input-only
      multimodal parts into assistant roles on model providers.
    - Drops tool-control payloads (function_call, function_result, approval payloads, etc.).
    - Drops messages with no remaining content.
    - Preserves original roles, author names, and additional properties for retained messages.

    Args:
        conversation: Full conversation history, including tool-control content

    Returns:
        Cleaned conversation history with semantic multimodal content preserved for user messages,
        suitable for handoff routing.
    """
    USER_ALLOWED_CONTENT_TYPES = {
        "text",
        "data",
        "uri",
        "hosted_file",
        "hosted_vector_store",
    }

    cleaned: list[Message] = []
    for msg in conversation:
        is_user = msg.role == "user" or str(msg.role).lower() == "user"
        allowed_types = USER_ALLOWED_CONTENT_TYPES if is_user else {"text"}

        retained_contents = []
        for content in msg.contents:
            ctype = getattr(content, "type", "text")

            # Skip disallowed types
            if ctype not in allowed_types:
                continue

            # Skip empty text parts
            if ctype == "text" and not getattr(content, "text", None):
                continue

            retained_contents.append(content)

        if not retained_contents:
            continue

        msg_copy = Message(
            role=msg.role,
            contents=retained_contents,
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
) -> Message:
    """Create a standardized completion message.

    Simple helper to avoid duplicating completion message creation.

    Args:
        text: Message text, or None to generate default
        author_name: Author/orchestrator name
        reason: Reason for completion (for default text generation)

    Returns:
        Message with assistant role
    """
    message_text = text or f"Conversation {reason}."
    return Message(
        role="assistant",
        contents=[message_text],
        author_name=author_name,
    )
