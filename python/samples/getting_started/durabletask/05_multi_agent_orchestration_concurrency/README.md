# Multi-Agent Orchestration with Concurrency Sample

This sample demonstrates how to host multiple agents and run them concurrently using a durable orchestration, aggregating their responses into a single result.

## Key Concepts Demonstrated

- Running multiple specialized agents in parallel within an orchestration.
- Using `OrchestrationAgentExecutor` to get `DurableAgentTask` objects for concurrent execution.
- Aggregating results from multiple agents using `task.when_all()`.
- Creating separate conversation threads for independent agent contexts.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using one of two approaches:

### Option 1: Combined Worker + Client (Quick Start)

```bash
cd samples/getting_started/durabletask/05_multi_agent_orchestration_concurrency
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

The orchestration will execute both agents concurrently, and you'll see output like:

```
Prompt: What is temperature?

Starting multi-agent concurrent orchestration...
Orchestration started with instance ID: abc123...
Orchestration status: COMPLETED

Results:

Physicist's response:
  Temperature measures the average kinetic energy of particles in a system...

Chemist's response:
  Temperature reflects how molecular motion influences reaction rates...
```

## Viewing Orchestration State

You can view the state of the orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view the orchestration instance, including:
   - The concurrent execution of both agents (Physicist and Chemist)
   - Separate conversation threads for each agent
   - Parallel task execution and completion timing
   - Aggregated results from both agents
   - Overall orchestration state and history

The orchestration demonstrates how multiple agents can be executed in parallel, with results collected and aggregated once all agents complete.


