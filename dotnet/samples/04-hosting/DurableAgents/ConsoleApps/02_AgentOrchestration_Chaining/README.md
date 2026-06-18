# Single Agent Orchestration Sample

This sample demonstrates how to use the durable agents extension to create a simple console app that orchestrates sequential calls to a single AI agent using the same session for context continuity.

## Key Concepts Demonstrated

- Orchestrating multiple interactions with the same agent in a deterministic order
- Using the same `AgentSession` across multiple calls to maintain conversational context
- Durable orchestration with automatic checkpointing and resumption from failures
- Waiting for orchestration completion using `WaitForInstanceCompletionAsync`

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/02_AgentOrchestration_Chaining
dotnet run --framework net10.0
```

The app will start the orchestration, wait for it to complete, and display the result:

```text
=== Single Agent Orchestration Chaining Sample ===
Starting orchestration...

Orchestration started with instance ID: 86313f1d45fb42eeb50b1852626bf3ff
Waiting for completion...

✓ Orchestration completed successfully!

Result: Learning serves as the key, opening doors to boundless opportunities and a brighter future.
```

The orchestration will proceed to run the WriterAgent twice in sequence:

1. First, it writes an inspirational sentence about learning
2. Then, it refines the initial output using the same conversation thread

## Viewing Orchestration State

You can view the state of the orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can see:
   - **Orchestrations**: View the orchestration instance, including its runtime status, input, output, and execution history
   - **Agents**: View the state of the WriterAgent, including conversation history maintained across the orchestration steps

The orchestration instance ID is displayed in the console output. You can use this ID to find the specific orchestration in the dashboard and inspect its execution details, including the sequence of agent calls and their results.
