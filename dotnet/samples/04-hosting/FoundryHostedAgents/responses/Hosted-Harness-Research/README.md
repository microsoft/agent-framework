# Hosted Harness Research

This sample hosts a research `HarnessAgent` with web search, a public-network browsing tool, planning, a bounded todo loop, and session-scoped file memory. It links the browsing tool from `dotnet/samples/02-agents/Harness/Harness_Step01_Research` instead of maintaining a second implementation.

The project references the framework **source in this repository** so it exercises the local Foundry hosting fix. `AddFoundryResponses(agent)` keeps the default `AllowStoredOutputEnabled = false`. The model must not store a second copy of the response; the harness's local history marker is not a service conversation ID.

## Run locally

1. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` for an existing Foundry model deployment, then sign in with `az login`. Copy `.env.example` to `.env` if you prefer a local file.
2. From this directory, run `dotnet run --tl:off`. The host serves `POST http://localhost:8088/responses` when `ASPNETCORE_URLS=http://localhost:8088`.
3. Send a research question with model `hosted-harness-research`. Send a second request with the same conversation ID to verify that local history continues without enabling agent-side storage. The platform `store` setting is independent of the model client's `store=false` setting.

Browsing allows public networks only. The browsing tool checks every redirect against the same policy and connects only to the addresses it approved, so a public page cannot send it to a private or metadata address. File memory goes under `agent-files` locally and the session's writable home directory when hosted.

Hosted file memory relies on Foundry's session sandbox: by default each caller gets their own session with a private `$HOME` (see [Isolate hosted agent sessions per user](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user)). If you [place several users in one session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users), partition the file store per user yourself.

## Container build from this checkout

The project links source code outside this directory and therefore **cannot** be uploaded alone for Foundry source/ZIP deployment. Publish from the MAF checkout first, then build the included runtime Dockerfile from this folder:

```powershell
dotnet publish HostedHarnessResearch.csproj -c Release -f net10.0 -r linux-musl-x64 --self-contained false -o out --tl:off
docker build -t hosted-harness-research .
```

The resulting image includes the local framework assemblies. Rebuild the image after changes to the framework; do not substitute currently published packages for this validation.

## Deploy with an existing Foundry project

Use a persistent directory **outside the repository** for the `azd` environment. The project and its ContainerRegistry connection must already exist. This flow builds the image remotely through that connection, so the developer does not need direct registry login or a local `docker build`. From this sample directory, after publishing:

```powershell
$state = '<persistent-azd-state-directory>'
$projectId = '<existing-Foundry-project-ARM-resource-id>'
$model = '<existing-model-deployment>'
$connection = '<existing-ContainerRegistry-connection-name>'
$agent = 'maf-harness-research'
$bundle = Join-Path $state 'src\hosted-harness-research'

New-Item -ItemType Directory -Path (Join-Path $bundle 'out') -Force | Out-Null
Copy-Item Dockerfile (Join-Path $bundle 'Dockerfile') -Force
Copy-Item -Path 'out\*' -Destination (Join-Path $bundle 'out') -Recurse -Force

# First deployment only. Keep the generated azure.yaml and .azure directory for later deployments.
azd ai agent init --no-prompt --kind hosted --deploy-mode container `
    --src $bundle --agent-name $agent --protocol responses `
    --project-id $projectId --model-deployment $model `
    --acr-connection $connection -C $state
azd deploy $agent -C $state --no-prompt
azd ai agent invoke $agent 'Name an official weather-data source.' `
    --new-session --new-conversation -C $state --no-prompt
```

For later changes, re-publish, copy the updated `out\*` files into the same bundle, and run `azd deploy` again. `azd ai agent invoke -o raw` reveals the actual `response.completed` or `response.failed` event; a zero CLI exit code does not prove the turn succeeded.

**Stateless web-search history:** The OpenAI chat adapter returns hosted search results with a raw `WebSearchCallResponseItem`. After another local function call, replaying that raw item to the Foundry model with `store=false` caused HTTP 400 `invalid_payload`. `StatelessWebSearchChatClient` omits only the raw search result from the *next model request*, leaving the original session history, assistant text, local function calls, and citations intact. The model does not receive that raw search metadata again, so later turns must rely on the cited assistant text for source details.

**Live validation:** On tao-cace, the same compound request that failed twice before this filter completed in two new hosted sessions with a cited source, a completed todo, and a saved report. A subsequent turn read the report from file memory. The previously failing plan-then-execute two-turn sequence also completed. Hosted web search remains enabled; `AllowStoredOutputEnabled` remains `false`. Check the raw terminal event when repeating this scenario: `azd` can exit zero even if a response failed.
