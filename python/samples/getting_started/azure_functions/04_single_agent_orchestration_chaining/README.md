# Single Agent Orchestration Sample (Python)

This sample shows how to chain two invocations of the same agent inside a Durable Functions orchestration while
preserving the conversation state between runs.

## Key Concepts
- Deterministic orchestrations that make sequential agent calls on a shared thread
- Reusing an agent thread to carry conversation history across invocations
- HTTP endpoints for starting the orchestration and polling for status/output

## Prerequisites
- Python 3.11+
- Azure Functions Core Tools v4
- Local Azure Storage / Azurite and the Durable Task sidecar running
- Environment variables configured:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
  - `AZURE_OPENAI_API_KEY` (omit if using Azure CLI authentication)
- `TASKHUB_NAME` matching the durable task hub defined in `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` (default is `default`).
- Copy `local.settings.json.template` to `local.settings.json` and populate those keys (and any storage settings) before running the Functions host, ensuring the `TaskHub` setting in the scheduler connection string stays in sync with `TASKHUB_NAME`.
- Dependencies installed: `pip install -r requirements.txt`

## Running the Sample
1. Start the Functions host: `func start`.
2. Kick off the orchestration:
   ```bash
   curl -X POST http://localhost:7071/api/singleagent/run
   ```
3. Copy the `statusQueryGetUri` from the response and poll until the orchestration completes:
   ```bash
   curl http://localhost:7071/api/singleagent/status/<instanceId>
   ```

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
