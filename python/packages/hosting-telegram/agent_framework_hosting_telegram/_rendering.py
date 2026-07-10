# Copyright (c) Microsoft. All rights reserved.

"""Rendering helpers that translate Agent Framework results into native Telegram Bot API calls.

Each helper returns (or yields) a small ``TelegramOperation`` -- a Telegram
Bot API method name plus its JSON payload. App-owned code decides how to
actually invoke the Bot API (``sendMessage``, ``sendPhoto``,
``editMessageText``, ...), including authentication, retries, and rate
limiting; these helpers make no network calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypedDict

from agent_framework import AgentResponse, AgentResponseUpdate, ResponseStream

# Telegram's documented maximum length, in UTF-16 code units, for message
# text (`sendMessage` / `editMessageText`) and photo captions (`sendPhoto`).
# Agent Framework text is plain `str`; truncating by Python character count
# is a conservative (never-too-long) approximation of the UTF-16 limit.
TELEGRAM_MAX_TEXT_LENGTH = 4096
TELEGRAM_MAX_CAPTION_LENGTH = 1024

_NO_RESPONSE_TEXT = "(no response)"


class TelegramOperation(TypedDict):
    """A single native Telegram Bot API call produced by a rendering helper.

    Attributes:
        method: The Telegram Bot API method name (e.g. ``"sendMessage"``).
        payload: The JSON-serializable request body for that method.
    """

    method: str
    payload: dict[str, Any]


def _truncate(text: str, max_length: int) -> str:
    """Deterministically cap ``text`` at ``max_length`` characters."""
    return text if len(text) <= max_length else text[:max_length]


def _text_and_image_uris(result: AgentResponse[Any]) -> tuple[str, list[str]]:
    """Return the response's concatenated text and any image uris it carries."""
    image_uris = [
        content.uri
        for message in result.messages
        for content in message.contents
        if content.type in ("data", "uri") and content.uri and (content.media_type or "").startswith("image/")
    ]
    return result.text, image_uris


def telegram_from_run(
    result: AgentResponse[Any],
    *,
    chat_id: int,
    parse_mode: str | None = None,
) -> TelegramOperation:
    """Render a finished agent run as one native Telegram Bot API call.

    An image in the response renders as ``sendPhoto`` (using the first image
    found; any accompanying text becomes its caption). Otherwise, response
    text renders as ``sendMessage``, falling back to ``"(no response)"`` when
    the response has neither text nor an image.

    Args:
        result: The finished agent response to render.

    Keyword Args:
        chat_id: The Telegram chat id to address the message to.
        parse_mode: Optional Telegram ``parse_mode`` (e.g. ``"MarkdownV2"``,
            ``"HTML"``) to attach to the rendered payload.

    Returns:
        A ``TelegramOperation`` describing the Bot API call to make.
    """
    text, image_uris = _text_and_image_uris(result)
    if image_uris:
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": image_uris[0]}
        if text:
            payload["caption"] = _truncate(text, TELEGRAM_MAX_CAPTION_LENGTH)
            if parse_mode:
                payload["parse_mode"] = parse_mode
        return TelegramOperation(method="sendPhoto", payload=payload)

    payload = {"chat_id": chat_id, "text": _truncate(text or _NO_RESPONSE_TEXT, TELEGRAM_MAX_TEXT_LENGTH)}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return TelegramOperation(method="sendMessage", payload=payload)


async def telegram_from_streaming_run(
    stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
    *,
    chat_id: int,
    message_id: int,
    initial_text: str | None = None,
    parse_mode: str | None = None,
) -> AsyncIterator[TelegramOperation]:
    """Render a streaming agent run as a sequence of native Telegram Bot API calls.

    Yields one ``editMessageText`` operation per update carrying new text, each
    with the cumulative text so far (Telegram has no incremental-append edit
    call). Interim edits omit ``parse_mode`` since intermediate text is not
    guaranteed to be valid in the target markup. After the stream ends, yields
    a final ``editMessageText`` reflecting the finalized response text (this
    one includes ``parse_mode`` when given) and then one ``sendPhoto``
    operation per image the finalized response carries. Errors raised while
    iterating the stream or while finalizing it (``stream.get_final_response()``)
    propagate to the caller rather than being swallowed.

    Args:
        stream: The agent response stream returned by ``agent.run(..., stream=True)``.

    Keyword Args:
        chat_id: The Telegram chat id the streamed message lives in.
        message_id: The id of the Telegram message to edit as new content arrives.
        initial_text: The current text of the app-created placeholder message.
            Matching edits are omitted because Telegram rejects no-op edits.
        parse_mode: Optional Telegram ``parse_mode`` to attach to the final text edit.

    Yields:
        ``TelegramOperation`` values describing the Bot API calls to make, in order.
    """
    text = ""
    last_rendered_text = _truncate(initial_text, TELEGRAM_MAX_TEXT_LENGTH) if initial_text is not None else ""
    async for update in stream:
        if update.text:
            text += update.text
            rendered_text = _truncate(text, TELEGRAM_MAX_TEXT_LENGTH)
            if rendered_text == last_rendered_text:
                continue
            last_rendered_text = rendered_text
            yield TelegramOperation(
                method="editMessageText",
                payload={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": rendered_text,
                },
            )

    final = await stream.get_final_response()
    final_text, image_uris = _text_and_image_uris(final)

    if final_text or not image_uris:
        rendered_text = _truncate(final_text or _NO_RESPONSE_TEXT, TELEGRAM_MAX_TEXT_LENGTH)
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": rendered_text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if rendered_text != last_rendered_text or parse_mode:
            yield TelegramOperation(method="editMessageText", payload=payload)
    else:
        yield TelegramOperation(
            method="deleteMessage",
            payload={"chat_id": chat_id, "message_id": message_id},
        )

    for uri in image_uris:
        yield TelegramOperation(method="sendPhoto", payload={"chat_id": chat_id, "photo": uri})
