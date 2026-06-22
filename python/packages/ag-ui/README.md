# Agent Framework AG-UI Integration

AG-UI protocol integration for Agent Framework, enabling seamless integration with AG-UI's web interface and streaming protocol.

## Installation

```bash
pip install agent-framework-ag-ui
```

## Quick Start

### Server (Host an AI Agent)

```python
from fastapi import FastAPI
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

# Create your agent
agent = Agent(
    name="my_agent",
    instructions="You are a helpful assistant.",
    client=OpenAIChatCompletionClient(
        azure_endpoint="https://your-resource.openai.azure.com/",
        model="gpt-4o-mini",
        api_key="your-api-key",
    ),
)

# Create FastAPI app and add AG-UI endpoint
app = FastAPI()
add_agent_framework_fastapi_endpoint(app, agent, "/")

# Run with: uvicorn main:app --reload
```

### Server (Host a Workflow)

```python
from fastapi import FastAPI
from agent_framework import WorkflowBuilder, WorkflowContext, executor
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

@executor(id="start")
async def start(message: str, ctx: WorkflowContext) -> None:
    await ctx.yield_output(f"Workflow received: {message}")

workflow = WorkflowBuilder(start_executor=start).build()

app = FastAPI()
add_agent_framework_fastapi_endpoint(app, workflow, "/")
```

### Server (Thread-Scoped WorkflowBuilder)

Use `workflow_factory` when your workflow keeps runtime state (for example pending `request_info` interrupts) and must be isolated per AG-UI thread:

```python
from fastapi import FastAPI
from agent_framework import Workflow, WorkflowBuilder
from agent_framework.ag_ui import AgentFrameworkWorkflow, add_agent_framework_fastapi_endpoint

def build_workflow_for_thread(thread_id: str) -> Workflow:
    # Build a fresh workflow instance for each thread id.
    return WorkflowBuilder(start_executor=...).build()

app = FastAPI()
thread_scoped_workflow = AgentFrameworkWorkflow(
    workflow_factory=build_workflow_for_thread,
    name="my_workflow",
)
add_agent_framework_fastapi_endpoint(app, thread_scoped_workflow, "/")
```

### Client (Connect to an AG-UI Server)

```python
import asyncio
from agent_framework.ag_ui import AGUIChatClient

async def main():
    async with AGUIChatClient(endpoint="http://localhost:8000/") as client:
        # Stream responses
        async for update in client.get_response("Hello!", stream=True):
            for content in update.contents:
                if content.type == "text" and content.text:
                    print(content.text, end="", flush=True)
        print()

asyncio.run(main())
```

The `AGUIChatClient` supports:
- Streaming and non-streaming responses
- Hybrid tool execution (client-side + server-side tools)
- Automatic thread management for conversation continuity
- Integration with `Agent` for client-side history management
- Interrupt metadata passthrough (`availableInterrupts` and `resume`)

## Tool Return Helpers

Use `state_update` when a backend tool needs to send different payloads to the model, the UI, and shared state. The `text` value remains the LLM-bound tool result, `tool_result` becomes the AG-UI `ToolCallResultEvent.content` for frontend rendering, and `state` is merged into durable shared state.

```python
from agent_framework import Content, tool
from agent_framework.ag_ui import state_update

@tool
async def get_weather(city: str) -> Content:
    data = await fetch_weather(city)
    return state_update(
        text=f"{city}: {data['temp']}°C and {data['conditions']}",
        tool_result={
            "component": "weather-card",
            "city": city,
            "temperature": data["temp"],
            "conditions": data["conditions"],
            "humidity": data["humidity"],
        },
        state={"weather": {"city": city, **data}},
    )
```

## Documentation

- **[Getting Started Tutorial](getting_started/)** - Step-by-step guide to building AG-UI servers and clients
  - Server setup with FastAPI
  - Client examples using `AGUIChatClient`
  - Hybrid tool execution (client-side + server-side)
  - Thread management and conversation continuity
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

Additional compatibility and draft support:
- Native `Workflow` endpoint registration via `add_agent_framework_fastapi_endpoint(...)`
- Workflow-to-AG-UI event mapping (run/step/activity/tool/custom events)
- Custom event compatibility for inbound `CUSTOM`, `CUSTOM_EVENT`, and `custom_event`
- Pragmatic multimodal input parsing for both legacy (`binary`) and draft media-part shapes
- Pragmatic interrupt/resume handling (`availableInterrupts`, `resume`, and `RUN_FINISHED.interrupt`)

## Security: Authentication & Authorization

The AG-UI endpoint does not enforce authentication by default. **For production deployments, you should add authentication** using FastAPI's dependency injection system via the `dependencies` parameter.

### API Key Authentication Example

```python
import os
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from agent_framework import Agent
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

# Configure API key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
EXPECTED_API_KEY = os.environ.get("AG_UI_API_KEY")

async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> None:
    """Verify the API key provided in the request header."""
    if not api_key or api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# Create agent and app
agent = Agent(name="my_agent", instructions="...", client=...)
app = FastAPI()

# Register endpoint WITH authentication
add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    dependencies=[Depends(verify_api_key)],  # Authentication enforced here
)
```

### Other Authentication Options

The `dependencies` parameter accepts any FastAPI dependency, enabling integration with:

- **OAuth 2.0 / OpenID Connect** - Use `fastapi.security.OAuth2PasswordBearer`
- **JWT Tokens** - Validate tokens with libraries like `python-jose`
- **Azure AD / Entra ID** - Use `azure-identity` for Microsoft identity platform
- **Rate Limiting** - Add request throttling dependencies
- **Custom Authentication** - Implement your organization's auth requirements

For a complete authentication example, see [getting_started/server.py](getting_started/server.py).

## AG-UI Thread Snapshots

AG-UI Thread Snapshot persistence is opt-in and disabled by default. Existing endpoints keep their current behavior
unless you provide a `snapshot_store`.

Thread snapshots let an AG-UI frontend recover replayable UI state after a refresh. When snapshot persistence is
enabled, the endpoint stores the latest replayable snapshot for an AG-UI Thread within an application-defined
Snapshot Scope. A Hydrate Request is an AG-UI request with a known `threadId`, `messages: []`, and no `resume`
payload. Hydration replays the stored Shared State, message snapshot, and interruption metadata when available,
then finishes without invoking the wrapped agent or workflow.

Use the built-in in-memory store for local development, demos, and tests:

```python
from fastapi import FastAPI

from agent_framework.ag_ui import InMemoryAGUIThreadSnapshotStore, add_agent_framework_fastapi_endpoint

app = FastAPI()
agent = ...
snapshot_store = InMemoryAGUIThreadSnapshotStore(max_snapshots=500)


def resolve_snapshot_scope(request):
    # Local demo scope. Production apps should derive the scope from authenticated user or tenant context.
    del request
    return "local-demo"


add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    snapshot_store=snapshot_store,
    snapshot_scope_resolver=resolve_snapshot_scope,
)
```

A frontend can then hydrate the latest stored snapshot for the scoped thread:

```json
{
  "threadId": "thread-1",
  "messages": []
}
```

Endpoint configuration requires `snapshot_scope_resolver` whenever a snapshot store is configured, including when
the store is already set on a pre-wrapped `AgentFrameworkAgent` or `AgentFrameworkWorkflow`. The resolver returns
the application-defined Snapshot Scope used with the AG-UI Thread id as the storage key.

AG-UI Thread ids identify AG-UI Threads; they do not authorize snapshot access. Do not treat a thread id as a bearer
credential or tenant boundary. Production applications must authenticate and authorize every AG-UI endpoint request
and choose a Snapshot Scope that represents the app's real access boundary, such as an authenticated user, tenant,
or workspace. Do not rely on untrusted client-provided fields by themselves to choose that boundary.

Stored snapshots are untrusted application data with confidentiality impact. They may contain sensitive user text,
model output, tool results, function arguments, UI payloads, Shared State, and interruption data. The built-in
`InMemoryAGUIThreadSnapshotStore` is in-memory only, process-local, bounded, latest-only, and not durable production
storage. It is cleared on process restart and is not shared across workers.

No file-backed AG-UI snapshot store is provided by the package. Applications that need durable persistence should
provide an app-owned implementation of the `AGUIThreadSnapshotStore` protocol and own storage hardening, including
encryption, access control, retention, audit, data residency, and deletion behavior.

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
