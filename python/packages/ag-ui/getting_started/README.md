# Getting Started with AG-UI (Python)

The AG-UI (Agent UI) protocol provides a standardized way for client applications to interact with AI agents over HTTP. This tutorial demonstrates how to build both server and client applications using the AG-UI protocol with Python.

## Quick Start - Client Examples

If you want to quickly try out the AG-UI client, we provide three ready-to-use examples:

### Basic Interactive Client (`client.py`)

A simple command-line chat client that demonstrates:
- Streaming responses in real-time
- Automatic thread management for conversation continuity
- Direct `AGUIChatClient` usage (caller manages message history)

**Run:**
```bash
python client.py
```

**Note:** This example sends only the current message to the server. The server is responsible for maintaining conversation history using the thread_id.

### Advanced Features Client (`client_advanced.py`)

Demonstrates advanced capabilities:
- Tool/function calling
- Both streaming and non-streaming responses
- Multi-turn conversations
- Error handling patterns

**Run:**
```bash
python client_advanced.py
```

**Note:** This example shows direct `AGUIChatClient` usage. Tool execution and conversation continuity depend on server-side configuration and capabilities.

### ChatAgent Integration (`client_with_agent.py`)

Best practice example using `ChatAgent` wrapper with **AgentThread**
- **AgentThread** maintains conversation state
- Client-side conversation history management via `thread.message_store`
- **Hybrid tool execution**: client-side + server-side tools simultaneously
- Full conversation history sent on each request
- Tool calling with conversation context

**To demonstrate hybrid tools:**

1. **Start server with server-side tool** (Terminal 1):
   ```bash
   # Server has get_time_zone tool
   python server.py
   ```

2. **Run client with client-side tool** (Terminal 2):
   ```bash
   # Client has get_weather tool
   python client_with_agent.py
   ```

All examples require a running AG-UI server (see Step 1 below for setup).

## Understanding AG-UI Architecture

### Thread Management

The AG-UI protocol supports two approaches to conversation history:

1. **Server-Managed Threads** (client.py, client_advanced.py)
   - Client sends only the current message + thread_id
   - Server maintains full conversation history
   - Requires server to support stateful thread storage
   - Lighter network payload

2. **Client-Managed History** (client_with_agent.py)
   - Client maintains full conversation history locally
   - Full message history sent with each request
   - Works with any AG-UI server (stateful or stateless)

The `ChatAgent` wrapper (used in client_with_agent.py) collects messages from local storage and sends the full history to `AGUIChatClient`, which then forwards everything to the server.

### Tool/Function Calling

The AG-UI protocol supports **hybrid tool execution** - both client-side AND server-side tools can coexist in the same conversation.

**The Hybrid Pattern** (client_with_agent.py):
```
Client defines:           Server defines:
- get_weather()          - get_current_time()
- read_sensors()         - get_server_forecast()

User: "What's the weather in SF and what time is it?"
    ↓
ChatAgent sends: full history + tool definitions for get_weather, read_sensors
    ↓
Server LLM decides: "I need get_weather('SF') and get_current_time()"
    ↓
Server executes get_current_time() → "2025-11-11 14:30:00 UTC"
Server sends function call request → get_weather('SF')
    ↓
ChatAgent intercepts get_weather call → executes locally
    ↓
Client sends result → "Sunny, 72°F"
    ↓
Server combines both results → "It's sunny and 72°F in SF, and the current time is 2:30 PM UTC"
    ↓
Client receives final response
```

**How it works:**

1. **Client-Side Tools** (`client_with_agent.py`):
   - Tools defined in ChatAgent's `tools` parameter execute locally
   - Tool metadata (name, description, schema) sent to server for planning
   - When server requests client tool → client intercepts → executes locally → sends result

2. **Server-Side Tools**:
   - Defined in server agent's configuration
   - Server executes directly without client involvement
   - Results included in server's response

3. **Hybrid Pattern (Both Together)**:
   - Server LLM sees ALL tool definitions (client + server)
   - Decides which to use based on task
   - Server tools execute server-side
   - Client tools execute client-side

**Direct AGUIChatClient Usage** (client_advanced.py):
Even without ChatAgent wrapper, client-side tools work:
- Tools passed in ChatOptions execute locally
- Server can also have its own tools
- Hybrid execution works automatically

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
pip install agent-framework-ag-ui
```

Or using uv:

```bash
uv pip install agent-framework-ag-ui
```

### Server Code

Create a file named `server.py`:

```python
# Copyright (c) Microsoft. All rights reserved.

"""AG-UI server example."""

import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI

# Read required configuration
endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
api_key = os.environ.get("AZURE_OPENAI_API_KEY")

if not endpoint:
    raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
if not deployment_name:
    raise ValueError("AZURE_OPENAI_DEPLOYMENT_NAME environment variable is required")
if not api_key:
    raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")

# Create the AI agent
agent = ChatAgent(
    name="AGUIAssistant",
    instructions="You are a helpful assistant.",
    chat_client=AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment_name,
        api_key=api_key,
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

The AG-UI client connects to the remote server and displays streaming responses. The `AGUIChatClient` is a built-in implementation that integrates with the Agent Framework's standard chat interface.

### Install Required Packages

The `AGUIChatClient` is included in the `agent-framework-ag-ui` package (already installed if you installed the server packages).

```bash
pip install agent-framework-ag-ui
```

### Client Code

Create a file named `client.py`:

```python
# Copyright (c) Microsoft. All rights reserved.

"""AG-UI client example using AGUIChatClient."""

import asyncio
import os

from agent_framework import TextContent
from agent_framework.ag_ui import AGUIChatClient


async def main():
    """Main client loop demonstrating AGUIChatClient usage."""
    # Get server URL from environment or use default
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")
    print(f"Connecting to AG-UI server at: {server_url}\n")

    # Create client with context manager for automatic cleanup
    async with AGUIChatClient(endpoint=server_url) as client:
        thread_id: str | None = None

        try:
            while True:
                # Get user input
                message = input("\nUser (:q or quit to exit): ")
                if not message.strip():
                    print("Request cannot be empty.")
                    continue

                if message.lower() in (":q", "quit"):
                    break

                # Send message and stream the response
                print("\nAssistant: ", end="", flush=True)

                # Use metadata to maintain conversation continuity
                metadata = {"thread_id": thread_id} if thread_id else None

                async for update in client.get_streaming_response(message, metadata=metadata):
                    # Extract thread ID from first update
                    if not thread_id and update.additional_properties:
                        thread_id = update.additional_properties.get("thread_id")
                        if thread_id:
                            print(f"\n[Thread: {thread_id}]")
                            print("Assistant: ", end="", flush=True)

                    # Stream text content as it arrives
                    for content in update.contents:
                        if isinstance(content, TextContent) and content.text:
                            print(content.text, end="", flush=True)

                print()  # New line after response

        except KeyboardInterrupt:
            print("\n\nExiting...")
        except Exception as e:
            print(f"\nAn error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Key Concepts

- **`AGUIChatClient`**: Built-in client that implements the Agent Framework's `BaseChatClient` interface
- **Automatic Event Handling**: The client automatically converts AG-UI events to Agent Framework types
- **Thread Management**: Pass `thread_id` in metadata to maintain conversation context across requests
- **Streaming Responses**: Use `get_streaming_response()` for real-time streaming or `get_response()` for non-streaming
- **Context Manager**: Use `async with` for automatic cleanup of HTTP connections
- **Standard Interface**: Works with all Agent Framework patterns (ChatAgent, tools, etc.)
- **Hybrid Tool Execution**: Supports both client-side and server-side tools executing together in the same conversation

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

[Thread: abc123]
Assistant: The capital of France is Paris. It is known for its rich history, culture,
and iconic landmarks such as the Eiffel Tower and the Louvre Museum.

User (:q or quit to exit): Tell me a fun fact about space
```

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
