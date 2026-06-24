# 13. Sub-workflow Human-in-the-Loop (HITL)

This sample demonstrates a **nested** human-in-the-loop pause: the `request_info`
happens inside an **inner workflow** that an outer workflow embeds via
`WorkflowExecutor`. It combines composition (sample 11 on the durabletask host) with
HITL (sample 12) and runs on Azure Durable Functions.

Unlike sample 12, this sample hosts **no AI agents**, so it needs only Azurite and
the Durable Task Scheduler emulator — no model credentials.

## Overview

```
moderation_pipeline (outer)
  intake (executor)
    -> review_sub = WorkflowExecutor(human_review)
         review_gate (executor: request_info -> response_handler)   <-- HITL pause
    -> publish (executor)
```

1. **User starts** the outer `moderation_pipeline` workflow with content.
2. **`intake`** normalizes the submission and forwards it.
3. **`review_sub`** runs the inner `human_review` workflow as a **child
   orchestration**; its `review_gate` pauses via `request_info`.
4. **The status endpoint** surfaces the nested pending request with a **qualified**
   id `review_sub~0~{requestId}`.
5. **The caller responds** against the *top-level* instance with that qualified id;
   the host routes it to the owning child orchestration.
6. **The inner workflow resumes**, yields its decision, and the outer `publish`
   executor produces the final result.

## Key Concept: one addressing surface for nested HITL

On the durable host each `WorkflowExecutor` node runs its inner workflow as its own
child orchestration, so a nested `request_info` is recorded on the *child* instance.
`AgentFunctionApp` bubbles those nested requests up into the top-level status with a
**qualified request id**, so the caller only ever addresses the top-level instance:

| Part | Meaning |
|------|---------|
| `review_sub` | the `WorkflowExecutor` node id that owns the child |
| `0` | the child's ordinal (a node may dispatch several children in one superstep) |
| `{requestId}` | the inner workflow's bare request id |

The separator is `~` (not `:`), so it never collides with framework-generated
request ids such as functional-workflow `auto::N` ids.

## Endpoints

`AgentFunctionApp` exposes routes only for the **top-level** workflow; the inner
workflow is driven as a child orchestration, not addressed directly.

| Endpoint | Description |
|----------|-------------|
| `POST /api/workflow/moderation_pipeline/run` | Start the workflow |
| `GET /api/workflow/moderation_pipeline/status/{instanceId}` | Status + nested pending HITL requests (qualified ids) |
| `POST /api/workflow/moderation_pipeline/respond/{instanceId}/{requestId}` | Send the human response (use the qualified id) |
| `GET /api/health` | Health check |

## Running

1. Start Azurite: `azurite --silent --location .`
2. Start the Durable Task Scheduler emulator on `localhost:8080`.
3. Copy `local.settings.json.sample` to `local.settings.json`.
4. `func start`
5. Drive it with [demo.http](./demo.http): start a run, GET the status to read the
   qualified `review_sub~0~{requestId}`, then POST the response to the top-level
   instance with that id.

Run `python function_app.py --maf` for pure MAF mode with DevUI (no Azure Functions).
