# Copyright (c) Microsoft. All rights reserved.

"""
Agent HTTP Streaming Sample

Demonstrates exposing an agent through Azure Functions HTTP trigger with streaming responses.

Components:
- AzureOpenAIChatClient for agent creation
- Azure Functions HTTP trigger with async generator streaming
- No durable orchestration or storage required
"""

import json
from random import randint
from typing import Annotated

import azure.functions as func
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from azurefunctions.extensions.http.fastapi import Request, StreamingResponse
from pydantic import Field

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = randint(10, 30)
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {temperature}°C."


# Create the agent (reused across requests)
_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
    name="WeatherAgent",
    instructions="You are a helpful weather assistant. Be friendly and concise.",
    tools=get_weather,
)


@app.route(route="agent/stream", methods=["POST"])
async def stream_agent(req: Request) -> StreamingResponse:
    """Stream agent responses in real-time.
    
    Request body: {"message": "What's the weather in Seattle?"}
    Response: Server-Sent Events stream with text chunks
    """
    # Parse request
    req_body = await req.json()
    message = req_body.get("message")
    
    if not message:
        return StreamingResponse(
            iter([json.dumps({"error": "Missing 'message' field"})]),
            media_type="application/json",
            status_code=400
        )
    
    # Stream agent responses as SSE
    async def generate():
        async for chunk in _agent.run_stream(message):
            if chunk.text:
                yield f"data: {json.dumps({'text': chunk.text})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


"""
Expected output when you POST {"message": "What's the weather in Seattle?"}:

data: {"text": "Let"}
data: {"text": " me"}
data: {"text": " check"}
data: {"text": " the"}
data: {"text": " weather"}
...
data: {"text": "The weather in Seattle is cloudy with a high of 15°C."}
"""
