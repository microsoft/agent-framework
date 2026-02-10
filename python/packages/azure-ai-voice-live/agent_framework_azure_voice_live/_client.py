# Copyright (c) Microsoft. All rights reserved.

"""Azure Voice Live realtime client using the SDK."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework._realtime_client import BaseRealtimeClient
from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.voicelive.aio import connect as vl_connect
from azure.ai.voicelive.models import (
    FunctionCallOutputItem,
    InputTextContentPart,
    ServerEventType,
    UserMessageItem,
)
from azure.core.credentials import AzureKeyCredential
from pydantic import ValidationError

from ._settings import AzureVoiceLiveSettings

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential

logger = logging.getLogger(__name__)

__all__ = ["AzureVoiceLiveClient"]

# OpenAI voice names supported by Voice Live
_OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
}


class AzureVoiceLiveClient(BaseRealtimeClient):
    """Azure Voice Live API client using the SDK's native WebSocket support.

    Connects to Azure Voice Live for bidirectional audio streaming with
    Azure Speech Services and generative AI models.

    Example:
        ```python
        # With API key
        client = AzureVoiceLiveClient(
            endpoint="https://myresource.services.ai.azure.com",
            model="gpt-4o-realtime-preview",
            api_key="your-api-key",
        )

        # With Azure credential
        from azure.identity.aio import DefaultAzureCredential

        client = AzureVoiceLiveClient(
            endpoint="https://myresource.services.ai.azure.com",
            model="gpt-4o-realtime-preview",
            credential=DefaultAzureCredential(),
        )

        await client.connect(
            RealtimeSessionConfig(
                instructions="You are helpful.",
                voice="alloy",
            )
        )

        async for event in client.events():
            if event.type == "audio":
                play_audio(event.data["audio"])
        ```
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.voice_live"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        credential: TokenCredential | None = None,
        model: str | None = None,
        api_version: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Azure Voice Live client.

        Keyword Args:
            endpoint: Azure Voice Live endpoint URL (https:// or wss://).
                Can also be set via AZURE_VOICELIVE_ENDPOINT env var.
            api_key: API key for authentication (mutually exclusive with credential).
                Can also be set via AZURE_VOICELIVE_API_KEY env var.
            credential: Azure TokenCredential for Entra ID authentication.
            model: Model deployment name (e.g., gpt-4o-realtime-preview).
                Can also be set via AZURE_VOICELIVE_MODEL env var.
            api_version: API version string (default: 2025-10-01).
                Can also be set via AZURE_VOICELIVE_API_VERSION env var.
            env_file_path: Path to .env file for settings fallback.
            env_file_encoding: Encoding of .env file (default: utf-8).
            **kwargs: Additional keyword arguments passed to BaseRealtimeClient.
        """
        try:
            settings = AzureVoiceLiveSettings(
                endpoint=endpoint,
                api_key=api_key,  # type: ignore[arg-type]
                model=model,
                api_version=api_version,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as exc:
            raise ServiceInitializationError(f"Failed to validate settings: {exc}") from exc

        if not settings.endpoint:
            raise ServiceInitializationError(
                "Azure Voice Live endpoint is required. Set via 'endpoint' parameter "
                "or 'AZURE_VOICELIVE_ENDPOINT' environment variable."
            )

        if not settings.model:
            raise ServiceInitializationError(
                "Azure Voice Live model is required. Set via 'model' parameter "
                "or 'AZURE_VOICELIVE_MODEL' environment variable."
            )

        if not settings.api_key and not credential:
            raise ServiceInitializationError("Either api_key or credential must be provided for authentication.")

        super().__init__(**kwargs)

        self._endpoint = settings.endpoint
        self._model = settings.model
        self._api_key = settings.api_key.get_secret_value() if settings.api_key else None
        self._credential = credential
        self._api_version = settings.api_version or "2025-10-01"

        self._connection: Any = None
        self._connection_manager: Any = None

    async def connect(self, config: RealtimeSessionConfig) -> None:
        """Connect to Azure Voice Live using the SDK.

        Args:
            config: Session configuration.

        Raises:
            ServiceInitializationError: If connection fails.
        """
        if self._api_key:
            credential: Any = AzureKeyCredential(self._api_key)
        elif self._credential:
            credential = self._credential
        else:
            raise ServiceInitializationError("Authentication credential required")

        try:
            self._connection_manager = vl_connect(
                endpoint=self._endpoint,
                credential=credential,
                model=self._model,
            )
            self._connection = await self._connection_manager.__aenter__()

            session = self._build_request_session(config)
            await self._connection.session.update(session=session)
            self._connected = True
        except Exception as exc:
            if self._connection_manager:
                with contextlib.suppress(Exception):
                    await self._connection_manager.__aexit__(None, None, None)
                self._connection_manager = None
                self._connection = None
            raise ServiceInitializationError(f"Failed to connect to Azure Voice Live: {exc}") from exc

    async def update_session(self, config: RealtimeSessionConfig) -> None:
        """Update session configuration on an existing connection.

        Args:
            config: New session configuration.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connection:
            raise RuntimeError("Not connected. Call connect() first.")
        session = self._build_request_session(config)
        await self._connection.session.update(session=session)

    async def disconnect(self) -> None:
        """Disconnect from Azure Voice Live API."""
        if self._connection_manager:
            with contextlib.suppress(Exception):
                await self._connection_manager.__aexit__(None, None, None)
            self._connection_manager = None
            self._connection = None
        self._connected = False

    async def send_audio(self, audio: bytes) -> None:
        """Send audio data to the model.

        Args:
            audio: Raw audio bytes (PCM16, 24kHz mono recommended).

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connection:
            raise RuntimeError("Not connected. Call connect() first.")
        await self._connection.input_audio_buffer.append(audio=audio)

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        """Send tool result back to the model.

        Args:
            tool_call_id: ID of the tool call.
            result: String result of the tool execution.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connection:
            raise RuntimeError("Not connected. Call connect() first.")

        await self._connection.conversation.item.create(
            item=FunctionCallOutputItem(call_id=tool_call_id, output=result),
        )
        await self._connection.response.create()

    async def send_text(self, text: str) -> None:
        """Send text input to the model.

        Args:
            text: Text message to send.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connection:
            raise RuntimeError("Not connected. Call connect() first.")
        await self._connection.conversation.item.create(
            item=UserMessageItem(content=[InputTextContentPart(text=text)]),
        )
        await self._connection.response.create()

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        """Async iterator of normalized events from the session.

        Yields:
            RealtimeEvent objects translated from SDK server events.
        """
        if not self._connection:
            return

        async for event in self._connection:
            normalized = self._normalize_event(event)
            if normalized:
                yield normalized

    def _build_request_session(self, config: RealtimeSessionConfig) -> Any:
        """Build a RequestSession from session configuration.

        Args:
            config: Session configuration.

        Returns:
            A RequestSession instance for the Voice Live SDK.
        """
        from azure.ai.voicelive.models import (
            AudioInputTranscriptionOptions,
            InputAudioFormat,
            Modality,
            OutputAudioFormat,
            RequestSession,
            ServerVad,
        )

        return RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            instructions=config.instructions,
            input_audio_transcription=AudioInputTranscriptionOptions(model="whisper-1"),
            voice=self._build_voice_config(config.voice),
            tools=config.tools,  # type: ignore[arg-type]
            turn_detection=config.turn_detection
            or ServerVad(  # type: ignore[arg-type]
                threshold=0.5,
                prefix_padding_ms=300,
                silence_duration_ms=500,
            ),
        )

    def _build_voice_config(self, voice: str | None) -> Any:
        """Build voice configuration for SDK.

        Voice Live supports multiple voice types:
        - OpenAI voices: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar
        - Azure Neural voices: en-US-AvaNeural, etc.

        Args:
            voice: Voice name or identifier.

        Returns:
            String for OpenAI voices, AzureStandardVoice for Azure Neural voices.
        """
        if not voice:
            return "alloy"

        if voice.lower() in _OPENAI_VOICES:
            return voice

        # Azure Neural voice format (e.g., en-US-AvaNeural)
        if "-" in voice and "Neural" in voice:
            from azure.ai.voicelive.models import AzureStandardVoice

            return AzureStandardVoice(name=voice)

        # Pass through unknown voice names
        return voice

    def _normalize_event(self, event: Any) -> RealtimeEvent | None:
        """Map SDK server event objects to RealtimeEvent.

        Args:
            event: Typed server event from SDK connection.

        Returns:
            Normalized RealtimeEvent or None if event should be ignored.
        """
        event_type = event.type

        if event_type == ServerEventType.RESPONSE_AUDIO_DELTA:
            audio_bytes = getattr(event, "delta", b"")
            if not audio_bytes:
                return None
            return RealtimeEvent(
                type="audio",
                data={"raw_type": event_type, "audio": audio_bytes},
            )

        if event_type in (ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA, ServerEventType.RESPONSE_TEXT_DELTA):
            return RealtimeEvent(
                type="transcript",
                data={"raw_type": event_type, "text": getattr(event, "delta", "")},
            )

        if event_type == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            return RealtimeEvent(
                type="tool_call",
                data={
                    "raw_type": event_type,
                    "id": getattr(event, "call_id", ""),
                    "name": getattr(event, "name", ""),
                    "arguments": getattr(event, "arguments", ""),
                },
            )

        if event_type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            return RealtimeEvent(
                type="input_transcript",
                data={"raw_type": event_type, "text": getattr(event, "transcript", "")},
            )

        if event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
            return RealtimeEvent(
                type="response_transcript",
                data={"raw_type": event_type, "text": getattr(event, "transcript", "")},
            )

        if event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            return RealtimeEvent(type="listening", data={"raw_type": event_type})

        if event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            return RealtimeEvent(type="interrupted", data={"raw_type": event_type})

        if event_type in (ServerEventType.RESPONSE_AUDIO_DONE, ServerEventType.RESPONSE_DONE):
            return RealtimeEvent(type="speaking_done", data={"raw_type": event_type})

        if event_type == ServerEventType.ERROR:
            error_data = getattr(event, "error", None)
            if error_data and hasattr(error_data, "model_dump"):
                error_value = error_data.model_dump()
            else:
                error_value = str(error_data) if error_data else "Unknown error"
            return RealtimeEvent(
                type="error",
                data={
                    "raw_type": event_type,
                    "error": error_value,
                },
            )

        if event_type in (ServerEventType.SESSION_CREATED, ServerEventType.SESSION_UPDATED):
            return RealtimeEvent(type="session_update", data={"raw_type": event_type})

        return None
