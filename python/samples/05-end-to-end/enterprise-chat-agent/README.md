# Enterprise Chat Agent

A production-ready sample demonstrating how to build a scalable Chat API using Microsoft Agent Framework with Azure Functions and Cosmos DB.

## Overview

This sample showcases:

- **Azure Functions HTTP Triggers** - Serverless REST API endpoints
- **Runtime Tool Selection** - Agent autonomously decides which tools to invoke based on user intent
- **Cosmos DB Persistence** - Two containers: `threads` (partition key `/thread_id`) and `messages` (`/session_id`)
- **Production Patterns** - Error handling, observability, and security best practices
- **One-command deployment** - `azd up` deploys all infrastructure

## Architecture

```text
Client → Azure Functions (HTTP Triggers) → ChatAgent → Azure OpenAI
                                              ↓
                                         [Tools]
                                ┌─────────┼──────────┐
                                ↓         ↓          ↓
                            Weather  Calculator  Knowledge Base
                                                     ↓
                             Microsoft Docs ← → Azure Cosmos DB
                            (MCP Integration)
```

## Prerequisites

- Python 3.11+
- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- Azure subscription with:
  - Azure OpenAI resource (GPT-4o recommended)

## Quick Start

### Option 1: Deploy to Azure (Recommended)

Deploy the complete infrastructure with a single command:

```bash
cd python/samples/05-end-to-end/enterprise-chat-agent

# Login to Azure
azd auth login

# Deploy infrastructure and application
azd up
```

This deploys:
- **Azure Function App** (Flex Consumption) - Serverless hosting
- **Azure Cosmos DB** (Serverless) - Conversation persistence
- **Azure Storage** - Function App state
- **Application Insights** - Monitoring and observability

#### Configuration

Before running `azd up`, you'll be prompted for:

| Parameter | Description |
|-----------|-------------|
| `AZURE_ENV_NAME` | Environment name (e.g., `dev`, `prod`) |
| `AZURE_LOCATION` | Azure region (e.g., `eastus2`) |
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL |
| `AZURE_OPENAI_MODEL` | Model deployment name (default: `gpt-4o`) |

#### Other azd Commands

```bash
# Provision infrastructure only (no deployment)
azd provision

# Deploy application code only
azd deploy

# View deployed resources
azd show

# Delete all resources
azd down
```

### Option 2: Run Locally

```bash
cd python/samples/05-end-to-end/enterprise-chat-agent
pip install -r requirements.txt
```

Copy `local.settings.json.example` to `local.settings.json` and update:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-4o",
    "AZURE_OPENAI_API_VERSION": "2024-10-21",
    "AZURE_COSMOS_ENDPOINT": "https://your-cosmos-account.documents.azure.com:443/",
    "AZURE_COSMOS_DATABASE_NAME": "chat_db",
    "AZURE_COSMOS_CONTAINER_NAME": "messages",
    "AZURE_COSMOS_THREADS_CONTAINER_NAME": "threads",
    "APPLICATIONINSIGHTS_CONNECTION_STRING": "",
    "ENABLE_INSTRUMENTATION": "true",
    "ENABLE_SENSITIVE_DATA": "false",
    "ENABLE_DEBUG_ENDPOINTS": "false"
  }
}
```

Run locally:

```bash
func start
```

### Test the API

After running `func start`, you can test the API in two ways:

#### Option A: API-Only Testing (demo.http)

Use the included `demo.http` file with VS Code's REST Client extension or any HTTP client:

```bash
# Create a thread
curl -X POST http://localhost:7071/api/threads

# Send a message
curl -X POST http://localhost:7071/api/threads/{thread_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "What is the weather in Seattle and what is 15% tip on $85?"}'
```

#### Option B: Interactive UI Testing (demo-ui.html)

For a quick visual way to interact with the API, open `demo-ui.html` in your browser. This provides a simple chat interface to test thread creation, messaging, and agent responses.

> ⚠️ **Development Only**: The `demo-ui.html` file is intended for local development and testing purposes only. It is not designed for production use.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/threads` | Create a new conversation thread |
| `GET` | `/api/threads` | List all threads (with optional filters) |
| `GET` | `/api/threads/{thread_id}` | Get thread metadata |
| `DELETE` | `/api/threads/{thread_id}` | Delete a thread |
| `POST` | `/api/threads/{thread_id}/messages` | Send a message and get response |
| `GET` | `/api/threads/{thread_id}/messages` | Get conversation history |

### Query Parameters for List Threads

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | string | Filter threads by user ID |
| `status` | string | Filter by status: `active`, `archived`, `deleted` |
| `limit` | int | Max threads to return (default 50, max 100) |
| `offset` | int | Skip N threads for pagination |

**Examples:**
```bash
# List all threads
GET /api/threads

# List threads for a specific user
GET /api/threads?user_id=user_1234

# List active threads with pagination
GET /api/threads?status=active&limit=20&offset=0
```

## Tool Selection Demo

The agent is configured with multiple tools and **decides at runtime** which to use:

```text
User: "What's the weather in Tokyo?"
→ Agent calls: get_weather("Tokyo")

User: "What's the weather in Paris and what's 18% tip on €75?"
→ Agent calls: get_weather("Paris") AND calculate("75 * 0.18")

User: "How do I configure partition keys in Azure Cosmos DB?"
→ Agent calls: microsoft_docs_search("Cosmos DB partition keys") via MCP
→ Returns: Official Microsoft documentation with best practices

User: "Show me Python code for Azure OpenAI chat completion"
→ Agent calls: microsoft_code_sample_search("Azure OpenAI chat") via MCP
→ Returns: Official code examples from Microsoft Learn

User: "What's your return policy?"
→ Agent calls: search_knowledge_base("return policy")

User: "Tell me a joke"
→ Agent responds directly (no tools needed)
```

### Available Tools

| Tool | Description | Source |
|------|-------------|--------|
| `microsoft_docs_search` | Search official Microsoft/Azure docs | MCP (remote) |
| `microsoft_code_sample_search` | Find code examples from Microsoft Learn | MCP (remote) |
| `search_knowledge_base` | Internal company knowledge | Local |
| `get_weather` | Current weather data | Local |
| `calculate` | Safe math evaluation (exponent ≤ 100) | Local |

> **Note:** MCP tools (`microsoft_docs_search`, `microsoft_code_sample_search`) are provided by the
> Microsoft Learn MCP server at `https://learn.microsoft.com/api/mcp` and discovered at runtime
> via `MCPStreamableHTTPTool`. No local tool file is needed.

## Streaming Responses

### Current Approach

This sample uses **buffered responses** - the agent processes the entire message and returns the complete response at once. This works well with Azure Functions and is simpler to implement.

### Streaming Support in Agent Framework

The Agent Framework supports streaming via `ResponseStream`:

```python
from agent_framework import Agent, AgentSession

# Enable streaming
response_stream = await agent.run(
    prompt="Hello, world!",
    session=session,
    stream=True  # Returns ResponseStream instead of Response
)

# Iterate over chunks as they arrive
async for chunk in response_stream:
    print(chunk.content, end="", flush=True)
```

### Why This Sample Doesn't Use Streaming

**Azure Functions buffers HTTP responses** - even with Server-Sent Events (SSE) or chunked transfer encoding, Azure Functions collects the entire response before sending it to the client. This means true streaming isn't achievable without additional infrastructure.

### Streaming Alternatives

If you need true streaming for a production chat experience, consider these options:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **FastAPI/Starlette** | Deploy as a container with native async streaming | True SSE streaming, simple to implement | Need container hosting (App Service, ACA) |
| **Azure Container Apps** | Host a streaming-capable web framework | Native streaming, auto-scaling | More infrastructure to manage |
| **Azure Web PubSub** | Real-time messaging service | True real-time, scalable | Additional service cost, more complexity |
| **Azure SignalR** | Managed SignalR service | WebSocket support, .NET integration | Adds dependency |

#### FastAPI Streaming Example

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from agent_framework import Agent, AgentSession

app = FastAPI()

@app.post("/api/threads/{thread_id}/messages/stream")
async def send_message_stream(thread_id: str, request: MessageRequest):
    async def generate():
        session = AgentSession(session_id=thread_id)
        response_stream = await agent.run(
            prompt=request.content,
            session=session,
            stream=True
        )
        async for chunk in response_stream:
            yield f"data: {json.dumps({'content': chunk.content})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Recommendation

- **For demos/prototypes**: Use buffered responses (this sample) with a typing indicator in the UI
- **For production chat UIs**: Consider FastAPI on Azure Container Apps or Web PubSub for true streaming

## Project Structure

```text
enterprise-chat-agent/
├── azure.yaml                # Azure Developer CLI configuration
├── DESIGN.md                 # Detailed design specification
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── local.settings.json.example
├── host.json                 # Azure Functions host config
├── function_app.py           # Azure Functions entry point
├── demo.http                 # API test requests
├── demo-ui.html              # Browser-based demo UI
├── services/
│   ├── agent_service.py      # ChatAgent + CosmosHistoryProvider
│   ├── cosmos_store.py       # Thread metadata storage
│   └── observability.py      # OpenTelemetry instrumentation
├── routes/
│   ├── threads.py            # Thread CRUD endpoints
│   ├── messages.py           # Message endpoint
│   └── health.py             # Health check
├── tools/
│   ├── weather.py            # Weather tool (local)
│   ├── calculator.py         # Calculator tool (local)
│   └── knowledge_base.py     # Knowledge base search tool (local)
└── infra/                    # Infrastructure as Code (Bicep)
    ├── main.bicep            # Main deployment template
    └── core/                 # Modular Bicep components
```

## Design Documentation

See [DESIGN.md](./docs/DESIGN.md) for:

- Architecture diagrams and message processing flow
- Cosmos DB data model and partition strategy
- Observability span hierarchy (framework vs custom)
- Tool selection and MCP integration details
- Security considerations

## Related Resources

- [GitHub Issue #2436](https://github.com/microsoft/agent-framework/issues/2436)
- [Microsoft Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)

