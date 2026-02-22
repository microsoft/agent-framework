# Multi-Agent Concurrent Orchestration Sample

This sample demonstrates how to use the durable agents extension to create a console app that orchestrates concurrent execution of multiple AI agents using durable orchestration.

## Key Concepts Demonstrated

- Running multiple agents concurrently in a single orchestration
- Using `Task.WhenAll` to wait for concurrent agent executions
- Combining results from multiple agents into a single response
- Waiting for orchestration completion using `WaitForInstanceCompletionAsync`

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/03_AgentOrchestration_Concurrency
dotnet run --framework net10.0
```

The app will prompt you for a question:

```text
=== Multi-Agent Concurrent Orchestration Sample ===
Enter a question for the agents:

What is temperature?
```

The orchestration will run both agents concurrently and display their responses:

```text
Orchestration started with instance ID: 86313f1d45fb42eeb50b1852626bf3ff
Waiting for completion...

✓ Orchestration completed successfully!

Physicist's response:
Temperature is a measure of the average kinetic energy of particles in a system...

Chemist's response:
From a chemistry perspective, temperature is crucial for chemical reactions...
```

Both agents run in parallel, and the orchestration waits for both to complete before returning the combined results.

## Viewing Orchestration State

You can view the state of the orchestration in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can see:
   - **Orchestrations**: View the orchestration instance, including its runtime status, input, output, and execution history
   - **Agents**: View the state of both the PhysicistAgent and ChemistAgent, including their individual conversation histories

The orchestration instance ID is displayed in the console output. You can use this ID to find the specific orchestration in the dashboard and inspect how the concurrent agent executions were coordinated, including the timing of when each agent started and completed.

## Scriptable Usage

You can also pipe input to the app:

```bash
echo "What is temperature?" | dotnet run
```
