# Copyright (c) Microsoft. All rights reserved.

"""Run a Telegram bot as a Foundry Hosted Agent using Invocations 2.0.

API Management authenticates Telegram, stamps ``channel="telegram"`` and a
trusted ingress secret, and supplies the Telegram chat id as the Foundry
``agent_session_id``. The hosted agent keeps conversation history in Cosmos DB
and sends streamed responses back through the Telegram Bot API.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from agent_framework import Agent, AgentResponse, AgentResponseUpdate, AgentRunInputs, Message, ResponseStream
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import enable_instrumentation
from agent_framework_azure_cosmos import CosmosHistoryProvider
from agent_framework_hosting_telegram import (
    TelegramOperation,
    telegram_callback_query_id,
    telegram_chat_id,
    telegram_command,
    telegram_from_streaming_run,
    telegram_media_file_id,
    telegram_to_run,
)
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient
from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import Response

load_dotenv()

LOGGER = logging.getLogger(__name__)
EDIT_INTERVAL_SECONDS = 0.4
MAX_MEDIA_BYTES = 1024 * 1024
PLACEHOLDER_TEXT = "..."
BOT_TOKEN_SECRET_NAME = "telegram-bot-token"
WEBHOOK_SECRET_NAME = "telegram-webhook-secret"
INGRESS_SECRET_HEADER = "X-Agent-Framework-Ingress-Secret"
ENABLE_SENSITIVE_DATA = os.getenv("ENABLE_SENSITIVE_DATA", "true").casefold() in {"1", "true", "yes", "on"}
AGENT_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8").strip()
MODEL_MEDIA_TYPES = {
    "application/pdf": "application/pdf",
    "audio/mp3": "audio/mp3",
    "audio/mpeg": "audio/mp3",
    "audio/wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/x-wav": "audio/wav",
    "image/gif": "image/gif",
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}

# Message bodies and Telegram file URLs can contain user content or the bot
# token, so keep dependency INFO logs out of non-sensitive telemetry.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("agent_framework").setLevel(logging.WARNING)


@dataclass
class Runtime:
    """Hold long-lived clients used by the hosted process."""

    credential: DefaultAzureCredential
    history: CosmosHistoryProvider
    agent: Agent
    secrets: SecretClient
    http: httpx.AsyncClient
    bot_token: str | None = None


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


async def get_runtime() -> Runtime:
    """Create and cache the Azure, Agent Framework, and HTTP clients."""
    global _runtime
    if _runtime is not None:
        return _runtime

    async with _runtime_lock:
        if _runtime is not None:
            return _runtime

        credential = DefaultAzureCredential()
        secrets = SecretClient(vault_url=os.environ["KEY_VAULT_URL"], credential=credential)
        history = CosmosHistoryProvider(
            endpoint=os.environ["AZURE_COSMOS_ENDPOINT"],
            database_name=os.environ["AZURE_COSMOS_DATABASE_NAME"],
            container_name=os.environ["AZURE_COSMOS_CONTAINER_NAME"],
            credential=credential,
        )
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        )
        await client.configure_azure_monitor(
            enable_sensitive_data=ENABLE_SENSITIVE_DATA,
            enable_live_metrics=True,
        )
        agent = Agent(
            client=client,
            name="TelegramAssistant",
            instructions=AGENT_INSTRUCTIONS,
            context_providers=[history],
            default_options={"store": False},
        )
        _runtime = Runtime(
            credential=credential,
            history=history,
            agent=agent,
            secrets=secrets,
            http=httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True),
        )
        return _runtime


async def get_bot_token(runtime: Runtime) -> str:
    """Return the cached Telegram bot token from Key Vault."""
    if runtime.bot_token is not None:
        return runtime.bot_token
    secret = await runtime.secrets.get_secret(BOT_TOKEN_SECRET_NAME)
    value = secret.value
    if not isinstance(value, str) or not value:
        raise RuntimeError("The Telegram bot token secret is empty")
    runtime.bot_token = value
    return value


async def authenticate_ingress(request: Request, runtime: Runtime) -> bool:
    """Validate the secret stamped by API Management."""
    provided_secret = request.headers.get(INGRESS_SECRET_HEADER)
    if not provided_secret:
        return False

    secret = await runtime.secrets.get_secret(WEBHOOK_SECRET_NAME)
    expected_secret = secret.value
    if not isinstance(expected_secret, str) or not expected_secret:
        raise RuntimeError("The Telegram webhook secret is empty")
    return hmac.compare_digest(provided_secret, expected_secret)


def _telegram_result(response: httpx.Response, method: str) -> dict[str, Any]:
    """Validate a Telegram Bot API response without exposing its request URL."""
    try:
        payload: dict[str, Any] = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Telegram returned invalid JSON for {method}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Telegram returned an invalid response for {method}")

    description = payload.get("description")
    if response.is_error or payload.get("ok") is not True:
        if (
            method == "editMessageText"
            and isinstance(description, str)
            and "message is not modified" in description.lower()
        ):
            LOGGER.debug("Telegram ignored an edit whose rendered content was unchanged")
            return {}
        safe_description = description if isinstance(description, str) else "unknown error"
        raise RuntimeError(f"Telegram rejected {method} with status {response.status_code}: {safe_description}")

    result = payload.get("result")
    return result if isinstance(result, dict) else {}


async def execute_telegram_operation(runtime: Runtime, operation: TelegramOperation) -> dict[str, Any]:
    """Execute one operation produced by the Telegram hosting helper."""
    token = await get_bot_token(runtime)
    method = operation["method"]
    try:
        response = await runtime.http.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=operation["payload"],
        )
    except httpx.HTTPError:
        # httpx exceptions include the token-bearing request URL.
        raise RuntimeError(f"Telegram request failed for {method}") from None
    return _telegram_result(response, method)


async def resolve_telegram_file(
    file_id: str,
    runtime: Runtime,
    *,
    media_type: str = "application/octet-stream",
) -> str | None:
    """Resolve and download a bounded Telegram file as a token-safe data URI."""
    try:
        metadata = await execute_telegram_operation(
            runtime,
            TelegramOperation(method="getFile", payload={"file_id": file_id}),
        )
    except RuntimeError:
        LOGGER.warning("Telegram media metadata could not be resolved")
        return None

    file_path = metadata.get("file_path")
    file_size = metadata.get("file_size")
    if not isinstance(file_path, str) or (isinstance(file_size, int) and file_size > MAX_MEDIA_BYTES):
        return None

    token = await get_bot_token(runtime)
    try:
        async with runtime.http.stream("GET", f"https://api.telegram.org/file/bot{token}/{file_path}") as response:
            if response.is_error:
                LOGGER.warning("Telegram media download returned status %s", response.status_code)
                return None

            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_MEDIA_BYTES:
                        return None
                except ValueError:
                    LOGGER.debug("Telegram media response had an invalid content-length")

            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_MEDIA_BYTES:
                    return None
    except httpx.HTTPError:
        LOGGER.warning("Telegram media download failed")
        return None

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _normalize_run_media_type(messages: AgentRunInputs, source_media_type: str, model_media_type: str) -> None:
    """Align converted URI content with the model serializer's supported media type."""
    if isinstance(messages, Message):
        normalized_messages = (messages,)
    elif isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
        normalized_messages = messages
    else:
        return
    for message in normalized_messages:
        if not isinstance(message, Message):
            continue
        for content in message.contents:
            if (
                getattr(content, "type", None) in {"data", "uri"}
                and getattr(content, "media_type", None) == source_media_type
            ):
                content.media_type = model_media_type


async def _send_command_response(
    update: Mapping[str, Any],
    command: str,
    session_id: str,
    runtime: Runtime,
) -> bool:
    """Handle sample-owned commands and return whether one matched."""
    chat_id = telegram_chat_id(update)
    if chat_id is None:
        raise ValueError("Telegram update does not contain a supported chat")

    name = command.partition(" ")[0]
    if name == "/start":
        text = "Hi! I am a Telegram assistant. Send text or media, or use /help to see available commands."
    elif name == "/help":
        text = "/new - clear this conversation\n/help - show this message\n/start - show the welcome message"
    elif name == "/new":
        await runtime.history.clear(session_id)
        text = "New conversation started. Your next message begins with empty history."
    else:
        return False

    await execute_telegram_operation(
        runtime,
        TelegramOperation(method="sendMessage", payload={"chat_id": chat_id, "text": text}),
    )
    return True


async def _stream_operations(
    stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
    *,
    chat_id: int,
    message_id: int,
) -> AsyncIterator[TelegramOperation]:
    """Render the agent response stream into Telegram operations."""
    async for operation in telegram_from_streaming_run(
        stream,
        chat_id=chat_id,
        message_id=message_id,
        initial_text=PLACEHOLDER_TEXT,
    ):
        yield operation


async def deliver_stream(
    runtime: Runtime,
    stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]],
    *,
    chat_id: int,
    message_id: int,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Deliver cumulative stream edits with a bounded Telegram edit rate."""
    last_edit_at = 0.0
    async for operation in _stream_operations(stream, chat_id=chat_id, message_id=message_id):
        if operation["method"] == "editMessageText":
            delay = EDIT_INTERVAL_SECONDS - (clock() - last_edit_at)
            if delay > 0:
                await sleep(delay)
            last_edit_at = clock()
        await execute_telegram_operation(runtime, operation)


async def handle_telegram_update(update: Mapping[str, Any], session_id: str, runtime: Runtime) -> None:
    """Handle one Telegram update using durable history for the supplied session."""
    chat_id = telegram_chat_id(update)
    if chat_id is None:
        raise ValueError("Telegram update does not contain a supported chat")
    if str(chat_id) != session_id:
        raise ValueError("Telegram chat id does not match agent_session_id")

    callback_query_id = telegram_callback_query_id(update)
    if callback_query_id is not None:
        await execute_telegram_operation(
            runtime,
            TelegramOperation(method="answerCallbackQuery", payload={"callback_query_id": callback_query_id}),
        )

    command = telegram_command(update)
    if command is not None and await _send_command_response(update, command, session_id, runtime):
        return

    media = telegram_media_file_id(update)
    model_media_type = MODEL_MEDIA_TYPES.get(media[1].lower()) if media is not None else None
    if media is not None and model_media_type is None:
        await execute_telegram_operation(
            runtime,
            TelegramOperation(
                method="sendMessage",
                payload={
                    "chat_id": chat_id,
                    "text": "I can process photos, PDF documents, and MP3 or WAV audio up to 1 MiB.",
                },
            ),
        )
        return
    resolved_media_type = model_media_type or "application/octet-stream"

    async def resolve_file(file_id: str) -> str | None:
        media_type = resolved_media_type if media is not None and media[0] == file_id else "application/octet-stream"
        return await resolve_telegram_file(file_id, runtime, media_type=media_type)

    try:
        run = await telegram_to_run(
            update,
            resolve_file_url=resolve_file,
            stream=True,
        )
    except ValueError:
        await execute_telegram_operation(
            runtime,
            TelegramOperation(
                method="sendMessage",
                payload={
                    "chat_id": chat_id,
                    "text": "I could not process that update. Try sending text or a supported file up to 1 MiB.",
                },
            ),
        )
        return
    if media is not None and resolved_media_type != media[1]:
        _normalize_run_media_type(run["messages"], media[1], resolved_media_type)

    placeholder = await execute_telegram_operation(
        runtime,
        TelegramOperation(method="sendMessage", payload={"chat_id": chat_id, "text": PLACEHOLDER_TEXT}),
    )
    message_id = placeholder.get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram did not return a message id for the streaming placeholder")

    session = runtime.agent.create_session(session_id=session_id)
    response = runtime.agent.run(
        run["messages"],
        session=session,
        options=run["options"],
        stream=True,
    )
    if not isinstance(response, ResponseStream):
        raise RuntimeError("Agent did not return a response stream")

    await deliver_stream(runtime, response, chat_id=chat_id, message_id=message_id)


async def dispatch_channel(payload: Mapping[str, Any], session_id: str, runtime: Runtime) -> None:
    """Validate the ingress channel and dispatch its unmodified payload."""
    channel = payload.get("channel")
    if not isinstance(channel, str):
        raise ValueError("Missing channel")

    update = {key: value for key, value in payload.items() if key != "channel"}
    match channel:
        case "telegram":
            await handle_telegram_update(update, session_id, runtime)
        case _:
            raise ValueError(f"Unsupported channel: {channel}")


app = InvocationAgentServerHost()
enable_instrumentation(enable_sensitive_data=ENABLE_SENSITIVE_DATA, force=True)


@app.invoke_handler
async def handle_invoke(request: Request) -> Response:
    """Process an update forwarded by API Management."""
    runtime = await get_runtime()
    if not await authenticate_ingress(request, runtime):
        return Response("Unauthorized ingress", status_code=401)

    session_id = get_request_context().session_id
    if not session_id:
        return Response("Missing agent_session_id", status_code=400)

    try:
        payload: dict[str, Any] = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        await dispatch_channel(payload, session_id, runtime)
    except ValueError as exc:
        return Response(str(exc), status_code=400)

    return Response(status_code=200)


if __name__ == "__main__":
    app.run()
