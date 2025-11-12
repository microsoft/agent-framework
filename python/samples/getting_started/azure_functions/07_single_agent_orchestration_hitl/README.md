# Single-Agent Orchestration (HITL) – Python

This sample demonstrates the human-in-the-loop (HITL) scenario.
A single writer agent iterates on content until a human reviewer approves the
output or a maximum number of attempts is reached.

## Prerequisites
- Python 3.10+ environment with the packages from `requirements.txt` installed.
- [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools) available on the PATH.
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) running locally so the sample can use `AzureWebJobsStorage=UseDevelopmentStorage=true`.
- Environment variables `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY`.
- Keep `TASKHUB_NAME` set to `default` unless you intend to change the durable task hub name.
- Copy `local.settings.json.template` to `local.settings.json` and configure those keys—including `AZURE_OPENAI_API_KEY`—plus storage settings before starting the Functions host.

## What It Shows
- Identical environment variable usage (`AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_DEPLOYMENT`) and HTTP surface area (`/api/hitl/...`).
- Durable orchestrations that pause for external events while maintaining
  deterministic state (`context.wait_for_external_event` + timed cancellation).
- Activity functions that encapsulate the out-of-band operations such as notifying
a reviewer and publishing content.
- Generated Azure Functions names use the prefix-agent pattern (e.g., `http-WriterAgent`).

## Run the Sample
1. Configure the environment variables and install dependencies with `pip install -r requirements.txt`.
2. Start the Functions host in this directory using `func start`.
3. Trigger the orchestration with `demo.http` (or another HTTP client) by POSTing to `/api/hitl/run`.
4. Poll the `statusQueryGetUri` or call `/api/hitl/status/{instanceId}` to monitor progress.
5. POST an approval or rejection payload to `/api/hitl/approve/{instanceId}` to complete the review loop.

## Expected Responses
- `POST /api/hitl/run` returns a 202 Accepted payload with the Durable Functions instance ID.
- `POST /api/hitl/approve/{instanceId}` echoes the decision that the orchestration receives.
- `GET /api/hitl/status/{instanceId}` reports `runtimeStatus`, custom status messages, and the final content when approved.
The orchestration sets custom status messages, retries on rejection with reviewer feedback, and raises a timeout if human approval does not arrive.
