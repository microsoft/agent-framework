# Multi-Agent Orchestration (Conditionals) – Python

This sample evaluates incoming emails with a spam detector agent and,
when appropriate, drafts a response using an email assistant agent.

## Prerequisites
- Python 3.10+ environment with dependencies from `requirements.txt` installed.
- [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools) available on the PATH.
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) running locally so the sample can use `AzureWebJobsStorage=UseDevelopmentStorage=true`.
- Environment variables `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY`.
- Keep `TASKHUB_NAME` set to `default` unless you intend to change the durable task hub name.
- Copy `local.settings.json.template` to `local.settings.json` and populate those Azure OpenAI settings—including `AZURE_OPENAI_API_KEY`—along with storage values before starting the host.

## Scenario Overview
- Two Azure OpenAI agents share a single deployment: one flags spam, the other drafts replies.
- Structured responses (`is_spam` and `reason`, or `response`) determine which orchestration branch runs.
- Activity functions handle the side effects of spam handling and email sending.
- Generated Azure Functions names use the prefix-agent pattern (e.g., `http-SpamDetector`).

## Run the Sample
1. Configure the environment variables and install dependencies with `pip install -r requirements.txt`.
2. Launch the Functions host from this directory using `func start`.
3. Send an email payload to `/api/spamdetection/run` (see `demo.http`).
4. Poll the provided `statusQueryGetUri` or call `/api/spamdetection/status/{instanceId}` to monitor results.

## Expected Responses
- Spam payloads return `Email marked as spam: <reason>` by invoking the `handle_spam_email` activity.
- Legitimate emails return `Email sent: <draft>` after the email assistant agent produces a structured reply.
- The status endpoint mirrors Durable Functions metadata, including runtime status and the agent output.
