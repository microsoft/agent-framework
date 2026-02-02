# Copyright (c) Microsoft. All rights reserved.

"""Helpers for managing chat conversation history.

These utilities operate on standard `list[ChatMessage]` collections and simple
dictionary snapshots so orchestrators can share logic without new mixins.
"""

from collections.abc import Sequence

from .._types import ChatMessage


def latest_user_message(conversation: Sequence[ChatMessage]) -> ChatMessage:
    """Return the most recent user-authored message from `conversation`."""
    for message in reversed(conversation):
        role_value = getattr(message.role, "value", message.role)
        if str(role_value).lower() == "user":
            return message
    raise ValueError("No user message in conversation")


def ensure_author(message: ChatMessage, fallback: str) -> ChatMessage:
    """Attach `fallback` author if message is missing `author_name`."""
    message.author_name = message.author_name or fallback
    return message
