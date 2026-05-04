# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :mod:`agent_framework_hosting_telegram`.

These tests exercise the internal parsing helpers and the webhook entry-point
without spinning up a real Telegram bot. The polling loop and HTTP-side
helpers are excluded from coverage because they require a live bot token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelCommand,
    ChannelCommandContext,
    HostedRunResult,
)
from starlette.testclient import TestClient

from agent_framework_hosting_telegram import TelegramChannel, telegram_isolation_key
from agent_framework_hosting_telegram._channel import (
    _parse_telegram_message,
    _telegram_media_file_id,
)

# --------------------------------------------------------------------------- #
# Pure helpers                                                                #
# --------------------------------------------------------------------------- #


def test_telegram_isolation_key_format() -> None:
    assert telegram_isolation_key(42) == "telegram:42"
    assert telegram_isolation_key("abc") == "telegram:abc"


class TestMediaFileId:
    def test_no_media(self) -> None:
        assert _telegram_media_file_id({"text": "hi"}) is None

    def test_photo_picks_largest(self) -> None:
        assert _telegram_media_file_id({"photo": [{"file_id": "small"}, {"file_id": "large"}]}) == (
            "large",
            "image/jpeg",
        )

    def test_photo_empty_list(self) -> None:
        assert _telegram_media_file_id({"photo": []}) is None

    def test_document_uses_mime_type(self) -> None:
        result = _telegram_media_file_id({"document": {"file_id": "f1", "mime_type": "application/pdf"}})
        assert result == ("f1", "application/pdf")

    def test_voice_default_mime(self) -> None:
        result = _telegram_media_file_id({"voice": {"file_id": "v1"}})
        assert result == ("v1", "audio/ogg")


@pytest.mark.asyncio
class TestParseTelegramMessage:
    async def test_text_only(self) -> None:
        async def resolve(_: str) -> str | None:
            return None

        msg = await _parse_telegram_message({"text": "hello"}, resolve)
        assert msg.role == "user"
        assert msg.text == "hello"

    async def test_text_and_photo(self) -> None:
        async def resolve(file_id: str) -> str | None:
            return f"https://files.telegram.org/{file_id}"

        msg = await _parse_telegram_message({"caption": "look", "photo": [{"file_id": "p1"}]}, resolve)
        assert msg.text == "look"
        # Image content present.
        assert any((getattr(c, "uri", None) or "").endswith("/p1") for c in msg.contents)

    async def test_unresolvable_media_falls_back_to_text(self) -> None:
        async def resolve(_: str) -> str | None:
            return None

        msg = await _parse_telegram_message({"text": "x", "voice": {"file_id": "v1"}}, resolve)
        # Resolver returned None — the contents should still include the
        # text without crashing.
        assert msg.text == "x"


# --------------------------------------------------------------------------- #
# Webhook entry point                                                          #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeAgentResponse:
    text: str


class _FakeAgent:
    def __init__(self, reply: str = "ok") -> None:
        self._reply = reply
        self.runs: list[Any] = []

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        self.runs.append({"messages": messages, "stream": stream, "kwargs": kwargs})

        async def _coro() -> _FakeAgentResponse:
            return _FakeAgentResponse(text=self._reply)

        return _coro()


def _make_telegram(stream_default: bool = False) -> tuple[TelegramChannel, _FakeAgent]:
    agent = _FakeAgent("hi")
    ch = TelegramChannel(
        bot_token="123:abc",
        webhook_url="https://example.com/hook",
        secret_token="s3cr3t",
        stream=stream_default,
    )
    # Replace the internal HTTP client with an AsyncMock so the channel
    # never tries to call the real Telegram API.
    fake_http = MagicMock()
    # post() returns a response object whose raise_for_status() is sync.
    response_mock = MagicMock()
    response_mock.json = MagicMock(return_value={"ok": True, "result": {}})
    fake_http.post = AsyncMock(return_value=response_mock)
    fake_http.get = AsyncMock(return_value=response_mock)
    fake_http.aclose = AsyncMock()
    ch._http = fake_http
    return ch, agent


class TestTelegramWebhook:
    def test_webhook_accepts_text_message_and_dispatches_to_agent(self) -> None:
        ch, agent = _make_telegram()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        # Skip lifespan so polling/setWebhook are not invoked.
        with TestClient(host.app) as client:
            r = client.post(
                "/telegram/webhook",
                json={"update_id": 1, "message": {"chat": {"id": 99}, "text": "hello"}},
                headers={"x-telegram-bot-api-secret-token": "s3cr3t"},
            )
        assert r.status_code == 200
        assert agent.runs, "expected the agent to be invoked"

    def test_webhook_rejects_bad_secret(self) -> None:
        ch, agent = _make_telegram()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post(
                "/telegram/webhook",
                json={"update_id": 1, "message": {"chat": {"id": 99}, "text": "hi"}},
                headers={"x-telegram-bot-api-secret-token": "WRONG"},
            )
        assert r.status_code == 401
        assert not agent.runs


@pytest.mark.asyncio
class TestPushAndCommand:
    async def test_push_calls_send(self) -> None:
        ch, _agent = _make_telegram()
        from agent_framework_hosting import ChannelIdentity

        await ch.push(ChannelIdentity(channel="telegram", native_id="42"), HostedRunResult(text="hi"))
        assert ch._http is not None
        ch._http.post.assert_called()  # type: ignore[attr-defined]
        args, kwargs = ch._http.post.call_args  # type: ignore[attr-defined]
        assert args[0].endswith("/sendMessage")
        assert kwargs["json"]["chat_id"] in ("42", 42)
        assert kwargs["json"]["text"] == "hi"

    async def test_command_handler_invoked(self) -> None:
        captured: list[ChannelCommandContext] = []

        async def handler(ctx: ChannelCommandContext) -> None:
            captured.append(ctx)
            await ctx.reply("pong")

        ch = TelegramChannel(
            bot_token="123:abc",
            webhook_url="https://example.com/hook",
            commands=[ChannelCommand(name="ping", description="ping", handle=handler)],
            register_native_commands=False,
        )
        fake_http = MagicMock()
        response_mock = MagicMock()
        response_mock.json = MagicMock(return_value={"ok": True, "result": {}})
        fake_http.post = AsyncMock(return_value=response_mock)
        fake_http.get = AsyncMock(return_value=response_mock)
        fake_http.aclose = AsyncMock()
        ch._http = fake_http
        host = AgentFrameworkHost(target=_FakeAgent(), channels=[ch])

        with TestClient(host.app) as client:
            r = client.post(
                "/telegram/webhook",
                json={"update_id": 2, "message": {"chat": {"id": 7}, "text": "/ping"}},
            )
        assert r.status_code == 200
        assert captured and captured[0].request.operation == "command.invoke"
