# Hosted-MemoryAgent

A hosted Foundry agent that uses **FoundryMemoryProvider** to remember user-private details across
requests and across sessions, scoped per end user via the Foundry platform's isolation keys. The
agent plays a friendly travel assistant: tell it about your trip, ask follow-up questions in a new
session, and it recalls what it learned about you.

This sample exists to demonstrate two things together:

1. How to host an agent that consumes a `Microsoft.Extensions.AI.AIContextProvider` (specifically
   `FoundryMemoryProvider`) under the Foundry Responses hosting layer.
2. How the new `HostedSessionContext` flows from the `Foundry` platform isolation headers
   (`x-agent-user-isolation-key`, `x-agent-chat-isolation-key`) through the
   `HostedSessionIsolationKeyProvider` into the provider's `stateInitializer`, so memories are
   partitioned per user automatically.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with at least one chat model deployment and one embedding model deployment
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Required:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
AZURE_AI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-ada-002
AZURE_AI_MEMORY_STORE_ID=hosted-memory-sample
AGENT_NAME=hosted-memory-agent
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
```

For local container runs only (the platform supplies these in production):

```env
HOSTED_USER_ISOLATION_KEY=alice
HOSTED_CHAT_ISOLATION_KEY=alice-chat-1
```

> `.env` is gitignored. The `.env.example` template is checked in as a reference.

## How memory scoping works

| Layer | Source of the user identity |
|---|---|
| Inbound request | The Foundry platform sets `x-agent-user-isolation-key` and `x-agent-chat-isolation-key` headers on every request. |
| Hosting layer | `AgentFrameworkResponseHandler` resolves a `HostedSessionIsolationKeyProvider` from DI and calls `GetKeysAsync(context, request, ct)`. The default implementation reads `context.Isolation.UserIsolationKey` and `context.Isolation.ChatIsolationKey`. |
| Session | The handler stores the resolved values on the session as a `HostedSessionContext` on the first request, and validates the values on every subsequent request that resumes the same conversation (mismatch returns 403). |
| Memory provider | The sample's `stateInitializer` reads `session.GetHostedContext().UserId` and uses it as the `FoundryMemoryProviderScope`. Memories are partitioned per user. |

When running outside the Foundry platform the headers are absent. The sample registers
`DevTemporaryLocalSessionIsolationKeyProvider` (via `AddDevTemporaryLocalContributorSetup`) which
falls back to the `HOSTED_USER_ISOLATION_KEY` and `HOSTED_CHAT_ISOLATION_KEY` environment variables,
defaulting to a single `local-dev-*` bucket when neither is set.

> **Production warning.** Never register `DevTemporaryLocalSessionIsolationKeyProvider` in
> production. The Foundry platform sets the isolation keys for every inbound request, and
> client-supplied environment variables can be forged.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-MemoryAgent
dotnet run
```

The agent starts on `http://localhost:8088`.

### Test it

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hi! My name is Taylor and I am planning a hiking trip to Patagonia in November.", "model": "hosted-memory-agent"}'
```

Wait a few seconds for memory extraction, then ask a follow-up using the response id from the
previous call as `previous_response_id`:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What do you already know about my upcoming trip?", "previous_response_id": "<id>", "model": "hosted-memory-agent"}'
```

## Running with Docker

Since this project uses `ProjectReference`, the standard `Dockerfile` cannot resolve dependencies
outside this folder. Use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-memory-agent .
```

### 3. Run the container

```bash
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-memory-agent \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  -e HOSTED_USER_ISOLATION_KEY=alice \
  -e HOSTED_CHAT_ISOLATION_KEY=alice-chat-1 \
  --env-file .env \
  hosted-memory-agent
```

### 4. Smoke test the running container

A scripted smoke test that exercises memory recall and per-user isolation across two simulated
users is provided at `scripts/smoke.ps1`. From the sample folder:

```powershell
pwsh ./scripts/smoke.ps1
```

The script publishes the project, builds the image, runs the container with two distinct
`HOSTED_USER_ISOLATION_KEY` values, drives a multi-turn conversation per user, asserts that each
user only sees their own memories, and exits non-zero on failure.

## Deploying to Foundry (azd spec)

This sample includes an `azd` manifest (`agent.manifest.yaml`) and hosted agent spec (`agent.yaml`) for deployment to Foundry.

Initialize an `azd` project from this sample's manifest:

```bash
mkdir hosted-memory-agent && cd hosted-memory-agent
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-MemoryAgent/agent.manifest.yaml
```

Then deploy:

```bash
azd deploy
```

If you need to override defaults, set deployment-time environment variables in the `azd` environment before deploying:

```bash
azd env set AGENT_NAME hosted-memory-agent
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4o
```

For end-to-end hosted agent deployment guidance, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

---

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the
standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in
`HostedMemoryAgent.csproj` for the `PackageReference` alternative.

## How it differs from sibling samples

| | Hosted-ChatClientAgent | Hosted-MemoryAgent |
|---|---|---|
| **Agent definition** | Inline (`AsAIAgent(model, instructions)`) | Inline, plus `AIContextProviders = [memoryProvider]` |
| **State** | None beyond the conversation history | Per-user memories persisted in Foundry Memory |
| **Identity** | Not used | Required: `HostedSessionContext.UserId` flows into the memory scope |
| **Local dev** | `AddDevTemporaryLocalContributorSetup()` keeps requests succeeding when isolation headers are absent | Same; additionally honours `HOSTED_USER_ISOLATION_KEY` to simulate distinct users |
