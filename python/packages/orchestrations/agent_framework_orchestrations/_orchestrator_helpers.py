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


_FENCE_MARKER = "```"


def _backtick_run_end(text: str, start: int) -> int:
    """Return the index just past the run of backticks that begins at ``start``."""
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


def _fence_info_string_end(text: str, start: int) -> int:
    """Return the index just past the info string of an opening fence such as ``json`` or ``application/json``.

    An info string has to start with a letter, so a same-line body such as ``{"a": 1}`` that
    follows the fence directly is left in place.
    """
    index = start
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text) or not text[index].isalpha():
        return start
    while index < len(text) and (text[index].isalnum() or text[index] in "_-+./"):
        index += 1
    return index


def extract_markdown_fence_bodies(text: str) -> list[str]:
    """Return the stripped bodies of the Markdown code fences in ``text``, in source order.

    Model output that ignores ``response_format`` often wraps JSON in a fence. An opening fence
    is a run of three or more backticks followed by an optional info string. The closing fence
    is the next run that is at least as long and ends its line, so backticks inside a JSON
    string value (which always end in a quote on the same line) never close the block, and an
    outer fence can use more backticks than the ones inside it. A fence that is never closed
    yields nothing.

    The scan advances through ``text`` without backtracking, so it stays linear in the input
    length for malformed output such as an unterminated fence followed by whitespace.
    """
    bodies: list[str] = []
    length = len(text)
    open_start = text.find(_FENCE_MARKER)
    while open_start != -1:
        open_end = _backtick_run_end(text, open_start)
        closing_marker = text[open_start:open_end]
        body_start = _fence_info_string_end(text, open_end)

        search_from = body_start
        close_start = close_end = -1
        while (run_start := text.find(closing_marker, search_from)) != -1:
            run_end = _backtick_run_end(text, run_start)
            line_end = run_end
            while line_end < length and text[line_end] in " \t\r":
                line_end += 1
            if line_end == length or text[line_end] == "\n":
                close_start, close_end = run_start, run_end
                break
            search_from = line_end
        if close_start == -1:
            break

        body = text[body_start:close_start].strip()
        if body:
            bodies.append(body)
        open_start = text.find(_FENCE_MARKER, close_end)
    return bodies
