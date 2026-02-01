# Single Agent Orchestration Sample (Python)

This sample shows how to chain two invocations of the same agent inside a Durable Functions orchestration while
preserving the conversation state between runs.

## Key Concepts
- Deterministic orchestrations that make sequential agent calls on a shared thread
- Reusing an agent thread to carry conversation history across invocations
- HTTP endpoints for starting the orchestration and polling for status/output

## Prerequisites

Start with the shared setup instructions in `../README.md` to create a virtual environment, install dependencies, and configure Azure OpenAI and storage settings.

## Running the Sample
Start the orchestration:

```bash
curl -X POST http://localhost:7071/api/singleagent/run
```

Poll the returned `statusQueryGetUri` until completion:

```bash
curl http://localhost:7071/api/singleagent/status/<instanceId>
```

> **Note:** The underlying agent run endpoint now waits for responses by default. If you invoke it directly and prefer an immediate HTTP 202, set the `x-ms-wait-for-response` header or include `"wait_for_response": false` in the payload.

The orchestration first requests an inspirational sentence from the agent, then refines the initial response while
keeping it under 25 words—mirroring the behaviour of the corresponding .NET sample.

## Expected Output

Sample response when starting the orchestration:

```json
{
  "message": "Single-agent orchestration started.",
  "instanceId": "ebb5c1df123e4d6fb8e7d703ffd0d0b0",
  "statusQueryGetUri": "http://localhost:7071/api/singleagent/status/ebb5c1df123e4d6fb8e7d703ffd0d0b0"
}
```

Sample completed status payload:

```json
{
  "instanceId": "ebb5c1df123e4d6fb8e7d703ffd0d0b0",
  "runtimeStatus": "Completed",
  "output": "Learning is a journey where curiosity turns effort into mastery."
}
```
