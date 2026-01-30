# Copyright (c) Microsoft. All rights reserved.

"""Voice Live session management."""

import base64
from collections.abc import AsyncIterable
from typing import Any

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, ChatMessage, Role

from ._event_processor import EventProcessor
from ._types import AudioContent


class VoiceLiveSession:
    """Manages Azure Voice Live WebSocket session.

    This class wraps the Azure Voice Live SDK connection and provides a simplified
    interface for sending/receiving audio and handling events.
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        credential: Any,
        config: Any,
    ) -> None:
        """Initialize voice live session.

        Args:
            endpoint: Azure OpenAI endpoint URL
            model: Model deployment name (e.g., "gpt-4o-realtime-preview")
            credential: Azure credential (AzureKeyCredential or TokenCredential)
            config: RequestSession configuration object
        """
        self._endpoint = endpoint
        self._model = model
        self._credential = credential
        self._config = config
        self._connection: Any = None
        self._connection_context: Any = None
        self._event_processor = EventProcessor()
        self._response_started = False  # Track if response has been started

    async def __aenter__(self) -> "VoiceLiveSession":
        """Connect to Azure Voice Live."""
        from azure.ai.voicelive.aio import connect

        # Establish WebSocket connection - store the context manager
        self._connection_context = connect(
            endpoint=self._endpoint, credential=self._credential, model=self._model
        )
        self._connection = await self._connection_context.__aenter__()

        # Configure session
        await self._connection.session.update(session=self._config)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Disconnect from Azure Voice Live."""
        print("[DEBUG] Closing session...")
        if hasattr(self, "_connection_context") and self._connection_context:
            await self._connection_context.__aexit__(exc_type, exc_val, exc_tb)
            self._connection = None
            self._connection_context = None
        print("[DEBUG] Session closed")

    async def send_text(self, text: str) -> None:
        """Send text input to conversation.

        Args:
            text: User message text
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        from azure.ai.voicelive.models import UserMessageItem

        # Create message item using UserMessageItem
        item = UserMessageItem()
        item["content"] = [{"type": "input_text", "text": text}]
        await self._connection.conversation.item.create(item=item)

    async def send_audio(self, audio_bytes: bytes, commit: bool = True) -> None:
        """Send audio input (PCM16 bytes).

        Args:
            audio_bytes: Raw PCM16 audio bytes (24kHz, mono, 16-bit)
            commit: Whether to commit the buffer after appending (default: True)
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        # Encode to base64
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Append to buffer
        await self._connection.input_audio_buffer.append(audio=audio_b64)

        # Optionally commit buffer
        if commit:
            await self._connection.input_audio_buffer.commit()

    async def send_audio_chunk(self, audio_chunk: bytes) -> None:
        """Send a single audio chunk for streaming input.

        This appends audio to the buffer without committing, allowing for
        continuous streaming. Server VAD will automatically detect speech
        boundaries and trigger responses.

        Args:
            audio_chunk: Raw PCM16 audio chunk (24kHz, mono, 16-bit)
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        # Encode to base64
        audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")

        # Append to buffer (no commit - let VAD handle it)
        await self._connection.input_audio_buffer.append(audio=audio_b64)

    async def create_response(self) -> None:
        """Manually trigger response generation.

        This is useful when not using server-side VAD or when you want to
        control exactly when the agent responds.

        If VAD already started a response, this will be skipped.
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        # Only create response if one hasn't been started yet (by VAD or otherwise)
        if not self._response_started:
            print(f"[DEBUG] Calling response.create() manually")
            await self._connection.response.create()
        else:
            print(f"[DEBUG] Skipping response.create() - response already started")

    async def cancel_response(self) -> None:
        """Cancel ongoing response.

        This is useful for implementing interruption handling when the user
        starts speaking while the agent is responding.
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        await self._connection.response.cancel()

    async def send_function_result(self, call_id: str, output: str) -> None:
        """Send function call result back to the model.

        Args:
            call_id: Function call ID from the function_call event
            output: Function execution result (as string)
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        from azure.ai.voicelive.models import FunctionCallOutputItem

        # Create function call output item
        item = FunctionCallOutputItem(call_id=call_id, output=output)
        await self._connection.conversation.item.create(item=item)

    async def stream_response(self) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream response events as AgentRunResponseUpdate.

        Yields:
            AgentRunResponseUpdate objects for each relevant event

        Raises:
            RuntimeError: If session is not connected
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        from azure.ai.voicelive.models import ServerEventType

        async for event in self._connection:
            # Track if response has started
            if event.type == ServerEventType.RESPONSE_CREATED:
                self._response_started = True

            update = self._event_processor.process_event(event)
            if update:
                yield update

            # Stop on response done
            if event.type == ServerEventType.RESPONSE_DONE:
                self._response_started = False  # Reset for next turn
                break

    async def stream_all_events(self) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream all events continuously (not just one response).

        Unlike stream_response() which stops after one response_done,
        this continues streaming all events for the session lifetime.
        This is used for streaming conversations with multiple turns.

        Yields:
            AgentRunResponseUpdate objects for each event

        Raises:
            RuntimeError: If session is not connected
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        from azure.ai.voicelive.models import ServerEventType

        async for event in self._connection:
            # Track response state
            if event.type == ServerEventType.RESPONSE_CREATED:
                self._response_started = True
            elif event.type == ServerEventType.RESPONSE_DONE:
                self._response_started = False

            update = self._event_processor.process_event(event)
            if update:
                yield update

    async def collect_response(self) -> AgentRunResponse:
        """Collect complete response (non-streaming).

        Returns:
            AgentRunResponse with complete audio and transcript

        Raises:
            RuntimeError: If session is not connected
        """
        if not self._connection:
            raise RuntimeError("Session not connected. Use async with context manager.")

        from azure.ai.voicelive.models import ServerEventType

        audio_chunks: list[bytes] = []
        transcript = ""

        async for event in self._connection:
            event_type = event.type

            if event_type == ServerEventType.RESPONSE_AUDIO_DELTA:
                if hasattr(event, "delta") and event.delta:
                    audio_chunks.append(event.delta)

            elif event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                if hasattr(event, "delta") and event.delta:
                    transcript += event.delta

            elif event_type == ServerEventType.RESPONSE_DONE:
                # Response complete
                break

        # Build response
        audio_content = AudioContent(audio_data=b"".join(audio_chunks), transcript=transcript)

        message = ChatMessage(role=Role.ASSISTANT, contents=[audio_content])

        return AgentRunResponse(messages=[message])
