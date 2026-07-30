# 13. Sub-workflow Human-in-the-Loop (HITL)

This sample demonstrates a **nested** human-in-the-loop pause: the `request_info`
happens inside an **inner workflow** that an outer workflow embeds via
`WorkflowExecutor`. It runs on Azure Durable Functions and is the Azure Functions
counterpart of the durabletask `12_subworkflow_hitl` sample.

This sample hosts **no AI agents**, so it needs only Azurite and the Durable Task
Scheduler emulator, with no model credentials.

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

## Notifying a reviewer from inside a nested workflow

This sample also notifies the reviewer from inside the inner workflow. The `review_gate` reads the id `request_info` generated and sends it to a downstream `NotifyExecutor`, which builds the respond URL with `WorkflowHitlContext`.

```python
# review_gate, inside the nested human_review workflow
await ctx.request_info(request_data=HumanApprovalRequest(...), response_type=HumanApprovalResponse)
request_id = await WorkflowHitlContext.pending_request_id(ctx)
# ... send request_id to the notify executor ...

# NotifyExecutor (also inside the inner workflow)
hitl = WorkflowHitlContext.from_context(ctx)
if hitl and request_id:
    respond_url = hitl.build_respond_url(request_id)  # already qualified back to the root
```

The notify executor runs inside the child orchestration, yet `build_respond_url` returns a URL that targets the **top-level** instance with the qualified `review_sub~0~{requestId}` id. You pass only the **bare** inner id. The host propagates the address context (the root instance, the workflow name, and the `review_sub~0~` path prefix) down into the child, so the executor qualifies the id for you and never needs to know how it is embedded.

The same two properties from the flat sample apply here. You never generate the id, because `request_info` creates it and `pending_request_id` reads it back, so call `pending_request_id` immediately after `request_info`. This is safe because each executor runs in its own Durable Functions activity with its own runner context, so the pending set only holds this executor's own requests and the newest one is the request you just emitted. And the email lives in a downstream executor, so a retried `review_gate` (activities are at least once) never emails a dead link, since only the committed attempt's id reaches the notifier.

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
