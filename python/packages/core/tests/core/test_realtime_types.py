# Copyright (c) Microsoft. All rights reserved.

from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig


def test_realtime_event_creation():
    """Test RealtimeEvent can be created with required fields."""
    event = RealtimeEvent(type="audio", data={"audio": b"test"})
    assert event.type == "audio"
    assert event.data == {"audio": b"test"}


def test_realtime_event_types():
    """Test all expected event types can be created."""
    event_types = [
        "audio",
        "transcript",
        "input_transcript",
        "response_transcript",
        "tool_call",
        "tool_result",
        "interrupted",
        "error",
        "session_update",
        "listening",
        "speaking_done",
    ]
    for event_type in event_types:
        event = RealtimeEvent(type=event_type, data={})
        assert event.type == event_type


def test_realtime_session_config_defaults():
    """Test RealtimeSessionConfig has sensible defaults."""
    config = RealtimeSessionConfig()
    assert config.instructions is None
    assert config.voice is None
    assert config.tools is None
    assert config.input_audio_format is None
    assert config.output_audio_format is None
    assert config.turn_detection is None


def test_realtime_session_config_with_values():
    """Test RealtimeSessionConfig accepts all fields."""
    config = RealtimeSessionConfig(
        instructions="You are helpful.",
        voice="nova",
        tools=[{"name": "test", "description": "test tool"}],
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        turn_detection={"type": "server_vad"},
    )
    assert config.instructions == "You are helpful."
    assert config.voice == "nova"
    assert len(config.tools) == 1


def test_exports_from_main_module():
    """Test realtime types are exported from main agent_framework module."""
    from agent_framework import (
        BaseRealtimeClient,
        RealtimeAgent,
        RealtimeClientProtocol,
        RealtimeEvent,
        RealtimeSessionConfig,
    )

    # Verify the imports are the correct types
    assert RealtimeEvent is not None
    assert RealtimeSessionConfig is not None
    assert RealtimeAgent is not None
    assert RealtimeClientProtocol is not None
    assert BaseRealtimeClient is not None


def test_openai_realtime_client_export():
    """Test OpenAIRealtimeClient is exported from openai module."""
    from agent_framework.openai import OpenAIRealtimeClient

    assert OpenAIRealtimeClient is not None


def test_azure_realtime_client_export():
    """Test AzureOpenAIRealtimeClient is exported from azure module."""
    from agent_framework.azure import AzureOpenAIRealtimeClient

    assert AzureOpenAIRealtimeClient is not None
