# Copyright (c) Microsoft. All rights reserved.

"""Shared helpers for normalizing workflow message inputs."""

from collections.abc import Sequence

from agent_framework import Message


def normalize_messages_input(
    messages: str | Message | Sequence[str | Message] | None = None,
) -> list[Message]:
    """Normalize heterogeneous message inputs to a list of Message objects.

    Args:
        messages: String, Message, or sequence of either. None yields empty list.

    Returns:
        List of Message instances suitable for workflow consumption.
    """
    if messages is None:
        return []

    if isinstance(messages, str):
        return [Message(role="user", text=messages)]

    if isinstance(messages, Message):
        return [messages]

    normalized: list[Message] = []
    for item in messages:
        if isinstance(item, str):
            normalized.append(Message(role="user", text=item))
        elif isinstance(item, Message):
            normalized.append(item)
        else:
            raise TypeError(
                f"Messages sequence must contain only str or Message instances; found {type(item).__name__}."
            )
    return normalized


__all__ = ["normalize_messages_input"]
