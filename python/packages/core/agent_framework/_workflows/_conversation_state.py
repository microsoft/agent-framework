# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Iterable
from typing import Any, cast

from agent_framework import ChatMessage, Role

from ._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value

"""Utilities for serializing and deserializing chat conversations for persistence.

These helpers convert rich `ChatMessage` instances to checkpoint-friendly payloads
using the same encoding primitives as the workflow runner. This preserves
`additional_properties` and other metadata without relying on unsafe mechanisms
such as pickling.
"""


def encode_chat_messages(messages: Iterable[ChatMessage]) -> list[dict[str, Any]]:
    """Serialize chat messages into checkpoint-safe payloads."""
    encoded: list[dict[str, Any]] = []
    for message in messages:
        encoded.append({
            "role": encode_checkpoint_value(message.role),
            "contents": [encode_checkpoint_value(content) for content in message.contents],
            "author_name": message.author_name,
            "message_id": message.message_id,
            "additional_properties": {
                key: encode_checkpoint_value(value) for key, value in message.additional_properties.items()
            },
        })
    return encoded


def decode_chat_messages(payload: Iterable[dict[str, Any]]) -> list[ChatMessage]:
    """Restore chat messages from checkpoint-safe payloads."""
    restored: list[ChatMessage] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        role_value = decode_checkpoint_value(item.get("role"))
        if isinstance(role_value, Role):
            role = role_value
        elif isinstance(role_value, dict):
            role_dict = cast(dict[str, Any], role_value)
            role = Role.from_dict(role_dict)
        elif isinstance(role_value, str):
            role = Role(value=role_value)
        else:
            role = Role.ASSISTANT

        contents_field = item.get("contents", [])
        contents: list[Any] = []
        if isinstance(contents_field, list):
            contents_iter: list[Any] = contents_field  # type: ignore[assignment]
            for entry in contents_iter:
                decoded_entry: Any = decode_checkpoint_value(entry)
                contents.append(decoded_entry)

        additional_field = item.get("additional_properties", {})
        additional: dict[str, Any] = {}
        if isinstance(additional_field, dict):
            additional_dict = cast(dict[str, Any], additional_field)
            for key, value in additional_dict.items():
                additional[key] = decode_checkpoint_value(value)

        restored.append(
            ChatMessage(
                role=role,
                contents=contents,
                author_name=item.get("author_name"),
                message_id=item.get("message_id"),
                additional_properties=additional,
            )
        )
    return restored
