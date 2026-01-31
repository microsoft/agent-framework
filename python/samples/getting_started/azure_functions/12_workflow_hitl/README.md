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

### Automatic HITL Endpoints

`AgentFunctionApp` automatically provides all the HTTP endpoints needed for HITL:

| Endpoint | Description |
|----------|-------------|
| `POST /api/workflow/run` | Start the workflow |
| `GET /api/workflow/status/{instanceId}` | Check status and pending HITL requests |
| `POST /api/workflow/respond/{instanceId}/{requestId}` | Send human response |
| `GET /api/health` | Health check |

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

2. Update `local.settings.json` with your Azure OpenAI credentials:
   ```json
   {
     "Values": {
       "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
       "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "gpt-4o"
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

1. **Start workflow** - `POST /api/workflow/run` with content payload
2. **Check status** - `GET /api/workflow/status/{instanceId}` to see pending HITL requests
3. **Send response** - `POST /api/workflow/respond/{instanceId}/{requestId}` with approval
4. **Check result** - `GET /api/workflow/status/{instanceId}` to see final output

## Related Samples

- [07_single_agent_orchestration_hitl](../07_single_agent_orchestration_hitl/) - HITL at orchestrator level (not using MAF pattern)
- [09_workflow_shared_state](../09_workflow_shared_state/) - Workflow with shared state
- [guessing_game_with_human_input](../../workflows/human-in-the-loop/guessing_game_with_human_input.py) - MAF HITL pattern (non-durable)
