# DevUI - A Sample App for Running Agents and Workflows

A lightweight, standalone sample app interface for running entities (agents/workflows) in the Microsoft Agent Framework supporting **directory-based discovery**, **in-memory entity registration**, and **sample entity gallery**.

> [!IMPORTANT]
> DevUI is a **sample app** to help you get started with the Agent Framework. It is **not** intended for production use. For production, or for features beyond what is provided in this sample app, it is recommended that you build your own custom interface and API server using the Agent Framework SDK.

![DevUI Screenshot](./docs/devuiscreen.png)

## Quick Start

```bash
# Install
pip install agent-framework-devui --pre
```

You can also launch it programmatically

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework.devui import serve

def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Weather in {location}: 72°F and sunny"

# Create your agent
agent = ChatAgent(
    name="WeatherAgent",
    chat_client=OpenAIChatClient(),
    tools=[get_weather]
)

# Launch debug UI - that's it!
serve(entities=[agent], auto_open=True)
# → Opens browser to http://localhost:8080
```

In addition, if you have agents/workflows defined in a specific directory structure (see below), you can launch DevUI from the _cli_ to discover and run them.

```bash

# Launch web UI + API server
devui ./agents --port 8080
# → Web UI: http://localhost:8080
# → API: http://localhost:8080/v1/*
```

When DevUI starts with no discovered entities, it displays a **sample entity gallery** with curated examples from the Agent Framework repository to help you get started quickly.

## Directory Structure

For your agents to be discovered by the DevUI, they must be organized in a directory structure like below. Each agent/workflow must have an `__init__.py` that exports the required variable (`agent` or `workflow`).

**Note**: `.env` files are optional but will be automatically loaded if present in the agent/workflow directory or parent entities directory. Use them to store API keys, configuration variables, and other environment-specific settings.

```
agents/
├── weather_agent/
│   ├── __init__.py      # Must export: agent = ChatAgent(...)
│   ├── agent.py
│   └── .env             # Optional: API keys, config vars
├── my_workflow/
│   ├── __init__.py      # Must export: workflow = WorkflowBuilder()...
│   ├── workflow.py
│   └── .env             # Optional: environment variables
└── .env                 # Optional: shared environment variables
```

## Viewing Telemetry (Otel Traces) in DevUI

Agent Framework emits OpenTelemetry (Otel) traces for various operations. You can view these traces in DevUI by enabling tracing when starting the server.

```bash
devui ./agents --tracing framework
```

## OpenAI-Compatible API

For convenience, you can interact with the agents/workflows using the standard OpenAI API format. Just specify the `entity_id` in the `extra_body` field. This can be an `agent_id` or `workflow_id`.

```bash
# Standard OpenAI format
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "model": "agent-framework",
  "input": "Hello world",
  "extra_body": {"entity_id": "weather_agent"}
}

```

## CLI Options

```bash
devui [directory] [options]

Options:
  --port, -p      Port (default: 8080)
  --host          Host (default: 127.0.0.1)
  --headless      API only, no UI
  --config        YAML config file
  --tracing       none|framework|workflow|all
  --reload        Enable auto-reload
```

## Key Endpoints

- `GET /v1/entities` - List discovered agents/workflows
- `GET /v1/entities/{entity_id}/info` - Get detailed entity information
- `POST /v1/entities/add` - Add entity from URL (for gallery samples)
- `DELETE /v1/entities/{entity_id}` - Remove remote entity
- `POST /v1/responses` - Execute agent/workflow (streaming or sync)
- `GET /health` - Health check
- `POST /v1/threads` - Create thread for agent (optional)
- `GET /v1/threads?agent_id={id}` - List threads for agent
- `GET /v1/threads/{thread_id}` - Get thread info
- `DELETE /v1/threads/{thread_id}` - Delete thread
- `GET /v1/threads/{thread_id}/messages` - Get thread messages

## Implementation

- **Discovery**: `agent_framework_devui/_discovery.py`
- **Execution**: `agent_framework_devui/_executor.py`
- **Message Mapping**: `agent_framework_devui/_mapper.py`
- **Session Management**: `agent_framework_devui/_session.py`
- **API Server**: `agent_framework_devui/_server.py`
- **CLI**: `agent_framework_devui/_cli.py`

## Examples

See `samples/` for working agent and workflow implementations.

## License

MIT
