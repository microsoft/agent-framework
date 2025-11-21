# Multi-Agent Orchestration (Concurrency) – Python

This sample starts a Durable Functions orchestration that runs two agents in parallel and merges their responses.

## Highlights
- Two agents (`PhysicistAgent` and `ChemistAgent`) share a single Azure OpenAI deployment configuration.
- The orchestration uses `context.task_all(...)` to safely run both agents concurrently.
- HTTP routes (`/api/multiagent/run` and `/api/multiagent/status/{instanceId}`) mirror the .NET sample for parity.

## Prerequisites

Use the shared setup instructions in `../README.md` to prepare the environment, install dependencies, and configure Azure OpenAI and storage settings before running this sample.

## Running the Sample
Start the orchestration:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data "What is temperature?" \
  http://localhost:7071/api/multiagent/run
```

Poll the returned `statusQueryGetUri` until completion:

```bash
curl http://localhost:7071/api/multiagent/status/<instanceId>
```

> **Note:** The agent run endpoints wait for responses by default. If you call them directly and need an immediate HTTP 202, set the `x-ms-wait-for-response` header or include `"wait_for_response": false` in the request payload.

The orchestration launches both agents simultaneously so their domain-specific answers can be combined for the caller.

## Expected Output

Example response when starting the orchestration:

```json
{
  "message": "Multi-agent concurrent orchestration started.",
  "prompt": "What is temperature?",
  "instanceId": "94d56266f0a04e5a8f9f3a1f77a4c597",
  "statusQueryGetUri": "http://localhost:7071/api/multiagent/status/94d56266f0a04e5a8f9f3a1f77a4c597"
}
```

Example completed status payload:

```json
{
  "instanceId": "94d56266f0a04e5a8f9f3a1f77a4c597",
  "runtimeStatus": "Completed",
  "output": {
    "physicist": "Temperature measures the average kinetic energy of particles in a system.",
    "chemist": "Temperature reflects how molecular motion influences reaction rates and equilibria."
  }
}
```
