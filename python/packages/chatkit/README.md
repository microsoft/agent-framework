# Agent Framework and ChatKit Integration

This package provides an integration layer between Microsoft Agent Framework
and [OpenAI ChatKit (Python)](https://github.com/openai/chatkit-python/).
Specifically, it mirrors the [Agent SDK integration](https://github.com/openai/chatkit-python/blob/main/docs/server.md#agents-sdk-integration), and provides the following helpers:

- `stream_agent_response`: A helper to convert a streamed `AgentResponseUpdate`
  from a Microsoft Agent Framework agent that implements `AgentProtocol` to ChatKit events.
- `ThreadItemConverter`: A extendable helper class to convert ChatKit thread items to
  `ChatMessage` objects that can be consumed by an Agent Framework agent.
- `simple_to_agent_input`: A helper function that uses the default implementation
  of `ThreadItemConverter` to convert a ChatKit thread to a list of `ChatMessage`,
  useful for getting started quickly.

## Installation

```bash
pip install agent-framework-chatkit --pre
```

This will install `agent-framework-core` and `openai-chatkit` as dependencies.

## Requirements and Limitations

### Frontend Requirements

The ChatKit integration requires the OpenAI ChatKit frontend library, which has the following requirements:

1. **Internet Connectivity Required**: The ChatKit UI is loaded from OpenAI's CDN (`cdn.platform.openai.com`). This library cannot be self-hosted or bundled locally.

2. **External Network Requests**: The ChatKit frontend makes requests to:
   - `cdn.platform.openai.com` - UI library (required)
   - `chatgpt.com/ces/v1/projects/oai/settings` - Configuration
   - `api-js.mixpanel.com` - Telemetry (metadata only, not user messages)

3. **Domain Registration for Production**: Production deployments require registering your domain at [platform.openai.com](https://platform.openai.com/settings/organization/security/domain-allowlist) and configuring a domain key.

### Air-Gapped / Regulated Environments

**The ChatKit frontend is not suitable for air-gapped or highly-regulated environments** where outbound connections to OpenAI domains are restricted.

**What IS self-hostable:**

- The backend components (`chatkit-python`, `agent-framework-chatkit`) are fully open source and have no external dependencies

**What is NOT self-hostable:**

- The frontend UI (`chatkit.js`) requires connectivity to OpenAI's CDN

For environments with network restrictions, consider building a custom frontend that consumes the ChatKit server protocol, or using alternative UI libraries like `ai-sdk`.

See [openai/chatkit-js#57](https://github.com/openai/chatkit-js/issues/57) for tracking self-hosting feature requests.

## Example Usage

Here's a minimal example showing how to integrate Agent Framework with ChatKit:

```python
from collections.abc import AsyncIterator
from typing import Any

from azure.identity import AzureCliCredential
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.chatkit import simple_to_agent_input, stream_agent_response

from chatkit.server import ChatKitServer
from chatkit.types import ThreadMetadata, UserMessageItem, ThreadStreamEvent

# You'll need to implement a Store - see the sample for a SQLiteStore implementation
from your_store import YourStore  # type: ignore[import-not-found]  # Replace with your Store implementation

# Define your agent with tools
agent = ChatAgent(
    chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
    instructions="You are a helpful assistant.",
    tools=[],  # Add your tools here
)

# Create a ChatKit server that uses your agent
class MyChatKitServer(ChatKitServer[dict[str, Any]]):
    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        if input_user_message is None:
            return

        # Load full thread history to maintain conversation context
        thread_items_page = await self.store.load_thread_items(
            thread_id=thread.id,
            after=None,
            limit=1000,
            order="asc",
            context=context,
        )

        # Convert all ChatKit messages to Agent Framework format
        agent_messages = await simple_to_agent_input(thread_items_page.data)

        # Run the agent and stream responses
        response_stream = agent.run_stream(agent_messages)

        # Convert agent responses back to ChatKit events
        async for event in stream_agent_response(response_stream, thread.id):
            yield event

# Set up FastAPI endpoint
app = FastAPI()
chatkit_server = MyChatKitServer(YourStore())  # type: ignore[misc]

@app.post("/chatkit")
async def chatkit_endpoint(request: Request):
    result = await chatkit_server.process(await request.body(), {"request": request})

    if hasattr(result, '__aiter__'):  # Streaming
        return StreamingResponse(result, media_type="text/event-stream")  # type: ignore[arg-type]
    else:  # Non-streaming
        return Response(content=result.json, media_type="application/json")  # type: ignore[union-attr]
```

For a complete end-to-end example with a full frontend, see the [weather agent sample](../../samples/demos/chatkit-integration/README.md).
