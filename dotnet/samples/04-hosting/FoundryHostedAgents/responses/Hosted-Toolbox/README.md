# Hosted-Toolbox

A hosted Foundry agent that loads tools from a single Foundry Toolbox via the AF Foundry hosting bridge.

`AddFoundryToolboxes(credential, name)` registers a `FoundryToolboxService` that connects to the Foundry Toolboxes MCP proxy at startup, discovers the toolbox's bundled tools via `tools/list`, and makes them available to the agent on every request. The agent code does nothing per request; the toolbox is baked in on the server.

This is the minimal toolbox intro. For a richer walkthrough where a single toolbox bundles three MCP tools each authenticated differently, see [`Hosted-Toolbox-AuthPaths/`](../Hosted-Toolbox-AuthPaths/).

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- A Foundry project with a deployed model (e.g., `gpt-4o`) and a Toolbox configured
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your values:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
TOOLBOX_NAME=my-toolset
```

Configuration notes:

- `AZURE_AI_PROJECT_ENDPOINT` (local-dev) or `FOUNDRY_PROJECT_ENDPOINT` (auto-injected in hosted containers).
- `AZURE_AI_MODEL_DEPLOYMENT_NAME` (default `gpt-4o`).
- `TOOLBOX_NAME` (default `my-toolset`). Use `TOOLBOX_NAME`, not `FOUNDRY_TOOLBOX_NAME`: all `FOUNDRY_*` env-var names are reserved by the Foundry platform and rejected at agent-create, so a `FOUNDRY_*`-named value would not survive deployment.

The `Foundry.Hosting` package builds the toolbox proxy URL from `FOUNDRY_PROJECT_ENDPOINT` as `{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{TOOLBOX_NAME}/mcp?api-version=v1` per [`tools-integration-spec.md`](https://github.com/microsoft/AgentSchema/blob/main/specs/agents/hosted_agents/container-spec/docs/tools-integration-spec.md) §2–§3.

## Running directly (contributors)

```powershell
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Toolbox
dotnet run --tl:off
```

### Test it

Using the Azure Developer CLI:

```powershell
azd ai agent invoke --local "What tools do you have available, and what can they do?"
```

## Running with Docker

### 1. Publish for the container runtime

```powershell
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build and run

```powershell
docker build -f Dockerfile.contributor -t hosted-toolbox .

$env:AZURE_BEARER_TOKEN = (az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

docker run --rm -p 8088:8088 `
  -e AGENT_NAME=hosted-toolbox-agent `
  -e AZURE_BEARER_TOKEN=$env:AZURE_BEARER_TOKEN `
  --env-file .env `
  hosted-toolbox
```

## Deploying to Foundry (azd spec)

This sample includes an `azd` manifest (`agent.manifest.yaml`) and hosted agent spec (`agent.yaml`) for deployment to Foundry.

Initialize an `azd` project from this sample's manifest:

```powershell
mkdir hosted-toolbox; cd hosted-toolbox
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Toolbox/agent.manifest.yaml
```

Then deploy:

```powershell
azd deploy
```

If you need to override defaults, set deployment-time environment variables in the `azd` environment before deploying:

```powershell
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4o
azd env set TOOLBOX_NAME my-toolset
```

For end-to-end hosted agent deployment guidance, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

---

## NuGet package users

Use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedToolbox.csproj` for the `PackageReference` alternative.

## Related samples

- [`Hosted-Toolbox-AuthPaths/`](../Hosted-Toolbox-AuthPaths/) — same hosting bones as this sample, but the toolbox bundles three MCP tools each authenticated differently (key, Entra agent identity, inline `Authorization`), driven by the shared `Using-Samples/SimpleAgent/` REPL.
- [`Hosted-McpTools/`](../Hosted-McpTools/) — contrasts client-side `McpClient` vs server-side `HostedMcpServerTool` for non-toolbox MCP servers.
