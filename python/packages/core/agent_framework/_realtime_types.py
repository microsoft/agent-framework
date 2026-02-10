# Copyright (c) Microsoft. All rights reserved.

"""Types for realtime voice agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["RealtimeEvent", "RealtimeSessionConfig"]


@dataclass
class RealtimeEvent:
    """Event emitted by a realtime client.

    Attributes:
        type: Event type - one of: "audio", "transcript", "tool_call",
              "interrupted", "error", "session_update", "listening",
              "speaking_done", "input_transcript", "response_transcript"
        data: Event-specific data payload
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealtimeSessionConfig:
    """Configuration for a realtime session.

    Attributes:
        instructions: System instructions for the agent
        voice: Provider-specific voice ID (e.g., "nova", "alloy", "shimmer")
        tools: List of tool schemas for function calling
        input_audio_format: Audio format for input (e.g., "pcm16")
        output_audio_format: Audio format for output (e.g., "pcm16")
        turn_detection: Provider-specific VAD/turn detection settings
    """

    instructions: str | None = None
    voice: str | None = None
    tools: list[dict[str, Any]] | None = None
    input_audio_format: str | None = None
    output_audio_format: str | None = None
    turn_detection: dict[str, Any] | None = None
