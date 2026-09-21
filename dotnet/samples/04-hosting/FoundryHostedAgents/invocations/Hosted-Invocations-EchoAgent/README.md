# Hosted-Invocations-EchoAgent

A minimal agent that echoes the user's input back, hosted as a Foundry Hosted Agent over the **Invocations protocol**. No LLM or external service is required, so it is the simplest way to see the hosting pipeline end to end.

This sample deploys to Foundry **directly from source (code / ZIP upload)**: the platform builds and runs your code with no container image, so there is no Dockerfile to author or container registry to manage. Source deploy is the default for .NET.

## How it works

- `EchoAIAgent.cs` — a tiny `AIAgent` that returns `Echo: <input>`; no model call.
- `EchoInvocationHandler.cs` — an `InvocationHandler` that reads the request body as plain text, runs the agent, and writes the response back as `text/plain`.
- `Program.cs` — registers the agent and the Invocations SDK (`AddInvocationsServer` / `MapInvocationsServer`), and maps `GET /readiness`.

> **Readiness note:** unlike the Responses SDK, the Invocations SDK does **not** auto-map the
> `GET /readiness` route the Foundry runtime probes before routing calls. `Program.cs` maps it
> explicitly; without it every invoke fails with HTTP 424 `session_not_ready`.

## Files

| File | Purpose |
|------|---------|
| `Program.cs` | Registers the echo agent and the Invocations server, maps `/readiness`. |
| `EchoAIAgent.cs` | The echo agent (no LLM). |
| `EchoInvocationHandler.cs` | Reads the request body, runs the agent, writes `text/plain`. |
| `azure.yaml` | The unified `azd` project file. Declares the Foundry project and the hosted agent with `codeConfiguration` (source/ZIP deploy) and the `invocations` protocol. |
| `.agentignore` | Controls which files are excluded from the code-deploy ZIP upload (`.gitignore` syntax). |
| `HostedInvocationsEchoAgent.csproj` | Self-contained project: single target framework and explicit package versions. |
| `.env.example` | Template for local configuration. |
| `../../scripts/Add-LocalFrameworkFeed.ps1`, `../../scripts/add-local-framework-feed.sh` | Contributor-only helpers, see [Deploy your local framework changes](#deploy-your-local-framework-changes-contributors). |

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An **existing** Foundry project (no model deployment is needed for this echo sample).
- Azure CLI logged in (`az login`)
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`

## Run and test locally

**Terminal 1 — host the agent:**

```
cd dotnet/samples/04-hosting/FoundryHostedAgents/invocations/Hosted-Invocations-EchoAgent
dotnet run
```

The agent starts on `http://localhost:8088`.

**Terminal 2 — invoke it** (the Invocations protocol takes a plain-text body and returns `text/plain`):

PowerShell:

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/invocations -Method POST -Body "Hello!").Content
```

Bash:

```bash
curl -X POST http://localhost:8088/invocations -d "Hello!"
```

You get back `Echo: Hello!`.

## Deploy to Foundry (source / ZIP)

`azd` scaffolds the project into a working folder, so every step below runs from an **empty
directory outside the repository**, and `-m` points at this sample's `azure.yaml`.

```powershell
$work = Join-Path $env:TEMP "hosted-invocations-echo-work"
mkdir $work
cd $work

$sample = "<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/invocations/Hosted-Invocations-EchoAgent/azure.yaml"
azd auth login
azd ai agent init -m $sample

cd hosted-invocations-echo-agent
azd provision
azd deploy
```

`azd` packages the source into a ZIP (honoring `.agentignore`), uploads it, and Foundry runs
`dotnet restore` + `dotnet publish` on it during provisioning (`dependencyResolution: remote_build`
in `azure.yaml`). No Dockerfile, no container registry.

Invoke the deployed agent through `azd` using the Invocations protocol:

```bash
azd ai agent invoke --protocol invocations "Hello!"
```

Clean up with `azd down`, then delete the working directory.

> **`azd down` does not delete the hosted agent.** It reports success but leaves the deployed agent
> in place. Delete it explicitly with a REST call:
>
> ```bash
> az rest --method delete \
>   --url "<project-endpoint>/agents/hosted-invocations-echo-agent" \
>   --url-parameters api-version=v1 force=true \
>   --resource https://ai.azure.com
> ```

## Deploy your local framework changes (contributors)

**Skip this section unless you are changing the Agent Framework itself.** The project restores the
**published** Agent Framework packages, and Foundry restores from nuget.org when it builds the
upload. To ship a local framework build instead, run the helper between `azd ai agent init` and
`azd provision`:

```powershell
cd $work
<repo>/dotnet/samples/04-hosting/FoundryHostedAgents/scripts/Add-LocalFrameworkFeed.ps1 -Path ./hosted-invocations-echo-agent
```

See the
[`Hosted-ChatClientAgent`](../../responses/Hosted-ChatClientAgent/README.md#deploy-your-local-framework-changes-contributors)
README for the full explanation.

For the full hosted-agent deployment guide, see the [official source-code deployment doc](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code).
