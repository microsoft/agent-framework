# PostgreSQL chat history with API hosting and DevUI

This sample implements a PostgreSQL-backed `DatabaseChatHistoryProvider` for an
agent exposed through the built-in OpenAI Responses, Conversations, Chat
Completions, and DevUI endpoints.

The Aspire AppHost provisions PostgreSQL in a container, creates the
`conversations` database, injects its connection string into the agent service,
and waits for the database before starting the service. No system-wide
PostgreSQL installation is required.

The agent service uses:

- `DatabaseChatHistoryProvider` to append and restore `ChatMessage` records;
- `PostgresConversationStore`, an `AgentSessionStore`, to persist the small
  provider state that associates the hosting conversation ID with its database
  history ID;
- the standard `AddDevUI`, `MapOpenAIResponses`, `MapOpenAIConversations`, and
  `MapOpenAIChatCompletions` hosting flow.

On each turn, built-in Responses hosting resolves the `AgentSession` by OpenAI
conversation ID. The chat-history provider then loads the matching messages
from PostgreSQL before the model call and appends the successful user and
assistant messages afterward.

## Prerequisites

- .NET 10
- Docker or Podman with a Docker-compatible API, or the repository's .NET Dev
  Container (`.devcontainer/dotnet`), which includes Docker-in-Docker
- a Microsoft Foundry project and an authenticated Azure CLI session (`az login`)

You do **not** need to install PostgreSQL locally.

## Run

From this directory:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<resource>.services.ai.azure.com/api/projects/<project>"
$env:FOUNDRY_MODEL = "gpt-5.4-mini" # Optional
$env:POSTGRES_PASSWORD = "<local-development-password>"
az login
dotnet run --project AppHost
```

Open the `DevUI` link shown in the Aspire dashboard. Start a conversation, tell
the agent a detail to remember, and ask for it in a later turn. The second turn
loads the prior messages from PostgreSQL using the conversation's persisted
session state.

The PostgreSQL resource uses `WithDataVolume()`, so its data survives container
replacement. Keep `POSTGRES_PASSWORD` unchanged when restarting the AppHost so
the new container can reconnect to the existing volume. Remove the
Aspire-managed volume when you want a clean database.

## What this sample persists

This targeted example persists agent chat messages and the framework session
state required to find them. The built-in OpenAI Conversations and Responses
protocol stores remain in memory. Therefore DevUI's conversation catalog and
completed response objects are reset when the agent service restarts, even
though the PostgreSQL records remain. A client that retained the last response
ID can continue after restart with `previous_response_id`; the restored session
still points the `DatabaseChatHistoryProvider` at the original conversation ID.

Chat Completions is mapped to match a typical API host, but that protocol is
stateless and does not carry a conversation ID. The database-backed multi-turn
path demonstrated here is the Responses plus Conversations flow used by DevUI.

## Deployment boundaries

This is a local-development sample. It disables session-store isolation and
does not configure authentication. Conversation IDs are lookup keys, not
authorization tokens.

Before production deployment:

- authenticate every endpoint and authorize conversation ownership;
- register an `AgentIsolationKeyProvider` and enable session-store isolation;
- coordinate concurrent turns for the same conversation across instances;
- apply database encryption, access controls, backups, retention, and deletion;
- manage schema migrations outside application startup.
