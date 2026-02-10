# Copyright (c) Microsoft. All rights reserved.

"""Realtime client protocol and base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig
from agent_framework._tools import ToolProtocol

from ._serialization import SerializationMixin

if TYPE_CHECKING:
    from agent_framework._realtime_agent import RealtimeAgent

__all__ = ["BaseRealtimeClient", "RealtimeClientProtocol"]


@runtime_checkable
class RealtimeClientProtocol(Protocol):
    """Protocol that all realtime clients must implement.

    This defines the interface for bidirectional audio streaming with LLM providers.
    Implementations handle provider-specific WebSocket protocols.
    """

    additional_properties: dict[str, Any]

    async def connect(self, config: RealtimeSessionConfig) -> None:
        """Establish connection and initialize session."""
        ...

    async def disconnect(self) -> None:
        """Close the connection gracefully."""
        ...

    async def send_audio(self, audio: bytes) -> None:
        """Send audio data to the model."""
        ...

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        """Send the result of a tool call back to the model."""
        ...

    async def send_text(self, text: str) -> None:
        """Send text input to the model."""
        ...

    async def update_session(self, config: RealtimeSessionConfig) -> None:
        """Update session configuration on an existing connection.

        Note:
            OpenAI and Azure OpenAI do not allow changing the voice once
            assistant audio is present in the conversation. Set
            ``config.voice`` to ``None`` to leave the voice unchanged.
            Azure Voice Live supports voice changes at any time.
        """
        ...

    def events(self) -> AsyncIterator[RealtimeEvent]:
        """Async iterator of events from the session."""
        ...


class BaseRealtimeClient(SerializationMixin, ABC):
    """Abstract base class for realtime client implementations."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "unknown"
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}

    def __init__(
        self,
        *,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a BaseRealtimeClient instance.

        Keyword Args:
            additional_properties: Additional properties for the client.
            kwargs: Additional keyword arguments (merged into additional_properties).
        """
        self._connected = False
        # Merge kwargs into additional_properties
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs)

    @property
    def is_connected(self) -> bool:
        """Whether the client is currently connected."""
        return self._connected

    @abstractmethod
    async def connect(self, config: RealtimeSessionConfig) -> None:
        """Establish connection and initialize session."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection gracefully."""
        ...

    @abstractmethod
    async def send_audio(self, audio: bytes) -> None:
        """Send audio data to the model."""
        ...

    @abstractmethod
    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        """Send tool result back to the model."""
        ...

    async def send_text(self, text: str) -> None:
        """Send text input. Optional - not all providers support this."""
        raise NotImplementedError("This client does not support text input")

    @abstractmethod
    async def update_session(self, config: RealtimeSessionConfig) -> None:
        """Update session configuration on an existing connection.

        Note:
            OpenAI and Azure OpenAI do not allow changing the voice once
            assistant audio is present in the conversation. Set
            ``config.voice`` to ``None`` to leave the voice unchanged.
            Azure Voice Live supports voice changes at any time.
        """
        ...

    @abstractmethod
    def events(self) -> AsyncIterator[RealtimeEvent]:
        """Async iterator of events from the session."""
        ...

    def _build_session_config(self, config: RealtimeSessionConfig) -> dict[str, Any]:
        """Translate RealtimeSessionConfig to a dict for the provider SDK.

        Args:
            config: Session configuration dataclass.

        Returns:
            Dict suitable for passing to session.update().
        """
        session: dict[str, Any] = {
            "modalities": ["text", "audio"],
            "input_audio_format": config.input_audio_format or "pcm16",
            "output_audio_format": config.output_audio_format or "pcm16",
        }
        if config.voice:
            session["voice"] = config.voice
        if config.instructions:
            session["instructions"] = config.instructions
        if config.tools:
            session["tools"] = config.tools
        session["turn_detection"] = config.turn_detection or {"type": "server_vad"}
        session["input_audio_transcription"] = {"model": "whisper-1"}
        return session

    def as_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        tools: list[ToolProtocol] | None = None,
        voice: str | None = None,
        **kwargs: Any,
    ) -> RealtimeAgent:
        """Create a RealtimeAgent with this client.

        This is a convenience method that creates a RealtimeAgent instance
        with this realtime client already configured.

        Keyword Args:
            id: Unique identifier for the agent.
            name: Name of the agent.
            description: Description of the agent's purpose.
            instructions: System instructions for the agent.
            tools: Tools available for function calling.
            voice: Voice ID for audio responses.
            **kwargs: Additional properties.

        Returns:
            A RealtimeAgent instance configured with this client.

        Example:
            ```python
            from agent_framework.openai import OpenAIRealtimeClient

            client = OpenAIRealtimeClient(api_key="sk-...")
            agent = client.as_agent(
                name="assistant",
                instructions="You are helpful.",
                voice="nova",
            )

            async for event in agent.run(audio_input):
                ...
            ```
        """
        from agent_framework._realtime_agent import RealtimeAgent

        return RealtimeAgent(
            realtime_client=self,
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            voice=voice,
            **kwargs,
        )
