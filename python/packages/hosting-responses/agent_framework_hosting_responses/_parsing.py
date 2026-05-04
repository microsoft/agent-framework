# Copyright (c) Microsoft. All rights reserved.

"""Parsing helpers for the OpenAI Responses-API request body.

The Responses API accepts ``input`` as either a string or a list of "input
items". An item is either a content part (``input_text`` / ``input_image``
/ ``input_file``) or a message envelope ``{type: "message", role,
content: [...]}``. We translate that into an Agent Framework ``Message``
list and split out the ChatOptions-shaped fields the API also carries.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from agent_framework import Content, Message
from agent_framework_hosting import ChannelIdentity, ChannelSession, ResponseTarget, logger

# OpenAI Responses field name → Agent Framework ChatOptions field name.
_RESPONSES_OPTION_REMAP = {
    "max_output_tokens": "max_tokens",
    "parallel_tool_calls": "allow_multiple_tool_calls",
}
# Fields we forward to ChatOptions verbatim.
_RESPONSES_OPTION_PASSTHROUGH = {
    "temperature",
    "top_p",
    "metadata",
    "user",
    "safety_identifier",
    "tool_choice",
    "tools",
    "store",
    "response_format",
    "stop",
    "seed",
    "frequency_penalty",
    "presence_penalty",
    "logit_bias",
    "instructions",
}
# Fields the Responses transport owns; they must not be forwarded as options.
_RESPONSES_TRANSPORT_KEYS = {"input", "model", "stream", "previous_response_id", "response_target"}


def parse_response_target(body: Mapping[str, Any]) -> ResponseTarget:
    """Translate the OpenAI Responses ``response_target`` field into a :class:`ResponseTarget`.

    Accepted shapes:

    - ``"originating"`` / ``"active"`` / ``"all_linked"`` / ``"none"`` — bare strings.
    - ``"telegram"`` / ``"telegram:<chat_id>"`` — single channel destination.
    - ``["telegram:<id>", "originating"]`` — list of destinations; the
      pseudo-name ``"originating"`` includes the originating channel.
    - ``{"channels": [...]}`` — same list semantics with the explicit key.
    - ``{"kind": "active"}`` / ``{"kind": "all_linked"}`` — explicit kind.

    Anything malformed is logged at WARNING and falls back to ``originating``.
    """
    raw = body.get("response_target")
    if raw is None:
        return ResponseTarget.originating  # type: ignore[attr-defined,no-any-return]
    if isinstance(raw, str):
        keyword = raw.strip()
        if keyword == "originating":
            return ResponseTarget.originating  # type: ignore[attr-defined,no-any-return]
        if keyword == "active":
            return ResponseTarget.active  # type: ignore[attr-defined,no-any-return]
        if keyword == "all_linked":
            return ResponseTarget.all_linked  # type: ignore[attr-defined,no-any-return]
        if keyword == "none":
            return ResponseTarget.none  # type: ignore[attr-defined,no-any-return]
        # Treat any other bare string as a single channel destination.
        return ResponseTarget.channel(keyword)
    if isinstance(raw, list):
        return _parse_channels_list(cast("list[Any]", raw))  # type: ignore[redundant-cast]
    if isinstance(raw, Mapping):
        raw_map = cast("Mapping[str, Any]", raw)
        channels = raw_map.get("channels")
        if isinstance(channels, list):
            return _parse_channels_list(cast("list[Any]", channels))  # type: ignore[redundant-cast]
        kind = raw_map.get("kind")
        if kind == "active":
            return ResponseTarget.active  # type: ignore[attr-defined,no-any-return]
        if kind == "all_linked":
            return ResponseTarget.all_linked  # type: ignore[attr-defined,no-any-return]
        if kind == "none":
            return ResponseTarget.none  # type: ignore[attr-defined,no-any-return]
        if kind == "originating":
            return ResponseTarget.originating  # type: ignore[attr-defined,no-any-return]
    logger.warning("responses: ignoring malformed response_target=%r", cast("Any", raw))
    return ResponseTarget.originating  # type: ignore[attr-defined,no-any-return]


def _parse_channels_list(raw: list[Any]) -> ResponseTarget:
    """Build a ``ResponseTarget.channels`` from a raw list, dropping non-string entries.

    An empty list (or one with no usable strings) collapses back to
    ``originating`` so we never silently produce a target that nobody
    will deliver to.
    """
    tokens = [t for t in raw if isinstance(t, str) and t]
    if len(tokens) != len(raw):
        logger.warning("responses: dropping non-string entries from response_target=%r", raw)
    if not tokens:
        return ResponseTarget.originating  # type: ignore[attr-defined,no-any-return]
    return ResponseTarget.channels(tokens)


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

    for item in cast("list[Any]", value):  # type: ignore[redundant-cast]
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
                parts = [
                    _content_from_input_item(cast("Mapping[str, Any]", c))
                    for c in cast("list[Any]", content)  # type: ignore[redundant-cast]
                    if isinstance(c, Mapping)
                ]
            else:
                parts = []
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

    - ``messages`` is the parsed conversation (``instructions`` is prepended
      as a system message when present).
    - ``options`` is a ``ChatOptions``-shaped dict with the model-tunable
      fields the channel lifted off the body.
    - ``session`` is a :class:`ChannelSession` keyed by
      ``previous_response_id`` when one was supplied, else ``None``.
    """
    messages = messages_from_responses_input(body.get("input"))

    if (instructions := body.get("instructions")) and isinstance(instructions, str):
        messages.insert(0, Message("system", [Content.from_text(text=instructions)]))

    options: dict[str, Any] = {}
    for key, value in body.items():
        if key in _RESPONSES_TRANSPORT_KEYS or value is None:
            continue
        if key == "instructions":
            continue
        if (mapped := _RESPONSES_OPTION_REMAP.get(key)) is not None:
            options[mapped] = value
        elif key in _RESPONSES_OPTION_PASSTHROUGH:
            options[key] = value
        # silently drop everything else (truncation, reasoning, include, ...)

    session: ChannelSession | None = None
    if (prev := body.get("previous_response_id")) and isinstance(prev, str):
        session = ChannelSession(isolation_key=prev)

    return messages, options, session


__all__ = [
    "messages_from_responses_input",
    "parse_response_target",
    "parse_responses_identity",
    "parse_responses_request",
]
