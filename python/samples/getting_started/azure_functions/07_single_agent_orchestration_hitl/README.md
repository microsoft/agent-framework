# Single-Agent Orchestration (HITL) – Python

This sample demonstrates the human-in-the-loop (HITL) scenario.
A single writer agent iterates on content until a human reviewer approves the
output or a maximum number of attempts is reached.

## Prerequisites

Complete the common setup instructions in `../README.md` to prepare the virtual environment, install dependencies, and configure Azure OpenAI and storage settings.

## What It Shows
- Identical environment variable usage (`AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_DEPLOYMENT`) and HTTP surface area (`/api/hitl/...`).
- Durable orchestrations that pause for external events while maintaining
  deterministic state (`context.wait_for_external_event` + timed cancellation).
- Activity functions that encapsulate the out-of-band operations such as notifying
a reviewer and publishing content.

## Running the Sample
Start the HITL orchestration:

```bash
curl -X POST http://localhost:7071/api/hitl/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "Write a friendly release note"}'
```

Poll the returned `statusQueryGetUri` or call the status route directly:

```bash
curl http://localhost:7071/api/hitl/status/<instanceId>
```

Approve or reject the draft:

```bash
curl -X POST http://localhost:7071/api/hitl/approve/<instanceId> \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "feedback": "Looks good"}'
```

> **Note:** Calls to the underlying agent run endpoint wait for responses by default. If you need an immediate HTTP 202 response, set the `x-ms-wait-for-response` header or include `"wait_for_response": false` in the request body.

## Expected Responses
- `POST /api/hitl/run` returns a 202 Accepted payload with the Durable Functions instance ID.
- `POST /api/hitl/approve/{instanceId}` echoes the decision that the orchestration receives.
- `GET /api/hitl/status/{instanceId}` reports `runtimeStatus`, custom status messages, and the final content when approved.
The orchestration sets custom status messages, retries on rejection with reviewer feedback, and raises a timeout if human approval does not arrive.
