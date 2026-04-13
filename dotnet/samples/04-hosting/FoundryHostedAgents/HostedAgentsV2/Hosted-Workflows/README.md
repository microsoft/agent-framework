# Hosted-Workflows

A hosted agent that demonstrates **multi-agent workflow orchestration**. Three translation agents are composed into a sequential pipeline: English → French → Spanish → English, showing how agents can be chained as workflow executors using `WorkflowBuilder`.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your project endpoint:

```bash
cp .env.local .env
```

Edit `.env` and set your Azure AI Foundry project endpoint:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
```

> **Note:** `.env` is gitignored. The `.env.local` template is checked in as a reference.

## Running directly (contributors)

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/HostedAgentsV2/Hosted-Workflows
AGENT_NAME=hosted-workflows dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "The quick brown fox jumps over the lazy dog"
```

Or with curl:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "The quick brown fox jumps over the lazy dog", "model": "hosted-workflows"}'
```

The text will be translated through the chain: English → French → Spanish → English.

## Running with Docker

### 1. Publish for the container runtime

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-workflows .
```

### 3. Run the container

```bash
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-workflows \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-workflows
```

### 4. Test it

```bash
azd ai agent invoke --local "Hello, how are you today?"
```

## How the workflow works

```
Input text
    │
    ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│ French Agent │ →  │ Spanish Agent │ →  │ English Agent │
│ (translate)  │    │ (translate)   │    │ (translate)   │
└─────────────┘    └──────────────┘    └──────────────┘
                                              │
                                              ▼
                                        Final output
                                     (back in English)
```

Each agent in the chain receives the output of the previous agent. The final result demonstrates how meaning is preserved (or subtly shifted) through multiple translation hops.

## NuGet package users

Use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedWorkflows.csproj` for the `PackageReference` alternative.
