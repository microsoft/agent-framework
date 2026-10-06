# Persist DevUI conversations and chat history in SQLite

This sample hosts an agent with the built-in OpenAI Responses, Conversations,
Chat Completions, and DevUI endpoints while storing durable conversation state
in SQLite.

It demonstrates three related persistence layers:

- `SqliteChatHistoryProvider` stores the model-facing `ChatMessage` history.
- `AgentSessionStore` stores the session state that links a hosted conversation
  to its chat-history record and preserves other session state such as pending
  tool approvals.
- `IOpenAIConversationStore` stores the OpenAI Conversations API records and
  items that DevUI uses to list and reopen conversations.

Keeping all three layers durable allows a DevUI conversation to be reopened by
conversation ID after the API process restarts.

## Run

Requires .NET 10 and an OpenAI-compatible endpoint:

```powershell
$env:OPENAI_API_KEY = "<your-api-key>"
$env:OPENAI_MODEL = "gpt-5.4-mini" # Optional
$env:OPENAI_ENDPOINT = "https://..." # Optional for the default OpenAI endpoint
$env:AGENT_DATABASE_PATH = Join-Path (Get-Location) "conversations.db"
dotnet run
```

Open `http://localhost:5130/devui`, start a conversation, and send a
message containing a detail the agent should remember. Stop the application,
restart it with the same `AGENT_DATABASE_PATH`, and reopen the conversation in
DevUI. The conversation list, displayed transcript, agent session, and
model-facing history are restored from SQLite.

The same host also maps:

- `/v1/responses`
- `/v1/conversations`
- `/assistant/v1/chat/completions`

Chat Completions is mapped to match a typical API host, but that protocol is
stateless and does not carry a conversation ID. The durable resume path shown
by this sample is the Responses plus Conversations flow used by DevUI.

## Why not only serialize `AgentSession`?

The default in-memory `ChatHistoryProvider` is serialized inside
`AgentSession`, so a session store alone is enough for many custom APIs. This
sample uses a database-backed `ChatHistoryProvider` because the issue scenario
specifically asks how to store message history outside the session.

DevUI additionally depends on the OpenAI Conversations API. Persisting only the
agent session would let the model resume internally, but DevUI would lose its
conversation list and transcript after a restart. `IOpenAIConversationStore`
keeps that protocol state durable as well.

## Deployment boundaries

This is a local-development sample. It intentionally disables session-store
isolation and does not configure authentication. Conversation IDs are lookup
keys, not authorization tokens.

Before production deployment:

- authenticate every endpoint and authorize conversation ownership;
- register an `AgentIsolationKeyProvider` and enable session-store isolation;
- coordinate concurrent turns for the same conversation across all instances;
- configure database encryption, backups, retention, and deletion of associated
  agent sessions and chat-history records;
- replace SQLite with a database and concurrency model suitable for the target
  deployment.

Completed response objects remain in the hosting process's in-memory Responses
store. Durable conversations and session state are sufficient for DevUI
conversation restore, but retrieving an old response directly by response ID
after restart is outside this sample's scope. The chat-history provider and
session store also commit through separate framework lifecycle callbacks; a
production design that requires one atomic commit should add a transaction or
outbox boundary around those writes.
