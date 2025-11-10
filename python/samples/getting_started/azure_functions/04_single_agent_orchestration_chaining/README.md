# Single Agent Orchestration Sample (Python)

This sample shows how to chain two invocations of the same agent inside a Durable Functions orchestration while
preserving the conversation state between runs.

## Key Concepts
- Deterministic orchestrations that make sequential agent calls on a shared thread
- Reusing an agent thread to carry conversation history across invocations
- HTTP endpoints for starting the orchestration and polling for status/output

## Prerequisites
- Python 3.10+
- [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools)
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) running locally so the sample can use `AzureWebJobsStorage=UseDevelopmentStorage=true`
- Environment variables configured:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
  - `AZURE_OPENAI_API_KEY` (required for key-based auth; ensure Azure CLI is logged in if you prefer token-based auth)
- Keep `TASKHUB_NAME` set to `default` unless you intend to change the durable task hub name.
- Copy `local.settings.json.template` to `local.settings.json` and populate those keys—including `AZURE_OPENAI_API_KEY`—along with any storage settings before running the Functions host.
- Install dependencies with `pip install -r requirements.txt`

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
