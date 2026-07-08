# Streaming Workflow Progress on a Standalone Durable Task Worker

This sample demonstrates **streaming a durable workflow's progress** from a
standalone Durable Task worker — no Azure Functions required. It is the
streaming counterpart to [`08_workflow`](../08_workflow/README.md).

## Key Concepts Demonstrated

- The async `DurableWorkflowClient` API:
  - `run_workflow(input, wait=False)` — start a workflow without blocking and get
    its instance id.
  - `stream_workflow(instance_id)` — an async iterator that yields typed
    `WorkflowEvent` objects (`executor_invoked` / `executor_completed` / `output`
    / ...) as the workflow progresses, ending when it reaches a terminal state.
    Each event's `data` is already reconstructed into its original typed object,
    so the client never deserializes anything by hand.
  - `await_workflow_output(instance_id)` — read the final reconstructed output.
- **Brokerless streaming.** The orchestrator publishes accumulated events to the
  orchestration **custom status** after each superstep (only on live execution,
  not replay), and the client streams them by polling. No Redis or other message
  broker is required.
- **Per-executor granularity.** Events fire per executor and per yielded output,
  not at the token level. Non-agent executors carry their captured event data;
  agent executors surface coarse `executor_invoked` / `executor_completed`
  lifecycle events. (Token-level streaming through a durable boundary would
  require an external broker.)

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
cd samples/04-hosting/durabletask/10_workflow_streaming
python worker.py
```

In a second terminal, run the client:

```bash
python client.py
```

The workflow is a linear pipeline — `WriterAgent` → `ReviewerAgent` → `publish` —
so the client prints the progress events as each executor runs, for example:

```text
Streaming workflow events:
  [executor_invoked] WriterAgent
  [executor_completed] WriterAgent
  [executor_invoked] ReviewerAgent
  [executor_completed] ReviewerAgent
  [executor_invoked] publish
  [executor_completed] publish
  [output] from publish: Published: ...
Final output: Published: ...
```
