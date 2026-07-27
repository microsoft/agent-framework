# Copyright (c) Microsoft. All rights reserved.

"""Conversion between native MCP values and Agent Framework run values."""

from __future__ import annotations

import base64
import logging
from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast

from agent_framework import AgentResponse, ChatOptions, Content, Message
from agent_framework_hosting import AgentRunArgs
from mcp import types

logger = logging.getLogger("agent_framework.hosting.mcp")


def mcp_to_run(
    arguments: Mapping[str, Any] | None,
    *,
    argument_name: str = "task",
    chat_option_arguments: Collection[str] = (),
) -> AgentRunArgs:
    """Convert native MCP tool arguments into Agent Framework run arguments.

    The application owns the MCP tool schema and chooses which string argument
    contains the user request. This helper does not create sessions, inspect
    request context, or interact with an MCP server.

    Args:
        arguments: Arguments supplied to an MCP ``call_tool`` handler.

    Keyword Args:
        argument_name: Name of the required string argument containing the user request.
        chat_option_arguments: MCP argument names to copy into Agent Framework chat options when present.

    Returns:
        Arguments corresponding to ``Agent.run(...)``.

    Raises:
        ValueError: If the selected argument is missing or is not a string.
    """
    if arguments is None or argument_name not in arguments:
        raise ValueError(f"MCP tool arguments must include a '{argument_name}' string.")

    message_value = arguments[argument_name]
    if not isinstance(message_value, str):
        raise ValueError(f"MCP tool argument '{argument_name}' must be a string.")

    options = {name: arguments[name] for name in chat_option_arguments if name in arguments}
    return AgentRunArgs(
        messages=[
            Message(
                "user",
                [Content.from_text(message_value)],
                raw_representation=dict(arguments),
            )
        ],
        options=cast("ChatOptions[Any]", options),
        stream=False,
    )


def mcp_from_run(
    result: AgentResponse[Any] | Message,
) -> list[types.ContentBlock]:
    """Convert Agent Framework output into native MCP content blocks.

    ``AgentResponse`` values are flattened in message order. User-role
    messages are omitted. Text, external URI, and inline data content become
    the corresponding native MCP content block types. Content-level metadata
    is preserved in each block's ``_meta`` field.

    Args:
        result: A completed response or response message.

    Returns:
        Native MCP content blocks ready for a ``CallToolResult``.

    Raises:
        ValueError: If Agent Framework data content contains an invalid data URI.
    """
    items: Sequence[Message] = result.messages if isinstance(result, AgentResponse) else [result]

    blocks: list[types.ContentBlock] = []
    for item in items:
        if item.role == "user":
            continue
        for content in item.contents:
            metadata = content.additional_properties or None
            match content.type:
                case "text" if content.text is not None:
                    blocks.append(types.TextContent(type="text", text=content.text, _meta=metadata))
                case "uri" if content.uri is not None:
                    name = content.uri.rsplit("/", maxsplit=1)[-1] or content.uri
                    blocks.append(
                        types.ResourceLink(
                            type="resource_link",
                            name=name,
                            uri=content.uri,  # pyright: ignore[reportArgumentType]
                            mimeType=content.media_type,
                            _meta=metadata,
                        )
                    )
                case "data" if content.uri is not None:
                    prefix, separator, encoded = content.uri.partition(",")
                    if not separator or not prefix.startswith("data:") or ";base64" not in prefix:
                        raise ValueError("Agent Framework data content must contain a base64 data URI.")
                    try:
                        base64.b64decode(encoded, validate=True)
                    except ValueError as exc:
                        raise ValueError("Agent Framework data content contains invalid base64 data.") from exc

                    if content.media_type and content.media_type.startswith("image/"):
                        blocks.append(
                            types.ImageContent(
                                type="image",
                                data=encoded,
                                mimeType=content.media_type,
                                _meta=metadata,
                            )
                        )
                    elif content.media_type and content.media_type.startswith("audio/"):
                        blocks.append(
                            types.AudioContent(
                                type="audio",
                                data=encoded,
                                mimeType=content.media_type,
                                _meta=metadata,
                            )
                        )
                    else:
                        resource_uri = (
                            content.additional_properties.get("uri") if content.additional_properties else None
                        )
                        if not isinstance(resource_uri, str):
                            resource_uri = "af://binary"
                        blocks.append(
                            types.EmbeddedResource(
                                type="resource",
                                resource=types.BlobResourceContents(
                                    uri=resource_uri,  # pyright: ignore[reportArgumentType]
                                    blob=encoded,
                                    mimeType=content.media_type,
                                ),
                                _meta=metadata,
                            )
                        )
                case _:
                    logger.warning(
                        "Agent Framework content type %s is not supported in MCP tool results and was omitted.",
                        content.type,
                    )
    return blocks
