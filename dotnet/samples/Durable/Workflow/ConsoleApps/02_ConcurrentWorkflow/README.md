# Concurrent Workflow Sample (Fan-Out/Fan-In)

This sample demonstrates the **fan-out/fan-in** pattern in a durable workflow, combining class-based executors with AI agents running in parallel.

## Key Concepts Demonstrated

- **Fan-out/Fan-in pattern**: Parallel execution with result aggregation
- **Mixed executor types**: Class-based executors and AI agents in the same workflow
- **AI agents as executors**: Using `ChatClient.AsAIAgent()` to create workflow-compatible agents
- **Workflow registration**: Auto-registration of agents used within workflows
- **Standalone agents**: Registering agents outside of workflows

## Overview

The sample implements an expert review workflow with four executors:

```
                    ParseQuestion
                         |
              +----------+----------+
              |                     |
          Physicist              Chemist
          (AI Agent)            (AI Agent)
              |                     |
              +----------+----------+
                         |
                    Aggregator
```

| Executor | Type | Description |
|----------|------|-------------|
| ParseQuestion | Class-based | Parses the user's question for expert review |
| Physicist | AI Agent | Provides physics perspective (runs in parallel) |
| Chemist | AI Agent | Provides chemistry perspective (runs in parallel) |
| Aggregator | Class-based | Combines expert responses into a final answer |

## Fan-Out/Fan-In Pattern

The workflow demonstrates the fan-out/fan-in pattern:

1. **Fan-out**: `ParseQuestion` sends the question to both `Physicist` and `Chemist` simultaneously
2. **Parallel execution**: Both AI agents process the question concurrently
3. **Fan-in**: `Aggregator` waits for both agents to complete, then combines their responses

This pattern is useful for:
- Gathering multiple perspectives on a problem
- Parallel processing of independent tasks
- Reducing overall execution time through concurrency

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment.

### Required Environment Variables

```bash
# Durable Task Scheduler (optional, defaults to localhost)
DURABLE_TASK_SCHEDULER_CONNECTION_STRING="Endpoint=http://localhost:8080;TaskHub=default;Authentication=None"

# Azure OpenAI (required)
AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
AZURE_OPENAI_DEPLOYMENT="gpt-4o"
AZURE_OPENAI_KEY="your-key"  # Optional if using Azure CLI credentials
```

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/02_ConcurrentWorkflow
dotnet run --framework net10.0
```

### Sample Output

```text
+-----------------------------------------------------------------------+
|  Fan-out/Fan-in Workflow Sample (4 Executors)                         |
|                                                                       |
|  ParseQuestion -> [Physicist, Chemist] -> Aggregator                  |
|  (class-based)    (AI agents, parallel)  (class-based)                |
+-----------------------------------------------------------------------+

Enter a science question (or 'exit' to quit):

Question: Why is the sky blue?
Instance: abc123...

[ParseQuestion] Parsing question for expert review...
[Physicist] Analyzing from physics perspective...
[Chemist] Analyzing from chemistry perspective...
[Aggregator] Combining expert responses...

Workflow completed!

Physics perspective: The sky appears blue due to Rayleigh scattering...
Chemistry perspective: The molecular composition of our atmosphere...
Combined answer: ...

Question: exit
```
