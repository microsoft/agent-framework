# Agent Framework AG-UI Integration

AG-UI protocol integration for Agent Framework, enabling seamless integration with AG-UI's web interface and streaming protocol.

## Installation

```bash
pip install agent-framework-ag-ui
```

## Quick Start

```python
from fastapi import FastAPI
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

# Create your agent
agent = ChatAgent(
    name="my_agent",
    instructions="You are a helpful assistant.",
    chat_client=AzureOpenAIChatClient(model_id="gpt-4o"),
)

# Create FastAPI app and add AG-UI endpoint
app = FastAPI()
add_agent_framework_fastapi_endpoint(app, agent, "/agent")

# Run with: uvicorn main:app --reload
```

## Features

This integration supports all 7 AG-UI features:

1. **Agentic Chat**: Basic streaming chat with tool calling support
2. **Backend Tool Rendering**: Tools executed on backend with results streamed via ToolCallResultEvent
3. **Human in the Loop**: Function approval requests for user confirmation before tool execution
4. **Agentic Generative UI**: Async tools for long-running operations with progress updates
5. **Tool-based Generative UI**: Custom UI components rendered on frontend based on tool calls
6. **Shared State**: Bidirectional state sync using StateSnapshotEvent and StateDeltaEvent
7. **Predictive State Updates**: Stream tool arguments as optimistic state updates during execution

## Examples

Complete examples for all features are in the `examples/` directory:

- `examples/agents/simple_agent.py` - Basic agentic chat
- `examples/agents/weather_agent.py` - Backend tool rendering
- `examples/agents/task_planner_agent.py` - Human in the loop with approvals
- `examples/agents/research_assistant_agent.py` - Agentic generative UI
- `examples/agents/ui_generator_agent.py` - Tool-based generative UI
- `examples/agents/recipe_agent.py` - Shared state management
- `examples/agents/document_writer_agent.py` - Predictive state updates
- `examples/server/main.py` - FastAPI server with all endpoints

Run the example server:

```bash
cd examples/server
uvicorn main:app --reload
```

To enable debug logging:

```bash
ENABLE_DEBUG_LOGGING=1 uvicorn main:app --reload
```

The server exposes endpoints at:
- `/agentic_chat`
- `/backend_tool_rendering`
- `/human_in_the_loop`
- `/agentic_generative_ui`
- `/tool_based_generative_ui`
- `/shared_state`
- `/predictive_state_updates`

## Architecture

The package uses a clean, orchestrator-based architecture:

- **AgentFrameworkAgent**: Lightweight wrapper that delegates to orchestrators
- **Orchestrators**: Handle different execution flows (default, human-in-the-loop, etc.)
- **Confirmation Strategies**: Domain-specific confirmation messages (extensible)
- **AgentFrameworkEventBridge**: Converts AgentRunResponseUpdate to AG-UI events
- **Message Adapters**: Bidirectional conversion between AG-UI and Agent Framework message formats
- **FastAPI Endpoint**: Streaming HTTP endpoint with Server-Sent Events (SSE)

### Key Design Patterns

- **Orchestrator Pattern**: Separates flow control from protocol translation
- **Strategy Pattern**: Pluggable confirmation message strategies
- **Context Object**: Lazy-loaded execution context passed to orchestrators
- **Event Bridge**: Stateless translation of Agent Framework events to AG-UI events

## Advanced Usage

### Shared State

State is injected as system messages and updated via predictive state updates:

```python
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.ag_ui import AgentFrameworkAgent

# Create your agent
agent = ChatAgent(
    name="recipe_agent",
    chat_client=AzureOpenAIChatClient(model_id="gpt-4o"),
)

state_schema = {
    "recipe": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "ingredients": {"type": "array"}
        }
    }
}

# Configure which tool updates which state fields
predict_state_config = {
    "recipe": {"tool": "update_recipe", "tool_argument": "recipe_data"}
}

wrapped_agent = AgentFrameworkAgent(
    agent=agent,
    state_schema=state_schema,
    predict_state_config=predict_state_config,
)
```

### Predictive State Updates

Predictive state updates automatically stream tool arguments as optimistic state updates:

```python
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.ag_ui import AgentFrameworkAgent

# Create your agent
agent = ChatAgent(
    name="document_writer",
    chat_client=AzureOpenAIChatClient(model_id="gpt-4o"),
)

predict_state_config = {
    "current_title": {"tool": "write_document", "tool_argument": "title"},
    "current_content": {"tool": "write_document", "tool_argument": "content"},
}

wrapped_agent = AgentFrameworkAgent(
    agent=agent,
    state_schema={"current_title": {"type": "string"}, "current_content": {"type": "string"}},
    predict_state_config=predict_state_config,
    require_confirmation=True,  # User can approve/reject changes
)
```

### Custom Confirmation Strategies

Provide domain-specific confirmation messages:

```python
from typing import Any
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.ag_ui import AgentFrameworkAgent, ConfirmationStrategy

class CustomConfirmationStrategy(ConfirmationStrategy):
    def on_approval_accepted(self, steps: list[dict[str, Any]]) -> str:
        return "Your custom approval message!"
    
    def on_approval_rejected(self, steps: list[dict[str, Any]]) -> str:
        return "Your custom rejection message!"
    
    def on_state_confirmed(self) -> str:
        return "State changes confirmed!"
    
    def on_state_rejected(self) -> str:
        return "State changes rejected!"

agent = ChatAgent(
    name="custom_agent",
    chat_client=AzureOpenAIChatClient(model_id="gpt-4o"),
)

wrapped_agent = AgentFrameworkAgent(
    agent=agent,
    confirmation_strategy=CustomConfirmationStrategy(),
)
```

### Human in the Loop

Human-in-the-loop is automatically handled when tools are marked for approval:

```python
from agent_framework import ai_function

@ai_function(approval_mode="always_require")
def sensitive_action(param: str) -> str:
    """This action requires user approval."""
    return f"Executed with {param}"

# The orchestrator automatically detects approval responses and handles them
```

### Custom Orchestrators

Add custom execution flows by implementing the Orchestrator pattern:

```python
from agent_framework.ag_ui._orchestrators import Orchestrator, ExecutionContext

class MyCustomOrchestrator(Orchestrator):
    def can_handle(self, context: ExecutionContext) -> bool:
        # Return True if this orchestrator should handle the request
        return context.input_data.get("custom_mode") == True
    
    async def run(self, context: ExecutionContext):
        # Custom execution logic
        yield RunStartedEvent(...)
        # ... your custom flow
        yield RunFinishedEvent(...)

wrapped_agent = AgentFrameworkAgent(
    agent=your_agent,
    orchestrators=[MyCustomOrchestrator(), DefaultOrchestrator()],
)

## Documentation

For detailed documentation, see [DESIGN.md](DESIGN.md).

## License

MIT
