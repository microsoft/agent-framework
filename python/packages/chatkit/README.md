# Agent Framework and ChatKit Integration

This package provides an integration layer between Microsoft Agent Framework
and [OpenAI ChatKit (Python)](https://github.com/openai/chatkit-python/).
Specifically, it mirrors the [Agent SDK integration](https://github.com/openai/chatkit-python/blob/main/docs/server.md#agents-sdk-integration), and provides the following helpers:

- `stream_agent_response`: A helper to converted a streamed `AgentRunResponseUpdate`
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

        # Convert ChatKit message to Agent Framework format
        agent_messages = await simple_to_agent_input(input_user_message)

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

For a complete end-to-end example with a full frontend, see the [weather agent sample](../../samples/chatkit-integration/README.md).
