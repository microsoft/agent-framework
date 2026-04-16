# Hosted-FoundryAgent

A hosted agent that delegates to a **Foundry-managed agent definition**. Instead of defining the model, instructions, and tools inline in code, this sample retrieves an existing agent registered in the Foundry platform via `AIProjectClient.AsAIAgent(agentRecord)` and hosts it using the Responses protocol.

This is the **Foundry hosting** pattern — the agent's behavior is configured in the platform (via Foundry UI, CLI, or API), and this server simply wraps and serves it.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a **registered agent** (created via Foundry UI, CLI, or API)
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your project endpoint:

```bash
cp .env.example .env
```

Edit `.env` and set your Azure AI Foundry project endpoint:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

You also need to set `AGENT_NAME` — the name of the Foundry-managed agent to host. This is injected automatically by the Foundry platform when deployed. For local development, pass it as an environment variable.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-FoundryAgent
AGENT_NAME=<your-agent-name> dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "Hello!"
```

Or with curl (specifying the agent name explicitly):

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello!", "model": "<your-agent-name>"}'
```

## Running with Docker

Since this project uses `ProjectReference`, the standard `Dockerfile` cannot resolve dependencies outside this folder. Use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-foundry-agent .
```

### 3. Run the container

Generate a bearer token on your host and pass it to the container:

```bash
# Generate token (expires in ~1 hour)
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Run with token
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=<your-agent-name> \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-foundry-agent
```

> **Note:** `AGENT_NAME` is passed via `-e` to simulate the platform injection. `AZURE_BEARER_TOKEN` provides Azure credentials to the container (tokens expire after ~1 hour). The `.env` file provides the remaining configuration.

### 4. Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "Hello!"
```

Or with curl (specifying the agent name explicitly):

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello!", "model": "<your-agent-name>"}'
```

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the standard `Dockerfile` instead of `Dockerfile.contributor` — it performs a full `dotnet restore` and `dotnet publish` inside the container. See the commented section in `HostedFoundryAgent.csproj` for the `PackageReference` alternative.

## How it differs from Hosted-ChatClientAgent

| | Hosted-ChatClientAgent | Hosted-FoundryAgent |
|---|---|---|
| **Agent definition** | Inline in code (`AsAIAgent(model, instructions)`) | Managed in Foundry platform (`AsAIAgent(agentRecord)`) |
| **Model/instructions** | Set in `Program.cs` | Set in Foundry UI/CLI/API |
| **Tools** | Defined in code | Configured in the platform |
| **Use case** | Full control over agent behavior | Platform-managed agent with centralized config |
