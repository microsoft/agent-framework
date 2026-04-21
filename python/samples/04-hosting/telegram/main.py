# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

import orjson
import tiktoken
from agent_framework import (
    Agent,
    SavedItemsContextProvider,
    SavedItemsFileStore,
    SelectiveToolCallCompactionStrategy,
    SummarizationStrategy,
    TodoFileStore,
    TodoListContextProvider,
    TokenBudgetComposedStrategy,
    TokenizerProtocol,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from handlers import (
    handle_approval_button,
    handle_cancel,
    handle_direct_message,
    handle_error,
    handle_list_notes,
    handle_list_reminders,
    handle_list_sessions,
    handle_list_todos,
    handle_new_session,
    handle_resume_session,
    handle_start,
    handle_toggle_reasoning,
    handle_toggle_tokens,
)
from helpers import (
    BOT_COMMANDS,
    LOGGER,
    SESSION_STORAGE_DIRECTORY,
    STORAGE_KIND_MEMORIES,
    STORAGE_KIND_TODOS,
    configure_logging,
)
from providers import TelegramFileHistoryProvider, TelegramReminderContextProvider

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

"""
This sample demonstrates how to connect a Telegram bot to an Agent Framework agent for
direct 1:1 conversations.

This sample uses the following main components:
- `python-telegram-bot` to poll Telegram for private chat messages.
- `FoundryChatClient` to back the Agent Framework agent with an Microsoft Foundry model.
- `FileHistoryProvider` to persist each local session as JSON Lines under `sessions/`.
- Foundry's built-in web search tool for current information.
- Agent Framework's built-in `TodoListContextProvider` and `SavedItemsContextProvider`
  with file-backed stores rooted under `sessions/`.
- Local reminder tools backed by `python-telegram-bot`'s `JobQueue`.
- Agent Framework streaming (`agent.run(..., stream=True)`) to progressively update a
  Telegram reply while the model is still generating text.

Before running:
1. Create a bot with BotFather and copy the token.
2. Set the environment variables listed below.
3. Run `az login` so `AzureCliCredential` can authenticate.
4. Send a direct message to your bot in Telegram.

Environment variables:
    TELEGRAM_BOT_TOKEN: Bot token created with BotFather.
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    FOUNDRY_MODEL: Foundry model deployment name.
    TELEGRAM_SAMPLE_LOG_LEVEL: Optional console log level for the sample (defaults to INFO).
"""

load_dotenv()
configure_logging()


class TiktokenTokenizer(TokenizerProtocol):
    """Small sample tokenizer wrapper backed by tiktoken."""

    def __init__(self, *, model: str | None = None) -> None:
        self._encoding: Any = (
            tiktoken.encoding_for_model(model) if model is not None else tiktoken.get_encoding("o200k_base")
        )

    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))


tokenizer = TiktokenTokenizer(model=os.environ.get("FOUNDRY_MODEL"))


@tool(approval_mode="never_require")
def get_utc_time() -> str:
    """Get the current UTC time in ISO 8601 format."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


todo_store = TodoFileStore(
    SESSION_STORAGE_DIRECTORY,
    kind=STORAGE_KIND_TODOS,
    owner_prefix="user_",
    owner_state_key="telegram_user_id",
)
saved_items_store = SavedItemsFileStore(
    SESSION_STORAGE_DIRECTORY,
    kind=STORAGE_KIND_MEMORIES,
    owner_prefix="user_",
    owner_state_key="telegram_user_id",
    dumps=orjson.dumps,
    loads=orjson.loads,
)


async def main() -> None:
    """Run the Telegram bot sample."""
    SESSION_STORAGE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    # Enable azure monitor client for the FoundryChatClient
    client = FoundryChatClient(credential=AzureCliCredential())
    await client.configure_azure_monitor()
    compaction_strategy = TokenBudgetComposedStrategy(
        token_budget=200_000,
        tokenizer=tokenizer,
        strategies=[
            SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=30),
            SummarizationStrategy(client=client, target_count=40, threshold=20),
        ],
    )

    # 1. Create the Agent Framework agent with global Telegram instructions plus provider-owned tool guidance.
    agent = Agent(
        client=client,
        name="TelegramAssistant",
        default_options={
            "max_tokens": 100_000,
            "reasoning": {"effort": "medium", "summary": "detailed"},
            "store": False,
        },
        instructions=(
            "You are my personal assistant replying inside a Telegram direct chat. "
            "Respond directly without fluff, only ask questions back when necessary. "
        ),
        tokenizer=tokenizer,
        compaction_strategy=compaction_strategy,
        require_per_service_call_history_persistence=True,
        tools=[
            FoundryChatClient.get_web_search_tool(search_context_size="medium"),
            FoundryChatClient.get_code_interpreter_tool(),
            get_utc_time,
        ],
        context_providers=[
            TelegramFileHistoryProvider(
                SESSION_STORAGE_DIRECTORY,
                dumps=orjson.dumps,
                loads=orjson.loads,
            ),
            TelegramReminderContextProvider(),
            TodoListContextProvider(store=todo_store),
            SavedItemsContextProvider(store=saved_items_store, dumps=orjson.dumps),
        ],
    )

    # 2. Create the Telegram application and store the mutable sample state in bot_data.
    application = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).concurrent_updates(True).build()
    application.bot_data["agent"] = agent
    application.bot_data["chat_states"] = {}
    application.bot_data["storage_directory"] = SESSION_STORAGE_DIRECTORY
    application.bot_data["todo_store"] = todo_store
    application.bot_data["saved_items_store"] = saved_items_store

    # 3. Register Telegram commands, callbacks, and direct-message handling.
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("new", handle_new_session))
    application.add_handler(CommandHandler("sessions", handle_list_sessions))
    application.add_handler(CommandHandler("todo", handle_list_todos))
    application.add_handler(CommandHandler("notes", handle_list_notes))
    application.add_handler(CommandHandler("reminders", handle_list_reminders))
    application.add_handler(CommandHandler("resume", handle_resume_session))
    application.add_handler(CommandHandler("cancel", handle_cancel))
    application.add_handler(CommandHandler("reasoning", handle_toggle_reasoning))
    application.add_handler(CommandHandler("tokens", handle_toggle_tokens))
    application.add_handler(CallbackQueryHandler(handle_approval_button, pattern=r"^approval:"))
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_direct_message,
        )
    )
    application.add_error_handler(handle_error)

    # 4. Start long polling and keep the sample running until interrupted.
    async with application:
        if application.updater is None:
            raise RuntimeError("This sample requires a polling-enabled Telegram application.")

        await application.bot.delete_webhook(drop_pending_updates=False)
        await application.start()
        await application.bot.set_my_commands(BOT_COMMANDS)
        await application.updater.start_polling(drop_pending_updates=False)

        LOGGER.info("Telegram sample is running. Press Ctrl+C to stop.")

        try:
            await asyncio.Event().wait()
        finally:
            await application.updater.stop()
            await application.stop()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

2026-04-15 10:00:00 INFO helpers Telegram sample is running. Press Ctrl+C to stop.
2026-04-15 10:00:12 INFO helpers Handling Telegram message for chat_id=123456789

Telegram direct chat:
User: What happened in AI this week, and what time is it in UTC right now?
Bot: Here is a short summary of recent AI news...
     Current UTC time: 2026-04-15T10:00:12+00:00
"""
