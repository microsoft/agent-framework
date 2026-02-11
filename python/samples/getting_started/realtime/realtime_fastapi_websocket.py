# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from agent_framework import BaseRealtimeClient, RealtimeAgent, tool
from agent_framework.azure import AzureOpenAIRealtimeClient, AzureVoiceLiveClient
from agent_framework.openai import OpenAIRealtimeClient
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import Field

"""
Realtime Voice Agent with FastAPI WebSocket

This sample demonstrates how to expose a realtime voice agent through a FastAPI
WebSocket endpoint, enabling web browsers and other clients to have voice
conversations with the AI.

Supported client types (set REALTIME_CLIENT_TYPE env var, default: "openai"):
- "openai"            — OpenAI Realtime API (requires OPENAI_API_KEY)
- "azure_openai"      — Azure OpenAI Realtime API (requires AZURE_OPENAI_ENDPOINT, etc.)
- "azure_voice_live"  — Azure Voice Live API (reads config from env)

Requirements:
- pip install fastapi uvicorn websockets

Run with:
    REALTIME_CLIENT_TYPE=openai uvicorn realtime_fastapi_websocket:app --reload

Then connect via WebSocket at: ws://localhost:8000/ws/voice

The sample shows:
1. Setting up a FastAPI WebSocket endpoint
2. Bridging client audio to RealtimeAgent
3. Streaming AI audio responses back to the client
4. Handling multiple concurrent sessions
"""

# ============================================================================
# Tools available to the voice agent
# ============================================================================


@tool
def get_weather(
    location: Annotated[str, Field(description="The city to get weather for")],
) -> str:
    """Get the current weather for a location."""
    # Mock implementation
    import random

    conditions = ["sunny", "cloudy", "rainy", "partly cloudy"]
    temp = random.randint(15, 30)
    return f"The weather in {location} is {conditions[random.randint(0, 3)]} with {temp}°C."


@tool
def get_time() -> str:
    """Get the current time."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return f"The current UTC time is {now.strftime('%I:%M %p')}."


# ============================================================================
# Client factory
# ============================================================================


def create_realtime_client(client_type: str) -> BaseRealtimeClient:
    """Create a realtime client based on the specified type."""
    if client_type == "openai":
        return OpenAIRealtimeClient(
            model_id="gpt-realtime"
        )
    if client_type == "azure_openai":
        return AzureOpenAIRealtimeClient(
            deployment_name="gpt-realtime",
            credential=DefaultAzureCredential()
        )
    if client_type == "azure_voice_live":
        return AzureVoiceLiveClient(
            credential=DefaultAzureCredential()
        )
    raise ValueError(f"Unknown client type: {client_type}. Valid values: openai, azure_openai, azure_voice_live")


# ============================================================================
# WebSocket Voice Session Handler
# ============================================================================


class VoiceSession:
    """Manages a single voice conversation session over WebSocket."""

    def __init__(self, websocket: WebSocket, agent: RealtimeAgent):
        self.websocket = websocket
        self.agent = agent
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._running = False

    async def audio_input_generator(self) -> AsyncIterator[bytes]:
        """Yields audio chunks received from the WebSocket client."""
        while self._running:
            try:
                audio = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                yield audio
            except asyncio.TimeoutError:
                continue

    async def handle_client_message(self, data: str) -> None:
        """Process a message received from the WebSocket client."""
        try:
            message = json.loads(data)
            msg_type = message.get("type", "")

            if msg_type == "audio":
                # Client sent audio data (base64 encoded)
                audio_b64 = message.get("audio", "")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    await self._audio_queue.put(audio_bytes)

            elif msg_type == "text":
                # Client sent text (for testing without microphone)
                # This could trigger a text-to-speech flow
                text = message.get("text", "")
                await self.send_event("info", {"message": f"Received text: {text}"})

        except json.JSONDecodeError:
            await self.send_event("error", {"message": "Invalid JSON"})

    async def send_event(self, event_type: str, data: dict) -> None:
        """Send an event to the WebSocket client."""
        await self.websocket.send_json({"type": event_type, **data})

    async def run(self) -> None:
        """Run the voice session, processing events from the RealtimeAgent."""
        self._running = True

        # Start receiving client messages in background
        receive_task = asyncio.create_task(self._receive_loop())

        try:
            # Run the agent and forward events to client
            async for event in self.agent.run(audio_input=self.audio_input_generator()):
                await self._handle_agent_event(event)

        except Exception as e:
            await self.send_event("error", {"message": str(e)})
        finally:
            self._running = False
            receive_task.cancel()
            with suppress(asyncio.CancelledError):
                await receive_task

    async def _receive_loop(self) -> None:
        """Background task to receive messages from the client."""
        try:
            while self._running:
                data = await self.websocket.receive_text()
                await self.handle_client_message(data)
        except WebSocketDisconnect:
            self._running = False
        except asyncio.CancelledError:
            pass

    async def _handle_agent_event(self, event) -> None:
        """Forward RealtimeAgent events to the WebSocket client."""
        if event.type == "audio":
            # Send audio as base64
            audio_bytes = event.data.get("audio", b"")
            if audio_bytes:
                await self.send_event("audio", {
                    "audio": base64.b64encode(audio_bytes).decode("utf-8")
                })

        elif event.type == "transcript":
            text = event.data.get("text", "")
            if text:
                await self.send_event("transcript", {"text": text})

        elif event.type == "listening":
            await self.send_event("listening", {})

        elif event.type == "speaking_done":
            await self.send_event("speaking_done", {})

        elif event.type == "tool_call":
            await self.send_event("tool_call", {
                "name": event.data.get("name", ""),
                "arguments": event.data.get("arguments", "{}"),
            })

        elif event.type == "tool_result":
            await self.send_event("tool_result", {
                "name": event.data.get("name", ""),
                "result": event.data.get("result", ""),
            })

        elif event.type == "input_transcript":
            text = event.data.get("text", "")
            if text:
                await self.send_event("input_transcript", {"text": text})

        elif event.type == "error":
            await self.send_event("error", {"details": event.data.get("error", {})})

        elif event.type == "session_update":
            await self.send_event("session_update", {
                "status": event.data.get("raw_type", "updated")
            })


# ============================================================================
# FastAPI Application
# ============================================================================


client_type = os.environ.get("REALTIME_CLIENT_TYPE", "openai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print(f"Realtime client type: {client_type}")
    print("Voice WebSocket endpoint available at: ws://localhost:8000/ws/voice")
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="Realtime Voice Agent API",
    description="WebSocket API for real-time voice conversations with AI",
    version="1.0.0",
    lifespan=lifespan,
)


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time voice conversations.

    Client Protocol:
    - Send: {"type": "audio", "audio": "<base64-encoded-pcm16>"}
    - Receive: {"type": "audio", "audio": "<base64-encoded-pcm16>"}
    - Receive: {"type": "transcript", "text": "..."}
    - Receive: {"type": "listening"}
    - Receive: {"type": "speaking_done"}
    - Receive: {"type": "tool_call", "name": "...", "arguments": "..."}
    - Receive: {"type": "error", "message": "..."}
    """
    await websocket.accept()

    # Create realtime client and agent for this session
    client = create_realtime_client(client_type)

    agent = RealtimeAgent(
        realtime_client=client,
        name="WebVoiceAssistant",
        instructions="""You are a helpful voice assistant accessible via web browser.
        Keep responses concise and conversational. You can check weather and time.""",
        voice="alloy",
        tools=[get_weather, get_time],
    )

    # Run the voice session
    session = VoiceSession(websocket, agent)

    try:
        await websocket.send_json({
            "type": "session_update",
            "status": "connecting",
        })
        await session.run()
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Session error: {e}")
        with suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        with suppress(Exception):
            await websocket.close()


# ============================================================================
# Run with: uvicorn realtime_fastapi_websocket:app --reload
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


"""
Sample Client (JavaScript):

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/voice');

// Handle incoming messages
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    switch(msg.type) {
        case 'audio':
            // Decode and play audio
            const audioData = atob(msg.audio);
            playAudio(audioData);
            break;
        case 'transcript':
            console.log('AI:', msg.text);
            break;
        case 'listening':
            console.log('Listening to you...');
            break;
        case 'speaking_done':
            console.log('AI finished speaking');
            break;
        case 'tool_call':
            console.log('Tool called:', msg.name);
            break;
        case 'error':
            console.error('Error:', msg.message);
            break;
    }
};

// Send audio from microphone
function sendAudio(pcm16Bytes) {
    const base64 = btoa(String.fromCharCode(...pcm16Bytes));
    ws.send(JSON.stringify({
        type: 'audio',
        audio: base64
    }));
}

// Capture microphone and stream
navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
        // Process audio and send via sendAudio()
        // Note: Browser audio needs to be converted to PCM16 24kHz
    });
```

Sample Output (Server):

$ REALTIME_CLIENT_TYPE=openai uvicorn realtime_fastapi_websocket:app --reload
INFO:     Uvicorn running on http://0.0.0.0:8000
Realtime client type: openai
Voice WebSocket endpoint available at: ws://localhost:8000/ws/voice
INFO:     Application startup complete.
"""
