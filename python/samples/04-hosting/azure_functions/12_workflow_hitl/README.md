# 12. Workflow with Human-in-the-Loop (HITL)

This sample demonstrates how to integrate human approval into a MAF workflow running on Azure Durable Functions using the MAF `request_info` and `@response_handler` pattern.

## Overview

The sample implements a content moderation pipeline:

1. **User starts workflow** with content for publication via HTTP endpoint
2. **AI Agent analyzes** the content for policy compliance
3. **Workflow pauses** and requests human reviewer approval
4. **Human responds** via HTTP endpoint with approval/rejection
5. **Workflow resumes** and publishes or rejects the content

## Key Concepts

### MAF HITL Pattern

This sample uses MAF's built-in human-in-the-loop pattern:

```python
# In an executor, request human input
await ctx.request_info(
    request_data=HumanApprovalRequest(...),
    response_type=HumanApprovalResponse,
)

# Handle the response in a separate method
@response_handler
async def handle_approval_response(
    self,
    original_request: HumanApprovalRequest,
    response: HumanApprovalResponse,
    ctx: WorkflowContext,
) -> None:
    # Process the human's decision
    ...
```

### Notifying a reviewer from inside the workflow

This sample also shows how a workflow notifies a human itself (for example to email an approval link) instead of relying on the caller to poll the status endpoint. It uses a two step pattern so the reviewer gets a working respond URL.

```python
# Pause the workflow. request_info generates the request id internally.
await ctx.request_info(
    request_data=HumanApprovalRequest(...),
    response_type=HumanApprovalResponse,
)

# Read that id back, then build the respond URL with WorkflowHitlContext.
request_id = await WorkflowHitlContext.pending_request_id(ctx)
hitl = WorkflowHitlContext.from_context(ctx)
if hitl and request_id:
    respond_url = hitl.build_respond_url(request_id)  # email this to the reviewer
```

Two things make this safe and worth understanding.

**You never generate the id.** `request_info` already creates one and stores it on the context before it returns, so `pending_request_id(ctx)` reads it straight back. You must call `pending_request_id` immediately after `request_info`, because it returns the newest pending request, which is the one you just emitted. On the durable host this is reliable. Every executor runs in its own Durable Functions activity with its own runner context, so that pending set only ever holds this executor's own requests. If a single executor emits several requests in one turn, read the id after each call, or pass your own `request_id` to `request_info`.

**The notification runs in a separate executor.** The review executor sends the id to a downstream `NotifyExecutor` that builds the URL, rather than emailing from the executor that generated the id. Because activities are at least once, an executor can be retried, and each retry mints a fresh id. Keeping the email in a downstream executor means only the committed attempt's id ever reaches the notifier, so a retried review executor never emails a dead link. `WorkflowHitlContext.from_context(ctx)` returns `None` when the executor is not on the durable host (for example under `--maf` DevUI), so the notify step skips cleanly there.

The base URL comes from the `WEBSITE_HOSTNAME` app setting, which Azure Functions sets automatically in the cloud. For a custom domain or an API Management gateway, pass `base_url=...` to `from_context`, because `WEBSITE_HOSTNAME` still reports the default `*.azurewebsites.net` host.

### Automatic HITL Endpoints

`AgentFunctionApp` automatically provides all the HTTP endpoints needed for HITL:

| Endpoint | Description |
|----------|-------------|
| `POST /api/workflow/content_moderation/run` | Start the workflow |
| `GET /api/workflow/content_moderation/status/{instanceId}` | Check status and pending HITL requests |
| `POST /api/workflow/content_moderation/respond/{instanceId}/{requestId}` | Send human response |
| `GET /api/health` | Health check |

These routes expose workflow status and human-response operations. In production, put them behind your application's authentication and authorization layer and verify that the caller is allowed to inspect or resume the targeted workflow before returning status or accepting a response.

Treat `instanceId` and `requestId` as correlation handles only. They help locate workflow state, but they are not secrets or proof that a caller is authorized to act on that workflow.

### Durable Functions Integration

When running on Durable Functions, the HITL pattern maps to:

| MAF Concept | Durable Functions |
|-------------|-------------------|
| `ctx.request_info()` | Workflow pauses, custom status updated |
| `RequestInfoEvent` | Exposed via status endpoint |
| HTTP response | `client.raise_event(instance_id, request_id, data)` |
| `@response_handler` | Workflow resumes, handler invoked |

## Workflow Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌────────────────────────┐
│  Input Router   │ ──► │ Content Analyzer     │ ──► │ Content Analyzer       │
│   Executor      │     │ Agent (AI)           │     │ Executor (Parse JSON)  │
└─────────────────┘     └──────────────────────┘     └────────────────────────┘
                                                                │
                                                                ▼
┌─────────────────┐     ┌──────────────────────┐
│    Publish      │ ◄── │   Human Review       │ ◄── HITL PAUSE
│   Executor      │     │   Executor           │     (wait for external event)
└─────────────────┘     └──────────────────────┘
```

## Prerequisites

1. **Azure OpenAI** - Access to Azure OpenAI with a deployed chat model
2. **Durable Task Scheduler** - Local emulator or Azure deployment
3. **Azurite** - Local Azure Storage emulator
4. **Azure CLI** - For authentication (`az login`)

## Setup

1. Copy the sample settings file:
   ```bash
   cp local.settings.json.sample local.settings.json
   ```

2. Update `local.settings.json` with your Foundry project settings:
   ```json
   {
     "Values": {
       "FOUNDRY_PROJECT_ENDPOINT": "https://your-project.services.ai.azure.com/api/projects/your-project",
       "FOUNDRY_MODEL": "gpt-4o"
     }
   }
   ```

3. Start the local emulators:
   ```bash
   # Terminal 1: Start Azurite
   azurite --silent --location .

   # Terminal 2: Start Durable Task Scheduler (if using local emulator)
   # Follow Durable Task Scheduler setup instructions
   ```

4. Start the Function App:
   ```bash
   func start
   ```

## Running in Pure MAF Mode

You can also run this sample in pure MAF mode (without Durable Functions) using the DevUI:

```bash
python function_app.py --maf
```

This launches the DevUI at http://localhost:8096 where you can interact with the workflow directly. This is useful for:
- Local development and debugging
- Testing the HITL pattern without Durable Functions infrastructure
- Comparing behavior between MAF and Durable modes

## Testing

Use the `demo.http` file with the VS Code REST Client extension:

1. **Start workflow** - `POST /api/workflow/content_moderation/run` with content payload
2. **Check status** - `GET /api/workflow/content_moderation/status/{instanceId}` to see pending HITL requests
3. **Send response** - `POST /api/workflow/content_moderation/respond/{instanceId}/{requestId}` with approval
4. **Check result** - `GET /api/workflow/content_moderation/status/{instanceId}` to see final output

## Related Samples

- [07_single_agent_orchestration_hitl](../07_single_agent_orchestration_hitl/) - HITL at orchestrator level (not using MAF pattern)
- [09_workflow_shared_state](../09_workflow_shared_state/) - Workflow with shared state
- [guessing_game_with_human_input](../../../03-workflows/human-in-the-loop/guessing_game_with_human_input.py) - MAF HITL pattern (non-durable)
