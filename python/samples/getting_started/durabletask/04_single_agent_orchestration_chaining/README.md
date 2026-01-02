# Single Agent Orchestration Chaining Sample

This sample demonstrates how to chain multiple invocations of the same agent using a durable orchestration while preserving conversation state between runs.

## Key Concepts Demonstrated

- Using durable orchestrations to coordinate sequential agent invocations.
- Chaining agent calls where the output of one run becomes input to the next.
- Maintaining conversation context across sequential runs using a shared thread.
- Using `DurableAIAgentOrchestrationContext` to access agents within orchestrations.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using one of two approaches:

### Option 1: Combined Worker + Client (Quick Start)

```bash
cd samples/getting_started/durabletask/04_single_agent_orchestration_chaining
python sample.py
```

This runs both worker and client in a single process.

### Option 2: Separate Worker and Client

**Start the worker in one terminal:**

```bash
python worker.py
```

**In a new terminal, run the client:**

```bash
python client.py
```

The orchestration will execute the writer agent twice sequentially, and you'll see output like:

```
[Orchestration] Starting single agent chaining...
[Orchestration] Created thread: abc-123
[Orchestration] First agent run: Generating initial sentence...
[Orchestration] Initial response: Every small step forward is progress toward mastery.
[Orchestration] Second agent run: Refining the sentence...
[Orchestration] Refined response: Each small step forward brings you closer to mastery and growth.
[Orchestration] Chaining complete

================================================================================
Orchestration Result
================================================================================
Each small step forward brings you closer to mastery and growth.
```

## Viewing Orchestration State

You can view the state of the orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view the orchestration instance, including:
   - The sequential execution of both agent runs
   - The conversation thread shared between runs
   - Input and output at each step
   - Overall orchestration state and history

The orchestration maintains the conversation context across both agent invocations, demonstrating how durable orchestrations can coordinate multi-step agent workflows.

