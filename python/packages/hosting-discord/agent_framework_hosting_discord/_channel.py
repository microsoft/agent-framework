# Copyright (c) Microsoft. All rights reserved.

"""Discord HTTP Interactions channel."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from typing import Any, cast

import httpx
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream
from agent_framework_hosting import (
    ChannelCommand,
    ChannelCommandContext,
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamTransformHook,
    HostedRunResult,
    apply_channel_response_hook,
    apply_run_hook,
)
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

logger = logging.getLogger("agent_framework.hosting.discord")

DiscordInteraction = Mapping[str, Any]
DiscordIsolationKeyFactory = Callable[[DiscordInteraction], str]

_DISCORD_API_BASE = "https://discord.com/api/v10"
_DISCORD_MAX_BODY_BYTES = 1024 * 1024
_DISCORD_MAX_CONTENT_LEN = 2000
_INTERACTION_PING = 1
_INTERACTION_APPLICATION_COMMAND = 2
_RESPONSE_PONG = 1
_RESPONSE_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5
_OPTION_STRING = 3
_APPLICATION_COMMAND_CHAT_INPUT = 1
_COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def discord_isolation_key(guild_id: str | None, channel_id: str, user_id: str) -> str:
    """Build the default Discord isolation key.

    Args:
        guild_id: Discord guild id, or ``None`` for a DM interaction.
        channel_id: Discord channel or thread id.
        user_id: Discord user id.

    Returns:
        A stable host isolation key scoped to guild/channel/user.
    """
    scope = guild_id or "dm"
    return f"discord:{scope}:{channel_id}:{user_id}"


def _default_isolation_key(interaction: DiscordInteraction) -> str:
    user = _user_from_interaction(interaction)
    user_id = _require_string(user.get("id"), "interaction user id")
    channel_id = _require_string(interaction.get("channel_id"), "interaction channel_id")
    guild_id = _string_or_none(interaction.get("guild_id"))
    return discord_isolation_key(guild_id, channel_id, user_id)


def _text_result(text: str) -> HostedRunResult[AgentResponse]:
    """Build a host delivery payload from text accumulated by this channel."""
    return HostedRunResult(AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(text=text)])]))


class DiscordChannel:
    """Discord channel backed by signed HTTP Interactions."""

    name = "discord"

    def __init__(
        self,
        *,
        application_id: str,
        public_key: str,
        bot_token: str | None = None,
        guild_id: str | None = None,
        path: str = "/discord",
        agent_command: str = "ask",
        agent_command_description: str = "Ask the agent",
        agent_command_option: str = "prompt",
        register_commands: bool = True,
        commands: Sequence[ChannelCommand] = (),
        run_hook: ChannelRunHook | None = None,
        response_hook: ChannelResponseHook | None = None,
        stream_transform_hook: ChannelStreamTransformHook | None = None,
        streaming: bool = False,
        isolation_key_factory: DiscordIsolationKeyFactory | None = None,
        skip_signature_verification: bool = False,
        edit_interval: float = 1.0,
        max_body_bytes: int = _DISCORD_MAX_BODY_BYTES,
        api_base_url: str = _DISCORD_API_BASE,
    ) -> None:
        """Configure the Discord channel.

        Keyword Args:
            application_id: Discord application id.
            public_key: Discord application public key as lowercase or
                uppercase hex. Used to verify interaction signatures.
            bot_token: Bot token used to register slash commands and push
                messages to Discord channel ids. Interaction webhook replies
                do not require this token.
            guild_id: Optional guild id for guild-scoped slash command
                registration. Recommended for development because global
                command registration can take a long time to propagate.
            path: Host mount path. The interaction route is contributed as
                ``/interactions`` below this path.
            agent_command: Slash command name that invokes the hosted agent.
            agent_command_description: Description for the agent slash command.
            agent_command_option: String option name that carries the prompt.
            register_commands: Whether startup should register slash commands
                through Discord REST when ``bot_token`` is configured.
            commands: Additional host ``ChannelCommand`` instances to expose
                as Discord slash commands.
            run_hook: Optional hook that can rewrite the channel request before
                it reaches the host.
            response_hook: Optional hook that can rewrite the hosted result
                before the originating Discord response is serialized.
            stream_transform_hook: Optional per-update transform hook applied
                while streaming.
            streaming: Whether the agent command should call ``run_stream``
                and edit the original interaction response as deltas arrive.
            isolation_key_factory: Optional callable that receives the raw
                Discord interaction and returns a host isolation key.
            skip_signature_verification: Disable Ed25519 verification. Use
                only for local tests; never expose publicly with this enabled.
            edit_interval: Minimum seconds between streaming edits to the
                original Discord interaction response.
            max_body_bytes: Maximum raw interaction request body size.
            api_base_url: Discord API base URL. Primarily useful for tests.

        Raises:
            ValueError: If public key hex or command names are invalid, or if
                command names collide.
        """
        self.application_id = application_id
        self.public_key = public_key
        self.bot_token = bot_token
        self.guild_id = guild_id
        self.path = path
        self.agent_command = agent_command
        self.agent_command_description = agent_command_description
        self.agent_command_option = agent_command_option
        self.register_commands = register_commands
        self._commands = tuple(commands)
        self._command_by_name = {command.name: command for command in self._commands}
        self._run_hook = run_hook
        self.response_hook = response_hook
        self._stream_transform_hook = stream_transform_hook
        self._streaming = streaming
        self._isolation_key_factory = isolation_key_factory or _default_isolation_key
        self._skip_signature_verification = skip_signature_verification
        self._edit_interval = edit_interval
        self._max_body_bytes = max_body_bytes
        self._api_base_url = api_base_url.rstrip("/")
        self._ctx: ChannelContext | None = None
        self._http: httpx.AsyncClient | None = None
        self._tasks: set[asyncio.Task[None]] = set()

        self._validate_configuration()
        try:
            self._verify_key = VerifyKey(bytes.fromhex(public_key))
        except ValueError as exc:
            raise ValueError("DiscordChannel public_key must be a valid Ed25519 public key hex string") from exc

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Register the Discord interaction route and lifecycle hooks."""
        self._ctx = context
        return ChannelContribution(
            routes=[Route("/interactions", self._handle, methods=["POST"])],
            commands=self._commands,
            on_startup=[self._on_startup],
            on_shutdown=[self._on_shutdown],
        )

    async def push(self, identity: ChannelIdentity, payload: HostedRunResult[Any]) -> None:
        """Push a hosted result to a Discord channel.

        Args:
            identity: Destination identity. ``identity.attributes`` must carry
                ``channel_id``.
            payload: Hosted run result to render as Discord message text.

        Raises:
            RuntimeError: If the channel has no bot token for Discord REST.
            ValueError: If ``channel_id`` is missing from the identity.
        """
        channel_id = _string_or_none(identity.attributes.get("channel_id"))
        if channel_id is None:
            raise ValueError("Discord push requires identity.attributes['channel_id']")
        if self.bot_token is None:
            raise RuntimeError("DiscordChannel.push requires bot_token to send channel messages")
        await self._send_channel_messages(channel_id, _payload_text(payload))

    async def _on_startup(self) -> None:
        """Open the Discord REST client and optionally register slash commands."""
        self._ensure_http()
        if self._skip_signature_verification:
            logger.warning(
                "DiscordChannel running with skip_signature_verification=True. "
                "Use only for local tests; public Discord endpoints must verify signatures."
            )
        if not self.register_commands:
            return
        if self.bot_token is None:
            logger.warning(
                "DiscordChannel register_commands=True but bot_token is not configured; "
                "slash commands must be registered outside the host."
            )
            return
        if self.guild_id is None:
            logger.warning(
                "DiscordChannel registering global slash commands; Discord can take a long time "
                "to propagate global command changes. Set guild_id for faster development updates."
            )
        try:
            await self._register_commands()
        except (RuntimeError, httpx.HTTPError):
            logger.exception("DiscordChannel slash command registration failed; continuing startup")

    async def _on_shutdown(self) -> None:
        """Drain in-flight interaction tasks and close the Discord REST client."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _handle(self, request: Request) -> Response:
        """Handle one Discord interaction webhook request."""
        raw_body = await request.body()
        if len(raw_body) > self._max_body_bytes:
            return JSONResponse({"error": "request body too large"}, status_code=413)
        if not self._skip_signature_verification and not self._verify_signature(request, raw_body):
            return JSONResponse({"error": "invalid signature"}, status_code=401)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        if not isinstance(body, Mapping):
            return JSONResponse({"error": "interaction body must be a JSON object"}, status_code=400)
        interaction = cast("DiscordInteraction", body)

        interaction_type = interaction.get("type")
        if interaction_type == _INTERACTION_PING:
            return JSONResponse({"type": _RESPONSE_PONG})
        if interaction_type != _INTERACTION_APPLICATION_COMMAND:
            return JSONResponse({"error": f"unsupported interaction type: {interaction_type!r}"}, status_code=400)

        self._schedule(self._dispatch_application_command(interaction))
        return JSONResponse({"type": _RESPONSE_DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE})

    async def _dispatch_application_command(self, interaction: DiscordInteraction) -> None:
        token = _require_string(interaction.get("token"), "interaction token")
        try:
            name = _application_command_name(interaction)
            if name == self.agent_command:
                await self._run_agent_command(interaction, token)
                return
            command = self._command_by_name.get(name)
            if command is None:
                await self._edit_original(token, f"Unknown Discord command: {name}")
                return
            await self._run_channel_command(command, interaction, token)
        except Exception:
            logger.exception("DiscordChannel interaction handling failed")
            await self._try_edit_original(token, "Sorry, something went wrong while handling that Discord command.")
            raise

    async def _run_agent_command(self, interaction: DiscordInteraction, token: str) -> None:
        if self._ctx is None:
            raise RuntimeError("DiscordChannel was not contributed to a host.")
        prompt = _string_option(interaction, self.agent_command_option)
        if prompt is None:
            await self._edit_original(token, f"Missing required `{self.agent_command_option}` option.")
            return
        request = self._build_request(
            interaction,
            operation="message.create",
            input_value=prompt,
            stream=self._streaming,
        )
        if self._run_hook is not None:
            request = await apply_run_hook(
                self._run_hook,
                request,
                target=self._ctx.target,
                protocol_request=interaction,
            )
        if request.stream:
            await self._run_streaming(request, token)
            return
        result = await self._ctx.run(request)
        include_originating = await self._ctx.deliver_response(request, result)
        if include_originating:
            result = await apply_channel_response_hook(self, result, request=request, originating=True)
            await self._edit_original_with_result(token, result)
        else:
            await self._edit_original(token, "Sent.")

    async def _run_channel_command(
        self,
        command: ChannelCommand,
        interaction: DiscordInteraction,
        token: str,
    ) -> None:
        command_input = _string_option(interaction, "input")
        request = self._build_request(
            interaction,
            operation="command.invoke",
            input_value=f"/{command.name}" if command_input is None else f"/{command.name} {command_input}",
            stream=False,
        )
        reply = _DiscordInteractionReply(self, token)
        await command.handle(ChannelCommandContext(request=request, reply=reply))
        if not reply.sent:
            await self._edit_original(token, "Done.")

    async def _run_streaming(self, request: ChannelRequest, token: str) -> None:
        if self._ctx is None:
            raise RuntimeError("DiscordChannel was not contributed to a host.")
        stream: ResponseStream[AgentResponseUpdate, AgentResponse] = self._ctx.run_stream(request)
        accumulated: list[str] = []
        last_edit = 0.0
        async for update in stream:
            transformed: AgentResponseUpdate | None = update
            if self._stream_transform_hook is not None:
                maybe = self._stream_transform_hook(update)
                if isinstance(maybe, Awaitable):
                    transformed = await cast("Awaitable[AgentResponseUpdate | None]", maybe)
                else:
                    transformed = maybe
            if transformed is None:
                continue
            chunk = _update_text(transformed)
            if not chunk:
                continue
            accumulated.append(chunk)
            now = time.monotonic()
            if self._edit_interval <= 0 or now - last_edit >= self._edit_interval:
                await self._edit_original(token, _stream_preview_content("".join(accumulated)))
                last_edit = now

        final = _text_result("".join(accumulated))
        include_originating = await self._ctx.deliver_response(request, final)
        if include_originating:
            final = await apply_channel_response_hook(self, final, request=request, originating=True)
            await self._edit_original_with_result(token, final)
        else:
            await self._edit_original(token, "Sent.")

    def _build_request(
        self,
        interaction: DiscordInteraction,
        *,
        operation: str,
        input_value: Any,
        stream: bool,
    ) -> ChannelRequest:
        identity = self._identity_from_interaction(interaction)
        command_name = _application_command_name(interaction)
        metadata = {
            "interaction_id": _string_or_none(interaction.get("id")),
            "application_id": self.application_id,
            "guild_id": _string_or_none(interaction.get("guild_id")),
            "channel_id": _string_or_none(interaction.get("channel_id")),
            "user_id": identity.native_id,
            "command": command_name,
        }
        clean_metadata = {key: value for key, value in metadata.items() if value is not None}
        return ChannelRequest(
            channel=self.name,
            operation=operation,
            input=input_value,
            session=ChannelSession(isolation_key=self._isolation_key_factory(interaction)),
            metadata=clean_metadata,
            attributes=clean_metadata,
            stream=stream,
            identity=identity,
        )

    def _identity_from_interaction(self, interaction: DiscordInteraction) -> ChannelIdentity:
        user = _user_from_interaction(interaction)
        user_id = _require_string(user.get("id"), "interaction user id")
        attributes = {
            "username": _string_or_none(user.get("username")),
            "global_name": _string_or_none(user.get("global_name")),
            "guild_id": _string_or_none(interaction.get("guild_id")),
            "channel_id": _string_or_none(interaction.get("channel_id")),
            "application_id": self.application_id,
        }
        return ChannelIdentity(
            channel=self.name,
            native_id=user_id,
            attributes={key: value for key, value in attributes.items() if value is not None},
        )

    def _verify_signature(self, request: Request, raw_body: bytes) -> bool:
        signature = request.headers.get("x-signature-ed25519")
        timestamp = request.headers.get("x-signature-timestamp")
        if not signature or not timestamp:
            return False
        try:
            self._verify_key.verify(timestamp.encode("utf-8") + raw_body, bytes.fromhex(signature))
        except (BadSignatureError, ValueError):
            return False
        return True

    def _schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("DiscordChannel background task failed")

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self._api_base_url, timeout=30.0)
        return self._http

    async def _register_commands(self) -> None:
        http = self._ensure_http()
        path = f"/applications/{self.application_id}/commands"
        if self.guild_id is not None:
            path = f"/applications/{self.application_id}/guilds/{self.guild_id}/commands"
        response = await http.put(path, headers=self._bot_headers(), json=self._command_payloads())
        _raise_for_discord_error(response, "register slash commands")

    async def _edit_original_with_result(self, token: str, payload: HostedRunResult[Any]) -> None:
        chunks = _split_content(_payload_text(payload))
        await self._edit_original(token, chunks[0])
        for chunk in chunks[1:]:
            await self._send_followup(token, chunk)

    async def _edit_original(self, token: str, content: str) -> None:
        http = self._ensure_http()
        response = await http.patch(
            f"/webhooks/{self.application_id}/{token}/messages/@original",
            json={"content": _normalize_content(content)},
        )
        _raise_for_discord_error(response, "edit interaction response")

    async def _try_edit_original(self, token: str, content: str) -> None:
        try:
            await self._edit_original(token, content)
        except (RuntimeError, httpx.HTTPError):
            logger.exception("DiscordChannel failed to edit interaction error response")

    async def _send_followup(self, token: str, content: str) -> None:
        http = self._ensure_http()
        response = await http.post(
            f"/webhooks/{self.application_id}/{token}",
            json={"content": _normalize_content(content)},
        )
        _raise_for_discord_error(response, "send interaction follow-up")

    async def _send_channel_messages(self, channel_id: str, content: str) -> None:
        http = self._ensure_http()
        for chunk in _split_content(content):
            response = await http.post(
                f"/channels/{channel_id}/messages",
                headers=self._bot_headers(),
                json={"content": chunk},
            )
            _raise_for_discord_error(response, "send channel message")

    def _bot_headers(self) -> dict[str, str]:
        if self.bot_token is None:
            raise RuntimeError("Discord bot token is required for this operation")
        return {"Authorization": f"Bot {self.bot_token}"}

    def _command_payloads(self) -> list[dict[str, Any]]:
        payloads = [
            {
                "type": _APPLICATION_COMMAND_CHAT_INPUT,
                "name": self.agent_command,
                "description": self.agent_command_description,
                "options": [
                    {
                        "type": _OPTION_STRING,
                        "name": self.agent_command_option,
                        "description": "Prompt for the agent.",
                        "required": True,
                    }
                ],
            }
        ]
        for command in self._commands:
            payloads.append({
                "type": _APPLICATION_COMMAND_CHAT_INPUT,
                "name": command.name,
                "description": command.description,
                "options": [
                    {
                        "type": _OPTION_STRING,
                        "name": "input",
                        "description": "Optional command input.",
                        "required": False,
                    }
                ],
            })
        return payloads

    def _validate_configuration(self) -> None:
        names = [self.agent_command, *(command.name for command in self._commands)]
        for name in names:
            if not _COMMAND_NAME_RE.fullmatch(name):
                raise ValueError(
                    "Discord command names must be lowercase ASCII letters, numbers, hyphen, "
                    f"or underscore, and 1-32 characters long: {name!r}"
                )
        if not _COMMAND_NAME_RE.fullmatch(self.agent_command_option):
            raise ValueError(
                "Discord agent_command_option must be lowercase ASCII letters, numbers, hyphen, "
                f"or underscore, and 1-32 characters long: {self.agent_command_option!r}"
            )
        if len(set(names)) != len(names):
            raise ValueError("Discord command names must be unique; agent_command cannot collide with commands")
        if self._edit_interval < 0:
            raise ValueError("edit_interval must be >= 0")
        if self._max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be > 0")


class _DiscordInteractionReply:
    """Reply helper that edits the deferred response first, then sends follow-ups."""

    def __init__(self, channel: DiscordChannel, token: str) -> None:
        self._channel = channel
        self._token = token
        self.sent = False

    async def __call__(self, body: str) -> None:
        chunks = _split_content(body)
        if not self.sent:
            await self._channel._edit_original(self._token, chunks[0])  # pyright: ignore[reportPrivateUsage]
            self.sent = True
            for chunk in chunks[1:]:
                await self._channel._send_followup(self._token, chunk)  # pyright: ignore[reportPrivateUsage]
            return
        for chunk in chunks:
            await self._channel._send_followup(self._token, chunk)  # pyright: ignore[reportPrivateUsage]


def _user_from_interaction(interaction: DiscordInteraction) -> Mapping[str, Any]:
    member = interaction.get("member")
    if isinstance(member, Mapping):
        member_user = member.get("user")
        if isinstance(member_user, Mapping):
            return member_user
    user = interaction.get("user")
    if isinstance(user, Mapping):
        return user
    raise ValueError("Discord interaction is missing user information")


def _application_command_name(interaction: DiscordInteraction) -> str:
    data = interaction.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("Discord application command interaction is missing data")
    return _require_string(data.get("name"), "application command name")


def _string_option(interaction: DiscordInteraction, name: str) -> str | None:
    data = interaction.get("data")
    if not isinstance(data, Mapping):
        return None
    options = data.get("options")
    if not isinstance(options, Sequence) or isinstance(options, (str, bytes)):
        return None
    for option in options:
        if not isinstance(option, Mapping):
            continue
        if option.get("name") != name:
            continue
        value = option.get("value")
        if value is None:
            return None
        return str(value)
    return None


def _payload_text(payload: HostedRunResult[Any]) -> str:
    text = getattr(payload.result, "text", None)
    if isinstance(text, str) and text:
        return text
    messages = getattr(payload.result, "messages", None)
    if isinstance(messages, Sequence):
        for message in reversed(messages):
            message_text = getattr(message, "text", None)
            if isinstance(message_text, str) and message_text:
                return message_text
    return "(no response)"


def _update_text(update: AgentResponseUpdate) -> str:
    parts: list[str] = []
    for content in update.contents:
        text = getattr(content, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts)


def _split_content(content: str) -> list[str]:
    normalized = _normalize_content(content)
    return [normalized[i : i + _DISCORD_MAX_CONTENT_LEN] for i in range(0, len(normalized), _DISCORD_MAX_CONTENT_LEN)]


def _stream_preview_content(content: str) -> str:
    return _split_content(content)[0]


def _normalize_content(content: str) -> str:
    return content if content else "(no response)"


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _require_string(value: Any, field_name: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Discord {field_name} must be a non-empty string")


def _raise_for_discord_error(response: httpx.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:500]
        raise RuntimeError(f"Discord {action} failed with HTTP {response.status_code}: {body}") from exc
