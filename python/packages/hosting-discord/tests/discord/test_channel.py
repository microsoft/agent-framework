# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import Any

import httpx
import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message
from agent_framework_hosting import (
    ChannelCommand,
    ChannelCommandContext,
    ChannelRequest,
    HostedRunResult,
)
from nacl.signing import SigningKey
from starlette.applications import Starlette
from starlette.testclient import TestClient

from agent_framework_hosting_discord import DiscordChannel, discord_isolation_key


def _run_result(text: str) -> HostedRunResult[AgentResponse]:
    return HostedRunResult(AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(text=text)])]))


def _interaction(command: str = "ask", *, prompt: str = "hello", token: str = "token") -> dict[str, Any]:
    return {
        "id": "interaction-1",
        "type": 2,
        "application_id": "app-1",
        "token": token,
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "member": {
            "user": {
                "id": "user-1",
                "username": "ada",
                "global_name": "Ada",
            }
        },
        "data": {
            "name": command,
            "options": [{"name": "prompt", "type": 3, "value": prompt}],
        },
    }


def _headers(signing_key: SigningKey, body: bytes) -> dict[str, str]:
    timestamp = "1234567890"
    signature = signing_key.sign(timestamp.encode("utf-8") + body).signature.hex()
    return {
        "x-signature-ed25519": signature,
        "x-signature-timestamp": timestamp,
        "content-type": "application/json",
    }


class _FakeContext:
    def __init__(self, *, text: str = "agent reply") -> None:
        self.target = object()
        self.text = text
        self.requests: list[ChannelRequest] = []
        self.fake_stream: _FakeStream | None = None

    async def run(
        self,
        request: ChannelRequest,
        *,
        run_hook: Any | None = None,
        protocol_request: Any | None = None,
        response_hook: Any | None = None,
        channel_name: str | None = None,
    ) -> HostedRunResult[AgentResponse]:
        if run_hook is not None:
            maybe_request = run_hook(request, target=self.target, protocol_request=protocol_request)
            if isinstance(maybe_request, Awaitable):
                request = await maybe_request
            else:
                request = maybe_request
        self.requests.append(request)
        result = _run_result(self.text)
        if response_hook is not None:
            maybe_result = response_hook(result, request=request, channel_name=channel_name or request.channel)
            if isinstance(maybe_result, Awaitable):
                return await maybe_result
            return maybe_result
        return result

    async def run_stream(
        self,
        request: ChannelRequest,
        *,
        run_hook: Any | None = None,
        protocol_request: Any | None = None,
        stream_update_hook: Any | None = None,
        response_hook: Any | None = None,
        channel_name: str | None = None,
    ) -> _FakeStream:
        if run_hook is not None:
            maybe_request = run_hook(request, target=self.target, protocol_request=protocol_request)
            if isinstance(maybe_request, Awaitable):
                request = await maybe_request
            else:
                request = maybe_request
        self.requests.append(request)
        if self.fake_stream is None:
            self.fake_stream = _FakeStream(["a", "b"])
        if stream_update_hook is not None:
            self.fake_stream.transform = stream_update_hook
        if response_hook is not None:
            self.fake_stream.response_hook = response_hook
            self.fake_stream.request = request
            self.fake_stream.channel_name = channel_name or request.channel
        return self.fake_stream


class _FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.transform: Any | None = None
        self.response_hook: Any | None = None
        self.request: ChannelRequest | None = None
        self.channel_name: str | None = None

    def __aiter__(self) -> AsyncIterator[AgentResponseUpdate]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[AgentResponseUpdate]:
        for chunk in self._chunks:
            update = AgentResponseUpdate(contents=[Content.from_text(text=chunk)], role="assistant")
            if self.transform is not None:
                transformed = self.transform(update)
                if isinstance(transformed, Awaitable):
                    transformed = await transformed
                if transformed is None:
                    continue
                update = transformed
            yield update

    async def get_final_response(self) -> AgentResponse:
        result = _run_result("".join(self._chunks))
        if self.response_hook is None:
            return result.result
        shaped = self.response_hook(result, request=self.request, channel_name=self.channel_name)
        if isinstance(shaped, Awaitable):
            shaped = await shaped
        return shaped.result


class _DiscordRecorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.json_payloads: list[Any] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.content:
                self.json_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"ok": True})

        return httpx.MockTransport(handler)


def test_discord_isolation_key_scopes_to_guild_channel_user() -> None:
    assert discord_isolation_key("guild", "channel", "user") == "discord:guild:channel:user"
    assert discord_isolation_key(None, "dm-channel", "user") == "discord:dm:dm-channel:user"


def test_ping_requires_valid_signature_and_returns_pong() -> None:
    signing_key = SigningKey.generate()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=signing_key.verify_key.encode().hex(),
        register_commands=False,
    )
    app = Starlette(routes=list(channel.contribute(_FakeContext()).routes))  # type: ignore[arg-type]
    body = json.dumps({"type": 1}).encode("utf-8")

    with TestClient(app) as client:
        ok = client.post("/", content=body, headers=_headers(signing_key, body))
        bad = client.post(
            "/",
            content=body,
            headers={
                **_headers(signing_key, body),
                "x-signature-ed25519": "00" * 64,
            },
        )

    assert ok.status_code == 200
    assert ok.json() == {"type": 1}
    assert bad.status_code == 401


def test_request_validation_errors() -> None:
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        skip_signature_verification=True,
        max_body_bytes=2,
    )
    app = Starlette(routes=list(channel.contribute(_FakeContext()).routes))  # type: ignore[arg-type]
    unsupported_channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        skip_signature_verification=True,
    )
    unsupported_app = Starlette(routes=list(unsupported_channel.contribute(_FakeContext()).routes))  # type: ignore[arg-type]

    with TestClient(app) as client:
        too_large = client.post("/", content=b"{}x")
        invalid_json = client.post("/", content=b"{")
    with TestClient(unsupported_app) as client:
        non_object = client.post("/", json=[])
        unsupported = client.post("/", json={"type": 99})

    assert too_large.status_code == 413
    assert invalid_json.status_code == 400
    assert non_object.status_code == 400
    assert unsupported.status_code == 400


def test_constructor_validates_discord_configuration() -> None:
    public_key = SigningKey.generate().verify_key.encode().hex()

    with pytest.raises(ValueError, match="public_key"):
        DiscordChannel(application_id="app-1", public_key="not-hex")
    with pytest.raises(ValueError, match="command names"):
        DiscordChannel(application_id="app-1", public_key=public_key, agent_command="Ask")
    with pytest.raises(ValueError, match="unique"):
        DiscordChannel(
            application_id="app-1",
            public_key=public_key,
            commands=[ChannelCommand(name="ask", description="Ask again", handle=lambda _ctx: _noop())],
        )
    with pytest.raises(ValueError, match="edit_interval"):
        DiscordChannel(application_id="app-1", public_key=public_key, edit_interval=-1)
    with pytest.raises(ValueError, match="max_body_bytes"):
        DiscordChannel(application_id="app-1", public_key=public_key, max_body_bytes=0)


async def test_agent_command_runs_host_and_edits_original_response() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext(text="agent says hi")
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        skip_signature_verification=True,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(prompt="what now?"), "token")

    assert context.requests[0].operation == "message.create"
    assert context.requests[0].input == "what now?"
    assert context.requests[0].session is not None
    assert context.requests[0].session.isolation_key == "discord:guild-1:channel-1:user-1"
    assert context.requests[0].identity is not None
    assert context.requests[0].identity.native_id == "user-1"
    assert context.requests[0].identity.attributes["channel_id"] == "channel-1"
    assert recorder.requests[0].method == "PATCH"
    assert recorder.requests[0].url.path == "/webhooks/app-1/token/messages/@original"
    assert recorder.json_payloads[0] == {"content": "agent says hi"}


async def test_run_hook_can_rewrite_agent_request() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext(text="agent says hi")

    async def hook(request: ChannelRequest, **_: Any) -> ChannelRequest:
        return ChannelRequest(
            channel=request.channel,
            operation=request.operation,
            input="rewritten",
            session=request.session,
            metadata=request.metadata,
            attributes=request.attributes,
            stream=request.stream,
            identity=request.identity,
        )

    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        run_hook=hook,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(prompt="original"), "token")

    assert context.requests[0].input == "rewritten"


async def test_response_hook_rewrites_originating_reply() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext(text="original")

    async def hook(result: HostedRunResult[Any], **kwargs: Any) -> HostedRunResult[Any]:
        assert result.result.text == "original"
        assert kwargs["channel_name"] == "discord"
        return _run_result("rewritten")

    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        response_hook=hook,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(), "token")

    assert recorder.json_payloads[-1] == {"content": "rewritten"}


async def test_missing_prompt_edits_original_without_calling_host() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext(text="should not run")
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())
    interaction = _interaction()
    interaction["data"]["options"] = []

    await channel._run_agent_command(interaction, "token")

    assert context.requests == []
    assert recorder.json_payloads[-1] == {"content": "Missing required `prompt` option."}


async def test_dispatch_application_command_routes_agent_command() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext(text="dispatched")
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._dispatch_application_command(_interaction(command="ask"))

    assert context.requests[0].operation == "message.create"
    assert recorder.json_payloads[-1] == {"content": "dispatched"}


async def test_channel_command_handler_receives_context_and_replies() -> None:
    recorder = _DiscordRecorder()
    captured: list[ChannelCommandContext] = []

    async def handler(ctx: ChannelCommandContext) -> None:
        captured.append(ctx)
        await ctx.reply("reset done")

    command = ChannelCommand(name="reset", description="Reset", handle=handler)
    context = _FakeContext()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        commands=[command],
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())
    interaction = _interaction(command="reset")
    interaction["data"]["options"] = [{"name": "input", "type": 3, "value": "please"}]

    await channel._run_channel_command(command, interaction, "token")

    assert captured
    assert captured[0].request.operation == "command.invoke"
    assert captured[0].request.input == "/reset please"
    assert recorder.json_payloads == [{"content": "reset done"}]


async def test_channel_command_reply_sends_followups_after_first_edit() -> None:
    recorder = _DiscordRecorder()

    async def handler(ctx: ChannelCommandContext) -> None:
        await ctx.reply("first")
        await ctx.reply("second")

    command = ChannelCommand(name="reset", description="Reset", handle=handler)
    context = _FakeContext()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        commands=[command],
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_channel_command(command, _interaction(command="reset"), "token")

    assert [request.method for request in recorder.requests] == ["PATCH", "POST"]
    assert recorder.json_payloads == [{"content": "first"}, {"content": "second"}]


async def test_channel_command_reply_chunks_long_content() -> None:
    recorder = _DiscordRecorder()

    async def handler(ctx: ChannelCommandContext) -> None:
        await ctx.reply("a" * 2001)

    command = ChannelCommand(name="reset", description="Reset", handle=handler)
    context = _FakeContext()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        commands=[command],
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_channel_command(command, _interaction(command="reset"), "token")

    assert [request.method for request in recorder.requests] == ["PATCH", "POST"]
    assert [len(payload["content"]) for payload in recorder.json_payloads] == [2000, 1]


async def test_channel_command_edits_done_when_handler_does_not_reply() -> None:
    recorder = _DiscordRecorder()

    async def handler(_ctx: ChannelCommandContext) -> None:
        return None

    command = ChannelCommand(name="reset", description="Reset", handle=handler)
    context = _FakeContext()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        commands=[command],
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_channel_command(command, _interaction(command="reset"), "token")

    assert recorder.json_payloads == [{"content": "Done."}]


async def test_unknown_command_edits_error_response() -> None:
    recorder = _DiscordRecorder()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        api_base_url="https://discord.test",
    )
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._dispatch_application_command(_interaction(command="missing"))

    assert recorder.json_payloads == [{"content": "Unknown Discord command: missing"}]


async def test_startup_bulk_registers_guild_commands() -> None:
    recorder = _DiscordRecorder()
    command = ChannelCommand(name="reset", description="Reset", handle=lambda _ctx: _noop())
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        bot_token="bot-token",
        guild_id="guild-1",
        commands=[command],
        api_base_url="https://discord.test",
    )
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._on_startup()

    assert recorder.requests[0].method == "PUT"
    assert recorder.requests[0].url.path == "/applications/app-1/guilds/guild-1/commands"
    assert recorder.requests[0].headers["authorization"] == "Bot bot-token"
    assert [payload["name"] for payload in recorder.json_payloads[0]] == ["ask", "reset"]


async def test_global_startup_registration_warns_about_propagation(caplog: pytest.LogCaptureFixture) -> None:
    recorder = _DiscordRecorder()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        bot_token="bot-token",
        api_base_url="https://discord.test",
    )
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._on_startup()

    assert recorder.requests[0].url.path == "/applications/app-1/commands"
    assert "global slash commands" in caplog.text


async def test_startup_warns_when_registration_has_no_bot_token(caplog: pytest.LogCaptureFixture) -> None:
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
    )

    await channel._on_startup()
    await channel._on_shutdown()

    assert "slash commands must be registered outside the host" in caplog.text


async def test_originating_reply_sends_followup_chunks() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext(text="a" * 2001)
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(), "token")

    assert [request.method for request in recorder.requests] == ["PATCH", "POST"]
    assert [len(payload["content"]) for payload in recorder.json_payloads] == [2000, 1]


async def test_streaming_edits_original_and_delivers_final_response() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext()
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        streaming=True,
        edit_interval=0,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(), "token")

    assert [payload["content"] for payload in recorder.json_payloads] == ["a", "ab", "ab"]


async def test_streaming_preview_is_limited_and_final_reply_is_chunked() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext()
    context.fake_stream = _FakeStream(["a" * 2001])
    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        streaming=True,
        edit_interval=0,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(), "token")

    assert [request.method for request in recorder.requests] == ["PATCH", "PATCH", "POST"]
    assert [len(payload["content"]) for payload in recorder.json_payloads] == [2000, 2000, 1]


async def test_stream_update_hook_can_drop_updates() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext()

    async def hook(update: AgentResponseUpdate) -> AgentResponseUpdate | None:
        if update.text == "a":
            return None
        return update

    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        streaming=True,
        stream_update_hook=hook,
        edit_interval=0,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(), "token")

    assert [payload["content"] for payload in recorder.json_payloads] == ["b", "ab"]


async def test_stream_update_hook_can_synchronously_rewrite_updates() -> None:
    recorder = _DiscordRecorder()
    context = _FakeContext()

    def hook(_update: AgentResponseUpdate) -> AgentResponseUpdate:
        return AgentResponseUpdate(contents=[Content.from_text(text="x")], role="assistant")

    channel = DiscordChannel(
        application_id="app-1",
        public_key=SigningKey.generate().verify_key.encode().hex(),
        register_commands=False,
        streaming=True,
        stream_update_hook=hook,
        edit_interval=0,
        api_base_url="https://discord.test",
    )
    channel.contribute(context)  # type: ignore[arg-type]
    channel._http = httpx.AsyncClient(base_url="https://discord.test", transport=recorder.transport())

    await channel._run_agent_command(_interaction(), "token")

    assert [payload["content"] for payload in recorder.json_payloads] == ["x", "xx", "ab"]


async def _noop() -> None:
    return None
