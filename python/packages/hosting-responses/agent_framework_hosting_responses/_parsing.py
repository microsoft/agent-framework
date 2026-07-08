# Copyright (c) Microsoft. All rights reserved.

"""Parsing helpers for the OpenAI Responses-API request body.

The Responses API accepts ``input`` as either a string or a list of "input
items". An item is either a content part (``input_text`` / ``input_image``
/ ``input_file``) or a message envelope ``{type: "message", role,
content: [...]}``. We translate that into an Agent Framework ``Message``
list and remap the generation-control fields the API also carries into
``ChatOptions``-shaped keys. The result is available to the channel's
``run_hook``; a default hook strips them before they reach the agent so
unknown fields from untrusted callers are not forwarded unless the host
developer explicitly opts in.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from agent_framework import Content, Message
from agent_framework_hosting import ChannelIdentity, ChannelSession

# OpenAI Responses field name → Agent Framework ChatOptions field name.
_RESPONSES_OPTION_REMAP = {
    "max_output_tokens": "max_tokens",
    "parallel_tool_calls": "allow_multiple_tool_calls",
}
# Fields the Responses transport owns; they are consumed separately and must
# not also appear in options.
_RESPONSES_TRANSPORT_KEYS = frozenset({"input", "stream", "previous_response_id"})


def parse_responses_identity(body: Mapping[str, Any], channel_name: str) -> ChannelIdentity | None:
    """Surface the caller as a :class:`ChannelIdentity` so the host can record it.

    OpenAI Responses replaced ``user`` with ``safety_identifier`` — we use
    that as the native id, falling back to the legacy ``user`` field.
    """
    native = body.get("safety_identifier") or body.get("user")
    if not isinstance(native, str) or not native:
        return None
    return ChannelIdentity(channel=channel_name, native_id=native)


def _content_from_input_item(item: Mapping[str, Any]) -> Content:
    """Convert a single OpenAI Responses ``input`` item into a :class:`Content` part.

    Handles the ``input_text``/``output_text``/``text`` text variants,
    ``input_image`` URL references, and ``input_file`` references via either
    a public URL or a hosted ``file_id``. Raises ``ValueError`` for any
    unsupported item type so the surrounding parser can return a 422.
    """
    item_type = item.get("type")
    if item_type in ("input_text", "output_text", "text"):
        return Content.from_text(text=str(item.get("text", "")))
    if item_type == "input_image":
        image_url: Any = item.get("image_url")
        if isinstance(image_url, Mapping):
            image_url = cast("Mapping[str, Any]", image_url).get("url")
        if not isinstance(image_url, str):
            raise ValueError("input_image requires `image_url`")
        return Content.from_uri(uri=image_url, media_type="image/*")
    if item_type == "input_file":
        if (uri := item.get("file_url")) and isinstance(uri, str):
            return Content.from_uri(uri=uri, media_type=item.get("mime_type"))
        if file_id := item.get("file_id"):
            return Content(type="hosted_file", file_id=str(file_id))
        raise ValueError("input_file requires `file_url` or `file_id`")
    raise ValueError(f"Unsupported Responses input content type: {item_type!r}")


def messages_from_responses_input(value: Any) -> list[Message]:
    """Translate ``input`` (string or list of items) into :class:`Message` objects."""
    if isinstance(value, str):
        return [Message("user", [Content.from_text(text=value)])]
    if not isinstance(value, list) or not value:
        raise ValueError("`input` must be a non-empty string or list")

    messages: list[Message] = []
    pending_user_parts: list[Content] = []

    def flush() -> None:
        """Emit any buffered loose user content as a single user message."""
        if pending_user_parts:
            messages.append(Message("user", list(pending_user_parts)))
            pending_user_parts.clear()

    for item in cast("list[Any]", value):
        if not isinstance(item, Mapping):
            raise ValueError("each `input` item must be an object")
        item_map = cast("Mapping[str, Any]", item)
        if item_map.get("type") == "message":
            flush()
            role = str(item_map.get("role") or "user")
            content: Any = item_map.get("content") or []
            parts: list[Content]
            if isinstance(content, str):
                parts = [Content.from_text(text=content)]
            elif isinstance(content, list):
                parts = []
                for content_item in cast("list[Any]", content):
                    if not isinstance(content_item, Mapping):
                        raise ValueError("each message `content` item must be an object")
                    parts.append(_content_from_input_item(cast("Mapping[str, Any]", content_item)))
            else:
                raise ValueError("message `content` must be a string or list")
            messages.append(Message(role, parts))
        else:
            pending_user_parts.append(_content_from_input_item(item_map))

    flush()
    if not messages:
        raise ValueError("`input` produced no messages")
    return messages


def parse_responses_request(
    body: Mapping[str, Any],
) -> tuple[list[Message], dict[str, Any], ChannelSession | None]:
    """Translate a Responses-API request body into Agent Framework constructs.

    Returns a triple ``(messages, options, session)`` where:

    - ``messages`` is the parsed conversation.
    - ``options`` is a ``ChatOptions``-shaped dict with the remapped
      generation-control fields. Known Responses→ChatOptions renames are
      applied (e.g. ``max_output_tokens`` → ``max_tokens``); transport/
      session keys are excluded; ``None``-valued fields are dropped.
      Unknown fields are forwarded as-is so the channel's ``run_hook``
      can inspect and filter them. The default ``ResponsesChannel`` strips
      all options before the agent runs; supply a custom ``run_hook`` to
      selectively keep fields.
    - ``session`` is a :class:`ChannelSession` keyed by
      ``previous_response_id`` when one was supplied, else ``None``.
    """
    messages = messages_from_responses_input(body.get("input"))

    options: dict[str, Any] = {}
    for key, value in body.items():
        if key in _RESPONSES_TRANSPORT_KEYS or value is None:
            continue
        options[_RESPONSES_OPTION_REMAP.get(key, key)] = value

    session: ChannelSession | None = None
    if (prev := body.get("previous_response_id")) and isinstance(prev, str):
        session = ChannelSession(isolation_key=prev)

    return messages, options, session


__all__ = [
    "messages_from_responses_input",
    "parse_responses_identity",
    "parse_responses_request",
]
