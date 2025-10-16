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

When DevUI starts with no discovered entities, it displays a **sample entity gallery** with curated examples from the Agent Framework repository. You can download these samples, review them, and run them locally to get started quickly.

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

For convenience, DevUI provides an OpenAI Responses backend API. This means you can run the backend and also use the OpenAI client sdk to connect to it. Use **agent/workflow name as the model**, and set streaming to `True` as needed.

```bash
# Simple - use your entity name as the model
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "model": "weather_agent",
  "input": "Hello world"
}
```

Or use the OpenAI Python SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed"  # API key not required for local DevUI
)

response = client.responses.create(
    model="weather_agent",  # Your agent/workflow name
    input="What's the weather in Seattle?"
)

# Extract text from response
print(response.output[0].content[0].text)
# Supports streaming with stream=True
```

### Multi-turn Conversations

Use the standard OpenAI `conversation` parameter for multi-turn conversations:

```python
# Create a conversation
conversation = client.conversations.create(
    metadata={"agent_id": "weather_agent"}
)

# Use it across multiple turns
response1 = client.responses.create(
    model="weather_agent",
    input="What's the weather in Seattle?",
    conversation=conversation.id
)

response2 = client.responses.create(
    model="weather_agent",
    input="How about tomorrow?",
    conversation=conversation.id  # Continues the conversation!
)
```

**How it works:** DevUI automatically retrieves the conversation's message history from the stored thread and passes it to the agent. You don't need to manually manage message history - just provide the same `conversation` ID for follow-up requests.

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

## API Mapping

Given that DevUI offers an OpenAI Responses API, it internally maps messages and events from Agent Framework to OpenAI Responses API events (in `_mapper.py`). For transparency, this mapping is shown below:

| Agent Framework Content         | OpenAI Event/Type                        | Status   |
| ------------------------------- | ---------------------------------------- | -------- |
| `TextContent`                   | `response.output_text.delta`             | Standard |
| `TextReasoningContent`          | `response.reasoning_text.delta`          | Standard |
| `FunctionCallContent` (initial) | `response.output_item.added`             | Standard |
| `FunctionCallContent` (args)    | `response.function_call_arguments.delta` | Standard |
| `FunctionResultContent`         | `response.function_result.complete`      | DevUI    |
| `FunctionApprovalRequestContent`| `response.function_approval.requested`   | DevUI    |
| `FunctionApprovalResponseContent`| `response.function_approval.responded`  | DevUI    |
| `ErrorContent`                  | `error`                                  | Standard |
| `UsageContent`                  | Final `Response.usage` field (not streamed) | Standard |
| `WorkflowEvent`                 | `response.workflow_event.complete`       | DevUI    |
| `DataContent`                   | `response.trace.complete`                | DevUI    |
| `UriContent`                    | `response.trace.complete`                | DevUI    |
| `HostedFileContent`             | `response.trace.complete`                | DevUI    |
| `HostedVectorStoreContent`      | `response.trace.complete`                | DevUI    |

- **Standard** = OpenAI Responses API spec
- **DevUI** = Custom extensions for Agent Framework features (workflows, traces, function approvals)

### OpenAI Responses API Compliance

DevUI follows the OpenAI Responses API specification for maximum compatibility:

**Standard OpenAI Types Used:**
- `ResponseOutputItemAddedEvent` - Output item notifications (function calls and results)
- `Response.usage` - Token usage (in final response, not streamed)
- All standard text, reasoning, and function call events

**Custom DevUI Extensions:**
- `response.function_approval.requested` - Function approval requests (for interactive approval workflows)
- `response.function_approval.responded` - Function approval responses (user approval/rejection)
- `response.workflow_event.complete` - Agent Framework workflow events
- `response.trace.complete` - Execution traces and internal content (DataContent, UriContent, hosted files/stores)

These custom extensions are clearly namespaced and can be safely ignored by standard OpenAI clients.

### Entity Management

- `GET /v1/entities` - List discovered agents/workflows
- `GET /v1/entities/{entity_id}/info` - Get detailed entity information
- `POST /v1/entities/{entity_id}/reload` - Hot reload entity (for development)

### Execution (OpenAI Responses API)

- `POST /v1/responses` - Execute agent/workflow (streaming or sync)

### Conversations (OpenAI Standard)

- `POST /v1/conversations` - Create conversation
- `GET /v1/conversations/{id}` - Get conversation
- `POST /v1/conversations/{id}` - Update conversation metadata
- `DELETE /v1/conversations/{id}` - Delete conversation
- `GET /v1/conversations?agent_id={id}` - List conversations _(DevUI extension)_
- `POST /v1/conversations/{id}/items` - Add items to conversation
- `GET /v1/conversations/{id}/items` - List conversation items
- `GET /v1/conversations/{id}/items/{item_id}` - Get conversation item

### Health

- `GET /health` - Health check

## Security

DevUI is designed as a **sample application for local development** and should not be exposed to untrusted networks or used in production environments.

**Security features:**
- Only loads entities from local directories or in-memory registration
- No remote code execution capabilities
- Binds to localhost (127.0.0.1) by default
- All samples must be manually downloaded and reviewed before running

**Best practices:**
- Never expose DevUI to the internet
- Review all agent/workflow code before running
- Only load entities from trusted sources
- Use `.env` files for sensitive credentials (never commit them)

## Implementation

- **Discovery**: `agent_framework_devui/_discovery.py`
- **Execution**: `agent_framework_devui/_executor.py`
- **Message Mapping**: `agent_framework_devui/_mapper.py`
- **Conversations**: `agent_framework_devui/_conversations.py`
- **API Server**: `agent_framework_devui/_server.py`
- **CLI**: `agent_framework_devui/_cli.py`

## Examples

See working implementations in `python/samples/getting_started/devui/`

## License

MIT
