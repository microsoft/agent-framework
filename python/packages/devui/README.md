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

## Using MCP Tools

**Important:** Don't use `async with` context managers when creating agents with MCP tools for DevUI - connections will close before execution.

```python
# ✅ Correct - DevUI handles cleanup automatically
mcp_tool = MCPStreamableHTTPTool(url="http://localhost:8011/mcp", chat_client=chat_client)
agent = ChatAgent(tools=mcp_tool)
serve(entities=[agent])
```

MCP tools use lazy initialization and connect automatically on first use. DevUI attempts to clean up connections on shutdown

## Resource Cleanup

Register cleanup hooks to properly close credentials and resources on shutdown:

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_devui import register_cleanup, serve

credential = DefaultAzureCredential()
client = AzureOpenAIChatClient()
agent = ChatAgent(name="MyAgent", chat_client=client)

# Register cleanup hook - credential will be closed on shutdown
register_cleanup(agent, credential.close)
serve(entities=[agent])
```

Works with multiple resources and file-based discovery. See tests for more examples.

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

For convenience, DevUI provides an OpenAI Responses backend API. This means you can run the backend and also use the OpenAI client sdk to connect to it. Use **agent/workflow name as the entity_id in metadata**, and set streaming to `True` as needed.

```bash
# Simple - use your entity name as the entity_id in metadata
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "metadata": {"entity_id": "weather_agent"},
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
    metadata={"entity_id": "weather_agent"},  # Your agent/workflow name
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
    metadata={"entity_id": "weather_agent"},
    input="What's the weather in Seattle?",
    conversation=conversation.id
)

response2 = client.responses.create(
    metadata={"entity_id": "weather_agent"},
    input="How about tomorrow?",
    conversation=conversation.id  # Continues the conversation!
)
```

**How it works:** DevUI automatically retrieves the conversation's message history from the stored thread and passes it to the agent. You don't need to manually manage message history - just provide the same `conversation` ID for follow-up requests.

### OpenAI Proxy Mode

DevUI provides an **OpenAI Proxy** feature for testing OpenAI models directly through the interface without creating custom agents. Enable via Settings → OpenAI Proxy tab.

**How it works:** The UI sends requests to the DevUI backend (with `X-Proxy-Backend: openai` header), which then proxies them to OpenAI's Responses API (and Conversations API for multi-turn chats). This proxy approach keeps your `OPENAI_API_KEY` secure on the server—never exposed in the browser or client-side code.

**Example:**

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "X-Proxy-Backend: openai" \
  -d '{"model": "gpt-4.1-mini", "input": "Hello"}'
```

**Note:** Requires `OPENAI_API_KEY` environment variable configured on the backend.

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
  --mode          developer|user (default: developer)
  --auth          Enable Bearer token authentication
```

### UI Modes

- **developer** (default): Full access - debug panel, entity details, hot reload, deployment
- **user**: Simplified UI with restricted APIs - only chat and conversation management

```bash
# Development
devui ./agents

# Production (user-facing)
devui ./agents --mode user --auth
```

## Key Endpoints

## API Mapping

Given that DevUI offers an OpenAI Responses API, it internally maps messages and events from Agent Framework to OpenAI Responses API events (in `_mapper.py`). For transparency, this mapping is shown below:

| OpenAI Event/Type                                            | Agent Framework Content           | Status   |
| ------------------------------------------------------------ | --------------------------------- | -------- |
|                                                              | **Lifecycle Events**              |          |
| `response.created` + `response.in_progress`                  | `AgentStartedEvent`               | OpenAI   |
| `response.completed`                                         | `AgentCompletedEvent`             | OpenAI   |
| `response.failed`                                            | `AgentFailedEvent`                | OpenAI   |
| `response.created` + `response.in_progress`                  | `WorkflowStartedEvent`            | OpenAI   |
| `response.completed`                                         | `WorkflowCompletedEvent`          | OpenAI   |
| `response.failed`                                            | `WorkflowFailedEvent`             | OpenAI   |
|                                                              | **Content Types**                 |          |
| `response.content_part.added` + `response.output_text.delta` | `TextContent`                     | OpenAI   |
| `response.reasoning_text.delta`                              | `TextReasoningContent`            | OpenAI   |
| `response.output_item.added`                                 | `FunctionCallContent` (initial)   | OpenAI   |
| `response.function_call_arguments.delta`                     | `FunctionCallContent` (args)      | OpenAI   |
| `response.function_result.complete`                          | `FunctionResultContent`           | DevUI    |
| `response.function_approval.requested`                       | `FunctionApprovalRequestContent`  | DevUI    |
| `response.function_approval.responded`                       | `FunctionApprovalResponseContent` | DevUI    |
| `response.output_item.added` (ResponseOutputImage)           | `DataContent` (images)            | DevUI    |
| `response.output_item.added` (ResponseOutputFile)            | `DataContent` (files)             | DevUI    |
| `response.output_item.added` (ResponseOutputData)            | `DataContent` (other)             | DevUI    |
| `response.output_item.added` (ResponseOutputImage/File)      | `UriContent` (images/files)       | DevUI    |
| `error`                                                      | `ErrorContent`                    | OpenAI   |
| Final `Response.usage` field (not streamed)                  | `UsageContent`                    | OpenAI   |
|                                                              | **Workflow Events**               |          |
| `response.output_item.added` (ExecutorActionItem)*           | `ExecutorInvokedEvent`            | OpenAI   |
| `response.output_item.done` (ExecutorActionItem)*            | `ExecutorCompletedEvent`          | OpenAI   |
| `response.output_item.done` (ExecutorActionItem with error)* | `ExecutorFailedEvent`             | OpenAI   |
| `response.output_item.added` (ResponseOutputMessage)         | `WorkflowOutputEvent`             | OpenAI   |
| `response.workflow_event.complete`                           | `WorkflowEvent` (other)           | DevUI    |
| `response.trace.complete`                                    | `WorkflowStatusEvent`             | DevUI    |
| `response.trace.complete`                                    | `WorkflowWarningEvent`            | DevUI    |
|                                                              | **Trace Content**                 |          |
| `response.trace.complete`                                    | `DataContent` (no data/errors)    | DevUI    |
| `response.trace.complete`                                    | `UriContent` (unsupported MIME)   | DevUI    |
| `response.trace.complete`                                    | `HostedFileContent`               | DevUI    |
| `response.trace.complete`                                    | `HostedVectorStoreContent`        | DevUI    |

\*Uses standard OpenAI event structure but carries DevUI-specific `ExecutorActionItem` payload

- **OpenAI** = Standard OpenAI Responses API event types
- **DevUI** = Custom event types specific to Agent Framework (e.g., workflows, traces, function approvals)

### OpenAI Responses API Compliance

DevUI follows the OpenAI Responses API specification for maximum compatibility:

**OpenAI Standard Event Types Used:**

- `ResponseOutputItemAddedEvent` - Output item notifications (function calls, images, files, data)
- `ResponseOutputItemDoneEvent` - Output item completion notifications
- `Response.usage` - Token usage (in final response, not streamed)

**Custom DevUI Extensions:**

- `response.output_item.added` with custom item types:
  - `ResponseOutputImage` - Agent-generated images (inline display)
  - `ResponseOutputFile` - Agent-generated files (inline display)
  - `ResponseOutputData` - Agent-generated structured data (inline display)
- `response.function_approval.requested` - Function approval requests (for interactive approval workflows)
- `response.function_approval.responded` - Function approval responses (user approval/rejection)
- `response.function_result.complete` - Server-side function execution results
- `response.workflow_event.complete` - Agent Framework workflow events
- `response.trace.complete` - Execution traces and internal content (DataContent, UriContent, hosted files/stores)

These custom extensions are clearly namespaced and can be safely ignored by standard OpenAI clients. Note that DevUI also uses standard OpenAI events with custom payloads (e.g., `ExecutorActionItem` within `response.output_item.added`).

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

DevUI is designed as a **sample application for local development** and should not be exposed to untrusted networks without proper authentication.

**For production deployments:**

```bash
# User mode with authentication (recommended)
devui ./agents --mode user --auth --host 0.0.0.0
```

This restricts developer APIs (reload, deployment, entity details) and requires Bearer token authentication.

**Security features:**

- User mode restricts developer-facing APIs
- Optional Bearer token authentication via `--auth`
- Only loads entities from local directories or in-memory registration
- No remote code execution capabilities
- Binds to localhost (127.0.0.1) by default

**Best practices:**

- Use `--mode user --auth` for any deployment exposed to end users
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
