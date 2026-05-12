# Hosted-Workflow-Handoff

A hosted agent server demonstrating two patterns in a single app:

- **`tool-agent`** — an agent with local tools (time, weather) plus remote Microsoft Learn MCP tools
- **`triage-workflow`** — a handoff workflow that routes conversations to specialist agents (code expert or creative writer) using `AgentWorkflowBuilder`

Both agents are served over the Responses protocol. The server also exposes interactive web demos at `/tool-demo` and `/workflow-demo`.

> Unlike the other samples in this folder, this one connects to an **Azure OpenAI** resource directly (not an Azure AI Foundry project endpoint).

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure OpenAI resource with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
AZURE_OPENAI_ENDPOINT=https://<your-account>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_BEARER_TOKEN=DefaultAzureCredential
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
```

`AZURE_BEARER_TOKEN=DefaultAzureCredential` is a sentinel value that tells the app to skip the bearer token and fall through to `DefaultAzureCredential` (requires `az login`). Set it to a real token only when running in Docker.

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Workflow-Handoff
dotnet run
```

The server starts on `http://localhost:8088`. Open `http://localhost:8088` to see the demo index page.

### Test it

Using the Azure Developer CLI (invokes `triage-workflow` — the primary/default agent):

```bash
azd ai agent invoke --local "Write me a short poem about coding"
```

To target a specific agent by name, use curl:

```bash
# Invoke triage-workflow explicitly
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Write me a haiku about autumn", "model": "triage-workflow"}'
```

```bash
# Invoke tool-agent (local tools + MCP)
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What time is it in Tokyo?", "model": "tool-agent"}'
```

## Running with Docker

### 1. Publish for the container runtime

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-workflow-handoff .
```

### 3. Run the container

```bash
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

docker run --rm -p 8088:8088 \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-workflow-handoff
```

### 4. Test it

```bash
azd ai agent invoke --local "Explain async/await in C#"
```

## How the triage workflow works

```
User message
     │
     ▼
┌──────────────┐
│ Triage Agent │  ──routes──▶  ┌─────────────┐
│  (router)    │               │ Code Expert │
└──────────────┘               └─────────────┘
     ▲                                │
     │◀──────────────────────────────┘
     │
     └──routes──▶  ┌─────────────────┐
                   │ Creative Writer │
                   └─────────────────┘
```

The triage agent receives every message and hands off to the appropriate specialist. Specialists route back to the triage agent after responding, allowing for multi-turn conversations.

## NuGet package users

Use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedWorkflowHandoff.csproj` for the `PackageReference` alternative.
