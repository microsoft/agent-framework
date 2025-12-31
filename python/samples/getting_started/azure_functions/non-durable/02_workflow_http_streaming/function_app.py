# Copyright (c) Microsoft. All rights reserved.

"""
Workflow HTTP Streaming Sample with Conversation Persistence

Demonstrates running a multi-agent workflow through Azure Functions with:
- Streaming responses
- Conversation history persistence using AgentThreads
- Session management with Azure Storage

Components:
- Sequential workflow with Research and Writer agents
- AgentExecutor with persistent AgentThread for conversation history
- Azure Functions HTTP trigger with streaming
- Azure Storage for session state persistence
"""

import json
import sys
from pathlib import Path
from random import randint
from typing import Annotated, Any

import azure.functions as func
from agent_framework import AgentThread, SequentialBuilder
from agent_framework._workflows._agent_executor import AgentExecutor
from agent_framework._workflows._events import AgentRunUpdateEvent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from azurefunctions.extensions.http.fastapi import Request, StreamingResponse
from pydantic import Field

# Add parent directory to path for session_storage import
sys.path.insert(0, str(Path(__file__).parent.parent))
from session_storage import SessionStorage

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Initialize session storage
_storage = SessionStorage()


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temperature = randint(10, 30)
    return f"Weather in {location}: {conditions[randint(0, 3)]}, {temperature}°C"


# Create chat client at module level
chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())


# Create workflow with persistent thread for conversation history
async def create_workflow_with_thread(session_id: str) -> tuple[Any, AgentThread]:
    """Create a workflow instance with a persistent thread for conversation history.
    
    The AgentThread is passed to AgentExecutors, which maintains conversation
    history across multiple workflow runs within the same session.
    
    Args:
        session_id: Session identifier for loading/saving thread state
        
    Returns:
        Tuple of (workflow, thread) where thread contains conversation history
    """
    # Load or create thread for this session
    thread_state = await _storage.load_thread(session_id)
    
    if thread_state:
        # Deserialize existing thread from storage
        thread = await AgentThread.deserialize(thread_state)
        print(f"Loaded existing thread for session {session_id}")
    else:
        # Create new thread - use any agent to get a new thread
        temp_agent = chat_client.create_agent(
            name="TempAgent",
            instructions="Temporary agent for thread creation.",
        )
        thread = temp_agent.get_new_thread()
        print(f"Created new thread for session {session_id}")
    
    # Create agents (these are stateless - thread holds the state)
    research_agent = chat_client.create_agent(
        name="Researcher",
        instructions="Research information using tools. Be brief.",
        tools=get_weather,
    )
    
    writer_agent = chat_client.create_agent(
        name="Writer",
        instructions="Write creative content based on the research. Keep it short.",
    )
    
    # Wrap agents in AgentExecutors with the shared thread
    # This allows conversation history to persist across workflow runs
    research_executor = AgentExecutor(
        research_agent,
        agent_thread=thread,
        id="researcher"
    )
    writer_executor = AgentExecutor(
        writer_agent,
        agent_thread=thread,
        id="writer"
    )
    
    # Build workflow
    workflow = (
        SequentialBuilder()
        .participants([research_executor, writer_executor])
        .build()
    )
    
    return workflow, thread


@app.route(route="workflow/stream", methods=["POST"])
async def stream_workflow(req: Request) -> StreamingResponse:
    """Stream workflow execution with conversation history persistence.
    
    Uses AgentThreads passed to AgentExecutors for true multi-turn conversations.
    The thread maintains conversation history across all HTTP requests for a session.
    
    Request body: {"message": "Research Seattle weather", "session_id": "abc123"}
    Response: Server-Sent Events stream with workflow events
    """
    # Parse request
    req_body = await req.json()
    message = req_body.get("message")
    session_id = req_body.get("session_id")
    
    if not message:
        return StreamingResponse(
            iter([json.dumps({"error": "Missing 'message' field"})]),
            media_type="application/json",
            status_code=400
        )
    
    if not session_id:
        return StreamingResponse(
            iter([json.dumps({"error": "Missing 'session_id' field for conversation history"})]),
            media_type="application/json",
            status_code=400
        )
    
    # Create/load workflow with persistent thread
    workflow, thread = await create_workflow_with_thread(session_id)
    
    # Create session metadata if new session
    if not _storage.session_exists(session_id):
        _storage.create_session(session_id, {"workflow": "ResearchWriter"})
        print(f"Created session {session_id}")
    
    # Stream workflow events as SSE
    async def generate():
        # Run workflow - the AgentThread automatically maintains conversation history
        async for event in workflow.run_stream(message=message):
            # Only stream output from the writer agent (final response)
            # Researcher agent works silently in the background
            if isinstance(event, AgentRunUpdateEvent) and event.data:
                if event.executor_id == "writer":
                    # AgentRunUpdateEvent.data is AgentRunResponseUpdate with contents
                    for content in event.data.contents:
                        if hasattr(content, 'text') and content.text:
                            yield f"data: {json.dumps({'text': content.text})}\n\n"
        
        # Save thread state after workflow completes
        # This persists the conversation history for the next request
        await _storage.save_thread(session_id, thread)
        print(f"Saved thread state for session {session_id}")
    
    return StreamingResponse(generate(), media_type="text/event-stream")


"""
Expected output when you POST {"message": "Research Seattle weather", "session_id": "abc123"}:

Note: Only the writer agent's output is streamed. The researcher agent works silently,
gathering data and calling tools, then the writer crafts the final response.

data: {"text": "Based"}
data: {"text": " on"}
data: {"text": " the"}
data: {"text": " weather"}
data: {"text": " data,"}
data: {"text": " Seattle"}
data: {"text": " is"}
data: {"text": " experiencing"}
data: {"text": " sunny"}
data: {"text": " skies..."}

On follow-up POST with same session_id, the workflow remembers previous conversation:
{"message": "Write a haiku about it", "session_id": "abc123"}

The agents will reference the weather from the previous conversation.
"""
