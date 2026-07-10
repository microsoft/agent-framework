# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-hosting",
#     "agent-framework-hosting-telegram",
#     "aiogram>=3.29.1,<4",
#     "azure-identity",
#     "fastapi>=0.115.0,<0.138.1",
#     "hypercorn>=0.17",
# ]
# ///
# Run with: uv run app.py

# Copyright (c) Microsoft. All rights reserved.

"""Run a self-contained Telegram bot as an authenticated webhook.

This entry point uses native FastAPI routes and aiogram update handling. At
startup it registers ``TELEGRAM_WEBHOOK_URL`` with Telegram and configures
Telegram to send ``TELEGRAM_WEBHOOK_SECRET`` in the
``X-Telegram-Bot-Api-Secret-Token`` header. The route validates that header
before accepting an update.

Production readiness
---
The secret header authenticates Telegram's webhook delivery, but it does not
authorize the end user represented by an update. Production apps must still
authorize chat/user ids before loading sensitive state, use durable state and
idempotent update processing, and add bounded background work with delivery
telemetry. See ``README.md#production-readiness``.

Required environment variables: ``FOUNDRY_PROJECT_ENDPOINT``,
``FOUNDRY_MODEL``, ``TELEGRAM_BOT_TOKEN``, ``TELEGRAM_WEBHOOK_URL``, and
``TELEGRAM_WEBHOOK_SECRET``.

Run::

    uv run app.py
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import logging
import os
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Annotated, Any, cast
from urllib.parse import urlparse

from agent_framework import Agent, InMemoryHistoryProvider, ResponseStream, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_telegram import (
    TelegramOperation,
    telegram_callback_query_id,
    telegram_chat_id,
    telegram_command,
    telegram_from_streaming_run,
    telegram_session_id,
    telegram_to_run,
)
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage, EditMessageText, SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Message, Update
from azure.identity.aio import DefaultAzureCredential
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from hypercorn.asyncio import serve
from hypercorn.config import Config

LOGGER = logging.getLogger(__name__)
EDIT_INTERVAL_SECONDS = 0.4
MAX_MEDIA_BYTES = 5 * 1024 * 1024
PLACEHOLDER_TEXT = "..."
ALLOWED_UPDATES = ["message", "edited_message", "callback_query"]
WEBHOOK_URL = os.environ["TELEGRAM_WEBHOOK_URL"]
WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
WEBHOOK_PATH = urlparse(WEBHOOK_URL).path or "/"


@tool(approval_mode="never_require")
def lookup_weather(
    location: Annotated[str, "The city to look up weather for."],
) -> str:
    """Return a deterministic weather report for a city."""
    high_temp = 5 + (sum(location.encode("utf-8")) % 21)
    reports = {
        "Seattle": f"Seattle is rainy with a high of {high_temp}°C.",
        "Amsterdam": f"Amsterdam is cloudy with a high of {high_temp}°C.",
        "Tokyo": f"Tokyo is clear with a high of {high_temp}°C.",
    }
    return reports.get(location, f"{location} is sunny with a high of {high_temp}°C.")


def create_agent() -> Agent:
    """Create the sample weather agent."""
    return Agent(
        client=FoundryChatClient(credential=DefaultAzureCredential()),
        name="WeatherAgent",
        instructions=(
            "You are a friendly weather assistant. Use the lookup_weather tool "
            "for weather questions and answer in one short sentence."
        ),
        tools=[lookup_weather],
        context_providers=[InMemoryHistoryProvider()],
        default_options={"store": False},
    )


state = AgentState(create_agent)
dispatcher = Dispatcher(disable_fsm=True)
bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])


def telegram_update(event_name: str, event: Message | CallbackQuery) -> dict[str, Any]:
    """Wrap one aiogram event in the Bot API update shape expected by helpers."""
    return {event_name: event.model_dump(mode="json", by_alias=True, exclude_none=True)}


async def execute_operation(operation: TelegramOperation) -> Any:
    """Execute one operation produced by a Telegram rendering helper."""
    try:
        match operation["method"]:
            case "sendMessage":
                return await bot(SendMessage.model_validate(operation["payload"]))
            case "sendPhoto":
                return await bot(SendPhoto.model_validate(operation["payload"]))
            case "editMessageText":
                return await bot(EditMessageText.model_validate(operation["payload"]))
            case "deleteMessage":
                return await bot(DeleteMessage.model_validate(operation["payload"]))
            case method:
                raise ValueError(f"Unsupported Telegram operation: {method}")
    except TelegramBadRequest as exc:
        if operation["method"] == "editMessageText" and "message is not modified" in exc.message.lower():
            LOGGER.debug("Telegram ignored an edit whose rendered content was unchanged")
            return None
        raise


async def handle_command(update: Mapping[str, Any], command: str) -> bool:
    """Handle sample-owned commands and return whether one matched."""
    chat_id = telegram_chat_id(update)
    session_id = telegram_session_id(update, bot_id=bot.id)
    if chat_id is None or session_id is None:
        return False

    name, _, argument = command.partition(" ")
    if name == "/start":
        text = "Hi! I am a weather assistant. Try asking about a city or use /weather <city>."
    elif name == "/help":
        text = "/new - reset this chat\n/weather <city> - look up weather directly\n/help - show this message"
    elif name == "/new":
        # SessionStore maps the stable Telegram chat key to its current
        # AgentSession. Deleting that entry makes the next message create a
        # fresh AgentSession with empty in-memory history.
        await state.session_store.delete(session_id)
        text = "New session started. Your next message begins with empty history."
    elif name == "/weather":
        text = lookup_weather(location=argument.strip() or "Seattle")
    else:
        return False

    await bot.send_message(chat_id=chat_id, text=text)
    return True


async def handle_update(update: Mapping[str, Any]) -> None:
    """Process one Telegram update through the sample agent."""
    callback_query_id = telegram_callback_query_id(update)
    if callback_query_id is not None:
        await bot.answer_callback_query(callback_query_id=callback_query_id)

    if (command := telegram_command(update)) is not None and await handle_command(update, command):
        return

    chat_id = telegram_chat_id(update)
    session_id = telegram_session_id(update, bot_id=bot.id)
    if chat_id is None or session_id is None:
        return

    async def resolve_file_url(file_id: str) -> str | None:
        file = await bot.get_file(file_id)
        if file.file_path is None or (file.file_size is not None and file.file_size > MAX_MEDIA_BYTES):
            return None
        destination = BytesIO()
        await bot.download_file(file.file_path, destination=destination)
        encoded = base64.b64encode(destination.getvalue()).decode("ascii")
        return f"data:application/octet-stream;base64,{encoded}"

    try:
        run = await telegram_to_run(update, resolve_file_url=resolve_file_url, stream=True)
    except ValueError:
        LOGGER.debug("Ignoring non-actionable Telegram update", exc_info=True)
        return

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    placeholder = await bot.send_message(chat_id=chat_id, text=PLACEHOLDER_TEXT)

    target = await state.get_target()
    # Reuse one AgentSession per Telegram chat. The /new command removes this
    # mapping so get_or_create_session creates a clean session next time.
    session = await state.get_or_create_session(session_id)
    stream = target.run(
        run["messages"],
        stream=True,
        session=session,
        options=run["options"],
    )
    if not isinstance(stream, ResponseStream):
        raise RuntimeError("agent did not return a response stream")

    last_edit_at = 0.0
    async for operation in telegram_from_streaming_run(
        stream,
        chat_id=chat_id,
        message_id=placeholder.message_id,
        initial_text=PLACEHOLDER_TEXT,
    ):
        if operation["method"] == "editMessageText":
            delay = EDIT_INTERVAL_SECONDS - (time.monotonic() - last_edit_at)
            if delay > 0:
                await asyncio.sleep(delay)
            last_edit_at = time.monotonic()
        await execute_operation(operation)

    # Persist the updated AgentSession back under the stable per-chat key after
    # streaming has finalized and the history provider has recorded the turn.
    await state.set_session(session_id, session)


@dispatcher.message()
async def on_message(message: Message) -> None:
    """Handle a new Telegram message."""
    await handle_update(telegram_update("message", message))


@dispatcher.edited_message()
async def on_edited_message(message: Message) -> None:
    """Handle an edited Telegram message."""
    await handle_update(telegram_update("edited_message", message))


@dispatcher.callback_query()
async def on_callback_query(callback_query: CallbackQuery) -> None:
    """Handle an inline-button callback query."""
    await handle_update(telegram_update("callback_query", callback_query))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Register the Telegram webhook and close the bot session on shutdown."""
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=ALLOWED_UPDATES,
    )
    yield
    # Leave the webhook registered. Deleting it during rolling shutdown can
    # remove the webhook just registered by the replacement process.
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.post(WEBHOOK_PATH, response_model=None)
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    """Authenticate and enqueue one Telegram webhook update."""
    received_secret = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="invalid Telegram webhook secret")

    try:
        payload = cast("dict[str, Any]", await request.json())
        update = Update.model_validate(payload, context={"bot": bot})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid Telegram update") from exc

    background_tasks.add_task(dispatcher.feed_update, bot, update)
    return Response(status_code=200)


async def main() -> None:
    """Run the webhook sample with Hypercorn for local development."""
    logging.basicConfig(level=logging.INFO)
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"]
    await serve(cast(Any, app), config)


if __name__ == "__main__":
    asyncio.run(main())

# Sample response:
# HTTP/1.1 200 OK
