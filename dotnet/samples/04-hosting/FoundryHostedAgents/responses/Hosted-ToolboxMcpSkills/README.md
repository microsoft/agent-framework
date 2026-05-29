# Hosted-ToolboxMcpSkills

A hosted agent that discovers **MCP-based skills from a Foundry Toolbox** and makes them available to the agent using `AgentSkillsProviderBuilder.UseMcpSkills(mcpClient)`.

The `AgentSkillsProvider` is attached to the agent as a context provider and implements the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern. When the agent is prompted, it discovers available skills in the Foundry Toolbox via the provider:

1. **Advertise** - skill names and descriptions are injected into the system prompt so the agent knows what is available.
2. **Load** - when the agent decides a skill is relevant, it retrieves the full skill body with detailed instructions via the provider.
3. **Read resources** - if a skill includes supplementary content (reference documents, assets), the agent reads them on demand via the provider.

This way the full skill body and resources are only loaded when the agent actually needs them, reducing token usage.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a deployed model (e.g., `gpt-5`)
- A Foundry Toolbox already configured with skills provisioned
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` and set your Azure AI Foundry project endpoint and toolbox name:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5
FOUNDRY_TOOLBOX_NAME=my-toolbox
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-ToolboxMcpSkills
dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What skills do you have available?"
```

## Running with Docker

Since this project uses `ProjectReference`, use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-toolbox-mcp-skills .
```

### 3. Run the container

Generate a bearer token on your host and pass it to the container:

```bash
# Generate token (expires in ~1 hour)
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Run with token
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-toolbox-mcp-skills \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-toolbox-mcp-skills
```

> **Note:** `AGENT_NAME` is passed via `-e` to simulate the platform injection. `AZURE_BEARER_TOKEN` provides Azure credentials to the container (tokens expire after ~1 hour). The `.env` file provides the remaining configuration.

### 4. Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What skills do you have available?"
```

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedToolboxMcpSkills.csproj` for the `PackageReference` alternative.
