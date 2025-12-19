# Hybrid Multi-Agent Workflow with Durable Functions – Python

This sample demonstrates a **hybrid approach** that combines Durable Functions orchestration with Agent Framework workflows.

## Overview

This sample bridges the gap between the two previous samples:
- **`06_multi_agent_orchestration_conditionals`** - Pure Durable Functions orchestration
- **`09_workflow_shared_state`** - Workflow with shared state

The hybrid approach:
1. Registers agents via `AgentFunctionApp` (Durable Functions style)
2. Retrieves agents from `DurableOrchestrationContext` during orchestration
3. Builds a `WorkflowBuilder` graph using those agents
4. Executes the workflow logic within the durable orchestration

## Architecture

```text
AgentFunctionApp
  ├─ Register SpamDetectionAgent
  └─ Register EmailAssistantAgent

DurableOrchestration
  ├─ Get agents from context
  ├─ Build WorkflowBuilder graph with agents + executors
  └─ Execute workflow logic (procedural with agents)
```

## Components

### AI Agents (registered via AgentFunctionApp)

1. **SpamDetectionAgent** - Analyzes emails for spam
2. **EmailAssistantAgent** - Drafts professional responses

### Executors (defined as classes)

1. **SpamHandlerExecutor** - Handles spam emails (non-AI activity)
2. **EmailSenderExecutor** - Sends email responses (non-AI activity)

## Key Features

- **Agent Registration**: Uses `AgentFunctionApp` for centralized agent management
- **Context-Based Retrieval**: Gets agents from `context.get_agent()`
- **Workflow Builder**: Constructs declarative workflow graphs
- **Executor Pattern**: Uses Executor classes (no traditional activity triggers)
- **Durable Orchestration**: Runs within durable context with state persistence

## Running the Sample

### Prerequisites

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Configure your environment:

   Copy the sample configuration files:
   ```bash
   cp .env.sample .env
   cp local.settings.json.sample local.settings.json
   ```

   Update `.env` and `local.settings.json` with your Azure OpenAI credentials.

3. Start Azurite (for local storage):

   ```bash
   azurite
   ```

### Execution Modes

This sample can be run in two modes by modifying the `launch(durable=...)` call at the bottom of `function_app.py`.

#### 1. Durable Functions Mode (Default)

Set `launch(durable=True)` in `function_app.py`.

- **Configuration**: Requires `local.settings.json`.
- **Command**:

  ```bash
  func start
  ```

- **Description**: Runs the workflow as a Durable Functions orchestration. The app will start on `http://localhost:7071`.

#### 2. Standalone Workflow Mode (DevUI)

Set `launch(durable=False)` in `function_app.py`.

- **Configuration**: Requires `.env`.
- **Command**:

  ```bash
  python function_app.py
  ```

- **Description**: Runs the workflow locally using the Agent Framework DevUI (available at `http://localhost:8094`).

### Test with HTTP Requests

Use `demo.http` or curl:

```bash
# Start orchestration
curl -X POST http://localhost:7071/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"email_id": "test-001", "email_content": "URGENT! Click here now!"}'

# Check status
curl http://localhost:7071/api/workflow/status/{instanceId}
```

## Comparison with Other Samples

| Feature | Orchestration | Workflow | **Hybrid** |
|---------|--------------|----------|------------|
| **Agent Registration** | AgentFunctionApp | Direct creation | **AgentFunctionApp** |
| **Agent Retrieval** | context.get_agent() | Direct reference | **context.get_agent()** |
| **Workflow Definition** | Procedural (yield) | Declarative (WorkflowBuilder) | **Both** |
| **Activity Style** | @activity_trigger | Executor classes | **Executor classes** |
| **Execution Model** | Durable orchestration | In-memory workflow | **Durable orchestration** |
| **State Persistence** | ✅ Azure Storage | ❌ In-memory | **✅ Azure Storage** |
| **Scalability** | ✅ Cloud-native | ❌ Single process | **✅ Cloud-native** |

## When to Use This Approach

**Use the Hybrid approach** when you:

- Want the declarative nature of WorkflowBuilder for documentation
- Need durable state persistence and cloud scalability
- Want to use Executor classes instead of activity triggers
- Want to visualize workflow structure programmatically
- Need both agent-based reasoning and executor-based activities
- Are exploring workflow patterns within durable orchestrations

**Don't use it** when:

- You only need simple orchestration (use pure Durable Functions)
- You want standalone workflows without Azure infrastructure (use pure WorkflowBuilder)
- The added complexity doesn't provide value

## Code Highlights

### Agent Registration

```python
app = AgentFunctionApp(agents=_create_agents(), enable_health_check=True)
```

### Agent Retrieval in Orchestration

```python
@app.orchestration_trigger(context_name="context")
def spam_detection_workflow_orchestration(context: DurableOrchestrationContext):
    # Get agents from context
    spam_agent = context.get_agent(SPAM_AGENT_NAME)
    email_agent = context.get_agent(EMAIL_AGENT_NAME)

    # Build workflow graph
    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_agent)
        .add_switch_case_edge_group(...)
        .build()
    )
```

### Mixed Execution Styles

```python
# Executor-based activity (no @activity_trigger needed)
class SpamHandlerExecutor(Executor):
    @handler
    async def handle_spam_result(self, agent_response, ctx):
        spam_result = SpamDetectionResult.model_validate_json(agent_response.agent_run_response.text)
        message = f"Email marked as spam: {spam_result.reason}"
        await ctx.yield_output(message)

# Workflow execution follows the graph structure but runs procedurally
if spam_result.is_spam:
    result = f"Email marked as spam: {spam_result.reason}"
    return result
```

## Benefits of Hybrid Approach

1. **Documentation** - WorkflowBuilder graph serves as living documentation
2. **Flexibility** - Mix declarative structure with procedural execution
3. **Scalability** - Leverage durable orchestration for production workloads
4. **Type Safety** - Workflow validation catches type mismatches
5. **Executor Pattern** - Modern class-based activity definitions instead of decorators

## Limitations

- WorkflowBuilder used for structure/documentation only (not native execution)
- Execution is still procedural with yield-based orchestration
- Requires understanding of both workflow and orchestration paradigms
- Executor classes defined but not automatically invoked by workflow engine

## Next Steps

- Explore pure workflow execution without orchestration
- Add workflow visualization endpoints
- Implement workflow-native execution within durable context
- Add telemetry and monitoring integration

## Related Samples

- `06_multi_agent_orchestration_conditionals` - Pure Durable Functions approach
- `09_workflow_shared_state` - Workflow with shared state
