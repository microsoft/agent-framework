# Workflow and Agents - Azure Functions Sample

This sample demonstrates how to combine **custom executors with AI agents** (backed by Azure OpenAI) in workflows hosted as Azure Functions. It shows single-agent workflows, multi-agent fan-out/fan-in workflows, and how multiple workflows can be registered together.

## Key Concepts Demonstrated

- Using **AI agents** (Azure OpenAI) as workflow executors alongside custom executors
- **Fan-out/fan-in** pattern with multiple AI agents running in parallel
- Registering **multiple workflows** in a single Azure Functions app via `ConfigureDurableOptions`

## Overview

Three workflows are registered, each demonstrating different patterns:

```
PhysicsExpertReview:     ParseQuestion ──► Physicist (AI Agent)

ExpertTeamReview:        ParseQuestion ──┬──► Physicist (AI Agent) ──┬──► Aggregator
                                         └──► Chemist   (AI Agent) ──┘

ChemistryExpertReview:   ParseQuestion ──► Chemist (AI Agent)
```

| Executor | Type | Description |
|----------|------|-------------|
| ParseQuestion | Custom Executor | Validates and formats the incoming question |
| Physicist | AI Agent | Physics expert backed by Azure OpenAI |
| Chemist | AI Agent | Chemistry expert backed by Azure OpenAI |
| ResponseAggregator | Custom Executor | Combines responses from multiple AI agents |

## Environment Setup

This sample requires:

- [.NET 10 SDK](https://dotnet.microsoft.com/download)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- [Durable Task Scheduler](https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-azure-managed-storage) running locally (default: `http://localhost:8080`)
- [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) for local Azure Storage emulation
- An [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/) deployment

### Configuration

Set the following environment variables in `local.settings.json`:

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | The model deployment name (e.g., `gpt-4o`) |
| `AZURE_OPENAI_KEY` | *(Optional)* API key. If not set, uses `AzureCliCredential` |

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/AzureFunctions/05_WorkflowAndAgents
func start
```

### Testing

**Single-agent workflow (Physics):**
```bash
curl -X POST http://localhost:7071/api/workflows/PhysicsExpertReview/run -H "Content-Type: text/plain" -d "What is the relationship between energy and mass?"
```

**Multi-agent workflow (Expert Team):**
```bash
curl -X POST http://localhost:7071/api/workflows/ExpertTeamReview/run -H "Content-Type: text/plain" -d "How does radiation affect living cells?"
```

**Single-agent workflow (Chemistry):**
```bash
curl -X POST http://localhost:7071/api/workflows/ChemistryExpertReview/run -H "Content-Type: text/plain" -d "What happens during combustion?"
```
