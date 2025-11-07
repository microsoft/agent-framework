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
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint

# Create your agent
agent = ChatAgent(
    name="my_agent",
    instructions="You are a helpful assistant.",
    chat_client=AzureOpenAIChatClient(
        endpoint="https://your-resource.openai.azure.com/",
        deployment_name="gpt-4o-mini",
    ),
)

# Create FastAPI app and add AG-UI endpoint
app = FastAPI()
add_agent_framework_fastapi_endpoint(app, agent, "/")

# Run with: uvicorn main:app --reload
```

## Documentation

- **[Getting Started Tutorial](getting_started/)** - Step-by-step guide to building your first AG-UI server and client
- **[Examples](agent_framework_ag_ui_examples/)** - Complete examples for AG-UI features

## Features

This integration supports all 7 AG-UI features:

1. **Agentic Chat**: Basic streaming chat with tool calling support
2. **Backend Tool Rendering**: Tools executed on backend with results streamed to client
3. **Human in the Loop**: Function approval requests for user confirmation before tool execution
4. **Agentic Generative UI**: Async tools for long-running operations with progress updates
5. **Tool-based Generative UI**: Custom UI components rendered on frontend based on tool calls
6. **Shared State**: Bidirectional state sync between client and server
7. **Predictive State Updates**: Stream tool arguments as optimistic state updates during execution

## Architecture

The package uses a clean, orchestrator-based architecture:

- **AgentFrameworkAgent**: Lightweight wrapper that delegates to orchestrators
- **Orchestrators**: Handle different execution flows (default, human-in-the-loop, etc.)
- **Confirmation Strategies**: Domain-specific confirmation messages (extensible)
- **AgentFrameworkEventBridge**: Converts Agent Framework events to AG-UI events
- **Message Adapters**: Bidirectional conversion between AG-UI and Agent Framework message formats
- **FastAPI Endpoint**: Streaming HTTP endpoint with Server-Sent Events (SSE)

## Next Steps

1. **New to AG-UI?** Start with the [Getting Started Tutorial](getting_started/)
2. **Want to see examples?** Check out the [Examples](agent_framework_ag_ui_examples/) for AG-UI features

## License

MIT
