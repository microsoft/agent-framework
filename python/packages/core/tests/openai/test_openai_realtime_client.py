# Copyright (c) Microsoft. All rights reserved.
"""Tests for OpenAIRealtimeClient."""

from unittest.mock import AsyncMock, patch

import pytest

from agent_framework._realtime_client import BaseRealtimeClient, RealtimeClientProtocol
from agent_framework._realtime_types import RealtimeSessionConfig
from agent_framework.openai._realtime_client import OpenAIRealtimeClient
from agent_framework.openai._shared import OpenAIConfigMixin


def test_openai_realtime_client_implements_protocol():
    """Test OpenAIRealtimeClient satisfies RealtimeClientProtocol."""
    client = OpenAIRealtimeClient(model_id="gpt-4o-realtime-preview", api_key="test-key")
    assert isinstance(client, RealtimeClientProtocol)


def test_openai_realtime_client_inherits_config_mixin():
    """Test OpenAIRealtimeClient inherits from OpenAIConfigMixin."""
    assert issubclass(OpenAIRealtimeClient, OpenAIConfigMixin)
    assert issubclass(OpenAIRealtimeClient, BaseRealtimeClient)


def test_openai_realtime_client_default_model():
    """Test default model is set."""
    client = OpenAIRealtimeClient(api_key="test-key")
    assert client.model_id == "gpt-4o-realtime-preview"


def test_openai_realtime_client_custom_model():
    """Test custom model can be set."""
    client = OpenAIRealtimeClient(api_key="test-key", model_id="gpt-4o-realtime-preview-2024-12-17")
    assert client.model_id == "gpt-4o-realtime-preview-2024-12-17"


def test_openai_realtime_client_has_openai_client():
    """Test client creates an AsyncOpenAI instance via mixin."""
    client = OpenAIRealtimeClient(api_key="test-key")
    assert client.client is not None


def test_openai_realtime_client_otel_provider_name():
    """Test OpenAIRealtimeClient has OTEL_PROVIDER_NAME."""
    assert OpenAIRealtimeClient.OTEL_PROVIDER_NAME == "openai"


def test_openai_realtime_client_has_additional_properties():
    """Test OpenAIRealtimeClient has additional_properties."""
    client = OpenAIRealtimeClient(api_key="test-key")
    assert hasattr(client, "additional_properties")
    assert isinstance(client.additional_properties, dict)


def test_openai_realtime_client_requires_api_key():
    """Test client requires api_key when no client provided."""
    from agent_framework.exceptions import ServiceInitializationError

    with pytest.raises(ServiceInitializationError):
        OpenAIRealtimeClient(model_id="gpt-4o-realtime-preview")


def test_openai_realtime_client_accepts_existing_client():
    """Test client accepts a pre-built AsyncOpenAI instance."""
    from openai import AsyncOpenAI

    existing_client = AsyncOpenAI(api_key="test-key")
    client = OpenAIRealtimeClient(model_id="gpt-4o-realtime-preview", client=existing_client)
    assert client.client is existing_client


def test_openai_realtime_client_settings_fallback(monkeypatch):
    """Test client falls back to OpenAISettings env vars."""
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    client = OpenAIRealtimeClient(model_id="gpt-4o-realtime-preview")
    assert client.client is not None


@pytest.mark.asyncio
async def test_openai_realtime_client_connect():
    """Test connect uses SDK realtime.connect()."""
    client = OpenAIRealtimeClient(api_key="test-key")

    mock_connection = AsyncMock()
    mock_connection_manager = AsyncMock()
    mock_connection_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection_manager.__aexit__ = AsyncMock(return_value=False)

    with patch.object(client.client.realtime, "connect", return_value=mock_connection_manager) as mock_connect:
        config = RealtimeSessionConfig(instructions="Be helpful", voice="nova")
        await client.connect(config)

        mock_connect.assert_called_once_with(model="gpt-4o-realtime-preview")
        mock_connection.session.update.assert_called_once()


@pytest.mark.asyncio
async def test_openai_realtime_client_disconnect():
    """Test disconnect closes SDK connection."""
    client = OpenAIRealtimeClient(api_key="test-key")

    mock_connection = AsyncMock()
    client._connection = mock_connection
    mock_connection_manager = AsyncMock()
    mock_connection_manager.__aexit__ = AsyncMock(return_value=False)
    client._connection_manager = mock_connection_manager
    client._connected = True

    await client.disconnect()

    mock_connection_manager.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_openai_realtime_client_send_audio():
    """Test send_audio sends base64-encoded audio via SDK."""
    client = OpenAIRealtimeClient(api_key="test-key")

    mock_connection = AsyncMock()
    client._connection = mock_connection
    client._connected = True

    await client.send_audio(b"\x00\x01\x02\x03")

    mock_connection.send.assert_called_once()
    call_args = mock_connection.send.call_args
    event = call_args[0][0]
    assert event["type"] == "input_audio_buffer.append"
    assert "audio" in event


@pytest.mark.asyncio
async def test_openai_realtime_client_send_tool_result():
    """Test send_tool_result sends function output via SDK."""
    client = OpenAIRealtimeClient(api_key="test-key")

    mock_connection = AsyncMock()
    client._connection = mock_connection
    client._connected = True

    await client.send_tool_result("call-123", "sunny, 72F")

    # Should send conversation.item.create then response.create
    assert mock_connection.send.call_count == 2


@pytest.mark.asyncio
async def test_openai_realtime_client_send_text():
    """Test send_text sends text input via SDK."""
    client = OpenAIRealtimeClient(api_key="test-key")

    mock_connection = AsyncMock()
    client._connection = mock_connection
    client._connected = True

    await client.send_text("Hello there")

    assert mock_connection.send.call_count == 2


async def test_openai_realtime_update_session_not_connected():
    """Test update_session raises RuntimeError when not connected."""
    client = OpenAIRealtimeClient(api_key="test-key")
    config = RealtimeSessionConfig(instructions="Updated instructions.")

    with pytest.raises(RuntimeError, match="Not connected"):
        await client.update_session(config)


async def test_openai_realtime_update_session_sends_update():
    """Test update_session calls connection.session.update with GA-format config."""
    from unittest.mock import MagicMock

    mock_sdk_client = MagicMock()
    mock_connection_manager = MagicMock()
    mock_connection = AsyncMock()

    mock_connection_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection_manager.__aexit__ = AsyncMock()
    mock_sdk_client.realtime.connect.return_value = mock_connection_manager

    client = OpenAIRealtimeClient(api_key="test-key", client=mock_sdk_client)

    # Connect first
    connect_config = RealtimeSessionConfig(instructions="Initial.", voice="nova")
    await client.connect(connect_config)

    # Reset mock to isolate update_session call
    mock_connection.session.update.reset_mock()

    # Update session with new config
    update_config = RealtimeSessionConfig(instructions="Updated instructions.", voice="alloy")
    await client.update_session(update_config)

    mock_connection.session.update.assert_called_once()
    call_kwargs = mock_connection.session.update.call_args.kwargs
    session = call_kwargs["session"]
    # Verify GA API format
    assert session["type"] == "realtime"
    assert session["output_modalities"] == ["audio"]
    assert "audio" in session
    assert "input" in session["audio"]
    assert "output" in session["audio"]
    assert session["audio"]["output"]["voice"] == "alloy"
    assert session["instructions"] == "Updated instructions."


def test_openai_build_session_config_minimal():
    """Test OpenAI _build_session_config produces GA format with minimal config."""
    client = OpenAIRealtimeClient(api_key="test-key")
    config = RealtimeSessionConfig()
    result = client._build_session_config(config)

    assert result["type"] == "realtime"
    assert result["output_modalities"] == ["audio"]
    assert result["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert result["audio"]["input"]["transcription"] == {"model": "whisper-1"}
    assert result["audio"]["input"]["turn_detection"] == {"type": "server_vad"}
    assert result["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert "voice" not in result["audio"]["output"]
    assert "instructions" not in result
    assert "tools" not in result


def test_openai_build_session_config_full():
    """Test OpenAI _build_session_config produces GA format with all fields."""
    client = OpenAIRealtimeClient(api_key="test-key")
    tools = [{"type": "function", "name": "get_weather", "description": "Get weather"}]
    turn_detection = {"type": "server_vad", "threshold": 0.5}
    config = RealtimeSessionConfig(
        instructions="Be helpful",
        voice="nova",
        tools=tools,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        turn_detection=turn_detection,
    )
    result = client._build_session_config(config)

    assert result["type"] == "realtime"
    assert result["output_modalities"] == ["audio"]
    assert result["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert result["audio"]["input"]["transcription"] == {"model": "whisper-1"}
    assert result["audio"]["input"]["turn_detection"] == turn_detection
    assert result["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert result["audio"]["output"]["voice"] == "nova"
    assert result["instructions"] == "Be helpful"
    assert result["tools"] == tools
