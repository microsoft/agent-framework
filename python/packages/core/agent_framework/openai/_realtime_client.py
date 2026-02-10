# Copyright (c) Microsoft. All rights reserved.
"""OpenAI Realtime API client using the SDK's native realtime support."""

from __future__ import annotations

import base64
import binascii
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, cast

from agent_framework._realtime_client import BaseRealtimeClient
from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig
from agent_framework.exceptions import ServiceInitializationError

from ._shared import OpenAIConfigMixin, OpenAISettings

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from openai.resources.realtime.realtime import AsyncRealtimeConnection, AsyncRealtimeConnectionManager

logger = logging.getLogger(__name__)

__all__ = ["OpenAIRealtimeClient"]


class OpenAIRealtimeClient(OpenAIConfigMixin, BaseRealtimeClient):
    """OpenAI Realtime API client using the SDK's native WebSocket support.

    Connects to OpenAI's realtime API for bidirectional audio streaming
    with GPT-4o realtime models. Uses the OpenAI SDK's built-in
    ``client.realtime.connect()`` for transport and authentication.

    Example:
        ```python
        client = OpenAIRealtimeClient(api_key="sk-...")
        await client.connect(
            RealtimeSessionConfig(
                instructions="You are helpful.",
                voice="nova",
            )
        )

        async for event in client.events():
            if event.type == "audio":
                play_audio(event.data["audio"])
        ```
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "openai"

    def __init__(
        self,
        *,
        model_id: str | None = None,
        api_key: str | Callable[[], str | Awaitable[str]] | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        base_url: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize OpenAI Realtime client.

        Keyword Args:
            model_id: Model ID for realtime conversations (default: gpt-4o-realtime-preview).
                Can also be set via OPENAI_CHAT_MODEL_ID environment variable.
            api_key: OpenAI API key. Can also be set via OPENAI_API_KEY env var.
            org_id: OpenAI organization ID.
            default_headers: Default headers for HTTP requests.
            client: An existing AsyncOpenAI client instance.
            base_url: Override base URL for the API.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional keyword arguments.
        """
        from pydantic import ValidationError

        try:
            openai_settings = OpenAISettings(
                api_key=api_key,  # type: ignore[reportArgumentType]
                base_url=base_url,
                org_id=org_id,
                chat_model_id=model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not client and not openai_settings.api_key:
            raise ServiceInitializationError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )

        resolved_model = openai_settings.chat_model_id or "gpt-4o-realtime-preview"

        super().__init__(
            model_id=resolved_model,
            api_key=self._get_api_key(openai_settings.api_key),
            base_url=openai_settings.base_url if openai_settings.base_url else None,
            org_id=openai_settings.org_id,
            default_headers=default_headers,
            client=client,
            **kwargs,
        )

        self._connection: AsyncRealtimeConnection | None = None
        self._connection_manager: AsyncRealtimeConnectionManager | None = None
        self._pending_function_names: dict[str, str] = {}

    def _build_session_config(self, config: RealtimeSessionConfig) -> dict[str, Any]:
        """Translate RealtimeSessionConfig to OpenAI GA API format.

        The GA realtime API requires ``type: "realtime"``, uses ``output_modalities``
        instead of ``modalities``, and nests audio settings under ``audio.input`` /
        ``audio.output``.

        Args:
            config: Session configuration dataclass.

        Returns:
            Dict conforming to ``RealtimeSessionCreateRequestParam``.
        """
        input_audio: dict[str, Any] = {
            "format": {"type": "audio/pcm", "rate": 24000},
            "transcription": {"model": "whisper-1"},
            "turn_detection": config.turn_detection or {"type": "server_vad"},
        }

        output_audio: dict[str, Any] = {
            "format": {"type": "audio/pcm", "rate": 24000},
        }
        if config.voice:
            output_audio["voice"] = config.voice

        session: dict[str, Any] = {
            "type": "realtime",
            "output_modalities": ["audio"],
            "audio": {
                "input": input_audio,
                "output": output_audio,
            },
        }
        if config.instructions:
            session["instructions"] = config.instructions
        if config.tools:
            session["tools"] = config.tools
        return session

    async def connect(self, config: RealtimeSessionConfig) -> None:
        """Connect to OpenAI Realtime API using the SDK.

        Args:
            config: Session configuration.
        """
        sdk_client = await self._ensure_client()
        # model_id is guaranteed to be str by __init__ (defaults to "gpt-4o-realtime-preview")
        self._connection_manager = sdk_client.realtime.connect(model=cast(str, self.model_id))
        self._connection = await self._connection_manager.__aenter__()

        session_config = self._build_session_config(config)
        await self._connection.session.update(session=session_config)  # type: ignore[arg-type]

    async def update_session(self, config: RealtimeSessionConfig) -> None:
        """Update session configuration on an existing connection.

        Note:
            OpenAI does not allow changing the voice once assistant audio
            is present. Set ``config.voice`` to ``None`` to leave the
            voice unchanged.

        Args:
            config: New session configuration.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connection:
            raise RuntimeError("Not connected. Call connect() first.")
        session_config = self._build_session_config(config)
        await self._connection.session.update(session=session_config)  # type: ignore[arg-type]

    async def disconnect(self) -> None:
        """Disconnect from OpenAI Realtime API."""
        if self._connection_manager:
            with contextlib.suppress(Exception):
                await self._connection_manager.__aexit__(None, None, None)
            self._connection_manager = None
            self._connection = None

    async def send_audio(self, audio: bytes) -> None:
        """Send audio data to the model.

        Args:
            audio: Raw audio bytes (PCM16, 24kHz mono recommended).
        """
        if self._connection:
            await self._connection.send({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio).decode("utf-8"),
            })

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        """Send tool result back to the model.

        Args:
            tool_call_id: ID of the tool call.
            result: String result of the tool execution.
        """
        if self._connection:
            await self._connection.send({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": tool_call_id,
                    "output": result,
                },
            })
            await self._connection.send({"type": "response.create"})

    async def send_text(self, text: str) -> None:
        """Send text input to the model.

        Args:
            text: Text message to send.
        """
        if self._connection:
            await self._connection.send({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            })
            await self._connection.send({"type": "response.create"})

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

    def _normalize_event(self, event: Any) -> RealtimeEvent | None:
        """Map SDK server event objects to RealtimeEvent.

        Args:
            event: Typed server event from the SDK connection.

        Returns:
            Normalized RealtimeEvent or None if event should be ignored.
        """
        event_type = event.type

        if event_type in ("response.output_audio.delta", "response.audio.delta"):
            try:
                audio_bytes = base64.b64decode(event.delta)
            except (ValueError, binascii.Error) as e:
                logger.warning(f"Failed to decode audio delta: {e}")
                return None
            return RealtimeEvent(
                type="audio",
                data={
                    "raw_type": event_type,
                    "audio": audio_bytes,
                },
            )
        if event_type in ("response.output_audio_transcript.delta", "response.audio_transcript.delta"):
            return RealtimeEvent(
                type="transcript",
                data={
                    "raw_type": event_type,
                    "text": getattr(event, "delta", ""),
                },
            )
        if event_type == "response.output_item.added":
            item = getattr(event, "item", None)
            if item and getattr(item, "type", "") == "function_call":
                call_id = getattr(item, "call_id", "")
                name = getattr(item, "name", "")
                if call_id and name:
                    self._pending_function_names[call_id] = name
            return None
        if event_type == "response.function_call_arguments.done":
            call_id = getattr(event, "call_id", "")
            name = self._pending_function_names.pop(call_id, "")
            return RealtimeEvent(
                type="tool_call",
                data={
                    "raw_type": event_type,
                    "id": call_id,
                    "name": name,
                    "arguments": getattr(event, "arguments", ""),
                },
            )
        if event_type == "conversation.item.input_audio_transcription.completed":
            return RealtimeEvent(
                type="input_transcript",
                data={
                    "raw_type": event_type,
                    "text": getattr(event, "transcript", "").strip(),
                },
            )
        if event_type == "input_audio_buffer.speech_started":
            return RealtimeEvent(type="listening", data={"raw_type": event_type})
        if event_type in ("response.output_audio.done", "response.audio.done"):
            return RealtimeEvent(type="speaking_done", data={"raw_type": event_type})
        if event_type == "error":
            return RealtimeEvent(
                type="error",
                data={
                    "raw_type": event_type,
                    "error": event.error.model_dump() if hasattr(event.error, "model_dump") else str(event.error),
                },
            )
        if event_type == "response.done":
            response = getattr(event, "response", None)
            if response and getattr(response, "status", None) == "failed":
                details = getattr(response, "status_details", None)
                error = getattr(details, "error", None) if details else None
                error_data = error.model_dump() if error and hasattr(error, "model_dump") else str(error)
                return RealtimeEvent(
                    type="error",
                    data={"raw_type": event_type, "error": error_data},
                )
            return None
        if event_type == "conversation.item.input_audio_transcription.failed":
            error = getattr(event, "error", None)
            error_data = error.model_dump() if error and hasattr(error, "model_dump") else str(error)
            return RealtimeEvent(
                type="error",
                data={"raw_type": event_type, "error": error_data},
            )
        if event_type in ("session.created", "session.updated"):
            return RealtimeEvent(type="session_update", data={"raw_type": event_type})

        logger.debug(f"Unhandled realtime event type: {event_type}")
        return None
