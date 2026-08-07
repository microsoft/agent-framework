# Hosted-Workflow-Resilient

A durable, long-running **workflow** hosted as a Foundry Hosted Agent using the **Responses protocol**. It is the same English to French to Spanish back to English translation chain as [`Hosted-Workflow-Simple`](../Hosted-Workflow-Simple/README.md), with one difference: it opts into **resilient background responses**, so a background response survives a container crash or graceful shutdown and resumes from the workflow's last completed step.

## What "resilient" means here

- **Long-running with no client connected.** When a caller starts a background response (`store: true`, `background: true`), the platform keeps the agent running even if the caller disconnects.
- **Crash recovery.** If the container crashes or is recycled mid-run, the platform restarts it and re-invokes the handler. A workflow hosted as an agent checkpoints its progress between steps, so it resumes from its last completed step instead of restarting from scratch.
- **At most one step repeats.** The hosting handler persists the session at each completed output item (a natural workflow step boundary), so a crash loses at most the step that was in flight.
- **Stable executor ids.** Recovery matches the saved checkpoint to the rebuilt workflow by executor id, and an agent-backed step derives its id from the agent's id. A default agent gets a fresh random id per process, which would never match after a restart, so each agent is created with an explicit stable `Id`:

  ```csharp
  AIAgent frenchAgent = chatClient.AsAIAgent(options: new()
  {
      Id = "french-translator",
      Name = "french-translator",
      ChatOptions = new() { Instructions = "...translate to French." },
  });
  ```

- **Opt-in, off by default.** Turning on resilience is one line:

  ```csharp
  builder.Services.AddFoundryResponses(agent, configure: o => o.ResilientBackground = true);
  ```

  Durability applies only to background responses. A foreground response (the caller waits on the connection) is not durable: a crash simply fails it.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- `az login` plus a Foundry **project endpoint** and a **model deployment** (each translation step calls the model).

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

cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Resilient
dotnet run
```

The agent starts on `http://localhost:8088`.

### Local crash-and-recover walkthrough

Resilient recovery needs a state store that survives a process restart. Locally the SDK auto-selects a file-backed store when `FOUNDRY_HOSTING_ENVIRONMENT` is unset; pin the store root and the session id so a restart finds the in-progress response:

```bash
export AGENTSERVER_STATE_ROOT=$PWD/.agentserver-state
export FOUNDRY_AGENT_SESSION_ID=local-demo-session
dotnet run
```

1. Start a background response and stream it. Capture the response id (`"id":"caresp_..."`):

   ```bash
   curl -N -s http://localhost:8088/responses \
     -H 'content-type: application/json' \
     -d '{"input":"renewable energy supply chains","stream":true,"store":true,"background":true}'
   ```

2. After a translation step or two, stop the process (Ctrl+C, or kill it) to simulate a crash.

3. Restart against the **same** `AGENTSERVER_STATE_ROOT` and `FOUNDRY_AGENT_SESSION_ID`. On startup the resilient task scanner reclaims the in-progress response and re-invokes the handler, which resumes the workflow from its last completed step.

4. Reconnect and watch it finish:

   ```bash
   curl -N -s "http://localhost:8088/responses/<response_id>?stream=true"
   ```

## How local mode works

| Env var | Effect |
|---|---|
| `FOUNDRY_HOSTING_ENVIRONMENT` (**unset**) | The SDK auto-selects the file-backed store instead of the hosted task API. |
| `AGENTSERVER_STATE_ROOT` | Where the resilient task store lives (must survive the restart). |
| `FOUNDRY_AGENT_SESSION_ID` | The session pinned across restarts so recovery finds the in-progress response. |
| `HOME` | The session working directory. The agent session store writes under `{HOME}/.checkpoints`; in a hosted container this is a durable per-session volume. |

## Deploy to Foundry

Initialize an `azd` project from this sample's manifest, then deploy:

```bash
mkdir hosted-workflow-resilient && cd hosted-workflow-resilient
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Resilient/agent.manifest.yaml
azd deploy
```

Drive it with a background response (`"background": true`), then exercise crash recovery by letting the platform restart the container. See the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).
