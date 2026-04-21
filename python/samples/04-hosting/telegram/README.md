# Telegram Hosting Samples

This folder contains Telegram integration samples for Microsoft Agent Framework.

## Sample Catalog

- **[`main.py`](./main.py)**: Connect a Telegram bot to a single Agent Framework agent for direct 1:1 conversations using `python-telegram-bot`, `FoundryChatClient`, and long polling. The sample adds Foundry web search, code execution, a UTC time tool, the built-in `TodoListContextProvider`, a reminder context provider, the built-in `SavedItemsContextProvider` for notes and memories, JobQueue-backed reminder CRUD, command registration, and local per-user storage under `sessions/user_<telegram_user_id>/...`, plus token-aware composed compaction via `tiktoken`, older tool-call compaction, summary generation, and inline-button approvals for cross-session session-note access.

## Sample layout

- **[`main.py`](./main.py)** - sample entrypoint, agent wiring, tokenizer setup, and Telegram application startup
- **[`providers.py`](./providers.py)** - sample-specific `TelegramFileHistoryProvider` and `TelegramReminderContextProvider`
- **[`handlers.py`](./handlers.py)** - Telegram commands, approval callbacks, streaming reply flow, and `/todo` / `/notes` / `/reminders` command handlers
- **[`helpers.py`](./helpers.py)** - shared Telegram state, formatting, session persistence, and storage-path helpers

## Why this sample starts with long polling

The first Telegram sample is optimized for local exploration:

- no public HTTPS endpoint is required
- no webhook registration is required
- you can run the bot directly from the repository with `uv run`

For production deployments, Telegram webhooks are usually the better fit. This sample is the local baseline that a later webhook-hosted sample can build on.

## Prerequisites

1. Create a Telegram bot with [BotFather](https://t.me/BotFather).
2. Make sure you have access to an Azure AI Foundry project and model deployment.
3. Sign in with Azure CLI:

   ```bash
   az login
   ```

4. Set the required environment variables:

   ```bash
    export TELEGRAM_BOT_TOKEN="your-bot-token"
    export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
    export FOUNDRY_MODEL="gpt-5"
    export TELEGRAM_SAMPLE_LOG_LEVEL="INFO"
    ```

   `TELEGRAM_SAMPLE_LOG_LEVEL` is optional. The sample defaults to `INFO` and keeps noisy HTTP and Telegram library logs at `WARNING`.

## Running the sample

From the `python/` directory:

```bash
uv run samples/04-hosting/telegram/main.py
```

Then open Telegram, start a direct chat with your bot, and send a message.

The sample creates a local `sessions/` directory next to `main.py` for runtime state. That directory is intentionally ignored by the sample-local `.gitignore`.

## Reminders with JobQueue

The sample uses a dedicated `TelegramReminderContextProvider` plus `python-telegram-bot`'s `JobQueue` to schedule reminder callbacks back into the same Telegram chat.

- `create_reminder` schedules a delayed callback with `run_once(...)` and supports `target="user"` or `target="agent"`
- `list_reminders`, `read_reminder`, `update_reminder`, and `delete_reminder` manage pending reminders for the current session
- user-targeted reminders are delivered as normal Telegram bot messages
- agent-targeted reminders first tell the user what the agent was reminded to do, then invoke the agent on the saved session so the agent response can follow
- reminder jobs are **in-memory only** in this sample, so they are lost if the bot process restarts

## Built-in todo provider

The sample uses Agent Framework's built-in `TodoListContextProvider` with the file-backed `TodoFileStore`.

- todos are stored on disk under `sessions/user_<telegram_user_id>/todos/<session_id>/todos.json`
- the provider injects planning/execution guidance plus the todo tools automatically
- the tools are `add_todos`, `complete_todos`, `remove_todos`, `get_remaining_todos`, and `get_all_todos`
- the todo list is session-scoped, so each Telegram session can track its own work plan independently

## Built-in saved items for notes and memories

The sample uses Agent Framework's built-in `SavedItemsContextProvider` with the file-backed `SavedItemsFileStore`, stored under the shared `sessions/` folder next to `main.py`.

- notes and memories share one data model with fields such as `item_id`, `item_type`, `scope`, `topic`, `text`, `date`, `session_id`, `owner_id`, and `ttl_seconds`
- `item_type="note"` is for note-like information, while `item_type="memory"` is for durable remembered facts or preferences
- `scope="session"` keeps an item local to the current session, while `scope="user"` keeps it available across sessions for that Telegram user
- the shared tools are `add_saved_item`, `list_saved_items`, `read_saved_item`, `update_saved_item`, `set_saved_item_ttl`, `delete_saved_item`, and `list_saved_item_topics`
- `list_saved_items_in_session` and `read_saved_item_in_session` are approval-gated for cross-session access to session-scoped items
- the provider prunes expired saved items before each run based on the creation timestamp and TTL
- omitting `ttl_seconds` makes an item effectively infinite, which is useful for long-lived facts such as a user's name
- per-session topic logs are kept in the same user/session tree so the agent can still see which topics have existed before, even after finite saved items expire
- saved items are stored under `sessions/user_<telegram_user_id>/memories/<session_id>/`

## Telegram commands

The sample registers these commands with Telegram on startup so they show up in the bot menu:

| Command | Purpose |
| --- | --- |
| `/start` | Introduce the bot and the available commands |
| `/new` | Start a fresh local Agent Framework session for the current Telegram chat |
| `/sessions` | List the local sessions currently tracked for this Telegram chat |
| `/todo` | List todo items for the active session |
| `/notes` | List saved notes for the active session |
| `/reminders` | List pending reminders for the active session |
| `/resume` | Switch back to the latest pending or previous local session |
| `/cancel` | Cancel the active in-progress response and clear its placeholder message |
| `/reasoning` | Toggle the transient reasoning preview on or off for this chat |
| `/tokens` | Toggle the input/output token footer on final agent replies for this chat (off by default) |

## What the sample demonstrates

1. Long-polling Telegram updates with `python-telegram-bot`
2. Registering Telegram commands and surfacing them in the bot command menu
3. Tracking multiple local Agent Framework sessions per Telegram chat
4. Listing current-session todos, notes, and reminders directly from Telegram commands
5. Persisting Telegram sandboxes locally with `FileHistoryProvider`, sortable UUIDv7 session ids, on-disk `session.json` snapshots, and `store=False`
6. Backing the bot with `FoundryChatClient`
7. Adding tools to the agent, including Foundry web search, session todo management, reminder CRUD, and unified saved-item CRUD for notes and memories
8. Injecting built-in todo, reminder, and saved-item behavior through `ContextProvider` implementations
9. Pausing on approval-required cross-session session-note access and resuming it with Telegram inline buttons
10. Using a `tiktoken` tokenizer with a token-budget `TokenBudgetComposedStrategy` that compacts older tool-call groups and summarizes older chat history
11. Streaming agent output into Telegram by editing a placeholder reply message
12. Cancelling an in-progress `agent.run(...)` from Telegram and clearing the in-flight placeholder message
13. Toggling the transient reasoning preview per chat with a Telegram command
14. Toggling a final input/output token usage footer per chat with a Telegram command

## Notes and limitations

- This sample is intentionally limited to **direct 1:1 chat**. It does not target Telegram groups or Telegram Channels.
- The sample rebuilds its Telegram chat-to-session registry from local `AgentSession` snapshots in `sessions/user_<telegram_user_id>/session/` plus file history in `sessions/user_<telegram_user_id>/history/`. After restart, the newest persisted sandbox for that chat becomes active automatically.
- The agent is configured with `store=False`, so conversation history is replayed from the local `FileHistoryProvider` instead of the chat service.
- The agent uses a `tiktoken`-backed `TokenBudgetComposedStrategy` for compaction, with `SelectiveToolCallCompactionStrategy` plus `SummarizationStrategy`, instead of a `CompactionProvider`. The current sample uses a high budget so compaction only kicks in after the chat grows substantially.
- The sample strips replay-only assistant `hosted_file` annotations before saving local file history so later turns do not resend them as invalid assistant `input_file` items to the Foundry/OpenAI Responses API.
- Telegram message edits are buffered to avoid editing on every tiny streamed chunk.
- Telegram bot formatting is not GitHub/CommonMark. This sample uses Telegram's Markdown parse mode, so formatted links and other markup must follow Telegram's supported syntax.
- Telegram bots cannot set arbitrary text colors in normal messages. The transient reasoning block is labeled `Thinking...` and is removed from the final answer.
- Final replies can include a `_Tokens: in X | out Y_` footer when usage details are available. This footer starts disabled and `/tokens` toggles it per chat.
- Web search availability depends on the Foundry model and tool support available in your environment.
- The reminder tool uses PTB `JobQueue`, so this sample depends on `python-telegram-bot[job-queue]`.
- Reminder jobs are not durable in this sample. Restarting the process clears scheduled reminders.
- Session todo state is stored in `samples/04-hosting/telegram/sessions/user_<telegram_user_id>/todos/<session_id>/todos.json`.
- Agent-targeted reminders depend on the original local session still being available when the reminder fires.
- Current-session notes are available without approval; cross-session session-note access uses approval-gated tools and inline buttons.
- Saved notes and memories are local `.json` files under `samples/04-hosting/telegram/sessions/user_<telegram_user_id>/memories/<session_id>/`.
- File-backed session history is stored under `samples/04-hosting/telegram/sessions/user_<telegram_user_id>/history/<session_id>/`.
- The generated `samples/04-hosting/telegram/sessions/` tree is runtime data and is ignored by the sample-local `.gitignore`.
- Telegram-sourced profile metadata is limited to what Telegram includes on the update; it does not provide sensitive facts such as date of birth.
- `/resume` first prefers a session that is waiting on approval, and otherwise walks backward through older persisted sandboxes so you can switch away from the newest active one after restart.
- If streaming behavior proves awkward for a specific model or network path, the sample can be adapted later to send only the final response.

## Expected experience

1. Start the sample locally.
2. Send `/start` to the bot.
3. Send `/new` to start a fresh session, or send a normal text message and let the sample create one automatically.
4. Send `/sessions` to inspect the local sessions tracked for your chat.
5. Send `/todo`, `/notes`, or `/reminders` to inspect the active session quickly.
6. Send `/reasoning` whenever you want to turn the transient reasoning preview on or off for your chat.
7. Send `/tokens` whenever you want to turn the final input/output token footer on or back off.
8. Ask a question and watch the bot's placeholder reply update as the agent stream advances.
9. Send `/cancel` while a response is still streaming to stop it and clear the in-flight bot message.
10. Ask the bot to set a reminder such as `remind me in 10 minutes to check the oven`.
11. Ask the bot to set an agent reminder such as `in 10 minutes, remind yourself to summarize my travel notes`.
12. Ask the bot to list or update pending reminders in the current session.
13. Ask the bot to save a session note such as `save a session note about trip ideas: visit Oslo in June`.
14. Ask the bot what saved notes are available in the current session.
15. Ask the bot to save a user memory such as `remember that I prefer aisle seats`.
16. Ask the bot to read or update one of those saved items.
17. Ask the bot to inspect notes from another session, then tap the approval button when the cross-session note prompt appears.
