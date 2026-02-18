# Copyright (c) Microsoft. All rights reserved.

"""Shared helpers for normalizing workflow message inputs."""

from agent_framework import Content, Message
from agent_framework._types import AgentRunInputs


def normalize_messages_input(
    messages: AgentRunInputs | None = None,
) -> list[Message]:
    """Normalize heterogeneous message inputs to a list of Message objects.

    Args:
        messages: String, Content, Message, or sequence of those values. None yields empty list.

    Returns:
        List of Message instances suitable for workflow consumption.
    """
    if messages is None:
        return []

    if isinstance(messages, str):
        return [Message(role="user", text=messages)]

    if isinstance(messages, Content):
        return [Message(role="user", contents=[messages])]

    if isinstance(messages, Message):
        return [messages]

    normalized: list[Message] = []
    for item in messages:
        if isinstance(item, str):
            normalized.append(Message(role="user", text=item))
        elif isinstance(item, Content):
            normalized.append(Message(role="user", contents=[item]))
        elif isinstance(item, Message):
            normalized.append(item)
        else:
            raise TypeError(
                f"Messages sequence must contain only str, Content, or Message instances; found {type(item).__name__}."
            )
    return normalized
