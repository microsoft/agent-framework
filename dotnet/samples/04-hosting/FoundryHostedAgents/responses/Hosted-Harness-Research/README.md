# Hosted Harness Research

This sample hosts a research `HarnessAgent` with web search, a public-network browsing tool, planning, a bounded todo loop, and session-scoped file memory. It links the browsing tool from `dotnet/samples/02-agents/Harness/Harness_Step01_Research` instead of maintaining a second implementation.

The project references the framework **source in this repository** so it exercises the local Foundry hosting fix. `AddFoundryResponses(agent)` keeps the default `AllowStoredOutputEnabled = false`. The model must not store a second copy of the response; the harness's local history marker is not a service conversation ID.

Deployment uses a **source ZIP**, with no Dockerfile or container registry. The preparation step copies the linked browsing tool into a standalone source folder. Foundry restores the packages and publishes the .NET 10 application from that folder.

## Prerequisites

- .NET 10 SDK.
- An existing Foundry project and model deployment.
- Azure CLI authenticated with `az login`.
- Azure Developer CLI (`azd`) with the AI agents extension: `azd extension install azure.ai.agents`.
- PowerShell 7 for the local framework packaging helper.

## Run locally

1. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` for an existing Foundry model deployment, then sign in with `az login`. Copy `.env.example` to `.env` if you prefer a local file.
2. From this directory, run `dotnet run --tl:off`. The host serves `POST http://localhost:8088/responses` when `ASPNETCORE_URLS=http://localhost:8088`.
3. Send a research question with model `hosted-harness-research`. Send a second request with the same conversation ID to verify that local history continues without enabling agent-side storage. The platform `store` setting is independent of the model client's `store=false` setting.

Browsing allows public networks only. The browsing tool checks every redirect against the same policy and connects only to the addresses it approved, so a public page cannot send it to a private or metadata address. File memory goes under `agent-files` locally and the session's writable home directory when hosted.

Hosted file memory relies on Foundry's session sandbox: by default each caller gets their own session with a private `$HOME` (see [Isolate hosted agent sessions per user](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user)). If you [place several users in one session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users), partition the file store per user yourself.

## Deploy to Foundry (source ZIP)

Start in this sample directory. Prepare the source in a working directory **outside the repository** so the upload includes the shared browsing tool without copying its implementation into the checked-in sample:

```powershell
$repo = (Resolve-Path '..\..\..\..\..\..').Path
$work = Join-Path $env:TEMP 'hosted-harness-research-work'
$source = Join-Path $work 'source'

New-Item -ItemType Directory -Path $work -Force | Out-Null
dotnet msbuild HostedHarnessResearch.csproj -target:PrepareSourceDeployment `
    "-property:SourceDeploymentDirectory=$source"

Set-Location $work
azd auth login
azd ai agent init -m (Join-Path $source 'azure.yaml') `
    -p '<existing-Foundry-project-ARM-resource-id>' -d '<existing-model-deployment>'
```

`PrepareSourceDeployment` copies the project, local C# files, deployment configuration, and linked browsing files. It does not copy `.env`, local sessions, or build output. The copied project has one target framework and explicit package versions, so it can build without the repository's shared project configuration.

`azd ai agent init` adopts the prepared `azure.yaml` and creates `hosted-harness-research` under `$work`. Passing `-p` selects an existing project rather than provisioning a new one.

### Include the local framework fix

**Do not skip this step when testing this branch.** Published packages may not contain the change that allows the harness to keep local chat history with model storage disabled.

The existing contributor helper packs the local framework, including `Microsoft.Agents.AI.Harness`, into the scaffolded folder. It creates `local-feed/` and `nuget.config` and updates `AgentFrameworkVersion`. Both the feed and configuration travel inside the ZIP.

```powershell
& (Join-Path $repo 'dotnet\samples\04-hosting\FoundryHostedAgents\scripts\Add-LocalFrameworkFeed.ps1') `
    -Path (Join-Path $work 'hosted-harness-research')

Set-Location (Join-Path $work 'hosted-harness-research')
dotnet build -c Debug --tl:off
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME '<existing-model-deployment>'
azd provision
azd deploy
azd ai agent invoke 'Name an official weather-data source.' `
    --new-session --new-conversation -o raw
```

Foundry runs `dotnet restore` and `dotnet publish` during deployment because `azure.yaml` sets `dependencyResolution: remote_build`. `.agentignore` excludes secrets, build output, and local session files. No Dockerfile or registry connection is needed.

For Linux or macOS, use the same `dotnet msbuild` preparation command with an absolute destination path and the sibling [`add-local-framework-feed.sh`](../../scripts/add-local-framework-feed.sh) helper after initialization. See [`Hosted-ChatClientAgent`](../Hosted-ChatClientAgent/README.md#deploy-your-local-framework-changes-contributors) for the package helper details.

For later changes, prepare a fresh source folder, copy its `.cs` and `.csproj` files and any `working/` data into the scaffolded agent directory, rerun the package helper, and run `azd deploy` from that directory. Keep the scaffolded `azure.yaml` and `.azure` environment rather than replacing them with the template. Check the raw terminal event for `response.completed` or `response.failed`; a zero CLI exit code does not prove the turn succeeded.

**Stateless web-search history:** The OpenAI chat adapter returns hosted search results with a raw `WebSearchCallResponseItem`. After another local function call, replaying that raw item to the Foundry model with `store=false` caused HTTP 400 `invalid_payload`. `StatelessWebSearchChatClient` omits only the raw search result from the *next model request*, leaving the original session history, assistant text, local function calls, and citations intact. The model does not receive that raw search metadata again, so later turns must rely on the cited assistant text for source details.

## Related samples

- [Hosted Harness Data Processing](../Hosted-Harness-DataProcessing/README.md) also uses source ZIP deployment.
- [Hosted Harness Scaling Capabilities](../Hosted-Harness-ScalingCapabilities/README.md) retains a Dockerfile to install Python for its skill scripts.
- [Official source deployment guide](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code).
