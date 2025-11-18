# Agent Framework AG-UI Integration

AG-UI protocol integration for Agent Framework, enabling seamless integration with AG-UI's web interface and streaming protocol.

## Installation

```bash
pip install agent-framework-ag-ui
```

## Quick Start

### Using Example Agents with Any Chat Client

All example agents are factory functions that accept any `ChatClientProtocol`-compatible chat client:

```python
from fastapi import FastAPI
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.openai import OpenAIChatClient
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework_ag_ui_examples.agents import simple_agent, weather_agent

app = FastAPI()

# Option 1: Use Azure OpenAI
azure_client = AzureOpenAIChatClient(model_id="gpt-4")
add_agent_framework_fastapi_endpoint(app, simple_agent(azure_client), "/chat")

# Option 2: Use OpenAI
openai_client = OpenAIChatClient(model_id="gpt-4o")
add_agent_framework_fastapi_endpoint(app, weather_agent(openai_client), "/weather")

# Run with: uvicorn main:app --reload
```

### Creating Your Own Agent

```python
from fastapi import FastAPI
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint

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

All example agents are implemented as **factory functions** that accept any chat client implementing `ChatClientProtocol`. This provides maximum flexibility to use Azure OpenAI, OpenAI, Anthropic, or any custom chat client implementation.

### Available Example Agents

Complete examples for all AG-UI features are available:

- `simple_agent(chat_client)` - Basic agentic chat (Feature 1)
- `weather_agent(chat_client)` - Backend tool rendering (Feature 2)
- `human_in_the_loop_agent(chat_client)` - Human-in-the-loop with step customization (Feature 3)
- `task_steps_agent_wrapped(chat_client)` - Agentic generative UI with step execution (Feature 4)
- `ui_generator_agent(chat_client)` - Tool-based generative UI (Feature 5)
- `recipe_agent(chat_client)` - Shared state management (Feature 6)
- `document_writer_agent(chat_client)` - Predictive state updates (Feature 7)
- `research_assistant_agent(chat_client)` - Research with progress events
- `task_planner_agent(chat_client)` - Task planning with approvals

### Using Example Agents

```python
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.openai import OpenAIChatClient
from agent_framework_ag_ui_examples.agents import (
    simple_agent,
    weather_agent,
    recipe_agent,
)

# Create a chat client (use any ChatClientProtocol implementation)
azure_client = AzureOpenAIChatClient(model_id="gpt-4")
openai_client = OpenAIChatClient(model_id="gpt-4o")

# Create agent instances by calling the factory functions
agent1 = simple_agent(azure_client)
agent2 = weather_agent(openai_client)
agent3 = recipe_agent(azure_client)
```

### Running the Example Server

The example server demonstrates all 7 AG-UI features:

```bash
# Install the package
pip install agent-framework-ag-ui

# Run the example server
python -m agent_framework_ag_ui_examples

# Or with debug logging
ENABLE_DEBUG_LOGGING=1 python -m agent_framework_ag_ui_examples
```

The server exposes endpoints at:
- `/agentic_chat` - Simple chat with `simple_agent`
- `/backend_tool_rendering` - Weather tools with `weather_agent`
- `/human_in_the_loop` - Step approval with `human_in_the_loop_agent`
- `/agentic_generative_ui` - Task steps with `task_steps_agent_wrapped`
- `/tool_based_generative_ui` - Custom UI components with `ui_generator_agent`
- `/shared_state` - Recipe management with `recipe_agent`
- `/predictive_state_updates` - Document writing with `document_writer_agent`

### Complete FastAPI Example

```python
from fastapi import FastAPI
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework_ag_ui_examples.agents import (
    simple_agent,
    weather_agent,
    human_in_the_loop_agent,
    task_steps_agent_wrapped,
    ui_generator_agent,
    recipe_agent,
    document_writer_agent,
)

app = FastAPI(title="AG-UI Examples")

# Create a chat client (shared across all agents, or create individual ones)
chat_client = AzureOpenAIChatClient(model_id="gpt-4")

# Add all example endpoints
add_agent_framework_fastapi_endpoint(app, simple_agent(chat_client), "/agentic_chat")
add_agent_framework_fastapi_endpoint(app, weather_agent(chat_client), "/backend_tool_rendering")
add_agent_framework_fastapi_endpoint(app, human_in_the_loop_agent(chat_client), "/human_in_the_loop")
add_agent_framework_fastapi_endpoint(app, task_steps_agent_wrapped(chat_client), "/agentic_generative_ui")  # type: ignore[arg-type]
add_agent_framework_fastapi_endpoint(app, ui_generator_agent(chat_client), "/tool_based_generative_ui")
add_agent_framework_fastapi_endpoint(app, recipe_agent(chat_client), "/shared_state")
add_agent_framework_fastapi_endpoint(app, document_writer_agent(chat_client), "/predictive_state_updates")
```

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

### Creating Custom Agent Factories

You can create your own agent factories following the same pattern as the examples:

```python
from agent_framework import ChatAgent, ai_function
from agent_framework._clients import ChatClientProtocol
from agent_framework_ag_ui import AgentFrameworkAgent

@ai_function
def my_tool(param: str) -> str:
    """My custom tool."""
    return f"Result: {param}"

def my_custom_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Create a custom agent with the specified chat client.
    
    Args:
        chat_client: The chat client to use for the agent
        
    Returns:
        A configured AgentFrameworkAgent instance
    """
    agent = ChatAgent(
        name="my_custom_agent",
        instructions="Custom instructions here",
        chat_client=chat_client,
        tools=[my_tool],
    )
    
    return AgentFrameworkAgent(
        agent=agent,
        name="MyCustomAgent",
        description="My custom agent description",
    )

# Use it
from agent_framework.azure import AzureOpenAIChatClient
chat_client = AzureOpenAIChatClient()
agent = my_custom_agent(chat_client)
```

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
