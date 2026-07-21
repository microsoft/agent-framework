# Copyright (c) Microsoft. All rights reserved.

"""Conversion between native A2A values and Agent Framework run values."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Sequence
from typing import Any, cast

from a2a.types import Message as A2AMessage
from a2a.types import Part
from agent_framework import AgentResponse, AgentResponseUpdate, ChatOptions, Content, Message
from agent_framework_hosting import AgentRunArgs
from google.protobuf.json_format import MessageToDict

logger = logging.getLogger("agent_framework.hosting.a2a")


def a2a_to_run(message: A2AMessage, *, stream: bool = False) -> AgentRunArgs:
    """Convert an A2A message into Agent Framework run arguments.

    A2A text, URL, raw-byte, and structured-data parts become Agent Framework
    content. The helper does not create sessions, inspect task stores, or
    interact with an A2A request handler.

    Args:
        message: Native A2A message to convert.

    Keyword Args:
        stream: Whether the caller intends to run the agent in streaming mode.

    Returns:
        Arguments corresponding to ``Agent.run(...)``.

    Raises:
        ValueError: If the message has no supported content parts.
    """
    contents: list[Content] = []
    for part in message.parts:
        metadata = MessageToDict(part.metadata) if part.metadata else None
        match part.WhichOneof("content"):
            case "text":
                contents.append(
                    Content.from_text(
                        text=part.text,
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case "url":
                contents.append(
                    Content.from_uri(
                        uri=part.url,
                        media_type=part.media_type or None,
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case "raw":
                contents.append(
                    Content.from_data(
                        data=part.raw,
                        media_type=part.media_type or "application/octet-stream",
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case "data":
                contents.append(
                    Content.from_text(
                        text=json.dumps(MessageToDict(part.data), separators=(",", ":"), sort_keys=True),
                        additional_properties=metadata,
                        raw_representation=part,
                    )
                )
            case unsupported:
                logger.warning("A2A message part type %s is not supported and was omitted.", unsupported)

    if not contents:
        raise ValueError("A2A message has no supported text, URL, raw, or data parts to convert to a run.")

    return AgentRunArgs(
        messages=[
            Message(
                "user",
                contents,
                message_id=message.message_id or None,
                additional_properties={"a2a_metadata": MessageToDict(message.metadata)} if message.metadata else None,
                raw_representation=message,
            )
        ],
        options=cast("ChatOptions[Any]", {}),
        stream=stream,
    )


def a2a_from_run(result: AgentResponse[Any] | Message | AgentResponseUpdate) -> list[Part]:
    """Convert Agent Framework output into native A2A parts.

    ``AgentResponse`` values are flattened in message order. User-role
    messages are omitted. Text, external URI, and inline data content become
    the corresponding native A2A part types. Content-level metadata is
    preserved on each part. The caller remains responsible for grouping parts
    into A2A messages or artifacts, including message boundaries and metadata,
    and publishing them through ``TaskUpdater`` or an event queue.

    Args:
        result: A completed response, response message, or streaming update.

    Returns:
        Native A2A parts ready for an A2A SDK message or artifact.

    Raises:
        ValueError: If Agent Framework data content contains an invalid data URI.
    """
    items: Sequence[Message | AgentResponseUpdate] = result.messages if isinstance(result, AgentResponse) else [result]

    parts: list[Part] = []
    for item in items:
        if item.role == "user":
            continue
        for content in item.contents:
            metadata = content.additional_properties or {}
            match content.type:
                case "text" if content.text is not None:
                    parts.append(Part(text=content.text, metadata=metadata))
                case "uri" if content.uri is not None:
                    parts.append(
                        Part(
                            url=content.uri,
                            media_type=content.media_type or "",
                            metadata=metadata,
                        )
                    )
                case "data" if content.uri is not None:
                    prefix, separator, encoded = content.uri.partition(",")
                    if not separator or not prefix.startswith("data:") or ";base64" not in prefix:
                        raise ValueError("Agent Framework data content must contain a base64 data URI.")
                    try:
                        raw = base64.b64decode(encoded, validate=True)
                    except ValueError as exc:
                        raise ValueError("Agent Framework data content contains invalid base64 data.") from exc
                    parts.append(
                        Part(
                            raw=raw,
                            media_type=content.media_type or "",
                            metadata=metadata,
                        )
                    )
                case _:
                    logger.warning(
                        "Agent Framework content type %s is not supported by A2A and was omitted.",
                        content.type,
                    )
    return parts
