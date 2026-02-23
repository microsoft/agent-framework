# Copyright (c) Microsoft. All rights reserved.

"""Shared orchestrator utilities for group chat patterns.

This module provides simple, reusable functions for common orchestration tasks.
No inheritance required - just import and call.
"""

import logging

from agent_framework._types import Message

logger = logging.getLogger(__name__)


def clean_conversation_for_handoff(conversation: list[Message]) -> list[Message]:
    """Keep only plain text chat history for handoff routing.

    Handoff executors must not replay prior tool-control artifacts (function calls,
    tool outputs, approval payloads) into future model turns, or providers may reject
    the next request due to unmatched tool-call state.

    This helper builds a text-only copy of the conversation:
    - Drops all non-text content from every message.
    - Drops messages with no remaining text content.
    - Preserves original roles and author names for retained text messages.
    """
    cleaned: list[Message] = []
    for msg in conversation:
        # Keep only plain text history for handoff routing. Tool-control content
        # (function_call/function_result/approval payloads) is runtime-only and
        # must not be replayed in future model turns.
        text_parts = [content.text for content in msg.contents if content.type == "text" and content.text]
        if not text_parts:
            continue

        msg_copy = Message(
            role=msg.role,
            text=" ".join(text_parts),
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
        text=message_text,
        author_name=author_name,
    )
