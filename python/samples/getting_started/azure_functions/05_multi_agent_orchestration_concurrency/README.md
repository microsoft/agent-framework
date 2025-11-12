# Multi-Agent Orchestration (Concurrency) – Python

This sample starts a Durable Functions orchestration that runs two agents in parallel and merges their responses.

## Highlights
- Two agents (`PhysicistAgent` and `ChemistAgent`) share a single Azure OpenAI deployment configuration.
- The orchestration uses `context.task_all(...)` to safely run both agents concurrently.
- HTTP routes (`/api/multiagent/run` and `/api/multiagent/status/{instanceId}`) mirror the .NET sample for parity.
- Generated Azure Functions names use the prefix-agent pattern (e.g., `http-PhysicistAgent`).

## Prerequisites
- Python 3.10+
- [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools)
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) running locally so the sample can use `AzureWebJobsStorage=UseDevelopmentStorage=true`
- Environment variables configured:
  - `AZURE_OPENAI_ENDPOINT`
  - `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`
  - `AZURE_OPENAI_API_KEY` (required for key-based auth; ensure the Azure CLI is logged in if you rely on token-based auth)
- Keep `TASKHUB_NAME` set to `default` unless you intend to change the durable task hub name.
- Copy `local.settings.json.template` to `local.settings.json` and fill in those Azure OpenAI values—including `AZURE_OPENAI_API_KEY`—along with storage settings before starting the Functions host.
- Install dependencies with `pip install -r requirements.txt`

## Running the Sample
1. Start the Functions host: `func start`.
2. Send a prompt to start the orchestration:
   ```bash
   curl -X POST \
        -H "Content-Type: text/plain" \
        --data "What is temperature?" \
        http://localhost:7071/api/multiagent/run
   ```
3. Poll the returned `statusQueryGetUri` until the orchestration completes:
   ```bash
   curl http://localhost:7071/api/multiagent/status/<instanceId>
   ```

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
