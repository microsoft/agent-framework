# Hosted Harness Data Processing

This sample hosts a `HarnessAgent` that reads a sample sales CSV and writes requested reports. It reuses `dotnet/samples/02-agents/Harness/Harness_Step03_DataProcessing/working/sales.csv`. File reads are auto-approved; writes still require an explicit approval that can resume on a later hosted turn.

The project references the framework **source in this repository**. `AddFoundryResponses(agent)` uses the default `AllowStoredOutputEnabled = false`; the agent keeps chat history in its session rather than in the model service.

Deployment uses a **source ZIP**, with no Dockerfile or container registry. The preparation step includes the linked sales CSV in a standalone source folder. No Python interpreter is needed.

## Prerequisites

- .NET 10 SDK.
- An existing Foundry project and model deployment.
- Azure CLI authenticated with `az login`.
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`.
- PowerShell 7 for the local framework packaging helper.

## Run locally

1. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` for an existing Foundry model deployment, then sign in with `az login`. Copy `.env.example` to `.env` if you prefer a local file.
2. From this directory, run `dotnet run --tl:off`, then call `POST http://localhost:8088/responses` with model `hosted-harness-data-processing` and a question such as "Which region sold the most units in sales.csv?".
3. Send another request with the same conversation ID. To exercise approval, ask for a written report. The response contains an `mcp_approval_request`; send an `mcp_approval_response` with its ID in the **same conversation and hosted session**. Do not auto-approve writes. `azd ai agent invoke -f` does not send a structured Responses body; use authenticated `az rest --resource https://ai.azure.com` for the approval response.

Hosted containers have a read-only application directory. On startup the sample copies **only missing** seed files into the session's writable home directory so edited files and generated reports survive later turns.

These files rely on Foundry's session sandbox: by default each caller gets their own session with a private `$HOME` (see [Isolate hosted agent sessions per user](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user)). If you [place several users in one session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users), partition the working folder per user yourself.

## Deploy to Foundry (source ZIP)

Start in this sample directory. Prepare the source in a working directory **outside the repository**, then initialize against an existing Foundry project:

```powershell
$repo = (Resolve-Path '..\..\..\..\..\..').Path
$work = Join-Path $env:TEMP 'hosted-harness-data-processing-work'
$source = Join-Path $work 'source'

New-Item -ItemType Directory -Path $work -Force | Out-Null
dotnet msbuild HostedHarnessDataProcessing.csproj -target:PrepareSourceDeployment `
    "-property:SourceDeploymentDirectory=$source"

Set-Location $work
azd auth login
azd ai agent init -m (Join-Path $source 'azure.yaml') `
    -p '<existing-Foundry-project-ARM-resource-id>' -d '<existing-model-deployment>'
```

`PrepareSourceDeployment` includes `working/sales.csv` from the console sample and does not copy `.env`, local sessions, or build output. The copied project has one target framework and explicit package versions. Its content settings copy the CSV into the published application.

**Do not skip the package helper when testing this branch.** It includes the local framework fix rather than relying on an older published package:

```powershell
& (Join-Path $repo 'dotnet\samples\04-hosting\FoundryHostedAgents\scripts\Add-LocalFrameworkFeed.ps1') `
    -Path (Join-Path $work 'hosted-harness-data-processing')

Set-Location (Join-Path $work 'hosted-harness-data-processing')
dotnet build -c Debug --tl:off
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME '<existing-model-deployment>'
azd provision
azd deploy
azd ai agent invoke 'Which region sold the most units in sales.csv?' `
    --new-session --new-conversation -o raw
```

Foundry restores packages and publishes the application with `dependencyResolution: remote_build`. `.agentignore` includes the CSV and local framework feed while excluding secrets, build output, and local session files. Check for `response.completed` in the raw output; a zero CLI exit code alone is not evidence that the turn succeeded.

See [Research's source ZIP instructions](../Hosted-Harness-Research/README.md#deploy-to-foundry-source-zip) for package preparation on Linux or macOS and for updating an existing deployment.

## Related samples

- [Hosted Harness Research](../Hosted-Harness-Research/README.md) uses the same source ZIP preparation.
- [Hosted Harness Scaling Capabilities](../Hosted-Harness-ScalingCapabilities/README.md) retains a Dockerfile because its skill scripts need Python.
- [Official source deployment guide](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code).
