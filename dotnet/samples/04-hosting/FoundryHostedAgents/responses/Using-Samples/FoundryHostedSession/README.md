# Foundry Hosted Session

This client creates a Foundry hosted session explicitly, attaches its identifier to an Agent Framework
`AgentSession`, and sends every turn to the same hosted sandbox. It deletes the hosted session when the
client exits.

Use this pattern when the application must know the hosted session identifier before the first agent
invocation. Common reasons include uploading files before the first turn and assigning several logical
users to a caller managed session pool.

## Sessions and conversations

A hosted session and a conversation solve different problems.

| Value | Purpose |
| --- | --- |
| Foundry `agent_session_id` | Selects the hosted sandbox, its compute, persisted `$HOME`, and session files. |
| Agent Framework `AgentSession` | Keeps the hosted session identifier and conversation continuation state together for the client. |
| Conversation or previous response identifier | Preserves model conversation history. Reusing only `agent_session_id` does not restore message history. |

The sample creates the platform session with `AgentAdministrationClient.CreateSessionAsync`. It then
calls `CreateFoundryHostedAgentSessionAsync(hostedSessionId: ...)`. Agent Framework stores the identifier
on the returned `AgentSession` and sends `agent_session_id` on every subsequent Responses request.

## Session lifetime

The platform owns the hosted session lifecycle. When the idle timeout is reached, Foundry can remove
the active compute while preserving the session filesystem. Referencing the session again causes Foundry
to provision compute and restore the saved state. A hosted session identifies a logical sandbox. It does
not reserve one physical virtual machine for its complete lifetime.

This sample deletes the session in a `finally` block. A production service can retain session identifiers
when it needs a longer lived pool, but it must eventually delete unused sessions or let the configured
expiration reclaim them.

## Session pools

Applications that serve many users usually should not create one hosted session for every registered user.
Instead, a middle tier can maintain a bounded pool:

1. Create a small number of hosted sessions.
2. Assign each user to one session.
3. Keep that assignment stable while the user is active.
4. Send the selected `agent_session_id` on every call.
5. Grow the pool according to observed concurrent work rather than total user count.

Sharing a hosted session does not automatically partition files or application data written by the
container. When users share a sandbox, container owned data must be stored under a per user partition.
The sibling [`UserIsolationAgent`](../UserIsolationAgent/) sample shows how to identify each user while
sharing one hosted session.

## Prerequisites

* [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
* A hosted agent deployed to Foundry
* Azure CLI authenticated with `az login`
* Permission to invoke the agent and create, read, and delete its hosted sessions

This sample targets a deployed agent because the Foundry session administration API is not available
from a local `dotnet run` agent server.

## Configuration

Copy `.env.example` to `.env` and set:

```env
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_AGENT_NAME=<deployed-hosted-agent-name>
```

## Run

```powershell
cd dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-Samples\FoundryHostedSession
dotnet run
```

The startup output prints the explicit hosted session identifier. All REPL turns reuse that identifier.
Entering `quit` or encountering an exception causes the `finally` block to request session deletion.
An abrupt process termination can prevent cleanup, so production systems should also reclaim abandoned
sessions outside the request process.

## Related documentation

* [Manage hosted agent sessions](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions)
* [Multiplex multiple users in one hosted agent session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users)
