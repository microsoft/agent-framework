# Copyright (c) Microsoft. All rights reserved.

"""Type definitions for Azure Voice Live integration."""

from typing import Any, Literal, Sequence

from agent_framework import Annotations, BaseContent
from pydantic import BaseModel, Field


class AudioContent(BaseContent):
    """Audio content with PCM16 data.

    Attributes:
        type: Content type identifier
        audio_data: Raw PCM16 audio bytes
        sample_rate: Audio sample rate in Hz
        channels: Number of audio channels
        transcript: Optional text transcription of the audio
    """

    def __init__(
        self,
        audio_data: bytes,
        *,
        sample_rate: int = 24000,
        channels: int = 1,
        transcript: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        annotations: Sequence[Annotations] | None = None,
        **kwargs: Any,
    ):
        """Initialize AudioContent.

        Args:
            audio_data: Raw PCM16 audio bytes

        Keyword Args:
            sample_rate: Audio sample rate in Hz (default: 24000)
            channels: Number of audio channels, 1=mono, 2=stereo (default: 1)
            transcript: Optional text transcription of the audio
            additional_properties: Optional additional properties
            raw_representation: Optional raw representation
            annotations: Optional annotations
            **kwargs: Any additional keyword arguments
        """
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.type: Literal["audio"] = "audio"
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.channels = channels
        self.transcript = transcript

    @property
    def duration_ms(self) -> int:
        """Calculate audio duration in milliseconds.

        Returns:
            Duration in milliseconds based on sample rate and data length
        """
        bytes_per_sample = self.channels * 2  # 2 bytes per PCM16 sample
        num_samples = len(self.audio_data) // bytes_per_sample
        return int((num_samples / self.sample_rate) * 1000)

    @property
    def duration_seconds(self) -> float:
        """Calculate audio duration in seconds.

        Returns:
            Duration in seconds
        """
        return self.duration_ms / 1000.0


class VoiceOptions(BaseModel):
    """Configuration options for VoiceLiveAgent.

    Attributes:
        voice: Azure voice name (e.g., "en-US-AvaNeural")
        temperature: Sampling temperature (0.0-1.0)
        max_response_tokens: Maximum tokens in response
        enable_vad: Enable server-side voice activity detection
        vad_threshold: VAD sensitivity (0.0-1.0, higher = less sensitive)
        vad_prefix_padding_ms: Milliseconds of audio before speech to include
        vad_silence_duration_ms: Milliseconds of silence to detect end of speech
        input_audio_transcription: Enable automatic transcription of user audio
    """

    voice: str = Field(
        default="en-US-AvaNeural",
        description="Azure voice name (e.g., 'en-US-AvaNeural', 'en-US-JennyNeural')",
    )
    temperature: float = Field(default=0.8, ge=0.0, le=1.0, description="Sampling temperature")
    max_response_tokens: int | None = Field(default=None, description="Maximum tokens in response")

    # VAD settings
    enable_vad: bool = Field(default=True, description="Enable server-side voice activity detection")
    vad_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="VAD sensitivity (0.0-1.0, higher = less sensitive)"
    )
    vad_prefix_padding_ms: int = Field(
        default=300, ge=0, description="Milliseconds of audio before speech to include"
    )
    vad_silence_duration_ms: int = Field(
        default=500, ge=0, description="Milliseconds of silence to detect end of speech"
    )

    # Transcription
    input_audio_transcription: bool = Field(
        default=True, description="Enable automatic transcription of user audio"
    )
