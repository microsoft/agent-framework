# Getting Started with AG-UI (Python)

The AG-UI (Agent UI) protocol provides a standardized way for client applications to interact with AI agents over HTTP. This tutorial demonstrates how to build both server and client applications using the AG-UI protocol with Python.

## What is AG-UI?

AG-UI is a protocol that enables:
- **Remote agent hosting**: Host AI agents as web services that can be accessed by multiple clients
- **Streaming responses**: Real-time streaming of agent responses using Server-Sent Events (SSE)
- **Standardized communication**: Consistent message format for agent interactions
- **Thread management**: Maintain conversation context across multiple requests
- **Advanced features**: Human-in-the-loop, state management, tool rendering

## Prerequisites

Before you begin, ensure you have the following:

- Python 3.10 or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for DefaultAzureCredential)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

**Note**: These samples use Azure OpenAI models. For more information, see [how to deploy Azure OpenAI models with Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai).

**Note**: These samples use `DefaultAzureCredential` for authentication. Make sure you're authenticated with Azure (e.g., via `az login`, or environment variables). For more information, see the [Azure Identity documentation](https://learn.microsoft.com/python/api/azure-identity/azure.identity.defaultazurecredential).

> **Warning**
> The AG-UI protocol is still under development and subject to change.
> We will keep these samples updated as the protocol evolves.

## Step 1: Creating an AG-UI Server

The AG-UI server hosts your AI agent and exposes it via HTTP endpoints using FastAPI.

### Install Required Packages

```bash
pip install agent-framework-ag-ui agent-framework-core fastapi uvicorn
```

Or using uv:

```bash
uv pip install agent-framework-ag-ui agent-framework-core fastapi uvicorn
```

### Server Code

Create a file named `server.py`:

```python
# Copyright (c) Microsoft. All rights reserved.

"""AG-UI server example."""

import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI

# Read required configuration
endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

if not endpoint:
    raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
if not deployment_name:
    raise ValueError("AZURE_OPENAI_DEPLOYMENT_NAME environment variable is required")

# Create the AI agent
agent = ChatAgent(
    name="AGUIAssistant",
    instructions="You are a helpful assistant.",
    chat_client=AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment_name,
    ),
)

# Create FastAPI app
app = FastAPI(title="AG-UI Server")

# Register the AG-UI endpoint
add_agent_framework_fastapi_endpoint(app, agent, "/")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5100)
```

### Key Concepts

- **`add_agent_framework_fastapi_endpoint`**: Registers the AG-UI endpoint with automatic request/response handling and SSE streaming
- **`ChatAgent`**: The agent that will handle incoming requests
- **FastAPI Integration**: Uses FastAPI's native async support for streaming responses
- **Instructions**: The agent is created with default instructions, which can be overridden by client messages
- **Configuration**: `AzureOpenAIChatClient` can read from environment variables (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, `AZURE_OPENAI_API_KEY`) or accept parameters directly

**Alternative (simpler)**: Use environment variables only:

```python
# No need to read environment variables manually
agent = ChatAgent(
    name="AGUIAssistant",
    instructions="You are a helpful assistant.",
    chat_client=AzureOpenAIChatClient(),  # Reads from environment automatically
)
```

### Configure and Run the Server

Set the required environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4o-mini"
# Optional: Set API key if not using DefaultAzureCredential
# export AZURE_OPENAI_API_KEY="your-api-key"
```

Run the server:

```bash
python server.py
```

Or using uvicorn directly:

```bash
uvicorn server:app --host 127.0.0.1 --port 5100
```

The server will start listening on `http://127.0.0.1:5100`.

## Step 2: Creating an AG-UI Client

The AG-UI client connects to the remote server and displays streaming responses.

### Install Required Packages

```bash
pip install httpx
```

### Client Code

Create a file named `client.py`:

```python
# Copyright (c) Microsoft. All rights reserved.

"""AG-UI client example."""

import asyncio
import json
import os
from typing import AsyncIterator

import httpx


class AGUIClient:
    """Simple AG-UI protocol client."""

    def __init__(self, server_url: str):
        """Initialize the client.

        Args:
            server_url: The AG-UI server endpoint URL
        """
        self.server_url = server_url
        self.thread_id: str | None = None

    async def send_message(self, message: str) -> AsyncIterator[dict]:
        """Send a message and stream the response.

        Args:
            message: The user message to send

        Yields:
            AG-UI events from the server
        """
        # Prepare the request
        request_data = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message},
            ]
        }

        # Include thread_id if we have one (for conversation continuity)
        if self.thread_id:
            request_data["thread_id"] = self.thread_id

        # Stream the response
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                self.server_url,
                json=request_data,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    # Parse Server-Sent Events format
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        try:
                            event = json.loads(data)
                            yield event

                            # Capture thread_id from RUN_STARTED event
                            if event.get("type") == "RUN_STARTED" and not self.thread_id:
                                self.thread_id = event.get("threadId")
                        except json.JSONDecodeError:
                            continue


async def main():
    """Main client loop."""
    # Get server URL from environment or use default
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")
    print(f"Connecting to AG-UI server at: {server_url}\n")

    client = AGUIClient(server_url)

    try:
        while True:
            # Get user input
            message = input("\nUser (:q or quit to exit): ")
            if not message.strip():
                print("Request cannot be empty.")
                continue

            if message.lower() in (":q", "quit"):
                break

            # Send message and display streaming response
            print("\n", end="")
            async for event in client.send_message(message):
                event_type = event.get("type", "")

                if event_type == "RUN_STARTED":
                    thread_id = event.get("threadId", "")
                    run_id = event.get("runId", "")
                    print(f"\033[93m[Run Started - Thread: {thread_id}, Run: {run_id}]\033[0m")

                elif event_type == "TEXT_MESSAGE_CONTENT":
                    # Stream text content in cyan
                    print(f"\033[96m{event.get('delta', '')}\033[0m", end="", flush=True)

                elif event_type == "RUN_FINISHED":
                    thread_id = event.get("threadId", "")
                    run_id = event.get("runId", "")
                    print(f"\n\033[92m[Run Finished - Thread: {thread_id}, Run: {run_id}]\033[0m")

                elif event_type == "RUN_ERROR":
                    error_message = event.get("message", "Unknown error")
                    print(f"\n\033[91m[Run Error - Message: {error_message}]\033[0m")

            print()

    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\n\033[91mAn error occurred: {e}\033[0m")


if __name__ == "__main__":
    asyncio.run(main())
```

### Key Concepts

- **Server-Sent Events (SSE)**: The protocol uses SSE format (`data: {json}\n\n`)
- **Event Types**: Different events provide metadata and content (all event types use UPPERCASE with underscores):
  - `RUN_STARTED`: Signals the agent has started processing
  - `TEXT_MESSAGE_START`: Signals the start of a text message from the agent
  - `TEXT_MESSAGE_CONTENT`: Incremental text streamed from the agent (with `delta` field)
  - `TEXT_MESSAGE_END`: Signals the end of a text message
  - `RUN_FINISHED`: Signals successful completion
  - `RUN_ERROR`: Error information if something goes wrong
- **Field Naming**: Event fields use camelCase (e.g., `threadId`, `runId`, `messageId`) when accessing JSON events
- **Thread Management**: The `threadId` maintains conversation context across requests
- **Client-Side Instructions**: System messages are sent from the client

### Configure and Run the Client

Optionally set a custom server URL:

```bash
export AGUI_SERVER_URL="http://127.0.0.1:5100/"
```

Run the client (in a separate terminal):

```bash
python client.py
```

## Step 3: Testing the Complete System

### Expected Output

```
$ python client.py
Connecting to AG-UI server at: http://127.0.0.1:5100/

User (:q or quit to exit): What is the capital of France?

[Run Started - Thread: abc123, Run: xyz789]
The capital of France is Paris. It is known for its rich history, culture,
and iconic landmarks such as the Eiffel Tower and the Louvre Museum.
[Run Finished - Thread: abc123, Run: xyz789]

User (:q or quit to exit): Tell me a fun fact about space

[Run Started - Thread: abc123, Run: def456]
Here's a fun fact: A day on Venus is longer than its year! Venus takes
about 243 Earth days to rotate once on its axis, but only about 225 Earth
days to orbit the Sun.
[Run Finished - Thread: abc123, Run: def456]

User (:q or quit to exit): :q
```

### Color-Coded Output

The client displays different content types with distinct colors:
- **Yellow**: Run started notifications
- **Cyan**: Agent text responses (streamed in real-time)
- **Green**: Run completion notifications
- **Red**: Error messages

## Testing with curl (Optional)

Before running the client, you can test the server manually using curl:

```bash
curl -N http://127.0.0.1:5100/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }'
```

You should see Server-Sent Events streaming back:

```
data: {"type":"RUN_STARTED","threadId":"...","runId":"..."}

data: {"type":"TEXT_MESSAGE_START","messageId":"...","role":"assistant"}

data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"...","delta":"The"}

data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"...","delta":" capital"}

...

data: {"type":"TEXT_MESSAGE_END","messageId":"..."}

data: {"type":"RUN_FINISHED","threadId":"...","runId":"..."}
```

## How It Works

### Server-Side Flow

1. Client sends HTTP POST request with messages
2. FastAPI endpoint receives the request
3. `AgentFrameworkAgent` wrapper orchestrates the execution
4. Agent processes the messages using Agent Framework
5. `AgentFrameworkEventBridge` converts agent updates to AG-UI events
6. Responses are streamed back as Server-Sent Events (SSE)
7. Connection closes when the run completes

### Client-Side Flow

1. Client sends HTTP POST request to server endpoint
2. Server responds with SSE stream
3. Client parses incoming `data:` lines as JSON events
4. Each event is displayed based on its type
5. `threadId` is captured for conversation continuity
6. Stream completes when `RUN_FINISHED` event arrives

### Protocol Details

The AG-UI protocol uses:
- **HTTP POST** for sending requests
- **Server-Sent Events (SSE)** for streaming responses
- **JSON** for event serialization
- **Thread IDs** for maintaining conversation context
- **Run IDs** for tracking individual executions
- **Event type naming**: UPPERCASE with underscores (e.g., `RUN_STARTED`, `TEXT_MESSAGE_CONTENT`)
- **Field naming**: camelCase (e.g., `threadId`, `runId`, `messageId`)

## Advanced Features

The Python AG-UI implementation supports all 7 AG-UI features:

### 1. Backend Tool Rendering

Add tools to your agent for backend execution:

```python
from typing import Any

from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient


@ai_function
def get_weather(location: str) -> dict[str, Any]:
    """Get weather for a location."""
    return {"temperature": 72, "conditions": "sunny"}


agent = ChatAgent(
    name="weather_agent",
    instructions="Use tools to help users.",
    chat_client=AzureOpenAIChatClient(
        endpoint="https://your-resource.openai.azure.com/",
        deployment_name="gpt-4o-mini",
    ),
    tools=[get_weather],
)
```

The client will receive `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, and `TOOL_CALL_RESULT` events.

### 2. Human in the Loop

Request user confirmation before executing tools:

```python
from fastapi import FastAPI
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_ag_ui import AgentFrameworkAgent, add_agent_framework_fastapi_endpoint

agent = ChatAgent(
    name="my_agent",
    instructions="You are a helpful assistant.",
    chat_client=AzureOpenAIChatClient(
        endpoint="https://your-resource.openai.azure.com/",
        deployment_name="gpt-4o-mini",
    ),
)

wrapped_agent = AgentFrameworkAgent(
    agent=agent,
    require_confirmation=True,  # Enable human-in-the-loop
)

app = FastAPI()
add_agent_framework_fastapi_endpoint(app, wrapped_agent, "/")
```

The client receives tool approval request events and can send approval responses.

### 3. State Management

Share state between client and server:

```python
wrapped_agent = AgentFrameworkAgent(
    agent=agent,
    state_schema={
        "location": {"type": "string"},
        "preferences": {"type": "object"},
    },
)
```

Events include `STATE_SNAPSHOT` and `STATE_DELTA` for bidirectional sync.

### 4. Predictive State Updates

Stream tool arguments as optimistic state updates:

```python
wrapped_agent = AgentFrameworkAgent(
    agent=agent,
    predict_state_config={
        "location": {"tool": "get_weather", "tool_argument": "location"}
    },
    require_confirmation=False,  # Auto-update without confirmation
)
```

State updates stream in real-time as the LLM generates tool arguments.

## Common Patterns

### Custom Server Configuration

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

add_agent_framework_fastapi_endpoint(app, agent, "/agent")
```

### Multiple Agents

```python
app = FastAPI()

weather_agent = ChatAgent(name="weather", ...)
finance_agent = ChatAgent(name="finance", ...)

add_agent_framework_fastapi_endpoint(app, weather_agent, "/weather")
add_agent_framework_fastapi_endpoint(app, finance_agent, "/finance")
```

### Custom Client Timeout

```python
async with httpx.AsyncClient(timeout=300.0) as client:
    async with client.stream("POST", server_url, ...) as response:
        async for line in response.aiter_lines():
            # Process events
            pass
```

### Error Handling

```python
try:
    async for event in client.send_message(message):
        if event.get("type") == "RUN_ERROR":
            error_msg = event.get("message", "Unknown error")
            print(f"Error: {error_msg}")
            # Handle error appropriately
except httpx.HTTPError as e:
    print(f"HTTP error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Conversation Continuity

The client automatically maintains `threadId` across requests:

```python
client = AGUIClient(server_url)

# First message
async for event in client.send_message("Hello"):
    # Client captures threadId from RUN_STARTED
    pass

# Second message - uses same threadId
async for event in client.send_message("Continue our conversation"):
    # Conversation context is maintained
    pass
```

## AG-UI Event Reference

### Core Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `RUN_STARTED` | Agent execution started | `threadId`, `runId` |
| `RUN_FINISHED` | Agent execution completed | `threadId`, `runId` |
| `RUN_ERROR` | Agent execution error | `message` |

### Text Message Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `TEXT_MESSAGE_START` | Start of agent text message | `messageId`, `role` |
| `TEXT_MESSAGE_CONTENT` | Streaming text content | `messageId`, `delta` |
| `TEXT_MESSAGE_END` | End of agent text message | `messageId` |

### Tool Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `TOOL_CALL_START` | Tool call initiated | `toolCallId`, `toolCallName` |
| `TOOL_CALL_ARGS` | Tool arguments streaming | `toolCallId`, `delta` |
| `TOOL_CALL_END` | Tool call complete | `toolCallId` |
| `TOOL_CALL_RESULT` | Tool execution result | `toolCallId`, `content` |

### State Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `STATE_SNAPSHOT` | Complete state | `snapshot` |
| `STATE_DELTA` | State changes (JSON Patch) | `delta` |

### Other Events

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `MESSAGES_SNAPSHOT` | Conversation history | `messages` |
| `CUSTOM` | Custom event data | `name`, `value` |

## Next Steps

Now that you understand the basics of AG-UI, you can:

- **Add Tools**: Create custom `@ai_function` tools for your domain
- **Web Integration**: Build React/Vue frontends using the AG-UI protocol
- **State Management**: Implement shared state for generative UI applications
- **Human-in-the-Loop**: Add approval workflows for sensitive operations
- **Deployment**: Deploy to Azure Container Apps or Azure App Service
- **Multi-Agent Systems**: Coordinate multiple specialized agents
- **Monitoring**: Add logging and OpenTelemetry for observability

## Additional Resources

- [AG-UI Examples](../agent_framework_ag_ui_examples/README.md): Complete working examples for all 7 features
- [Agent Framework Documentation](../../core/README.md): Learn more about creating agents
- [AG-UI Protocol Spec](https://docs.ag-ui.com/): Official protocol documentation

## Troubleshooting

### Connection Refused

Ensure the server is running before starting the client:

```bash
# Terminal 1
python server.py

# Terminal 2 (after server starts)
python client.py
```

### Authentication Errors

Make sure you're authenticated with Azure:

```bash
az login
```

Verify you have the correct role assignment on the Azure OpenAI resource.

### Streaming Not Working

Check that your client timeout is sufficient:

```python
httpx.AsyncClient(timeout=60.0)  # 60 seconds should be enough
```

For long-running agents, increase the timeout accordingly.

### No Events Received

Ensure you're using the correct `Accept` header:

```python
headers={"Accept": "text/event-stream"}
```

And parsing SSE format correctly (lines starting with `data: `).

### Thread Context Lost

The client automatically manages thread continuity. If context is lost:

1. Check that `threadId` is being captured from `RUN_STARTED` events
2. Ensure the same client instance is used across messages
3. Verify the server is receiving the `thread_id` in subsequent requests

### Event Type Mismatches

Remember that event types are UPPERCASE with underscores (`RUN_STARTED`, not `run_started`) and field names are camelCase (`threadId`, not `thread_id`).

### Import Errors

Make sure all packages are installed:

```bash
pip install agent-framework-ag-ui agent-framework-core fastapi uvicorn httpx
```

Or check your virtual environment is activated:

```bash
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```
