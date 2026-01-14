# Multi-Agent Orchestration with Concurrency

This sample demonstrates how to host multiple agents and run them concurrently using a durable orchestration, aggregating their responses into a single result.

## Key Concepts Demonstrated

- Running multiple specialized agents in parallel within an orchestration.
- Using `OrchestrationAgentExecutor` to get `DurableAgentTask` objects for concurrent execution.
- Aggregating results from multiple agents using `task.when_all()`.
- Creating separate conversation threads for independent agent contexts.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample using the combined approach or separate worker and client processes:

**Option 1: Combined (Recommended for Testing)**

```bash
cd samples/getting_started/durabletask/05_multi_agent_orchestration_concurrency
python sample.py
```

**Option 2: Separate Processes**

Start the worker in one terminal:

```bash
python worker.py
```

In a new terminal, run the client:

```bash
python client.py
```

The orchestration will execute both agents concurrently:

```
Prompt: What is temperature?

Starting multi-agent concurrent orchestration...
Orchestration started with instance ID: abc123...
⚡ Running PhysicistAgent and ChemistAgent in parallel...
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
2. In the dashboard, you can view:
   - The concurrent execution of both agents (PhysicistAgent and ChemistAgent)
   - Separate conversation threads for each agent
   - Parallel task execution and completion timing
   - Aggregated results from both agents


