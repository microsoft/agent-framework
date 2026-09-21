# Copyright (c) Microsoft. All rights reserved.

"""Shared orchestrator utilities for group chat patterns.

This module provides simple, reusable functions for common orchestration tasks.
No inheritance required - just import and call.
"""

import logging

from agent_framework._types import Message

logger = logging.getLogger(__name__)


# Semantic content types that carry real user input and must survive handoff routing.
# Everything else (function calls, function results, approval payloads, tool outputs)
# is runtime-only tool-control state that providers reject when replayed.
_USER_SEMANTIC_CONTENT_TYPES: frozenset[str] = frozenset({"text", "data", "uri", "hosted_file", "hosted_vector_store"})


def clean_conversation_for_handoff(conversation: list[Message]) -> list[Message]:
    """Clean the conversation history for handoff routing.

    Handoff executors must not replay prior tool-control artifacts (function calls,
    tool outputs, approval payloads) into future model turns, or providers may reject
    the next request due to unmatched tool-call state. At the same time, genuine user
    input such as images or files must be preserved so the receiving agent keeps the
    full context of the request.

    This helper builds a cleaned copy of the conversation:
    - Keeps text content on every message.
    - Additionally keeps semantic multimodal content (data, uri, hosted_file,
      hosted_vector_store) on user messages.
    - Keeps assistant and other non-user messages text-only, because providers treat
      multimodal parts as input-only and reject them when replayed on assistant turns.
    - Drops tool-control payloads (function_call, function_result, approval payloads, etc.).
    - Drops messages with no remaining content.
    - Preserves original roles and author names for retained messages.

    Args:
        conversation: Full conversation history, including tool-control content
    Returns:
        Cleaned conversation history suitable for handoff routing, with semantic
        multimodal content preserved on user messages.
    """
    cleaned: list[Message] = []
    for msg in conversation:
        # Tool-control content (function_call/function_result/approval payloads) is
        # runtime-only and must not be replayed in future model turns.
        allowed_types = _USER_SEMANTIC_CONTENT_TYPES if str(msg.role).lower() == "user" else frozenset({"text"})
        retained = [
            content
            for content in msg.contents
            if content.type in allowed_types and (content.type != "text" or content.text)
        ]
        if not retained:
            continue

        msg_copy = Message(
            role=msg.role,
            contents=retained,
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
