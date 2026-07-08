# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :mod:`agent_framework_hosting_telegram`.

These tests exercise the internal parsing helpers and the webhook entry-point
without spinning up a real Telegram bot. The polling loop and HTTP-side
helpers are excluded from coverage because they require a live bot token.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from agent_framework import Content, Message, ServiceSessionId
from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelCommand,
    ChannelCommandContext,
    ChannelRequest,
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
    messages: list[Message] = field(default_factory=list)


class _FakeAgent:
    def __init__(self, reply: str = "ok") -> None:
        self.id = "fake-agent"
        self.name: str | None = "Fake Agent"
        self.description: str | None = "Test fake agent"
        self._reply = reply
        self.runs: list[Any] = []

    def create_session(self, *, session_id: str | None = None) -> Any:
        return {"session_id": session_id}

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> Any:
        return {"service_session_id": service_session_id, "session_id": session_id}

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        self.runs.append({"messages": messages, "stream": stream, "kwargs": kwargs})

        async def _coro() -> _FakeAgentResponse:
            return _FakeAgentResponse(text=self._reply)

        return _coro()


def _make_telegram(
    stream_default: bool = False, *, path: str = "/telegram/webhook"
) -> tuple[TelegramChannel, _FakeAgent]:
    agent = _FakeAgent("hi")
    ch = TelegramChannel(
        bot_token="123:abc",
        path=path,
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
    object.__setattr__(ch, "_http", fake_http)
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

    def test_slash_only_text_is_ignored(self) -> None:
        ch, agent = _make_telegram()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post(
                "/telegram/webhook",
                json={"update_id": 1, "message": {"chat": {"id": 99}, "text": "/"}},
                headers={"x-telegram-bot-api-secret-token": "s3cr3t"},
            )
        assert r.status_code == 200
        assert not agent.runs

    def test_non_int_chat_id_is_ignored(self) -> None:
        ch, agent = _make_telegram()
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post(
                "/telegram/webhook",
                json={"update_id": 1, "message": {"chat": {"id": "99"}, "text": "hello"}},
                headers={"x-telegram-bot-api-secret-token": "s3cr3t"},
            )
        assert r.status_code == 200
        assert not agent.runs

    def test_empty_path_mounts_at_app_root(self) -> None:
        ch, agent = _make_telegram(path="")
        host = AgentFrameworkHost(target=agent, channels=[ch])
        with TestClient(host.app) as client:
            r = client.post(
                "/",
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

    async def test_response_hook_can_rewrite_originating_reply(self) -> None:
        seen_kwargs: list[dict[str, Any]] = []

        def hook(result: HostedRunResult, **kwargs: Any) -> HostedRunResult:
            seen_kwargs.append(dict(kwargs))
            return HostedRunResult(_FakeAgentResponse(text=result.result.text.upper()), session=result.session)

        ch, agent = _make_telegram()
        ch.response_hook = hook

        class _Ctx:
            target: Any = agent

            async def run(
                self,
                _request: ChannelRequest,
                *,
                run_hook: Any | None = None,
                protocol_request: Any | None = None,
                response_hook: Any | None = None,
                channel_name: str | None = None,
            ) -> HostedRunResult:
                result = HostedRunResult(_FakeAgentResponse(text="hi"))
                if response_hook is None:
                    return result
                shaped = response_hook(result, request=_request, channel_name=channel_name or _request.channel)
                if isinstance(shaped, Awaitable):
                    return await shaped
                return shaped

        object.__setattr__(ch, "_ctx", _Ctx())

        request = ChannelRequest(channel="telegram", operation="message.create", input="hi", stream=False)
        await ch._dispatch(99, request)  # pyright: ignore[reportPrivateUsage]

        http_mock = cast(Any, ch._http)
        assert http_mock is not None
        args, kwargs = http_mock.post.call_args
        assert args[0].endswith("/sendMessage")
        assert kwargs["json"]["text"] == "HI"
        assert seen_kwargs
        assert seen_kwargs[0]["channel_name"] == "telegram"


class TestCommand:
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
        object.__setattr__(ch, "_http", fake_http)
        host = AgentFrameworkHost(target=_FakeAgent(), channels=[ch])

        with TestClient(host.app) as client:
            r = client.post(
                "/telegram/webhook",
                json={"update_id": 2, "message": {"chat": {"id": 7}, "text": "/ping"}},
            )
        assert r.status_code == 200
        assert captured and captured[0].request.operation == "command.invoke"


# --------------------------------------------------------------------------- #
# Per-chat serial ordering                                                    #
# --------------------------------------------------------------------------- #


class TestPerChatOrdering:
    async def test_updates_for_same_chat_run_serially(self) -> None:
        """Two updates for the same chat must process in arrival order."""
        ch, _ = _make_telegram()
        order: list[int] = []
        slow_event = asyncio.Event()

        async def fake_process(update: Mapping[str, Any]) -> None:
            uid = update.get("update_id")
            assert isinstance(uid, int)
            if uid == 1:
                # Block the first update so the second is queued behind it.
                await slow_event.wait()
            order.append(uid)

        object.__setattr__(ch, "_process_update", cast(Any, fake_process))

        ch._enqueue_update({"update_id": 1, "message": {"chat": {"id": 100}, "text": "first"}})
        ch._enqueue_update({"update_id": 2, "message": {"chat": {"id": 100}, "text": "second"}})

        # Let the worker start the first update.
        await asyncio.sleep(0)
        assert order == []  # blocked on slow_event
        slow_event.set()
        # Drain.
        worker = ch._chat_workers[100]
        # Wait for the queue to empty.
        await ch._chat_queues[100].join()
        # Cleanup
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert order == [1, 2]

    async def test_updates_for_different_chats_run_in_parallel(self) -> None:
        """Different chats get separate workers and can interleave freely."""
        ch, _ = _make_telegram()
        started: list[int] = []
        gate_a = asyncio.Event()

        async def fake_process(update: Mapping[str, Any]) -> None:
            uid = update.get("update_id")
            assert isinstance(uid, int)
            started.append(uid)
            if uid == 1:
                await gate_a.wait()

        object.__setattr__(ch, "_process_update", cast(Any, fake_process))

        ch._enqueue_update({"update_id": 1, "message": {"chat": {"id": 1}, "text": "a"}})
        ch._enqueue_update({"update_id": 2, "message": {"chat": {"id": 2}, "text": "b"}})

        # Both should be admitted into their respective workers despite
        # update 1 being blocked.
        await asyncio.sleep(0)
        # Update 2 finishes; update 1 still blocked.
        assert 2 in started
        gate_a.set()
        for cid in (1, 2):
            await ch._chat_queues[cid].join()
        for w in ch._chat_workers.values():
            w.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await w


# --------------------------------------------------------------------------- #
# Webhook ack-before-run + shutdown drains workers                            #
# --------------------------------------------------------------------------- #


class TestWebhookAckBeforeRun:
    async def test_webhook_returns_200_before_agent_completes(self) -> None:
        """The webhook must ack before the agent runs, to dodge Telegram's 60s redelivery."""
        ch, _ = _make_telegram()
        from starlette.requests import Request

        agent_started = asyncio.Event()
        agent_release = asyncio.Event()

        async def fake_process(update: Mapping[str, Any]) -> None:
            agent_started.set()
            await agent_release.wait()

        object.__setattr__(ch, "_process_update", cast(Any, fake_process))

        async def receive() -> Any:
            payload = b'{"update_id":1,"message":{"chat":{"id":42},"text":"hi"}}'
            return {"type": "http.request", "body": payload, "more_body": False}

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/telegram/webhook",
            "headers": [(b"x-telegram-bot-api-secret-token", b"s3cr3t")],
            "query_string": b"",
        }
        request = Request(scope, receive=receive)

        # Drive the webhook handler. Even though the agent won't complete
        # (gate_a still cleared) the webhook must still 200 promptly.
        resp = await ch._handle(request)
        assert resp.status_code == 200
        # The agent task is in flight but not finished — proves ack came first.
        await asyncio.wait_for(agent_started.wait(), timeout=1.0)
        assert not agent_release.is_set()

        # Cleanup: release the agent and drain.
        agent_release.set()
        await ch._chat_queues[42].join()
        for w in list(ch._chat_workers.values()):
            w.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await w


class TestShutdownDrainsWorkers:
    async def test_shutdown_cancels_in_flight_chat_workers(self) -> None:
        """`_on_shutdown` must drain per-chat workers, not leak them."""
        ch, _ = _make_telegram()
        forever = asyncio.Event()

        async def stuck(update: Mapping[str, Any]) -> None:
            await forever.wait()

        object.__setattr__(ch, "_process_update", cast(Any, stuck))
        ch._enqueue_update({"update_id": 9, "message": {"chat": {"id": 1}, "text": "a"}})
        await asyncio.sleep(0)
        assert ch._chat_workers and ch._update_tasks

        await ch._on_shutdown()
        assert not ch._chat_workers
        assert not ch._update_tasks


def _deletewebhook_called(http_mock: Any) -> bool:
    return any(call.args and str(call.args[0]).endswith("/deleteWebhook") for call in http_mock.post.call_args_list)


class TestWebhookShutdownTeardown:
    async def test_shutdown_keeps_webhook_by_default(self) -> None:
        """Default: shutdown must NOT delete the webhook (avoids redeploy races)."""
        ch, _ = _make_telegram()
        assert ch._transport == "webhook"
        await ch._on_shutdown()
        http_mock = cast(Any, ch._http)
        assert http_mock is not None
        assert not _deletewebhook_called(http_mock)
        http_mock.aclose.assert_awaited()

    async def test_shutdown_deletes_webhook_when_opted_in(self) -> None:
        """Opt-in: ``delete_webhook_on_shutdown=True`` performs best-effort teardown."""
        ch = TelegramChannel(
            bot_token="123:abc",
            webhook_url="https://example.com/hook",
            secret_token="s3cr3t",
            delete_webhook_on_shutdown=True,
            stream=False,
        )
        fake_http = MagicMock()
        response_mock = MagicMock()
        response_mock.json = MagicMock(return_value={"ok": True, "result": {}})
        fake_http.post = AsyncMock(return_value=response_mock)
        fake_http.get = AsyncMock(return_value=response_mock)
        fake_http.aclose = AsyncMock()
        object.__setattr__(ch, "_http", fake_http)
        await ch._on_shutdown()
        assert _deletewebhook_called(fake_http)
        fake_http.aclose.assert_awaited()


@dataclass
class _FakeStreamUpdate:
    contents: list[Content] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> _FakeStreamUpdate:
        return cls(contents=[Content.from_text(text=text)])

    @classmethod
    def from_image(cls, uri: str, media_type: str = "image/png") -> _FakeStreamUpdate:
        return cls(contents=[Content.from_uri(uri=uri, media_type=media_type)])


class _FakeResponseStream:
    def __init__(self, chunks: list[str | _FakeStreamUpdate], final: _FakeAgentResponse) -> None:
        self._chunks = chunks
        self._final = final

    def __aiter__(self) -> Any:
        async def _gen() -> Any:
            for chunk in self._chunks:
                if isinstance(chunk, str):
                    yield _FakeStreamUpdate.from_text(chunk)
                else:
                    yield chunk

        return _gen()

    async def get_final_response(self) -> _FakeAgentResponse:
        return self._final


class TestStreamingBehavior:
    async def test_streaming_long_text_does_not_hang(self) -> None:
        ch, _ = _make_telegram()
        long_text = "x" * 5000
        stream = _FakeResponseStream([long_text], _FakeAgentResponse(text=long_text))
        request = ChannelRequest(channel="telegram", operation="message.create", input="hello", stream=True)
        await asyncio.wait_for(
            ch._stream_to_chat(1, request, cast(Any, stream)),
            timeout=1.0,
        )  # pyright: ignore[reportPrivateUsage]

    async def test_streaming_falls_back_to_send_text_when_final_edit_fails(self) -> None:
        ch, _ = _make_telegram()
        ch._send_typing_action = False  # pyright: ignore[reportPrivateUsage]

        placeholder_response = MagicMock()
        placeholder_response.raise_for_status = MagicMock()
        placeholder_response.json = MagicMock(return_value={"result": {"message_id": 11}})
        failed_edit_response = MagicMock()
        failed_edit_response.status_code = 429

        http_mock = cast(Any, ch._http)
        assert http_mock is not None
        http_mock.post = AsyncMock(side_effect=[placeholder_response, failed_edit_response])

        reply_with_result = AsyncMock()
        object.__setattr__(ch, "_reply_with_result", reply_with_result)

        final = _FakeAgentResponse(text="final response")
        stream = _FakeResponseStream([], final)
        request = ChannelRequest(channel="telegram", operation="message.create", input="hello", stream=True)
        await ch._stream_to_chat(6, request, cast(Any, stream))  # pyright: ignore[reportPrivateUsage]

        assert reply_with_result.await_count == 1
        await_args = reply_with_result.await_args
        assert await_args is not None
        assert await_args.kwargs["send_text"] is True

    async def test_streaming_sends_images_from_final_result(self) -> None:
        ch, _ = _make_telegram()
        send_photo = AsyncMock()
        object.__setattr__(ch, "_send_photo", send_photo)

        final = _FakeAgentResponse(
            text="hello",
            messages=[
                Message(
                    "assistant",
                    [Content.from_uri(uri="https://example.com/cat.png", media_type="image/png")],
                )
            ],
        )
        stream = _FakeResponseStream(["hello"], final)
        request = ChannelRequest(channel="telegram", operation="message.create", input="hello", stream=True)
        await ch._stream_to_chat(7, request, cast(Any, stream))  # pyright: ignore[reportPrivateUsage]

        send_photo.assert_awaited_once_with(7, "https://example.com/cat.png")

    async def test_streaming_honors_send_typing_action_toggle(self) -> None:
        ch, _ = _make_telegram()
        ch._send_typing_action = False  # pyright: ignore[reportPrivateUsage]
        send_chat_action = AsyncMock()
        object.__setattr__(ch, "_send_chat_action", send_chat_action)

        stream = _FakeResponseStream(["hello"], _FakeAgentResponse(text="hello"))
        request = ChannelRequest(channel="telegram", operation="message.create", input="hello", stream=True)
        await ch._stream_to_chat(8, request, cast(Any, stream))  # pyright: ignore[reportPrivateUsage]

        send_chat_action.assert_not_awaited()

    async def test_streaming_multimodal_updates_do_not_accumulate_as_text(self) -> None:
        """Non-text stream updates (e.g. images) must not corrupt the text accumulator."""
        ch, _ = _make_telegram()
        send_photo = AsyncMock()
        object.__setattr__(ch, "_send_photo", send_photo)

        image_update = _FakeStreamUpdate.from_image("https://example.com/img.png")
        final = _FakeAgentResponse(
            text="caption",
            messages=[
                Message(
                    "assistant",
                    [Content.from_uri(uri="https://example.com/img.png", media_type="image/png")],
                )
            ],
        )
        stream = _FakeResponseStream(["text chunk", image_update], final)
        request = ChannelRequest(channel="telegram", operation="message.create", input="hi", stream=True)
        await ch._stream_to_chat(9, request, cast(Any, stream))  # pyright: ignore[reportPrivateUsage]

        # Image from the final response must be forwarded.
        send_photo.assert_awaited_once_with(9, "https://example.com/img.png")
