# Hosted-LocalTools

A hosted agent with **local C# function tools** for hotel search. Demonstrates how to define and wire local tools that the LLM can invoke — a key advantage of code-based hosted agents over prompt agents.

The agent specializes in finding hotels in Seattle, with a `GetAvailableHotels` tool that searches a mock hotel database by dates and budget.

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
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-LocalTools
AGENT_NAME=hosted-local-tools dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "Find me a hotel in Seattle for Dec 20-25 under $200/night"
```

Or with curl:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Find me a hotel in Seattle for Dec 20-25 under $200/night", "model": "hosted-local-tools"}'
```

## Running with Docker

Since this project uses `ProjectReference`, use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-local-tools .
```

### 3. Run the container

Generate a bearer token on your host and pass it to the container:

```bash
# Generate token (expires in ~1 hour)
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Run with token
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-local-tools \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-local-tools
```

### 4. Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What hotels are available in Seattle for next weekend?"
```

## How local tools work

The agent has a single tool `GetAvailableHotels` defined as a C# method with `[Description]` attributes. The LLM decides when to call it based on the user's request:

| Parameter | Type | Description |
|-----------|------|-------------|
| `checkInDate` | string | Check-in date (YYYY-MM-DD) |
| `checkOutDate` | string | Check-out date (YYYY-MM-DD) |
| `maxPrice` | int | Max price per night in USD (default: 500) |

The tool searches a mock database of 6 Seattle hotels and returns formatted results with name, location, rating, and pricing.

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedLocalTools.csproj` for the `PackageReference` alternative.
