# Enterprise Chat Agent

A production-ready sample demonstrating how to build a scalable Chat API using Microsoft Agent Framework with Azure Functions and Cosmos DB.

## Overview

This sample showcases:

- **Azure Functions HTTP Triggers** - Serverless REST API endpoints
- **Runtime Tool Selection** - Agent autonomously decides which tools to invoke based on user intent
- **Cosmos DB Persistence** - Durable thread and message storage with thread_id partition key
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
cd python/samples/demos/enterprise-chat-agent

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
cd python/samples/demos/enterprise-chat-agent
pip install -r requirements.txt
```

Copy `local.settings.json.example` to `local.settings.json` and update:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_MODEL": "gpt-4o",
    "AZURE_OPENAI_API_VERSION": "2024-10-21",
    "AZURE_COSMOS_ENDPOINT": "https://your-cosmos-account.documents.azure.com:443/",
    "AZURE_COSMOS_DATABASE_NAME": "chat_db",
    "AZURE_COSMOS_CONTAINER_NAME": "messages"
  }
}
```

Run locally:

```bash
func start
```

### Test the API

Use the included `demo.http` file or:

```bash
# Create a thread
curl -X POST http://localhost:7071/api/threads

# Send a message
curl -X POST http://localhost:7071/api/threads/{thread_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "What is the weather in Seattle and what is 15% tip on $85?"}'
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/threads` | Create a new conversation thread |
| `GET` | `/api/threads/{thread_id}` | Get thread metadata |
| `DELETE` | `/api/threads/{thread_id}` | Delete a thread |
| `POST` | `/api/threads/{thread_id}/messages` | Send a message and get response |
| `GET` | `/api/threads/{thread_id}/messages` | Get conversation history |

## Tool Selection Demo

The agent is configured with multiple tools and **decides at runtime** which to use:

```text
User: "What's the weather in Tokyo?"
→ Agent calls: get_weather("Tokyo")

User: "What's the weather in Paris and what's 18% tip on €75?"
→ Agent calls: get_weather("Paris") AND calculate("75 * 0.18")

User: "How do I configure partition keys in Azure Cosmos DB?"
→ Agent calls: search_microsoft_docs("Cosmos DB partition keys")
→ Returns: Official Microsoft documentation with best practices

User: "Show me Python code for Azure OpenAI chat completion"
→ Agent calls: search_microsoft_code_samples("Azure OpenAI chat", language="python")
→ Returns: Official code examples from Microsoft Learn

User: "What's your return policy?"
→ Agent calls: search_knowledge_base("return policy")

User: "Tell me a joke"
→ Agent responds directly (no tools needed)
```

### Available Tools

| Tool | Description | Example Use |
|------|-------------|-------------|
| `search_microsoft_docs` | Search official Microsoft/Azure docs | Azure services, cloud architecture |
| `search_microsoft_code_samples` | Find code examples from Microsoft Learn | SDK usage, implementation samples |
| `search_knowledge_base` | Internal company knowledge | Policies, FAQs, procedures |
| `get_weather` | Current weather data | Weather queries |
| `calculate` | Safe math evaluation | Calculations, tips, conversions |

## Project Structure

```text
enterprise-chat-agent/
├── azure.yaml                # Azure Developer CLI configuration
├── DESIGN.md                 # Detailed design specification
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── local.settings.json.example
├── host.json                 # Azure Functions host config
├── function_app.py           # HTTP trigger endpoints
├── cosmos_store.py           # Cosmos DB conversation store
├── tools/
│   ├── __init__.py
│   ├── weather.py            # Weather tool
│   ├── calculator.py         # Calculator tool
│   ├── knowledge_base.py     # Knowledge base search tool
│   └── microsoft_docs.py     # Microsoft Docs MCP integration
├── infra/                    # Infrastructure as Code (Bicep)
│   ├── main.bicep            # Main deployment template
│   ├── main.parameters.json  # Parameter file
│   ├── abbreviations.json    # Resource naming abbreviations
│   └── core/
│       ├── database/
│       │   └── cosmos-nosql.bicep
│       ├── host/
│       │   └── function-app.bicep
│       ├── monitor/
│       │   └── monitoring.bicep
│       └── storage/
│           └── storage-account.bicep
└── demo.http                 # Test requests
```

## Design Documentation

See [DESIGN.md](./DESIGN.md) for:

- Detailed architecture decisions
- Cosmos DB data model and partition strategy
- Thread-based conversation isolation
- Phased implementation plan
- Security considerations

## Related Resources

- [GitHub Issue #2436](https://github.com/microsoft/agent-framework/issues/2436)
- [Microsoft Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)

## Implementation Status

### ✅ Completed
- ✅ Create tools (weather, calculator, knowledge_base)
- ✅ Create an agent (ChatAgent with Azure OpenAI)
- ✅ Use tools with agents (@ai_function decorators + agent configuration)
- ✅ Cosmos DB persistence
- ✅ OpenTelemetry observability

### 🔄 Pending
- ⏳ Test agent locally with `func start`
- ⏳ Check the logs in Application Insights
- ⏳ Deploy to Azure with `azd up`
