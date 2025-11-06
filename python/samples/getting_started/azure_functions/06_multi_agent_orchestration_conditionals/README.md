# Multi-Agent Orchestration (Conditionals) – Python

This sample evaluates incoming emails with a spam detector agent and,
when appropriate, drafts a response using an email assistant agent.

## Prerequisites
- Python 3.11 environment with dependencies from `requirements.txt` installed.
- Azure Functions Core Tools (`func`) available on the PATH.
- Environment variables `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and either
  `AZURE_OPENAI_API_KEY` or an active Azure CLI login.
- Copy `local.settings.json.template` to `local.settings.json` and populate those Azure OpenAI settings (and storage values) before starting the host.

## Scenario Overview
- Two Azure OpenAI agents share a single deployment: one flags spam, the other drafts replies.
- Structured responses (`is_spam` and `reason`, or `response`) determine which orchestration branch runs.
- Activity functions handle the side effects of spam handling and email sending.

## Run the Sample
1. Configure the environment variables and install dependencies with `pip install -r requirements.txt`.
2. Launch the Functions host from this directory using `func start`.
3. Send an email payload to `/api/spamdetection/run` (see `demo.http`).
4. Poll the provided `statusQueryGetUri` or call `/api/spamdetection/status/{instanceId}` to monitor results.

## Expected Responses
- Spam payloads return `Email marked as spam: <reason>` by invoking the `handle_spam_email` activity.
- Legitimate emails return `Email sent: <draft>` after the email assistant agent produces a structured reply.
- The status endpoint mirrors Durable Functions metadata, including runtime status and the agent output.
