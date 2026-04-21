# Telegram Hosting Samples

This folder contains Telegram integration samples for Microsoft Agent Framework.

## Sample Catalog

- **[`main.py`](./main.py)**: Connect a Telegram bot to a single Agent Framework agent for direct 1:1 conversations using `python-telegram-bot`, `FoundryChatClient`, and long polling. The sample adds Foundry web search, code execution, a UTC time tool, the built-in `TodoListContextProvider`, a reminder context provider, the built-in `MemoryContextProvider` with literal `MEMORY.md` plus topic files and transcript history, JobQueue-backed reminder CRUD, command registration, and local per-user storage under `sessions/user_<telegram_user_id>/...`, plus token-aware composed compaction via `tiktoken`, older tool-call compaction, summary generation, and a 4-turn short-term transcript window that skips tool-call groups.

## Sample layout

- **[`main.py`](./main.py)** - sample entrypoint, agent wiring, tokenizer setup, and Telegram application startup
- **[`providers.py`](./providers.py)** - sample-specific reminder provider plus Telegram history sanitization helpers
- **[`handlers.py`](./handlers.py)** - Telegram commands, approval callbacks, streaming reply flow, and `/todo` / `/memories` / `/reminders` command handlers
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

## Built-in memory provider

The sample uses Agent Framework's built-in `MemoryContextProvider` with the file-backed `MemoryFileStore`, stored under the shared `sessions/` folder next to `main.py`.

- the provider keeps a literal `MEMORY.md` index that is always injected into context
- durable topic files live under `sessions/user_<telegram_user_id>/memories/topics/*.md`
- raw transcript history lives under `sessions/user_<telegram_user_id>/memories/transcripts/*.jsonl`
- the sample also injects the last 4 transcript turns for short-term continuity alongside the durable memory layer, while skipping grouped tool-call turns
- the provider owns transcript persistence directly and strips replay-only assistant `hosted_file` annotations before writing JSONL
- the shared tools are `list_memory_topics`, `read_memory_topic`, `write_memory`, `delete_memory_topic`, `search_memory_transcripts`, and `consolidate_memories`
- after each completed turn, the provider extracts durable memory candidates from the latest transcript delta and writes them into topic files
- the provider also consolidates topic files and rewrites `MEMORY.md` when its configured thresholds are met

## Telegram commands

The sample registers these commands with Telegram on startup so they show up in the bot menu:

| Command | Purpose |
| --- | --- |
| `/start` | Introduce the bot and the available commands |
| `/new` | Start a fresh local Agent Framework session for the current Telegram chat |
| `/sessions` | List the local sessions currently tracked for this Telegram chat |
| `/todo` | List todo items for the active session |
| `/memories` | List memory topics for the active session owner |
| `/reminders` | List pending reminders for the active session |
| `/resume` | Switch back to the latest pending or previous local session |
| `/cancel` | Cancel the active in-progress response and clear its placeholder message |
| `/reasoning` | Toggle the transient reasoning preview on or off for this chat |
| `/tokens` | Toggle the input/output token footer on final agent replies for this chat (off by default) |

## What the sample demonstrates

1. Long-polling Telegram updates with `python-telegram-bot`
2. Registering Telegram commands and surfacing them in the bot command menu
3. Tracking multiple local Agent Framework sessions per Telegram chat
4. Listing current-session todos, memory topics, and reminders directly from Telegram commands
5. Persisting Telegram sandboxes locally with sortable UUIDv7 session ids, on-disk `session.json` snapshots, transcript JSONL, and `store=False`
6. Backing the bot with `FoundryChatClient`
7. Adding tools to the agent, including Foundry web search, session todo management, reminder CRUD, and topic-memory CRUD plus transcript search
8. Injecting built-in todo, reminder, and memory behavior through `ContextProvider` implementations
9. Combining durable memory topics with the last 4 transcript turns for short-term continuity while skipping grouped tool-call turns
10. Using a `tiktoken` tokenizer with a token-budget `TokenBudgetComposedStrategy` that compacts older tool-call groups and summarizes older chat history
11. Streaming agent output into Telegram by editing a placeholder reply message
12. Cancelling an in-progress `agent.run(...)` from Telegram and clearing the in-flight placeholder message
13. Toggling the transient reasoning preview per chat with a Telegram command
14. Toggling a final input/output token usage footer per chat with a Telegram command

## Notes and limitations

- This sample is intentionally limited to **direct 1:1 chat**. It does not target Telegram groups or Telegram Channels.
- The sample rebuilds its Telegram chat-to-session registry from local `AgentSession` snapshots in `sessions/user_<telegram_user_id>/session/` plus transcript history in `sessions/user_<telegram_user_id>/memories/transcripts/`. After restart, the newest persisted sandbox for that chat becomes active automatically.
- The agent is configured with `store=False`, so conversation history is replayed from the local memory-owned transcript archive instead of the chat service.
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
- Memory topics are stored as markdown files under `samples/04-hosting/telegram/sessions/user_<telegram_user_id>/memories/topics/`.
- File-backed transcript history is stored under `samples/04-hosting/telegram/sessions/user_<telegram_user_id>/memories/transcripts/`.
- Raw transcript search remains available when the agent needs exact historical detail from the archive.
- The generated `samples/04-hosting/telegram/sessions/` tree is runtime data and is ignored by the sample-local `.gitignore`.
- Telegram-sourced profile metadata is limited to what Telegram includes on the update; it does not provide sensitive facts such as date of birth.
- `/resume` first prefers a session that is waiting on approval, and otherwise walks backward through older persisted sandboxes so you can switch away from the newest active one after restart.
- If streaming behavior proves awkward for a specific model or network path, the sample can be adapted later to send only the final response.

## Expected experience

1. Start the sample locally.
2. Send `/start` to the bot.
3. Send `/new` to start a fresh session, or send a normal text message and let the sample create one automatically.
4. Send `/sessions` to inspect the local sessions tracked for your chat.
5. Send `/todo`, `/memories`, or `/reminders` to inspect the active session quickly.
6. Send `/reasoning` whenever you want to turn the transient reasoning preview on or off for your chat.
7. Send `/tokens` whenever you want to turn the final input/output token footer on or back off.
8. Ask a question and watch the bot's placeholder reply update as the agent stream advances.
9. Send `/cancel` while a response is still streaming to stop it and clear the in-flight bot message.
10. Ask the bot to set a reminder such as `remind me in 10 minutes to check the oven`.
11. Ask the bot to set an agent reminder such as `in 10 minutes, remind yourself to summarize my travel notes`.
12. Ask the bot to list or update pending reminders in the current session.
13. Ask the bot to save a durable memory such as `remember that I prefer aisle seats`.
14. Send `/memories` to inspect the currently known topic files.
15. Ask the bot to read or update a specific topic memory file.
16. Ask the bot to search older raw transcripts for something specific.
17. Use transcript search when you need an exact quote or detail from older history that is not already in the topic files.
