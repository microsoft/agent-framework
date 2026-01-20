# Workflow with SharedState Sample

This sample demonstrates running **Agent Framework workflows with SharedState** in Azure Durable Functions.

## Overview

This sample shows how to use `AgentFunctionApp` to execute a `WorkflowBuilder` workflow that uses SharedState to pass data between executors. SharedState is a local dictionary maintained by the orchestration that allows executors to share data across workflow steps.

## What This Sample Demonstrates

1. **Workflow Execution** - Running `WorkflowBuilder` workflows in Azure Durable Functions
2. **SharedState APIs** - Using `ctx.set_shared_state()` and `ctx.get_shared_state()` to share data
3. **Conditional Routing** - Routing messages based on spam detection results
4. **Agent + Executor Composition** - Combining AI agents with non-AI function executors

## Workflow Architecture

```
store_email → spam_detector (agent) → to_detection_result → [branch]:
    ├── If spam: handle_spam → yield "Email marked as spam: {reason}"
    └── If not spam: submit_to_email_assistant → email_assistant (agent) → finalize_and_send → yield "Email sent: {response}"
```

### SharedState Usage by Executor

| Executor | SharedState Operations |
|----------|----------------------|
| `store_email` | `set_shared_state("email:{id}", email)`, `set_shared_state("current_email_id", id)` |
| `to_detection_result` | `get_shared_state("current_email_id")` |
| `submit_to_email_assistant` | `get_shared_state("email:{id}")` |

SharedState allows executors to pass large payloads (like email content) by reference rather than through message routing.

## Prerequisites

1. **Azure OpenAI** - Endpoint and deployment configured
2. **Azurite** - For local storage emulation

## Setup

1. Copy `local.settings.json.sample` to `local.settings.json` and configure:
   ```json
   {
     "Values": {
       "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
       "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "gpt-4o"
     }
   }
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start Azurite:
   ```bash
   azurite --silent
   ```

4. Run the function app:
   ```bash
   func start
   ```

## Testing

Use the `demo.http` file with REST Client extension or curl:

### Test Spam Email
```bash
curl -X POST http://localhost:7071/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '"URGENT! You have won $1,000,000! Click here to claim!"'
```

### Test Legitimate Email
```bash
curl -X POST http://localhost:7071/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '"Hi team, reminder about our meeting tomorrow at 10 AM."'
```

## Expected Output

**Spam email:**
```
Email marked as spam: This email exhibits spam characteristics including urgent language, unrealistic claims of monetary winnings, and requests to click suspicious links.
```

**Legitimate email:**
```
Email sent: Hi, Thank you for the reminder about the sprint planning meeting tomorrow at 10 AM. I will review the agenda and come prepared with my updates. See you then!
```

## Related Samples

- `10_workflow_no_shared_state` - Workflow execution without SharedState usage
- `06_multi_agent_orchestration_conditionals` - Manual Durable Functions orchestration with agents
