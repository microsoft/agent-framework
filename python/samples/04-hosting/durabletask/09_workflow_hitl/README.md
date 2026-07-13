# Human-in-the-Loop Workflow on a Standalone Durable Task Worker

This sample demonstrates a Human-in-the-Loop (HITL) agent-framework `Workflow`
running as a durable orchestration on a **standalone Durable Task worker** — no
Azure Functions required. It is the durabletask counterpart to the Azure
Functions sample `samples/04-hosting/azure_functions/12_workflow_hitl`.

## Key Concepts Demonstrated

- Pausing a workflow for human input with MAF's `ctx.request_info()` /
  `@response_handler` pattern, hosted on a standalone worker via
  `DurableAIAgentWorker.configure_workflow(workflow)`.
- Discovering pending HITL requests from a client with
  `DurableWorkflowClient.get_pending_hitl_requests(instance_id)`.
- Resuming the workflow by sending a decision with
  `DurableWorkflowClient.send_hitl_response(instance_id, request_id, response)`.
- Reading the final result with `DurableWorkflowClient.await_workflow_output(instance_id)`.

The workflow is a content-moderation pipeline:

```
input_router -> ContentAnalyzerAgent -> content_analyzer_executor
             -> human_review_executor (HITL pause) -> publish_executor
```

## How HITL Works Here

The HITL mechanism is host-agnostic — the same shared workflow orchestrator
drives it on both Azure Functions and a standalone worker:

1. `human_review_executor` calls `ctx.request_info(...)`, which pauses the
   workflow. The orchestrator records the open request in its **custom status**
   and waits for an external event named by the request's `request_id`.
2. The client reads the custom status via `get_pending_hitl_requests` and sends
   a response via `send_hitl_response`, which raises that external event.
3. The orchestrator routes the response back to the executor's
   `@response_handler`, and the workflow resumes.

`send_hitl_response` sanitizes the payload (neutralizing pickle-marker
injection) before delivery, since the worker deserializes it.

## Environment Setup

See the [README.md](../README.md) in the parent directory for environment setup.

This sample uses Azure AI Foundry credentials:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL`

It also needs a Durable Task Scheduler. For local development, start the
emulator (defaults to `http://localhost:8080`):

```bash
docker run -d -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```

## Running the Sample

Start the worker in one terminal:

```bash
cd samples/04-hosting/durabletask/09_workflow_hitl
python worker.py
```

In a second terminal, run the client:

```bash
python client.py
```

The client runs two cases:

- **Appropriate content** → analyzed → HITL pause → client **approves** →
  `"Content '...' has been APPROVED and published."`
- **Spammy content** → analyzed → HITL pause → client **rejects** →
  `"Content '...' has been REJECTED."`
