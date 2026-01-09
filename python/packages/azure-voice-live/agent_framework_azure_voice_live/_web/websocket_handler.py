# Copyright (c) Microsoft. All rights reserved.

"""WebSocket handler for browser voice connections."""

import asyncio
import json
from typing import Any

from .._voice_live_agent import VoiceLiveAgent
from .._voice_live_session import VoiceLiveSession


class VoiceWebSocketHandler:
    """Handle browser WebSocket connections for voice chat.

    This handler bridges browser WebSocket connections to Azure Voice Live,
    enabling web-based voice interfaces.

    Example:
        ```python
        from fastapi import FastAPI, WebSocket
        from agent_framework_azure_voice_live import VoiceLiveAgent
        from agent_framework_azure_voice_live._web import VoiceWebSocketHandler

        app = FastAPI()
        agent = VoiceLiveAgent(...)
        handler = VoiceWebSocketHandler(agent)

        @app.websocket("/voice")
        async def voice_endpoint(websocket: WebSocket):
            await handler.handle_connection(websocket)
        ```
    """

    def __init__(self, agent: VoiceLiveAgent) -> None:
        """Initialize WebSocket handler.

        Args:
            agent: VoiceLiveAgent instance to handle voice conversations
        """
        self._agent = agent

    async def handle_connection(self, websocket: Any) -> None:
        """Handle WebSocket connection from browser.

        Args:
            websocket: FastAPI WebSocket instance
        """
        await websocket.accept()

        # Create session
        session = VoiceLiveSession(
            endpoint=self._agent._endpoint,
            model=self._agent._model,
            credential=self._agent._credential,
            config=self._agent._build_session_config(),
        )

        try:
            async with session:
                # Bidirectional streaming
                receive_task = asyncio.create_task(self._receive_from_browser(websocket, session))
                send_task = asyncio.create_task(self._send_to_browser(websocket, session))

                # Wait for both tasks
                await asyncio.gather(receive_task, send_task, return_exceptions=True)

        except Exception as e:
            # Send error to browser
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass  # WebSocket may already be closed

        finally:
            # Close WebSocket
            try:
                await websocket.close()
            except Exception:
                pass  # Already closed

    async def _receive_from_browser(self, websocket: Any, session: VoiceLiveSession) -> None:
        """Receive audio from browser and forward to Azure.

        Args:
            websocket: FastAPI WebSocket instance
            session: VoiceLiveSession instance
        """
        try:
            while True:
                message = await websocket.receive()

                if "bytes" in message:
                    # Browser sends PCM16 audio chunks
                    await session.send_audio(message["bytes"])

                elif "text" in message:
                    # Handle control messages
                    try:
                        data = json.loads(message["text"])
                        message_type = data.get("type")

                        if message_type == "text":
                            # Text message from user
                            await session.send_text(data.get("text", ""))
                            await session.create_response()

                        elif message_type == "cancel":
                            # Cancel ongoing response
                            await session.cancel_response()

                        elif message_type == "trigger":
                            # Manually trigger response
                            await session.create_response()

                    except json.JSONDecodeError:
                        pass  # Ignore malformed JSON

        except Exception as e:
            print(f"Error receiving from browser: {e}")

    async def _send_to_browser(self, websocket: Any, session: VoiceLiveSession) -> None:
        """Receive from Azure and forward to browser.

        Args:
            websocket: FastAPI WebSocket instance
            session: VoiceLiveSession instance
        """
        try:
            from azure.ai.voicelive.models import ServerEventType

            async for event in session._connection:
                event_type = event.type

                if event_type == ServerEventType.RESPONSE_AUDIO_DELTA:
                    # Send audio chunk to browser
                    if hasattr(event, "delta") and event.delta:
                        await websocket.send_bytes(event.delta)

                elif event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                    # Send transcript delta
                    if hasattr(event, "delta") and event.delta:
                        await websocket.send_json({"type": "transcript", "text": event.delta})

                elif event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                    # User started speaking
                    await websocket.send_json({"type": "speech_started"})

                elif event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
                    # User stopped speaking
                    await websocket.send_json({"type": "speech_stopped"})

                elif event_type == ServerEventType.RESPONSE_CREATED:
                    # Response started
                    response_id = event.response.id if hasattr(event.response, "id") else None
                    await websocket.send_json({"type": "response_started", "response_id": response_id})

                elif event_type == ServerEventType.RESPONSE_DONE:
                    # Response complete
                    await websocket.send_json({"type": "response_complete"})

                elif event_type == ServerEventType.ERROR:
                    # Error event
                    error_msg = str(event.error) if hasattr(event, "error") else "Unknown error"
                    await websocket.send_json({"type": "error", "message": error_msg})

        except Exception as e:
            print(f"Error sending to browser: {e}")
