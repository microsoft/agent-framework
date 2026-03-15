# Hosting Your Agent

**Sample:** `dotnet/samples/01-get-started/06_host_your_agent/`

The `Microsoft.Agents.AI.Hosting.AzureFunctions` package lets you host any `AIAgent` as an Azure Functions app. It auto-generates HTTP endpoints and uses Durable Functions for stateful, long-running conversations.

## The Complete Program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to host an AI agent with Azure Functions (DurableAgents).
//
// Prerequisites:
//   - Azure Functions Core Tools
//   - Azure OpenAI resource
//
// Environment variables:
//   AZURE_OPENAI_ENDPOINT
//   AZURE_OPENAI_DEPLOYMENT_NAME (defaults to "gpt-4o-mini")
//
// Run with: func start
// Then call: POST http://localhost:7071/api/agents/HostedAgent/run

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Set up an AI agent following the standard MAF pattern.
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(
        instructions: "You are a helpful assistant hosted in Azure Functions.",
        name: "HostedAgent");

// Configure the function app to host the AI agent.
// This will automatically generate HTTP API endpoints for the agent.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)))
    .Build();

app.Run();
```

## How DurableAgents Works

The `ConfigureDurableAgents` extension wraps your `AIAgent` with Azure Durable Functions orchestration:

```
Client → POST /api/agents/{name}/run
              ↓
         Durable orchestrator (manages session lifecycle)
              ↓
         Your AIAgent.RunAsync(message, session)
              ↓
         Azure OpenAI
```

Sessions are persisted in Durable Functions state storage — no database code needed. The `timeToLive` parameter sets when idle sessions are cleaned up.

## Generated HTTP Endpoints

After `func start`, the following endpoints are available:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/agents/{name}/run` | Start a new conversation or continue an existing one |
| `GET` | `/api/agents/{name}/sessions/{sessionId}` | Get session metadata |
| `DELETE` | `/api/agents/{name}/sessions/{sessionId}` | Delete a session |

### Example: Start a conversation

```bash
curl -X POST http://localhost:7071/api/agents/HostedAgent/run \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello!"}'
```

Response:
```json
{
  "sessionId": "abc123",
  "response": "Hello! How can I help you today?"
}
```

### Example: Continue the conversation

```bash
curl -X POST http://localhost:7071/api/agents/HostedAgent/run \
     -H "Content-Type: application/json" \
     -d '{"sessionId": "abc123", "message": "What did I just say?"}'
```

## Running Locally

### Prerequisites

```bash
# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

### Run

```bash
cd dotnet/samples/01-get-started/06_host_your_agent
func start
```

### Test

```bash
curl -X POST http://localhost:7071/api/agents/HostedAgent/run \
     -H "Content-Type: application/json" \
     -d '{"message": "Tell me a joke."}'
```

## Deploying to Azure

The sample runs locally via Azure Functions Core Tools. To deploy to Azure:

```bash
# Create a function app (requires Azure CLI)
az functionapp create \
    --resource-group myRG \
    --name my-maf-agent \
    --storage-account mystorageacct \
    --runtime dotnet-isolated \
    --runtime-version 9 \
    --functions-version 4

# Deploy
func azure functionapp publish my-maf-agent
```

Set the same environment variables (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`) as Application Settings in the Azure portal.

## Key Takeaways

- `ConfigureDurableAgents` is one method call — it handles HTTP routing, session persistence, and TTL
- Any `AIAgent` (with tools, memory, etc.) works as a hosted agent
- Sessions are persisted automatically by Durable Functions
- The same HTTP API works locally and in Azure
- `timeToLive` controls how long idle sessions are kept before cleanup
