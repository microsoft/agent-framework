# Copyright (c) Microsoft. All rights reserved.

"""Tests for the Telegram Bot API rendering helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream

from agent_framework_hosting_telegram import (
    TELEGRAM_MAX_TEXT_LENGTH,
    telegram_from_run,
    telegram_from_streaming_run,
)


def _text_response(text: str) -> AgentResponse[None]:
    return AgentResponse(messages=Message(role="assistant", contents=[Content.from_text(text=text)]))


class TestTelegramFromRun:
    def test_text_response_renders_send_message(self) -> None:
        operation = telegram_from_run(_text_response("hello there"), chat_id=555)
        assert operation["method"] == "sendMessage"
        assert operation["payload"] == {"chat_id": 555, "text": "hello there"}

    def test_parse_mode_is_included_when_given(self) -> None:
        operation = telegram_from_run(_text_response("hi"), chat_id=555, parse_mode="MarkdownV2")
        assert operation["payload"]["parse_mode"] == "MarkdownV2"

    def test_no_text_or_image_falls_back_to_no_response(self) -> None:
        empty = AgentResponse(messages=Message(role="assistant", contents=[]))
        operation = telegram_from_run(empty, chat_id=1)
        assert operation["method"] == "sendMessage"
        assert operation["payload"]["text"] == "(no response)"

    def test_text_is_truncated_to_max_length(self) -> None:
        long_text = "x" * (TELEGRAM_MAX_TEXT_LENGTH + 500)
        operation = telegram_from_run(_text_response(long_text), chat_id=1)
        assert len(operation["payload"]["text"]) == TELEGRAM_MAX_TEXT_LENGTH
        assert operation["payload"]["text"] == "x" * TELEGRAM_MAX_TEXT_LENGTH

    def test_image_uri_renders_send_photo(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="assistant",
                contents=[Content.from_uri(uri="https://example.com/cat.png", media_type="image/png")],
            )
        )
        operation = telegram_from_run(result, chat_id=1)
        assert operation["method"] == "sendPhoto"
        assert operation["payload"] == {"chat_id": 1, "photo": "https://example.com/cat.png"}

    def test_image_with_text_uses_caption(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_text(text="a cat"),
                    Content.from_uri(uri="https://example.com/cat.png", media_type="image/png"),
                ],
            )
        )
        operation = telegram_from_run(result, chat_id=1, parse_mode="HTML")
        assert operation["method"] == "sendPhoto"
        assert operation["payload"]["caption"] == "a cat"
        assert operation["payload"]["parse_mode"] == "HTML"

    def test_non_image_uri_is_not_rendered_as_photo(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_text(text="here is a pdf"),
                    Content.from_uri(uri="https://example.com/report.pdf", media_type="application/pdf"),
                ],
            )
        )
        operation = telegram_from_run(result, chat_id=1)
        assert operation["method"] == "sendMessage"
        assert operation["payload"]["text"] == "here is a pdf"

    def test_only_first_image_is_rendered(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_uri(uri="https://example.com/first.png", media_type="image/png"),
                    Content.from_uri(uri="https://example.com/second.png", media_type="image/png"),
                ],
            )
        )
        operation = telegram_from_run(result, chat_id=1)
        assert operation["payload"]["photo"] == "https://example.com/first.png"


class TestTelegramFromStreamingRun:
    async def test_accumulates_text_across_updates(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="hel")], role="assistant")
            yield AgentResponseUpdate(contents=[Content.from_text(text="lo")], role="assistant")

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]

        interim = [op for op in operations if op["payload"].get("text") in ("hel", "hello")]
        assert operations[0]["method"] == "editMessageText"
        assert operations[0]["payload"] == {"chat_id": 1, "message_id": 42, "text": "hel"}
        assert operations[1]["payload"]["text"] == "hello"
        assert len(interim) == 2

    async def test_final_edit_includes_parse_mode(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="hi")], role="assistant")

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [
            op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42, parse_mode="MarkdownV2")
        ]

        interim_op = operations[0]
        final_op = operations[-1]
        assert "parse_mode" not in interim_op["payload"]
        assert final_op["method"] == "editMessageText"
        assert final_op["payload"]["parse_mode"] == "MarkdownV2"
        assert final_op["payload"]["text"] == "hi"

    async def test_edit_matching_initial_placeholder_is_omitted(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="...")], role="assistant")
            yield AgentResponseUpdate(contents=[Content.from_text(text="done")], role="assistant")

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [
            op
            async for op in telegram_from_streaming_run(
                stream,
                chat_id=1,
                message_id=42,
                initial_text="...",
            )
        ]

        assert len(operations) == 1
        assert operations[0]["payload"]["text"] == "...done"

    async def test_final_text_is_truncated(self) -> None:
        long_text = "y" * (TELEGRAM_MAX_TEXT_LENGTH + 200)

        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text=long_text)], role="assistant")

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]

        assert all(len(op["payload"]["text"]) <= TELEGRAM_MAX_TEXT_LENGTH for op in operations)

    async def test_images_from_final_response_render_as_send_photo(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(
                contents=[Content.from_uri(uri="https://example.com/cat.png", media_type="image/png")],
                role="assistant",
            )

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]

        photo_ops = [op for op in operations if op["method"] == "sendPhoto"]
        assert len(photo_ops) == 1
        assert photo_ops[0]["payload"] == {"chat_id": 1, "photo": "https://example.com/cat.png"}

    async def test_no_text_and_no_image_falls_back_to_no_response(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            return
            yield  # pragma: no cover - make this an async generator with no items

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]

        assert len(operations) == 1
        assert operations[0]["payload"]["text"] == "(no response)"

    async def test_image_only_final_response_skips_text_edit(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(
                contents=[Content.from_uri(uri="https://example.com/cat.png", media_type="image/png")],
                role="assistant",
            )

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        operations = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]

        assert operations[0]["method"] == "deleteMessage"
        assert operations[0]["payload"] == {"chat_id": 1, "message_id": 42}
        assert operations[1]["method"] == "sendPhoto"

    async def test_error_during_iteration_propagates(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="partial")], role="assistant")
            raise RuntimeError("upstream blew up")

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        with pytest.raises(RuntimeError, match="upstream blew up"):
            _ = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]

    async def test_error_during_finalization_propagates(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(text="partial")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse[None]:
            raise RuntimeError("finalizer blew up")

        stream = ResponseStream(updates(), finalizer=finalizer)

        with pytest.raises(RuntimeError, match="finalizer blew up"):
            _ = [op async for op in telegram_from_streaming_run(stream, chat_id=1, message_id=42)]
