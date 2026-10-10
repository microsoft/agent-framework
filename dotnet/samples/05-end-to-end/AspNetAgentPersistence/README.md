# Persist an API-hosted agent conversation in SQLite

This local sample stores the agent's serialized session in SQLite, keyed by a
conversation ID. A later HTTP request restores that session before invoking the
agent. The conversation survives restarting the API with the same database file.
It uses the existing `SerializeSessionAsync` and `DeserializeSessionAsync` APIs;
no custom `ChatHistoryProvider` is needed for this approach.

## Run

Requires .NET 10 and an OpenAI API key. From this directory:

```powershell
$env:OPENAI_API_KEY = "<your-api-key>"
$env:OPENAI_MODEL = "gpt-5.4-mini" # Optional
$env:AGENT_DATABASE_PATH = Join-Path (Get-Location) "conversations.db"
dotnet run
```

In another PowerShell terminal:

```powershell
$base = "http://localhost:5130"
$conversation = Invoke-RestMethod "$base/conversations" -Method Post
$id = $conversation.conversationId
Invoke-RestMethod "$base/conversations/$id/messages" -Method Post `
    -ContentType "application/json" -Body '{"message":"Remember invoice INV-123 for this conversation."}'
```

Stop and restart the API using the same database path, then reuse `$id`:

```powershell
Invoke-RestMethod "$base/conversations/$id/messages" -Method Post `
    -ContentType "application/json" -Body '{"message":"Which invoice did I mention?"}'
```

The default chat history provider keeps messages in the session. Restoring its
serialized state restores that history. A new conversation ID starts a separate
session. The client sends only the new message, not the previous transcript.
Session state is committed after a successful turn; a failed run leaves the last
saved session intact. This does not roll back external tool side effects.

## Session persistence versus message storage

`AgentSession` serialization stores the state needed to resume this agent,
including its default in-memory history. `ChatHistoryProvider` is a separate
extension point for loading/storing messages outside the session. See
[third-party history storage](../../02-agents/Agents/Agent_Step04_3rdPartyChatHistoryStorage/Program.cs)
and the existing
[Cosmos DB history provider](../../../src/Microsoft.Agents.AI.CosmosNoSql/CosmosChatHistoryProvider.cs)
when individual message queries or a different database layout are required.
External history storage may still require persisting the session's storage key.

This sample exposes a custom HTTP API, not the OpenAI Conversations/Responses
endpoints used by DevUI. Adding DevUI does not automatically connect those
protocol stores to this SQLite table.

## Deployment boundaries

The endpoint is anonymous and binds to localhost. Conversation IDs are lookup
keys, **not authorization**: any caller with access to this API and an ID can
resume that conversation. Before remote deployment, authenticate callers and
authorize ownership on every load/save, using a tenant/user plus conversation key.
See [ASP.NET agent authorization](../AspNetAgentAuthorization/README.md).

For clarity, one semaphore serializes turns across this single process. Multiple
instances need database concurrency control around the full load/run/save cycle;
an atomic upsert alone does not prevent lost turns. Add retention/deletion,
database access controls, and storage encryption according to your deployment.
The sample retains conversations until the local database file is deleted.
Keep model/provider configuration compatible when restoring sessions, and plan
state migrations when upgrading the application.
