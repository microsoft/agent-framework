# Workflow Execution Sample

This sample demonstrates running **Agent Framework workflows** in Azure Durable Functions without using SharedState.

## Overview

This sample shows how to use `AgentFunctionApp` with a `WorkflowBuilder` workflow. The workflow is passed directly to `AgentFunctionApp`, which orchestrates execution using Durable Functions:

```python
workflow = _create_workflow()  # Build the workflow graph
app = AgentFunctionApp(workflow=workflow)
```

This approach provides durable, fault-tolerant workflow execution with minimal code.

## What This Sample Demonstrates

1. **Workflow Registration** - Pass a `Workflow` directly to `AgentFunctionApp`
2. **Durable Execution** - Workflow executes with Durable Functions durability and scalability
3. **Conditional Routing** - Route messages based on spam detection (is_spam → spam handler, not spam → email assistant)
4. **Agent + Executor Composition** - Combine AI agents with non-AI executor classes

## Workflow Architecture

```
SpamDetectionAgent → [branch based on is_spam]:
    ├── If spam: SpamHandlerExecutor → yield "Email marked as spam: {reason}"
    └── If not spam: EmailAssistantAgent → EmailSenderExecutor → yield "Email sent: {response}"
```

### Components

| Component | Type | Description |
|-----------|------|-------------|
| `SpamDetectionAgent` | AI Agent | Analyzes emails for spam indicators |
| `EmailAssistantAgent` | AI Agent | Drafts professional email responses |
| `SpamHandlerExecutor` | Executor | Handles spam emails (non-AI) |
| `EmailSenderExecutor` | Executor | Sends email responses (non-AI) |

## Prerequisites

1. **Azure OpenAI** - Endpoint and deployment configured
2. **Azurite** - For local storage emulation

## Setup

1. Copy configuration files:
   ```bash
   cp local.settings.json.sample local.settings.json
   ```

2. Configure `local.settings.json`:

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start Azurite:
   ```bash
   azurite --silent
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
  -d '{"email_id": "test-001", "email_content": "URGENT! You have won $1,000,000! Click here!"}'
```

### Test Legitimate Email
```bash
curl -X POST http://localhost:7071/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"email_id": "test-002", "email_content": "Hi team, reminder about our meeting tomorrow at 10 AM."}'
```

### Check Status
```bash
curl http://localhost:7071/api/workflow/status/{instanceId}
```

## Expected Output

**Spam email:**
```
Email marked as spam: This email exhibits spam characteristics including urgent language, unrealistic claims of monetary winnings, and requests to click suspicious links.
```

**Legitimate email:**
```
Email sent: Hi, Thank you for the reminder about the sprint planning meeting tomorrow at 10 AM. I will be there.
```

## Code Highlights

### Creating the Workflow

```python
workflow = (
    WorkflowBuilder()
    .set_start_executor(spam_agent)
    .add_switch_case_edge_group(
        spam_agent,
        [
            Case(condition=is_spam_detected, target=spam_handler),
            Default(target=email_agent),
        ],
    )
    .add_edge(email_agent, email_sender)
    .build()
)
```

### Registering with AgentFunctionApp

```python
app = AgentFunctionApp(workflow=workflow, enable_health_check=True)
```

### Executor Classes

```python
class SpamHandlerExecutor(Executor):
    @handler
    async def handle_spam_result(
        self,
        agent_response: AgentExecutorResponse,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        spam_result = SpamDetectionResult.model_validate_json(agent_response.agent_run_response.text)
        await ctx.yield_output(f"Email marked as spam: {spam_result.reason}")
```

## Standalone Mode (DevUI)

This sample also supports running standalone for local development:

```python
# Change launch(durable=True) to launch(durable=False) in function_app.py
# Then run:
python function_app.py
```

This starts the DevUI at `http://localhost:8094` for interactive testing.

## Related Samples

- `09_workflow_shared_state` - Workflow with SharedState for passing data between executors
- `06_multi_agent_orchestration_conditionals` - Manual Durable Functions orchestration with agents
