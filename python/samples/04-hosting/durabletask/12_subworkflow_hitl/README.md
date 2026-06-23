# Human-in-the-Loop in a Sub-Workflow (Durable Task Worker)

This sample combines **workflow composition** (`11_subworkflow`) with
**human-in-the-loop** (`09_workflow_hitl`): the HITL `request_info` pause lives
**inside an inner workflow** that an outer workflow embeds via `WorkflowExecutor`.

On the durable host the inner workflow runs as its own **child orchestration**, so
its pending request is recorded on the *child* instance. The parent records the
child instance id in its custom status, which lets the client discover the nested
request behind a **single top-level addressing surface**.

## Key Concepts Demonstrated

- A HITL pause (`ctx.request_info` / `@response_handler`) inside a sub-workflow.
- `DurableAIAgentWorker.configure_workflow(outer_workflow)` registers a durable
  orchestration for each workflow:
  - `dafx-moderation_pipeline` — the outer workflow.
  - `dafx-human_review` — the inner (HITL) workflow, run as a child orchestration.
- **Qualified request ids:** the nested request surfaces to the client with a
  qualified id (`review_sub::{requestId}`). The client posts the response against the
  *top-level* instance id, and the host routes it to the owning child orchestration —
  so the caller never has to discover child instance ids.

## Composition Layout

```text
moderation_pipeline (outer)
  intake (executor)
    -> review_sub = WorkflowExecutor(human_review)
         review_gate (executor: request_info -> response_handler)
    -> publish (executor)
```

## Environment Setup

See the [README.md](../README.md) in the parent directory for environment setup.

This sample uses **no AI agents**, so no model credentials are required. It only
needs a Durable Task Scheduler. For local development, start the emulator (defaults
to `http://localhost:8080`):

```bash
docker run -d -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
```

## Running the Sample

Start the worker in one terminal:

```bash
cd samples/04-hosting/durabletask/12_subworkflow_hitl
python worker.py
```

In a second terminal, run the client:

```bash
python client.py
```

Each case flows: `intake` → `review_sub` (child orchestration pauses at
`review_gate`) → client responds to the qualified request → `review_gate` resumes →
inner decision forwarded to `publish` → final output.
