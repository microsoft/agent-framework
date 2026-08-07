# Hosted-Steering

A chat agent hosted as a Foundry Hosted Agent using the **Responses protocol**, with **steerable conversations** enabled. A new input sent while a turn is still running is queued behind the current turn and folded into the ongoing answer, instead of being rejected with a conversation-locked error.

## What "steering" means here

- **Mid-turn input is queued, not rejected.** With `SteerableConversations = true`, a follow-up request for a conversation that is still in progress is accepted (`status: queued`) and drained at the next safe point, so a user can course-correct without cancelling and restarting.
- **Independent of resilience.** Steering and resilient background responses are separate options; you can enable either on its own. This sample turns on only steering. For crash recovery, see [`Hosted-Workflow-Resilient`](../Hosted-Workflow-Resilient/README.md).
- **Opt-in, off by default.** The only code difference from the non-steering [`Hosted-ChatClientAgent`](../Hosted-ChatClientAgent/README.md) is one line:

  ```csharp
  builder.Services.AddFoundryResponses(agent, configure: o => o.SteerableConversations = true);
  ```

  Without the option, an overlapping turn on the same conversation is rejected (`conversation_locked`).

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- `az login` plus a Foundry **project endpoint** and a **model deployment**.

## Configuration

```bash
cp .env.example .env
# set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL
```

## Run locally (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
az login
export FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
export FOUNDRY_MODEL=gpt-4o

cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Steering
dotnet run
```

The agent starts on `http://localhost:8088`.

### Try steering

1. Start a background response for a conversation and note its response id:

   ```bash
   curl -N -s http://localhost:8088/responses \
     -H 'content-type: application/json' \
     -d '{"input":"Write a detailed plan for a birthday party","stream":true,"store":true,"background":true}'
   ```

2. While it is still running, send a follow-up for the same chain (set `previous_response_id` to the latest response id). Instead of `conversation_locked`, it is queued and the agent folds it in:

   ```bash
   curl -N -s http://localhost:8088/responses \
     -H 'content-type: application/json' \
     -d '{"input":"Actually, make it a surprise party on a tight budget","previous_response_id":"<id>","stream":true,"store":true,"background":true}'
   ```

Without `SteerableConversations`, step 2 would be rejected while the first turn is in progress.

## Deploy to Foundry

Initialize an `azd` project from this sample's manifest, then deploy:

```bash
mkdir hosted-steering && cd hosted-steering
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Steering/agent.manifest.yaml
azd deploy
```

See the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).
