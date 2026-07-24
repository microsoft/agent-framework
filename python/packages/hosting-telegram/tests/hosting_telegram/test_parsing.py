# Copyright (c) Microsoft. All rights reserved.

"""Tests for the Telegram update parsing/extraction helpers."""

from __future__ import annotations

from typing import Any, cast

import pytest
from agent_framework import Message

from agent_framework_hosting_telegram import (
    telegram_callback_query_id,
    telegram_chat_id,
    telegram_command,
    telegram_media_file_id,
    telegram_session_id,
    telegram_to_run,
)


def _message_update(**message_fields: Any) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": 0,
            "chat": {"id": 555, "type": "private"},
            "from": {"id": 777, "is_bot": False, "first_name": "Ada"},
            **message_fields,
        },
    }


class TestTelegramChatId:
    def test_reads_from_message(self) -> None:
        assert telegram_chat_id(_message_update(text="hi")) == 555

    def test_reads_from_edited_message(self) -> None:
        update = {"update_id": 1, "edited_message": {"chat": {"id": 42}, "text": "hi"}}
        assert telegram_chat_id(update) == 42

    def test_reads_from_callback_query_message(self) -> None:
        update = {
            "update_id": 1,
            "callback_query": {"id": "cb1", "data": "x", "message": {"chat": {"id": 99}}},
        }
        assert telegram_chat_id(update) == 99

    def test_returns_none_when_absent(self) -> None:
        assert telegram_chat_id({"update_id": 1}) is None

    def test_returns_none_for_non_int_chat_id(self) -> None:
        update = {"update_id": 1, "message": {"chat": {"id": "not-an-int"}}}
        assert telegram_chat_id(update) is None


class TestTelegramSessionId:
    def test_private_chat_uses_bot_and_user_id(self) -> None:
        assert telegram_session_id(_message_update(text="hi"), bot_id=123) == "telegram_123_user_777"

    def test_returns_none_when_no_chat_id(self) -> None:
        assert telegram_session_id({"update_id": 1}, bot_id=123) is None

    def test_private_chat_returns_none_when_no_user_id(self) -> None:
        update = _message_update(text="hi")
        del update["message"]["from"]
        assert telegram_session_id(update, bot_id=123) is None

    def test_group_chat_uses_bot_and_chat_id(self) -> None:
        update = _message_update(text="hi")
        update["message"]["chat"] = {"id": -555, "type": "supergroup"}
        assert telegram_session_id(update, bot_id=123) == "telegram_123_chat_-555"

    def test_private_callback_uses_callback_sender(self) -> None:
        update = {
            "update_id": 1,
            "callback_query": {
                "id": "cb1",
                "from": {"id": 888},
                "message": {"chat": {"id": 555, "type": "private"}},
            },
        }
        assert telegram_session_id(update, bot_id=123) == "telegram_123_user_888"


class TestTelegramCommand:
    def test_plain_command(self) -> None:
        assert telegram_command(_message_update(text="/start")) == "/start"

    def test_command_with_args(self) -> None:
        assert telegram_command(_message_update(text="/echo hello world")) == "/echo hello world"

    def test_bot_suffixed_command_normalizes(self) -> None:
        assert telegram_command(_message_update(text="/start@mybot")) == "/start"

    def test_bot_suffixed_command_with_args_normalizes(self) -> None:
        assert telegram_command(_message_update(text="/echo@mybot hello")) == "/echo hello"

    def test_edited_message_text(self) -> None:
        update = {"update_id": 1, "edited_message": {"chat": {"id": 1}, "text": "/help"}}
        assert telegram_command(update) == "/help"

    def test_callback_query_data(self) -> None:
        update = {"update_id": 1, "callback_query": {"id": "cb1", "data": "/confirm@mybot yes"}}
        assert telegram_command(update) == "/confirm yes"

    def test_non_command_text_returns_none(self) -> None:
        assert telegram_command(_message_update(text="hello there")) is None

    def test_missing_text_returns_none(self) -> None:
        assert telegram_command({"update_id": 1, "message": {"chat": {"id": 1}}}) is None

    def test_no_actionable_source_returns_none(self) -> None:
        assert telegram_command({"update_id": 1}) is None


class TestTelegramCallbackQueryId:
    def test_returns_id(self) -> None:
        update = {"update_id": 1, "callback_query": {"id": "cb-123", "data": "x"}}
        assert telegram_callback_query_id(update) == "cb-123"

    def test_returns_none_without_callback_query(self) -> None:
        assert telegram_callback_query_id(_message_update(text="hi")) is None


class TestTelegramMediaFileId:
    def test_picks_largest_photo_by_file_size(self) -> None:
        update = _message_update(
            photo=[
                {"file_id": "small", "file_size": 100, "width": 90, "height": 90},
                {"file_id": "large", "file_size": 5000, "width": 800, "height": 600},
                {"file_id": "medium", "file_size": 1000, "width": 320, "height": 240},
            ]
        )
        assert telegram_media_file_id(update) == ("large", "image/jpeg")

    def test_picks_largest_photo_by_area_when_no_file_size(self) -> None:
        update = _message_update(
            photo=[
                {"file_id": "small", "width": 90, "height": 90},
                {"file_id": "large", "width": 800, "height": 600},
            ]
        )
        assert telegram_media_file_id(update) == ("large", "image/jpeg")

    def test_document_uses_declared_mime_type(self) -> None:
        update = _message_update(document={"file_id": "doc1", "mime_type": "application/pdf"})
        assert telegram_media_file_id(update) == ("doc1", "application/pdf")

    def test_document_falls_back_to_default_mime_type(self) -> None:
        update = _message_update(document={"file_id": "doc1"})
        assert telegram_media_file_id(update) == ("doc1", "application/octet-stream")

    def test_voice_defaults_to_ogg(self) -> None:
        update = _message_update(voice={"file_id": "v1"})
        assert telegram_media_file_id(update) == ("v1", "audio/ogg")

    def test_audio_defaults_to_mpeg(self) -> None:
        update = _message_update(audio={"file_id": "a1"})
        assert telegram_media_file_id(update) == ("a1", "audio/mpeg")

    def test_video_defaults_to_mp4(self) -> None:
        update = _message_update(video={"file_id": "vi1"})
        assert telegram_media_file_id(update) == ("vi1", "video/mp4")

    def test_accepts_bare_message_object(self) -> None:
        message = {"chat": {"id": 1}, "document": {"file_id": "doc1", "mime_type": "text/plain"}}
        assert telegram_media_file_id(message) == ("doc1", "text/plain")

    def test_returns_none_without_media(self) -> None:
        assert telegram_media_file_id(_message_update(text="hi")) is None

    def test_reads_media_from_callback_query_message(self) -> None:
        update = {
            "update_id": 1,
            "callback_query": {
                "id": "cb1",
                "data": "x",
                "message": {"chat": {"id": 1}, "document": {"file_id": "doc1", "mime_type": "text/plain"}},
            },
        }
        assert telegram_media_file_id(update) == ("doc1", "text/plain")


class TestTelegramToRun:
    async def test_message_text_becomes_user_message(self) -> None:
        run = await telegram_to_run(_message_update(text="hello"))
        messages = cast("list[Message]", run["messages"])
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "hello"
        assert run["stream"] is False

    async def test_stream_flag_is_forwarded(self) -> None:
        run = await telegram_to_run(_message_update(text="hello"), stream=True)
        assert run["stream"] is True

    async def test_edited_message_becomes_user_message(self) -> None:
        update = {"update_id": 1, "edited_message": {"chat": {"id": 1}, "text": "edited"}}
        run = await telegram_to_run(update)
        messages = cast("list[Message]", run["messages"])
        assert messages[0].text == "edited"

    async def test_callback_query_data_becomes_user_text(self) -> None:
        update = {"update_id": 1, "callback_query": {"id": "cb1", "data": "action:confirm"}}
        run = await telegram_to_run(update)
        messages = cast("list[Message]", run["messages"])
        assert messages[0].text == "action:confirm"

    async def test_caption_used_when_no_text(self) -> None:
        update = _message_update(caption="a cute cat", photo=[{"file_id": "p1", "file_size": 10}])
        run = await telegram_to_run(update)
        messages = cast("list[Message]", run["messages"])
        assert messages[0].text == "a cute cat"

    async def test_media_resolved_via_resolver(self) -> None:
        update = _message_update(caption="a cute cat", photo=[{"file_id": "p1", "file_size": 10}])

        async def resolve_file_url(file_id: str) -> str | None:
            assert file_id == "p1"
            return "https://example.com/p1.jpg"

        run = await telegram_to_run(update, resolve_file_url=resolve_file_url)
        messages = cast("list[Message]", run["messages"])
        uris = [c.uri for c in messages[0].contents if c.type == "uri"]
        assert uris == ["https://example.com/p1.jpg"]
        assert messages[0].text == "a cute cat"

    async def test_media_without_resolver_preserves_text(self) -> None:
        update = _message_update(caption="a cute cat", photo=[{"file_id": "p1", "file_size": 10}])
        run = await telegram_to_run(update)
        messages = cast("list[Message]", run["messages"])
        assert messages[0].text == "a cute cat"
        assert not any(c.type == "uri" for c in messages[0].contents)

    async def test_media_resolver_returning_none_preserves_text(self) -> None:
        update = _message_update(caption="a cute cat", photo=[{"file_id": "p1", "file_size": 10}])

        async def resolve_file_url(file_id: str) -> str | None:
            return None

        run = await telegram_to_run(update, resolve_file_url=resolve_file_url)
        messages = cast("list[Message]", run["messages"])
        assert messages[0].text == "a cute cat"

    async def test_media_only_unresolved_raises(self) -> None:
        update = _message_update(photo=[{"file_id": "p1", "file_size": 10}])
        with pytest.raises(ValueError, match="Cannot resolve"):
            await telegram_to_run(update)

    async def test_media_only_no_resolver_raises(self) -> None:
        update = _message_update(document={"file_id": "d1"})
        with pytest.raises(ValueError, match="Cannot resolve"):
            await telegram_to_run(update)

    async def test_empty_message_raises(self) -> None:
        update = {"update_id": 1, "message": {"chat": {"id": 1}}}
        with pytest.raises(ValueError, match="no text, caption, or resolvable media"):
            await telegram_to_run(update)

    async def test_callback_query_without_data_raises(self) -> None:
        update = {"update_id": 1, "callback_query": {"id": "cb1"}}
        with pytest.raises(ValueError, match="no actionable"):
            await telegram_to_run(update)

    async def test_update_without_actionable_content_raises(self) -> None:
        with pytest.raises(ValueError, match="no actionable"):
            await telegram_to_run({"update_id": 1, "poll": {"id": "p1"}})
