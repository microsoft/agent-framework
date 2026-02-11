# Copyright (c) Microsoft. All rights reserved.
"""Azure OpenAI Realtime API client using the SDK's native realtime support."""

from __future__ import annotations

import base64
import binascii
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, ClassVar

from azure.core.credentials import TokenCredential
from openai.lib.azure import AsyncAzureOpenAI
from openai.resources.realtime.realtime import AsyncRealtimeConnection, AsyncRealtimeConnectionManager
from pydantic import ValidationError

from agent_framework._realtime_client import BaseRealtimeClient
from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig
from agent_framework.exceptions import ServiceInitializationError

from ._shared import DEFAULT_AZURE_API_VERSION, AzureOpenAIConfigMixin, AzureOpenAISettings

logger = logging.getLogger(__name__)

# The general DEFAULT_AZURE_API_VERSION (2024-10-21) predates realtime API support.
# The realtime WebSocket endpoint requires a version that includes the realtime feature.
DEFAULT_AZURE_REALTIME_API_VERSION = "2024-10-01-preview"

__all__ = ["AzureOpenAIRealtimeClient"]


class AzureOpenAIRealtimeClient(AzureOpenAIConfigMixin, BaseRealtimeClient):
    """Azure OpenAI Realtime API client using the SDK's native WebSocket support.

    Connects to Azure OpenAI's realtime API for bidirectional audio streaming
    with GPT-4o realtime models. Uses the Azure OpenAI SDK's built-in
    ``client.realtime.connect()`` for transport and authentication.

    Example:
        ```python
        # Using API key
        client = AzureOpenAIRealtimeClient(
            endpoint="https://myresource.openai.azure.com",
            deployment_name="gpt-4o-realtime",
            api_key="your-api-key",
        )

        # Using Azure credential
        from azure.identity import DefaultAzureCredential

        client = AzureOpenAIRealtimeClient(
            endpoint="https://myresource.openai.azure.com",
            deployment_name="gpt-4o-realtime",
            credential=DefaultAzureCredential(),
            token_endpoint="https://cognitiveservices.azure.com/.default",
        )

        # Connect and start session
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

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: Callable[[], str | Awaitable[str]] | None = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Azure OpenAI Realtime client.

        Keyword Args:
            api_key: The API key. If provided, will override the value in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_API_KEY.
            deployment_name: The deployment name. If provided, will override the value
                (realtime_deployment_name) in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME.
            endpoint: The deployment endpoint. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_ENDPOINT.
            base_url: The deployment base URL. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_BASE_URL.
            api_version: The deployment API version. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_API_VERSION.
            ad_token: The Azure Active Directory token.
            ad_token_provider: The Azure Active Directory token provider.
            token_endpoint: The token endpoint to request an Azure token.
                Can also be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
            credential: The Azure credential for authentication.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            client: An existing AsyncAzureOpenAI client to use.
            env_file_path: Use the environment settings file as a fallback to using env vars.
            env_file_encoding: The encoding of the environment settings file, defaults to 'utf-8'.
            **kwargs: Additional keyword arguments.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureOpenAIRealtimeClient

                # Using environment variables
                # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
                # Set AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME=gpt-4o-realtime
                # Set AZURE_OPENAI_API_KEY=your-key
                client = AzureOpenAIRealtimeClient()

                # Or passing parameters directly
                client = AzureOpenAIRealtimeClient(
                    endpoint="https://your-endpoint.openai.azure.com",
                    deployment_name="gpt-4o-realtime",
                    api_key="your-key",
                )

                # Or loading from a .env file
                client = AzureOpenAIRealtimeClient(env_file_path="path/to/.env")
        """
        try:
            azure_openai_settings = AzureOpenAISettings(
                api_key=api_key,  # type: ignore[reportArgumentType]
                base_url=base_url,  # type: ignore[reportArgumentType]
                endpoint=endpoint,  # type: ignore[reportArgumentType]
                realtime_deployment_name=deployment_name,
                api_version=api_version,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
                token_endpoint=token_endpoint,
            )
        except ValidationError as exc:
            raise ServiceInitializationError(f"Failed to validate settings: {exc}") from exc

        if not azure_openai_settings.realtime_deployment_name:
            raise ServiceInitializationError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME' environment variable."
            )

        if api_version:
            resolved_api_version = api_version
        elif azure_openai_settings.api_version != DEFAULT_AZURE_API_VERSION:
            # The settings value differs from the general default, meaning the user
            # set AZURE_OPENAI_API_VERSION explicitly — respect that.
            resolved_api_version = azure_openai_settings.api_version or DEFAULT_AZURE_REALTIME_API_VERSION
        else:
            resolved_api_version = DEFAULT_AZURE_REALTIME_API_VERSION

        super().__init__(
            deployment_name=azure_openai_settings.realtime_deployment_name,
            endpoint=azure_openai_settings.endpoint,
            base_url=azure_openai_settings.base_url,
            api_version=resolved_api_version,
            api_key=azure_openai_settings.api_key.get_secret_value() if azure_openai_settings.api_key else None,
            ad_token=ad_token,
            ad_token_provider=ad_token_provider,
            token_endpoint=azure_openai_settings.token_endpoint,
            credential=credential,
            default_headers=default_headers,
            client=client,
            **kwargs,
        )

        self._connection: AsyncRealtimeConnection | None = None
        self._connection_manager: AsyncRealtimeConnectionManager | None = None
        self._pending_function_names: dict[str, str] = {}

    async def connect(self, config: RealtimeSessionConfig) -> None:
        """Connect to Azure OpenAI Realtime API using the SDK.

        Args:
            config: Session configuration.
        """
        sdk_client = await self._ensure_client()
        self._connection_manager = sdk_client.realtime.connect(model=self.deployment_name)
        self._connection = await self._connection_manager.__aenter__()

        session_config = self._build_session_config(config)
        await self._connection.session.update(session=session_config)  # type: ignore[arg-type]
        self._connected = True

    async def update_session(self, config: RealtimeSessionConfig) -> None:
        """Update session configuration on an existing connection.

        Note:
            Azure OpenAI does not allow changing the voice once assistant
            audio is present. Set ``config.voice`` to ``None`` to leave
            the voice unchanged.

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
        """Disconnect from Azure OpenAI Realtime API."""
        self._connected = False
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
