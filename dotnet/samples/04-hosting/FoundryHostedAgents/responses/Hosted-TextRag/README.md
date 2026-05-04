# Hosted-TextRag

A hosted agent with **Retrieval Augmented Generation (RAG)** capabilities using `TextSearchProvider`. The agent grounds its answers in product documentation by running a search before each model invocation, then citing the source in its response.

This sample demonstrates how to add knowledge grounding to a hosted agent without requiring an external search index — using a mock search function that can be replaced with Azure AI Search or any other provider.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a deployed model (e.g., `gpt-4o`)
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
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
AZURE_BEARER_TOKEN=
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-TextRag
AGENT_NAME=hosted-text-rag dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What is your return policy?"
azd ai agent invoke --local "How long does shipping take?"
azd ai agent invoke --local "How do I clean my tent?"
```

Or with curl:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is your return policy?", "model": "hosted-text-rag"}'
```

## Running with Docker

Since this project uses `ProjectReference`, use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-text-rag .
```

### 3. Run the container

Generate a bearer token on your host and pass it to the container:

```bash
# Generate token (expires in ~1 hour)
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Run with token
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-text-rag \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-text-rag
```

### 4. Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What is your return policy?"
```

## How RAG works in this sample

The `TextSearchProvider` runs a mock search **before each model invocation**:

| User query contains | Search result injected |
|---|---|
| "return" or "refund" | Contoso Outdoors Return Policy |
| "shipping" | Contoso Outdoors Shipping Guide |
| "tent" or "fabric" | TrailRunner Tent Care Instructions |

The model receives the search results as additional context and cites the source in its response. In production, replace `MockSearchAsync` with a call to Azure AI Search or your preferred search provider.

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedTextRag.csproj` for the `PackageReference` alternative.
