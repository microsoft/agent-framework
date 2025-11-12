# Multi-Agent Orchestration (Conditionals) – Python

This sample evaluates incoming emails with a spam detector agent and,
when appropriate, drafts a response using an email assistant agent.

## Prerequisites

Set up the shared prerequisites outlined in `../README.md`, including the virtual environment, dependency installation, and Azure OpenAI and storage configuration.

## Scenario Overview
- Two Azure OpenAI agents share a single deployment: one flags spam, the other drafts replies.
- Structured responses (`is_spam` and `reason`, or `response`) determine which orchestration branch runs.
- Activity functions handle the side effects of spam handling and email sending.

## Running the Sample
Submit an email payload:

```bash
curl -X POST http://localhost:7071/api/spamdetection/run \
  -H "Content-Type: application/json" \
  -d '{"subject": "Sale now on", "body": "Limited time offer"}'
```

Poll the returned `statusQueryGetUri` or call the status route directly:

```bash
curl http://localhost:7071/api/spamdetection/status/<instanceId>
```

> **Note:** The spam detection run endpoint waits for responses by default. To opt into an immediate HTTP 202, set the `x-ms-wait-for-response` header or include `"wait_for_response": false` in the POST body.

## Expected Responses
- Spam payloads return `Email marked as spam: <reason>` by invoking the `handle_spam_email` activity.
- Legitimate emails return `Email sent: <draft>` after the email assistant agent produces a structured reply.
- The status endpoint mirrors Durable Functions metadata, including runtime status and the agent output.
