# Copyright (c) Microsoft. All rights reserved.

"""Parsing helpers for the Telegram Bot API ``Update`` object.

Telegram delivers updates as JSON objects shaped like ``{"update_id": ...,
"message": {...}}`` (or ``edited_message`` / ``callback_query`` instead of
``message``). These helpers pull out the handful of fields an app-owned route
needs -- chat id, a namespaced session id, a leading slash command, a
callback query id, and inbound media -- and translate an update into Agent
Framework ``Agent.run`` arguments. They do not poll for updates, register
webhooks, call the Telegram HTTP API, or dispatch commands; that is app-owned
route/bot-client code.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from agent_framework import ChatOptions, Content, Message
from agent_framework_hosting import AgentRunArgs

# Telegram media fields whose objects carry a `file_id` (and, except photos,
# a `mime_type`) directly, mapped to the MIME type Telegram uses when the
# object omits `mime_type` (voice notes are always OGG/Opus, for example).
_MEDIA_DEFAULT_MIME_TYPES: dict[str, str] = {
    "document": "application/octet-stream",
    "voice": "audio/ogg",
    "audio": "audio/mpeg",
    "video": "video/mp4",
}

# Matches a leading Telegram bot command: `/name`, optionally `@botname`,
# optionally followed by arguments. Command names are `[A-Za-z0-9_]` per the
# Bot API's `bot_command` entity rules.
_COMMAND_PATTERN = re.compile(r"^/(?P<name>[A-Za-z0-9_]+)(?:@(?P<bot>[A-Za-z0-9_]+))?(?P<rest>.*)$", re.DOTALL)

ResolveFileUrl = Callable[[str], Awaitable[str | None]]
"""Async callable resolving a Telegram ``file_id`` to a fetchable URL, or ``None``."""


def _inner_message(update: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the ``message`` or ``edited_message`` object from ``update``, if present."""
    for key in ("message", "edited_message"):
        candidate = update.get(key)
        if isinstance(candidate, Mapping):
            return cast("Mapping[str, Any]", candidate)
    return None


def _callback_query(update: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the ``callback_query`` object from ``update``, if present."""
    candidate = update.get("callback_query")
    return cast("Mapping[str, Any]", candidate) if isinstance(candidate, Mapping) else None


def telegram_chat_id(update: Mapping[str, Any]) -> int | None:
    """Return the chat id an update belongs to.

    Reads ``message.chat.id`` / ``edited_message.chat.id``, falling back to
    ``callback_query.message.chat.id`` for callback-only updates.

    Args:
        update: A Telegram Bot API ``Update`` object.

    Returns:
        The chat id, or ``None`` if the update carries none of the supported shapes.
    """
    message = _inner_message(update)
    if message is None:
        callback_query = _callback_query(update)
        candidate = callback_query.get("message") if callback_query is not None else None
        if not isinstance(candidate, Mapping):
            return None
        message = cast("Mapping[str, Any]", candidate)
    chat_candidate = message.get("chat")
    if not isinstance(chat_candidate, Mapping):
        return None
    chat = cast("Mapping[str, Any]", chat_candidate)
    chat_id = chat.get("id")
    return chat_id if isinstance(chat_id, int) else None


def telegram_session_id(update: Mapping[str, Any], *, bot_id: int) -> str | None:
    """Return a session id using Telegram's native bot, user, and chat boundaries.

    Args:
        update: A Telegram Bot API ``Update`` object.

    Keyword Args:
        bot_id: The Telegram bot's numeric user id.

    Returns:
        ``telegram:<bot_id>:<user_id>`` for a private chat,
        ``telegram:<bot_id>:<chat_id>`` for other chats, or ``None`` when the
        required Telegram identity is absent.
    """
    chat_id = telegram_chat_id(update)
    if chat_id is None:
        return None

    message = _inner_message(update)
    callback_query = _callback_query(update)
    if message is None and callback_query is not None:
        callback_message = callback_query.get("message")
        if isinstance(callback_message, Mapping):
            message = cast("Mapping[str, Any]", callback_message)

    chat_candidate = message.get("chat") if message is not None else None
    chat = cast("Mapping[str, Any]", chat_candidate) if isinstance(chat_candidate, Mapping) else None
    chat_type = chat.get("type") if chat is not None else None
    if chat_type != "private":
        return f"telegram:{bot_id}:{chat_id}"

    if callback_query is not None:
        sender_candidate = callback_query.get("from")
    elif message is not None:
        sender_candidate = message.get("from")
    else:
        return None
    if not isinstance(sender_candidate, Mapping):
        return None
    sender = cast("Mapping[str, Any]", sender_candidate)
    sender_id = sender.get("id")
    return f"telegram:{bot_id}:{sender_id}" if isinstance(sender_id, int) else None


def telegram_callback_query_id(update: Mapping[str, Any]) -> str | None:
    """Return the callback query id from an update, if present.

    Apps need this to answer the callback query (``answerCallbackQuery``) so
    Telegram stops showing the client-side loading spinner; this helper only
    extracts the id, it does not call the Bot API.

    Args:
        update: A Telegram Bot API ``Update`` object.

    Returns:
        The callback query id, or ``None`` if the update has no ``callback_query``.
    """
    callback_query = _callback_query(update)
    if callback_query is None:
        return None
    query_id = callback_query.get("id")
    return query_id if isinstance(query_id, str) else None


def _command_source_text(update: Mapping[str, Any]) -> str | None:
    """Return the text a leading command should be parsed from."""
    message = _inner_message(update)
    if message is not None:
        text = message.get("text")
        if isinstance(text, str):
            return text
    callback_query = _callback_query(update)
    if callback_query is not None:
        data = callback_query.get("data")
        if isinstance(data, str):
            return data
    return None


def telegram_command(update: Mapping[str, Any]) -> str | None:
    """Parse a leading slash command out of an update, without dispatching it.

    Looks at ``message.text`` / ``edited_message.text`` first, then
    ``callback_query.data``. A bot-suffixed command (``/name@bot args``) is
    normalized to ``/name args`` since a single Bot API integration only ever
    serves one bot username. Callers are responsible for matching the
    returned command name and acting on it.

    Args:
        update: A Telegram Bot API ``Update`` object.

    Returns:
        The normalized command (e.g. ``"/start"`` or ``"/start hello"``), or
        ``None`` if the source text does not start with a command.
    """
    text = _command_source_text(update)
    if text is None:
        return None
    match = _COMMAND_PATTERN.match(text)
    if not match:
        return None
    return f"/{match.group('name')}{match.group('rest')}".rstrip()


def _resolve_media_message(update_or_message: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the message object to inspect for media, from either an update or a bare message."""
    if "message" in update_or_message or "edited_message" in update_or_message or "callback_query" in update_or_message:
        message = _inner_message(update_or_message)
        if message is not None:
            return message
        callback_query = _callback_query(update_or_message)
        if callback_query is not None:
            candidate = callback_query.get("message")
            if isinstance(candidate, Mapping):
                return cast("Mapping[str, Any]", candidate)
        return None
    return update_or_message


def _largest_photo_file_id(photo_sizes: Sequence[Any]) -> str | None:
    """Return the ``file_id`` of the highest-resolution entry in a Telegram ``photo`` array."""
    candidates = [cast("Mapping[str, Any]", size) for size in photo_sizes if isinstance(size, Mapping)]
    if not candidates:
        return None

    def _area(size: Mapping[str, Any]) -> int:
        file_size = size.get("file_size")
        if isinstance(file_size, int):
            return file_size
        width, height = size.get("width"), size.get("height")
        return width * height if isinstance(width, int) and isinstance(height, int) else 0

    largest = max(candidates, key=_area)
    file_id = largest.get("file_id")
    return file_id if isinstance(file_id, str) else None


def telegram_media_file_id(update_or_message: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return the ``(file_id, mime_type)`` of the inbound media attached to an update or message.

    Accepts either a full ``Update`` object (media is read from ``message`` /
    ``edited_message`` / ``callback_query.message``) or a bare Telegram
    message object. Photos pick the largest size Telegram sent (by
    ``file_size``, falling back to pixel area); documents, voice notes,
    audio, and video use their own ``file_id`` and ``mime_type`` (falling
    back to Telegram's known default MIME type when the field is absent).

    Args:
        update_or_message: A Telegram ``Update`` or message object.

    Returns:
        A ``(file_id, mime_type)`` tuple, or ``None`` if there is no supported media.
    """
    message = _resolve_media_message(update_or_message)
    if message is None:
        return None

    photo = message.get("photo")
    if isinstance(photo, Sequence) and not isinstance(photo, (str, bytes, bytearray)) and photo:
        file_id = _largest_photo_file_id(cast("Sequence[Any]", photo))
        if file_id is not None:
            return file_id, "image/jpeg"

    for key, default_mime_type in _MEDIA_DEFAULT_MIME_TYPES.items():
        item_candidate = message.get(key)
        if isinstance(item_candidate, Mapping):
            item = cast("Mapping[str, Any]", item_candidate)
            file_id = item.get("file_id")
            if isinstance(file_id, str):
                mime_type = item.get("mime_type")
                return file_id, mime_type if isinstance(mime_type, str) and mime_type else default_mime_type
    return None


async def _contents_from_message(
    message: Mapping[str, Any],
    resolve_file_url: ResolveFileUrl | None,
) -> list[Content]:
    """Translate one Telegram message object into Agent Framework content parts.

    Raises:
        ValueError: If the message has no text, caption, or resolvable media.
    """
    text = message.get("text")
    caption = message.get("caption")
    text_value = text if isinstance(text, str) and text else (caption if isinstance(caption, str) and caption else None)

    contents: list[Content] = []
    media = telegram_media_file_id(message)
    if media is not None:
        file_id, mime_type = media
        resolved_url = await resolve_file_url(file_id) if resolve_file_url is not None else None
        if resolved_url:
            contents.append(Content.from_uri(uri=resolved_url, media_type=mime_type))
        elif text_value is None:
            raise ValueError(
                f"Cannot resolve Telegram media file_id={file_id!r}: no `resolve_file_url` was given (or it "
                "returned None), and the message has no text/caption to fall back to."
            )
    if text_value is not None:
        contents.append(Content.from_text(text=text_value))

    if not contents:
        raise ValueError("Telegram message has no text, caption, or resolvable media to convert to a run.")
    return contents


async def telegram_to_run(
    update: Mapping[str, Any],
    *,
    resolve_file_url: ResolveFileUrl | None = None,
    stream: bool = False,
) -> AgentRunArgs:
    """Convert a Telegram update into Agent Framework run values.

    Supports ``message``, ``edited_message``, and ``callback_query`` updates.
    Message/edited-message text or caption becomes text content; inbound
    media becomes uri content when ``resolve_file_url`` resolves it (media
    alone with no resolvable URL and no text/caption raises rather than
    producing an empty run). A callback query's ``data`` becomes the user's
    text.

    Args:
        update: A Telegram Bot API ``Update`` object.

    Keyword Args:
        resolve_file_url: Optional async callable that resolves a Telegram
            ``file_id`` (typically via the Bot API's ``getFile``) to a
            fetchable URL, or ``None`` if it cannot. When omitted, media is
            ignored and only text/caption is used.
        stream: Whether the caller intends to run the agent in streaming mode.

    Returns:
        Arguments corresponding to ``Agent.run``.

    Raises:
        ValueError: If the update has no actionable message/callback data, or
            a message has no text, caption, or resolvable media.
    """
    message = _inner_message(update)
    if message is not None:
        contents = await _contents_from_message(message, resolve_file_url)
    else:
        callback_query = _callback_query(update)
        data = callback_query.get("data") if callback_query is not None else None
        if not isinstance(data, str) or not data:
            raise ValueError("Telegram update has no actionable `message`, `edited_message`, or `callback_query.data`.")
        contents = [Content.from_text(text=data)]

    return AgentRunArgs(
        messages=[Message("user", contents)],
        options=cast("ChatOptions[Any]", {}),
        stream=stream,
    )
