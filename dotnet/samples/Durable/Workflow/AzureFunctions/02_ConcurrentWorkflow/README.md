# Concurrent Workflow Sample

This sample demonstrates how to use the Microsoft Agent Framework to create an Azure Functions app that orchestrates concurrent execution of multiple AI agents using the fan-out/fan-in pattern within a durable workflow.

## Key Concepts Demonstrated

- Defining workflows with fan-out/fan-in edges for parallel execution using `WorkflowBuilder`
- Mixing custom executors with AI agents in a single workflow
- Concurrent execution of multiple AI agents (physics and chemistry experts)
- Response aggregation from parallel branches into a unified result
- Durable orchestration with automatic checkpointing and resumption from failures
- Viewing workflow execution history and status in the Durable Task Scheduler (DTS) dashboard

## Workflow

This sample defines a single workflow:

**ExpertReview**: `ParseQuestion` → [`Physicist`, `Chemist`] (parallel) → `Aggregator`

1. **ParseQuestion** — A custom executor that validates and formats the incoming question.
2. **Physicist** and **Chemist** — AI agents that run concurrently, each providing an expert perspective.
3. **Aggregator** — A custom executor that combines the parallel responses into a comprehensive answer.

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

This sample requires Azure OpenAI. Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` — Your Azure OpenAI endpoint URL.
- `AZURE_OPENAI_DEPLOYMENT` — The name of your chat model deployment.
- `AZURE_OPENAI_KEY` (optional) — Your Azure OpenAI API key. If not set, Azure CLI credentials are used.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request with a science question to the workflow endpoint.

You can use the `demo.http` file to trigger the workflow, or a command line tool like `curl` as shown below:

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/workflows/ExpertReview/run \
    -H "Content-Type: text/plain" \
    -d "What is temperature?"
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/workflows/ExpertReview/run `
    -ContentType text/plain `
    -Body "What is temperature?"
```

The response will confirm the workflow orchestration has started:

```text
Workflow orchestration started for ExpertReview. Orchestration instanceId: abc123def456
```

In the function app logs, you will see the fan-out/fan-in execution pattern:

```text
│ [ParseQuestion] Preparing question for AI agents...
│ [ParseQuestion] Question: "What is temperature?"
│ [ParseQuestion] → Sending to Physicist and Chemist in PARALLEL...
│ [Aggregator] 📋 Received 2 AI agent responses
│ [Aggregator] Combining into comprehensive answer...
│ [Aggregator] ✓ Aggregation complete!
```

The Physicist and Chemist AI agents execute concurrently, and the Aggregator combines their responses into a formatted expert panel result.

### Viewing Workflows in the DTS Dashboard

After running a workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to visualize the completed orchestration, inspect inputs/outputs for each step, and view execution history.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.
