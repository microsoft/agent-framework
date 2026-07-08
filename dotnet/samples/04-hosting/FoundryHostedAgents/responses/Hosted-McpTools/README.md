# Hosted-McpTools

A hosted agent demonstrating **two layers of MCP (Model Context Protocol) tool integration**:

1. **Client-side MCP (Microsoft Learn)** — The agent connects directly to the Microsoft Learn MCP server via `McpClient`, discovers tools, and handles tool invocations locally within the agent process.

2. **Server-side MCP (Microsoft Learn)** — The agent declares a `HostedMcpServerTool` which delegates tool discovery and invocation to the LLM provider (Azure OpenAI Responses API). The provider calls the MCP server on behalf of the agent with no local connection needed.

## How the two MCP patterns differ

| | Client-side MCP | Server-side MCP |
|---|---|---|
| **Connection** | Agent connects to MCP server directly | LLM provider connects to MCP server |
| **Tool invocation** | Handled by the agent process | Handled by the Responses API |
| **Auth** | Agent manages credentials | Provider manages credentials |
| **Use case** | Custom/private MCP servers, fine-grained control | Public MCP servers, simpler setup |
| **Example** | Microsoft Learn (`McpClient` + `HttpClientTransport`) | Microsoft Learn (`HostedMcpServerTool`) |

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- A Foundry project with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
FOUNDRY_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
FOUNDRY_MODEL=gpt-4o
```

## Running directly (contributors)

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-McpTools
dotnet run
```

### Test it

Using the Azure Developer CLI:

```bash
# Uses GitHub MCP (client-side)
azd ai agent invoke --local "Search for the agent-framework repository on GitHub"

# Uses Microsoft Learn MCP (server-side)
azd ai agent invoke --local "How do I create an Azure storage account using az cli?"
```

## Running with Docker

### 1. Publish for the container runtime

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build and run

```bash
docker build -f Dockerfile.contributor -t hosted-mcp-tools .

export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

docker run --rm -p 8088:8088 \
  -e AGENT_NAME=mcp-tools \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-mcp-tools
```

## Deploying to Foundry (azd spec)

This sample includes an `azd` manifest (`agent.manifest.yaml`) and hosted agent spec (`agent.yaml`) for deployment to Foundry.

Initialize an `azd` project from this sample's manifest:

```bash
mkdir mcp-tools && cd mcp-tools
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-McpTools/agent.manifest.yaml
```

Then deploy:

```bash
azd deploy
```

If you need to override defaults, set deployment-time environment variables in the `azd` environment before deploying:

```bash
azd env set AGENT_NAME mcp-tools
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4o
```

For end-to-end hosted agent deployment guidance, see the [official deployment guide](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

---

## NuGet package users

Use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedMcpTools.csproj` for the `PackageReference` alternative.

## Related samples

- [`Hosted-Toolbox/`](../Hosted-Toolbox/) — connects to a single Foundry Toolbox via the AF Foundry hosting bridge (`AddFoundryToolboxes` + `FoundryAITool.CreateHostedMcpToolbox`).
- [`Hosted-Toolbox-AuthPaths/`](../Hosted-Toolbox-AuthPaths/) — same hosting bones as `Hosted-Toolbox/`, but the toolbox bundles three MCP tools each authenticated differently (key, Entra agent identity, inline `Authorization`), driven by the shared `Using-Samples/SimpleAgent/` REPL.

