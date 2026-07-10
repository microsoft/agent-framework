# Composed Workflow (Sub-Workflow) on a Standalone Durable Task Worker

This sample demonstrates **workflow composition** on a standalone Durable Task
worker: an inner agent-framework `Workflow` is embedded as a node inside an outer
`Workflow` using `WorkflowExecutor`. On the durable host, the inner workflow runs
as its own durable **child orchestration**.

## Key Concepts Demonstrated

- Embedding one `Workflow` inside another with
  `WorkflowExecutor(inner_workflow, id=...)`.
- A single `DurableAIAgentWorker.configure_workflow(outer_workflow)` call walks the
  composition and auto-registers a durable orchestration for **each** workflow:
  - `dafx-review_pipeline` — the outer workflow.
  - `dafx-sentiment_analysis` — the inner workflow, run as a durable **child
    orchestration** when the outer workflow reaches the `WorkflowExecutor` node.
- Per-workflow scoping: each workflow's agent executors become durable entities and
  its non-agent executors become durable activities, named per workflow so the same
  executor id in two workflows never collides.
- Output forwarding: the inner workflow yields a string and, because
  `allow_direct_output` is left at its default (`False`), that output is forwarded to
  the outer workflow as a message delivered to the `reporter` executor.

## Composition Layout

```text
review_pipeline (outer)
  intake (executor)
    -> sentiment_sub = WorkflowExecutor(sentiment_analysis)
         sentiment_agent (agent) -> sentiment_formatter (executor)
    -> reporter (executor)
```

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
cd samples/04-hosting/durabletask/11_subworkflow
python worker.py
```

In a second terminal, run the client:

```bash
python client.py
```

The client targets only the outer workflow (`review_pipeline`); the sub-workflow
runs automatically as a child orchestration. Each review flows:

`intake` → `sentiment_sub` (child orchestration: `sentiment_agent` →
`sentiment_formatter`) → `reporter` → `"Review analysis complete -> sentiment: ..."`.
