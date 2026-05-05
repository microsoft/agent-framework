# Copyright (c) Microsoft. All rights reserved.

"""Built-in channel: Telegram (polling + webhook transports).

Inspired by PR #5393's Telegram sample. Two transports are supported:

- ``polling`` (default when no ``webhook_url`` is set): the channel runs a
  background ``getUpdates`` long-poll loop. No public URL required —
  perfect for local development. This is what ``python-telegram-bot``
  uses by default.
- ``webhook``: when ``webhook_url`` is set, the channel registers it via
  ``setWebhook`` on startup and receives updates over HTTPS POSTs to the
  mounted ``/webhook`` route. This is the production-recommended mode.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

import httpx
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    ResponseStream,
)
from agent_framework_hosting import (
    ChannelCommand,
    ChannelCommandContext,
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelRequest,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamTransformHook,
    HostedRunResult,
    apply_run_hook,
    logger,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

# Telegram update parsing ------------------------------------------------------
#
# A Telegram message can carry text, a caption, and one of several media kinds
# (photo, document, voice, audio, video). For media we resolve the file_id
# into a public bot-file URL via ``getFile`` and emit a ``Content.from_uri``;
# the agent then receives a multi-content Message with text + media side by
# side, the same as it would over the Responses API.

_TELEGRAM_MEDIA_DEFAULT_MIMETYPE = {
    "photo": "image/jpeg",
    "document": "application/octet-stream",
    "voice": "audio/ogg",
    "audio": "audio/mpeg",
    "video": "video/mp4",
}

# Telegram's hard limit on a single message body. Past this, sendMessage /
# editMessageText return 400. We truncate interim and final edits at this
# boundary; if the agent emits more, callers can split into a follow-up
# sendMessage in their run hook.
_TELEGRAM_MAX_TEXT_LEN = 4096


def telegram_isolation_key(chat_id: Any) -> str:
    """Build the namespaced isolation key the Telegram channel writes under.

    Exposed at module scope so other channels' ``run_hook`` callbacks can opt
    into the same per-chat session (e.g. a Responses caller resuming a
    Telegram conversation by passing the chat id).
    """
    return f"telegram:{chat_id}"


def _telegram_media_file_id(message: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return ``(file_id, fallback_media_type)`` for any media on the message."""
    photo = message.get("photo")
    if isinstance(photo, list) and photo:
        # Telegram delivers photos as an array of progressively-larger sizes.
        largest = photo[-1]
        if isinstance(largest, Mapping) and (fid := largest.get("file_id")):
            return str(fid), _TELEGRAM_MEDIA_DEFAULT_MIMETYPE["photo"]
    for kind in ("document", "voice", "audio", "video"):
        media = message.get(kind)
        if media and isinstance(media, Mapping) and (fid := media.get("file_id")):
            return str(fid), str(media.get("mime_type") or _TELEGRAM_MEDIA_DEFAULT_MIMETYPE[kind])
    return None


async def _parse_telegram_message(
    message: Mapping[str, Any],
    resolve_file_url: Callable[[str], Awaitable[str | None]],
) -> Message:
    """Translate one Telegram ``message`` object into an Agent Framework Message."""
    parts: list[Content] = []
    if (text := message.get("text") or message.get("caption")) and isinstance(text, str):
        parts.append(Content.from_text(text=text))

    if (media := _telegram_media_file_id(message)) is not None:
        file_id, media_type = media
        if (uri := await resolve_file_url(file_id)) is not None:
            parts.append(Content.from_uri(uri=uri, media_type=media_type))

    if not parts:
        # Edge case: no recognizable content — emit an empty placeholder so the
        # agent contract still receives a Message and can react gracefully.
        parts.append(Content.from_text(text=""))
    return Message("user", parts)


class TelegramChannel:
    """Telegram channel with both polling and webhook transports.

    Update kinds handled (both transports):
    - ``message`` / ``edited_message``  — text, captions, and media
      (photo/document/voice/audio/video).
    - ``callback_query``  — inline-button presses; the ``data`` payload is
      treated as the user's next utterance and the click is acknowledged.

    Streaming
    ---------
    The channel defaults to ``stream=True`` on every ``ChannelRequest``: it
    drives ``ChannelContext.run_stream`` and progressively edits a single
    Telegram message as ``AgentResponseUpdate`` chunks arrive (Telegram has
    no native streaming primitive). Pass ``stream=False`` on the constructor
    to opt out for all messages, or override per-request inside the
    ``run_hook`` (set ``ChannelRequest.stream = False``). A ``stream_transform_hook``
    can rewrite or drop individual updates before they hit the wire — useful
    for redaction, formatting, or merging tool-call deltas.
    """

    name = "telegram"

    def __init__(
        self,
        *,
        bot_token: str,
        path: str = "/telegram",
        commands: Sequence[ChannelCommand] = (),
        register_native_commands: bool = True,
        run_hook: ChannelRunHook | None = None,
        api_base: str = "https://api.telegram.org",
        webhook_url: str | None = None,
        secret_token: str | None = None,
        parse_mode: str | None = None,
        send_typing_action: bool = True,
        transport: Literal["auto", "polling", "webhook"] = "auto",
        polling_timeout: int = 30,
        stream: bool = True,
        stream_transform_hook: ChannelStreamTransformHook | None = None,
        stream_edit_min_interval: float = 0.4,
    ) -> None:
        self.path = path
        self._token = bot_token
        self._commands = list(commands)
        self._register = register_native_commands
        self._hook = run_hook
        self._stream_default = stream
        self._stream_transform_hook = stream_transform_hook
        self._stream_edit_min_interval = stream_edit_min_interval
        self._api = f"{api_base}/bot{bot_token}"
        self._webhook_url = webhook_url
        self._secret_token = secret_token
        self._parse_mode = parse_mode
        self._send_typing_action = send_typing_action
        if transport == "auto":
            transport = "webhook" if webhook_url else "polling"
        if transport == "webhook" and not webhook_url:
            raise ValueError("transport='webhook' requires webhook_url")
        self._transport: Literal["polling", "webhook"] = transport
        self._polling_timeout = polling_timeout
        self._ctx: ChannelContext | None = None
        self._http: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._update_tasks: set[asyncio.Task[None]] = set()

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Register the webhook route (only in ``webhook`` transport) plus lifecycle hooks.

        Polling-mode hosts intentionally expose no HTTP route — adding one
        would just confuse readers who expect inbound HTTP traffic to do
        something.
        """
        self._ctx = context
        routes: list[BaseRoute] = []
        if self._transport == "webhook":
            routes.append(Route("/webhook", self._handle, methods=["POST"]))
        return ChannelContribution(
            routes=routes,
            commands=self._commands,
            on_startup=[self._on_startup],
            on_shutdown=[self._on_shutdown],
        )

    # -- lifecycle --------------------------------------------------------- #

    async def _on_startup(self) -> None:
        """Open the HTTP client, optionally register slash commands, and start the transport.

        - Polling: clears any previously-set webhook (Telegram refuses
          ``getUpdates`` while one is registered) and launches the
          long-poll task.
        - Webhook: ``setWebhook`` to the configured URL, including the
          optional secret token used to authenticate inbound calls.
        """
        # ``getUpdates`` blocks for up to ``polling_timeout`` seconds, so the
        # client timeout has to comfortably exceed it. Skip when a client has
        # been pre-injected (e.g. by tests).
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._polling_timeout + 15)
        if self._register and self._commands:
            cmd_payload: dict[str, Any] = {
                "commands": [{"command": c.name, "description": c.description} for c in self._commands]
            }
            await self._http.post(f"{self._api}/setMyCommands", json=cmd_payload)
            logger.info("Registered %d Telegram commands", len(self._commands))

        if self._transport == "webhook":
            payload: dict[str, Any] = {
                "url": self._webhook_url,
                "allowed_updates": ["message", "edited_message", "callback_query"],
            }
            if self._secret_token:
                payload["secret_token"] = self._secret_token
            response = await self._http.post(f"{self._api}/setWebhook", json=payload)
            response.raise_for_status()
            logger.info("Telegram webhook registered: %s", self._webhook_url)
        else:
            # Telegram refuses getUpdates while a webhook is set, so clear it.
            await self._http.post(f"{self._api}/deleteWebhook", json={"drop_pending_updates": False})
            self._poll_task = asyncio.create_task(self._poll_loop(), name="telegram-poll")
            logger.info("Telegram polling started (long-poll timeout=%ss)", self._polling_timeout)

    async def _on_shutdown(self) -> None:
        """Stop the polling task, drop the webhook registration, close the HTTP client.

        Webhook teardown is best-effort — failures (e.g. revoked token at
        shutdown) are logged but never raised so app shutdown can complete.
        """
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._poll_task
            self._poll_task = None
        if self._http is not None:
            if self._transport == "webhook":
                try:
                    await self._http.post(f"{self._api}/deleteWebhook")
                except Exception:  # pragma: no cover - best-effort cleanup
                    logger.exception("deleteWebhook failed")
            await self._http.aclose()

    # -- polling loop ------------------------------------------------------ #

    async def _poll_loop(self) -> None:
        """Long-poll ``getUpdates`` until cancelled.

        Each batch advances the ``offset`` by the highest seen
        ``update_id`` so processed updates aren't redelivered. Updates are
        dispatched to per-update tasks so a slow agent invocation cannot
        block the next poll iteration; ordering inside a chat is still
        preserved by Telegram-side queueing. Transient errors back off for
        2 seconds before retrying.
        """
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        offset: int | None = None
        while True:
            try:
                params: dict[str, Any] = {
                    "timeout": self._polling_timeout,
                    "allowed_updates": '["message","edited_message","callback_query"]',
                }
                if offset is not None:
                    params["offset"] = offset
                response = await self._http.get(f"{self._api}/getUpdates", params=params)
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    logger.warning("Telegram getUpdates returned error: %s", payload)
                    await asyncio.sleep(1.0)
                    continue
                for update in payload.get("result", []) or []:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = update_id + 1
                    # Each update is processed in its own task so a slow agent
                    # call doesn't stall the next poll. Order within a chat is
                    # still preserved by Telegram-side queueing.
                    task = asyncio.create_task(self._safe_process_update(update))
                    self._update_tasks.add(task)
                    task.add_done_callback(self._update_tasks.discard)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram polling iteration failed; retrying in 2s")
                await asyncio.sleep(2.0)

    async def _safe_process_update(self, update: Mapping[str, Any]) -> None:
        """Wrap :meth:`_process_update` so a failure on one update never escapes a task."""
        try:
            await self._process_update(update)
        except Exception:
            logger.exception("Telegram update processing failed: %s", update.get("update_id"))

    # -- request handling -------------------------------------------------- #

    async def _handle(self, request: Request) -> Response:
        """Webhook endpoint — verifies the secret token then queues the update.

        Telegram includes the configured secret in the
        ``X-Telegram-Bot-Api-Secret-Token`` header on every webhook delivery;
        we reject mismatches so leaked URLs alone aren't enough to inject
        traffic.
        """
        if self._secret_token is not None:
            received = request.headers.get("x-telegram-bot-api-secret-token")
            if received != self._secret_token:
                logger.warning("Telegram webhook secret token mismatch — rejecting update")
                return JSONResponse({"ok": False, "error": "invalid secret"}, status_code=401)

        update = await request.json()
        await self._safe_process_update(update)
        return JSONResponse({"ok": True})

    async def _process_update(self, update: Mapping[str, Any]) -> None:
        """Convert one Telegram update into a :class:`ChannelRequest` and dispatch.

        Branches:
        - ``callback_query`` — inline-button click; handled separately so we
          can ack the click and treat the button payload as the next user
          utterance.
        - ``message`` / ``edited_message`` — the common text-and-attachment
          case; runs slash commands when present, otherwise builds a
          message and dispatches to the agent.
        """
        if self._ctx is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")

        # Inline-button presses: ack the click, treat the payload as input.
        if (callback := update.get("callback_query")) is not None:
            await self._handle_callback_query(callback)
            return

        # message and edited_message share the same shape.
        message = update.get("message") or update.get("edited_message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = message.get("text") or message.get("caption")
        has_media = any(k in message for k in ("photo", "document", "voice", "audio", "video"))
        if chat_id is None or (not isinstance(text, str) and not has_media):
            return  # Nothing actionable.

        # Native command dispatch — bypasses the agent.
        if isinstance(text, str) and text.startswith("/"):
            command_name = text[1:].split()[0].split("@", 1)[0]
            handler = next((c for c in self._commands if c.name == command_name), None)
            if handler is not None:
                channel_request = ChannelRequest(
                    channel=self.name,
                    operation="command.invoke",
                    input=text,
                    session=ChannelSession(isolation_key=telegram_isolation_key(chat_id)),
                    attributes={"chat_id": chat_id},
                    identity=ChannelIdentity(channel=self.name, native_id=str(chat_id)),
                )
                ctx = ChannelCommandContext(
                    request=channel_request,
                    reply=lambda body, cid=chat_id: self._send(cid, body),
                )
                await handler.handle(ctx)
                return

        # Plain message → agent run. Build a multi-content Message with the
        # text/caption alongside any attached media (photo, document, ...).
        parsed = await _parse_telegram_message(message, self._resolve_file_url)
        channel_request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=[parsed],
            session=ChannelSession(isolation_key=telegram_isolation_key(chat_id)),
            attributes={"chat_id": chat_id},
            stream=self._stream_default,
            identity=ChannelIdentity(channel=self.name, native_id=str(chat_id)),
        )
        if self._hook is not None:
            channel_request = await apply_run_hook(
                self._hook,
                channel_request,
                target=self._ctx.target,
                protocol_request=update,
            )

        await self._dispatch(chat_id, channel_request)

    async def _handle_callback_query(self, callback: Mapping[str, Any]) -> None:
        """Handle an inline-button click.

        Always answers the callback query to clear the spinner on the user's
        client, then treats the button's ``data`` payload as the user's
        next utterance and dispatches it as if they had typed it.
        Callbacks without a chat or string ``data`` are silently dropped.
        """
        if self._ctx is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        callback_id = callback.get("id")
        data = callback.get("data")
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")

        if callback_id is not None:
            # Always answer to remove the loading spinner on the user's client.
            try:
                await self._http.post(f"{self._api}/answerCallbackQuery", json={"callback_query_id": callback_id})
            except Exception:  # pragma: no cover - defensive
                logger.exception("answerCallbackQuery failed")

        if chat_id is None or not isinstance(data, str):
            return

        channel_request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=data,
            session=ChannelSession(isolation_key=telegram_isolation_key(chat_id)),
            attributes={"chat_id": chat_id, "callback_query_id": callback_id},
            stream=self._stream_default,
            identity=ChannelIdentity(channel=self.name, native_id=str(chat_id)),
        )
        if self._hook is not None:
            channel_request = await apply_run_hook(
                self._hook,
                channel_request,
                target=self._ctx.target,
                protocol_request=callback,
            )

        await self._dispatch(chat_id, channel_request)

    async def _resolve_file_url(self, file_id: str) -> str | None:
        """Resolve a Telegram file_id into an HTTPS URL via getFile."""
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        try:
            response = await self._http.get(f"{self._api}/getFile", params={"file_id": file_id})
            response.raise_for_status()
            file_path = response.json().get("result", {}).get("file_path")
        except Exception:  # pragma: no cover - defensive: bad token, network, etc.
            logger.exception("getFile failed for %s", file_id)
            return None
        return f"{self._api.replace('/bot', '/file/bot')}/{file_path}" if file_path else None

    # -- outbound helpers -------------------------------------------------- #

    async def _dispatch(self, chat_id: int, request: ChannelRequest) -> None:
        """Run the request and forward results to ``chat_id``."""
        if self._ctx is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        if not request.stream:
            if self._send_typing_action:
                await self._send_chat_action(chat_id, "typing")
            result = await self._ctx.run(request)
            await self._reply_with_result(chat_id, result)
            return

        stream = self._ctx.run_stream(request)
        await self._stream_to_chat(chat_id, stream)

    async def _stream_to_chat(
        self,
        chat_id: int,
        stream: ResponseStream[AgentResponseUpdate, AgentResponse],
    ) -> None:
        """Iterate the agent's ResponseStream and progressively edit a Telegram message.

        Smoothness recipe:

        1. Send the placeholder message up front so the user sees instant
           activity (a "…" bubble) instead of waiting for the first edit.
        2. Token consumption never awaits the network — a background
           ``edit_worker`` watches an asyncio.Event, coalesces accumulated
           text, rate-limits itself to ``stream_edit_min_interval`` (default
           0.4s — well under Telegram's per-chat edit limits), and only sends
           when the text actually changed.
        3. Interim edits are sent as **plain text** even if a ``parse_mode``
           is configured. Partial Markdown/HTML mid-stream is invalid and
           Telegram rejects it with 400 ``can't parse entities``. The final
           edit re-applies the configured ``parse_mode`` so the user ends up
           with formatted output.
        4. ``sendChatAction("typing")`` is re-issued every 4s while the
           stream is live so the typing bubble doesn't disappear on long
           responses (Telegram clears it after ~5s).
        """
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        # Pin to a local so mypy narrows inside the nested closures below.
        http = self._http

        accumulated = ""
        last_sent = ""
        last_edit_at = 0.0
        message_id: int | None = None
        worker_done = asyncio.Event()
        wake = asyncio.Event()

        async def send_initial_placeholder() -> None:
            nonlocal message_id, last_edit_at
            try:
                response = await http.post(
                    f"{self._api}/sendMessage",
                    json={"chat_id": chat_id, "text": "…"},
                )
                response.raise_for_status()
                message_id = response.json().get("result", {}).get("message_id")
                last_edit_at = time.monotonic()
            except Exception:  # pragma: no cover - placeholder is best-effort
                logger.exception("Telegram placeholder send failed")

        async def edit_worker() -> None:
            nonlocal last_sent, last_edit_at
            while not (worker_done.is_set() and accumulated == last_sent):
                await wake.wait()
                wake.clear()
                if message_id is None or accumulated == last_sent:
                    continue
                elapsed = time.monotonic() - last_edit_at
                if elapsed < self._stream_edit_min_interval:
                    try:
                        await asyncio.wait_for(wake.wait(), timeout=self._stream_edit_min_interval - elapsed)
                        wake.clear()
                    except asyncio.TimeoutError:
                        pass
                snapshot = accumulated[:_TELEGRAM_MAX_TEXT_LEN]
                if snapshot == last_sent:
                    continue
                # Interim edits go out as plain text — partial Markdown/HTML
                # is invalid mid-stream and Telegram returns 400.
                try:
                    await http.post(
                        f"{self._api}/editMessageText",
                        json={"chat_id": chat_id, "message_id": message_id, "text": snapshot},
                    )
                except Exception:  # pragma: no cover - keep streaming on error
                    logger.exception("Telegram interim edit failed")
                last_sent = snapshot
                last_edit_at = time.monotonic()

        async def typing_worker() -> None:
            while not worker_done.is_set():
                await self._send_chat_action(chat_id, "typing")
                try:
                    await asyncio.wait_for(worker_done.wait(), timeout=4.0)
                except asyncio.TimeoutError:
                    continue

        await send_initial_placeholder()
        edit_task = asyncio.create_task(edit_worker(), name="telegram-edit-worker")
        typing_task = asyncio.create_task(typing_worker(), name="telegram-typing-worker")

        try:
            async for update in stream:
                if self._stream_transform_hook is not None:
                    transformed = self._stream_transform_hook(update)
                    if isinstance(transformed, Awaitable):
                        transformed = await transformed
                    if transformed is None:
                        continue
                    update = transformed
                chunk = getattr(update, "text", None)
                if chunk:
                    accumulated += chunk
                    wake.set()
        except Exception:
            logger.exception("Telegram streaming consumption failed")
        finally:
            worker_done.set()
            wake.set()
            try:
                await edit_task
            except Exception:  # pragma: no cover
                logger.exception("Telegram edit worker crashed")
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await typing_task

        # Always finalize so context providers / history hooks run.
        try:
            final = await stream.get_final_response()
        except Exception:  # pragma: no cover - finalize is best-effort
            logger.exception("Stream finalize failed")
            final = None

        # Final edit applies parse_mode (if configured) to the full text.
        final_text = (accumulated or last_sent)[:_TELEGRAM_MAX_TEXT_LEN]
        if message_id is not None and final_text and final_text != last_sent:
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": final_text,
            }
            if self._parse_mode:
                payload["parse_mode"] = self._parse_mode
            try:
                response = await self._http.post(f"{self._api}/editMessageText", json=payload)
                # If parse_mode rejected the final edit, retry as plain text
                # so the user still sees the answer.
                if response.status_code == 400 and self._parse_mode:
                    payload.pop("parse_mode", None)
                    await self._http.post(f"{self._api}/editMessageText", json=payload)
            except Exception:  # pragma: no cover
                logger.exception("Telegram final edit failed")

        # If nothing ever streamed (no text chunks at all), fall back to the
        # full result so images / tool outputs still reach the user.
        if not accumulated:
            await self._reply_with_result(chat_id, final)

    async def _reply_with_result(self, chat_id: int, result: Any) -> None:
        """Forward an AgentRunResponse back to Telegram.

        Sends any image attachments on the last assistant message as photos,
        then the text body via ``sendMessage``. Falls back to a ``"(no
        response)"`` placeholder if neither text nor images are present so
        the user is never left hanging.
        """
        sent_photo = False
        last_message = None
        messages = getattr(result, "messages", None) or []
        for msg in reversed(messages):
            if getattr(msg, "role", None) == "assistant":
                last_message = msg
                break

        if last_message is not None:
            for content in getattr(last_message, "contents", []) or []:
                uri = getattr(content, "uri", None)
                media_type = getattr(content, "media_type", "") or ""
                if uri and isinstance(media_type, str) and media_type.startswith("image/"):
                    await self._send_photo(chat_id, uri)
                    sent_photo = True

        text = getattr(result, "text", None)
        if text:
            await self._send(chat_id, text)
        elif not sent_photo:
            await self._send(chat_id, "(no response)")

    async def _send(self, chat_id: int, text: str, **extra: Any) -> None:
        """POST a ``sendMessage`` to Telegram, applying the configured ``parse_mode`` by default.

        Extra kwargs are merged into the payload after ``parse_mode`` so
        callers can override any field per-call (e.g. drop ``parse_mode``
        for a known-unsafe interim text).
        """
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if self._parse_mode and "parse_mode" not in extra:
            payload["parse_mode"] = self._parse_mode
        payload.update(extra)
        await self._http.post(f"{self._api}/sendMessage", json=payload)

    # -- ChannelPush -------------------------------------------------------- #

    async def push(self, identity: ChannelIdentity, payload: HostedRunResult) -> None:
        """Proactive delivery to a Telegram chat.

        Implements :class:`host.ChannelPush` so other channels' callers can
        target Telegram via ``ChannelRequest.response_target``
        (e.g. ``ResponseTarget.channels(["telegram:8741188429"])`` from a
        ``/responses`` request). ``identity.native_id`` is the Telegram
        chat id.
        """
        try:
            chat_id = int(identity.native_id)
        except ValueError as exc:
            raise ValueError(f"Telegram push requires an int chat_id, got {identity.native_id!r}") from exc
        if self._http is None:
            raise RuntimeError("TelegramChannel.push called before startup")
        await self._send(chat_id, payload.text)

    async def _send_photo(self, chat_id: int, photo_url: str, caption: str | None = None) -> None:
        """POST a ``sendPhoto`` to Telegram with an optional caption."""
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo_url}
        if caption:
            payload["caption"] = caption
        await self._http.post(f"{self._api}/sendPhoto", json=payload)

    async def _send_chat_action(self, chat_id: int, action: str) -> None:
        """Fire a ``sendChatAction`` (typing, upload_photo, …); errors are logged and swallowed.

        Chat actions are pure UX hints — Telegram clears them after ~5s
        — so failures should never propagate to the caller.
        """
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("telegram channel not started")
        try:
            await self._http.post(f"{self._api}/sendChatAction", json={"chat_id": chat_id, "action": action})
        except Exception:  # pragma: no cover - non-critical UX
            logger.exception("sendChatAction failed")


__all__ = ["TelegramChannel", "telegram_isolation_key"]
