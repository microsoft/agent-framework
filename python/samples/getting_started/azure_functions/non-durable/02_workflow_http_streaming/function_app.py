# Copyright (c) Microsoft. All rights reserved.

"""
Workflow HTTP Streaming Sample

Demonstrates running a multi-agent workflow through Azure Functions with streaming.

Components:
- Sequential workflow with Research and Writer agents
- Azure Functions HTTP trigger with streaming
- No durable orchestration required
"""

import json
from random import randint
from typing import Annotated

import azure.functions as func
from agent_framework import SequentialBuilder
from agent_framework._workflows._events import AgentRunUpdateEvent
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
    return f"Weather in {location}: {conditions[randint(0, 3)]}, {temperature}°C"


# Create workflow (reused across requests)
chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

research_agent = chat_client.create_agent(
    name="Researcher",
    instructions="Research information using tools. Be brief.",
    tools=get_weather,
)

writer_agent = chat_client.create_agent(
    name="Writer",
    instructions="Write creative content based on the research. Keep it short.",
)

_workflow = (
    SequentialBuilder()
    .participants([research_agent, writer_agent])
    .build()
)


@app.route(route="workflow/stream", methods=["POST"])
async def stream_workflow(req: Request) -> StreamingResponse:
    """Stream workflow execution in real-time.
    
    Request body: {"message": "Research Seattle weather and write about it"}
    Response: Server-Sent Events stream with workflow events
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
    
    # Stream workflow events as SSE
    async def generate():
        async for event in _workflow.run_stream(message):
            if isinstance(event, AgentRunUpdateEvent) and event.data:
                text = event.data.text
                if text:
                    yield f"data: {json.dumps({'text': text})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


"""
Expected output when you POST {"message": "Research Seattle weather and write a poem"}:

data: {"agent": "Researcher"}
data: {"text": "Let"}
data: {"text": " me"}
data: {"text": " check"}
...
data: {"agent": "Writer"}
data: {"text": "Seattle's"}
data: {"text": " sky"}
...
"""
