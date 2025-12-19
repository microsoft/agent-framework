# Workflow Shared State Sample

This sample demonstrates **Workflow SharedState functionality** with the Agent Framework Azure Functions package.

## What This Sample Demonstrates

This sample validates the SharedState implementation in workflow orchestrations:

1. **`ctx.set_shared_state(key, value)`** - Store values in SharedState
2. **`ctx.get_shared_state(key)`** - Retrieve values from SharedState  
3. **`ctx.shared_state.delete(key)`** - Delete keys from SharedState
4. **State persistence** - State passed between executors via `DurableSharedState` entity

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
| `finalize_and_send` | `shared_state.delete("email:{id}")`, `shared_state.delete("current_email_id")` |
| `handle_spam` | `shared_state.delete("email:{id}")`, `shared_state.delete("current_email_id")` |

## Prerequisites

1. **Azure OpenAI** - Endpoint and deployment configured
2. **Durable Task Scheduler** - Running locally or in Azure
3. **Azurite** - For local storage emulation

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

4. Start Durable Task Scheduler:
   ```bash
   durabletask-scheduler start
   ```

5. Run the function app:
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
Email sent: Hi, Thank you for the reminder about the sprint planning meeting tomorrow at 10 AM. I will review the agenda in Jira and come prepared with my updates. See you then!
```
