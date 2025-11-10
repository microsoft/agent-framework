# Copyright (c) Microsoft. All rights reserved.

"""Shared helpers for normalizing workflow message inputs."""

from collections.abc import Sequence

from agent_framework import ChatMessage, Role


def normalize_messages_input(
    messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
) -> list[ChatMessage]:
    """Normalize heterogeneous message inputs to a list of ChatMessage objects.

    Args:
        messages: String, ChatMessage, or sequence of either. None yields empty list.

    Returns:
        List of ChatMessage instances suitable for workflow consumption.
    """
    if messages is None:
        return []

    if isinstance(messages, str):
        return [ChatMessage(role=Role.USER, text=messages)]

    if isinstance(messages, ChatMessage):
        return [messages]

    normalized: list[ChatMessage] = []
    for item in messages:
        if isinstance(item, str):
            normalized.append(ChatMessage(role=Role.USER, text=item))
        elif isinstance(item, ChatMessage):
            normalized.append(item)
        else:
            raise TypeError(
                f"Messages sequence must contain only str or ChatMessage instances; found {type(item).__name__}."
            )
    return normalized


__all__ = ["normalize_messages_input"]
