# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework._realtime_client import BaseRealtimeClient
from agent_framework._realtime_types import RealtimeSessionConfig
from agent_framework.exceptions import ServiceInitializationError
from pydantic import ValidationError

from agent_framework_azure_voice_live import AzureVoiceLiveClient


def _make_client():
    return AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )


def _mock_event(event_type: str, **attrs):
    event = MagicMock()
    event.type = event_type
    for k, v in attrs.items():
        setattr(event, k, v)
    return event


def test_inherits_base_realtime_client():
    """AzureVoiceLiveClient inherits from BaseRealtimeClient."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    assert isinstance(client, BaseRealtimeClient)


def test_requires_endpoint():
    """Raises ServiceInitializationError when endpoint is missing."""
    with pytest.raises(ServiceInitializationError, match="endpoint"):
        AzureVoiceLiveClient(
            model="gpt-4o-realtime-preview",
            api_key="test-key",
        )


def test_requires_model():
    """Raises ServiceInitializationError when model is missing."""
    with pytest.raises(ServiceInitializationError, match="model"):
        AzureVoiceLiveClient(
            endpoint="https://test.services.ai.azure.com",
            api_key="test-key",
        )


def test_requires_auth():
    """Raises ServiceInitializationError when neither api_key nor credential provided."""
    with pytest.raises(ServiceInitializationError, match="api_key or credential"):
        AzureVoiceLiveClient(
            endpoint="https://test.services.ai.azure.com",
            model="gpt-4o-realtime-preview",
        )


def test_settings_validation_error():
    """Raises ServiceInitializationError when settings validation fails."""
    with (
        patch(
            "agent_framework_azure_voice_live._client.AzureVoiceLiveSettings",
            side_effect=ValidationError.from_exception_data(
                title="AzureVoiceLiveSettings",
                line_errors=[],
            ),
        ),
        pytest.raises(ServiceInitializationError, match="Failed to validate settings"),
    ):
        AzureVoiceLiveClient(
            endpoint="https://test.services.ai.azure.com",
            model="gpt-4o-realtime-preview",
            api_key="test-key",
        )


def test_accepts_api_key():
    """Client stores api_key."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    assert client._api_key == "test-key"
    assert client._credential is None


def test_accepts_credential():
    """Client stores credential."""
    mock_cred = MagicMock()
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        credential=mock_cred,
    )
    assert client._api_key is None
    assert client._credential is mock_cred


def test_default_api_version():
    """Default API version is 2025-10-01."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    assert client._api_version == "2025-10-01"


def test_custom_api_version():
    """Custom API version is stored."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
        api_version="2026-01-01",
    )
    assert client._api_version == "2026-01-01"


def test_settings_from_env(monkeypatch):
    """Constructor uses env vars via AzureVoiceLiveSettings."""
    monkeypatch.setenv("AZURE_VOICELIVE_ENDPOINT", "https://env.services.ai.azure.com")
    monkeypatch.setenv("AZURE_VOICELIVE_MODEL", "gpt-4o-realtime-env")
    monkeypatch.setenv("AZURE_VOICELIVE_API_KEY", "env-key")

    client = AzureVoiceLiveClient()
    assert client._endpoint == "https://env.services.ai.azure.com"
    assert client._model == "gpt-4o-realtime-env"
    assert client._api_key == "env-key"


def test_otel_provider_name():
    """OTEL_PROVIDER_NAME is set correctly."""
    assert AzureVoiceLiveClient.OTEL_PROVIDER_NAME == "azure.ai.voice_live"


def test_build_voice_config_openai():
    """OpenAI voices return string directly."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    assert client._build_voice_config("alloy") == "alloy"
    assert client._build_voice_config("shimmer") == "shimmer"
    assert client._build_voice_config("coral") == "coral"


def test_build_voice_config_azure_neural():
    """Azure Neural voices return AzureStandardVoice object."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    with patch("azure.ai.voicelive.models.AzureStandardVoice") as MockVoice:
        MockVoice.return_value = "mock-azure-voice"
        result = client._build_voice_config("en-US-AvaNeural")
        MockVoice.assert_called_once_with(name="en-US-AvaNeural")
        assert result == "mock-azure-voice"


def test_build_voice_config_default():
    """None voice returns 'alloy' default."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    assert client._build_voice_config(None) == "alloy"


def test_build_voice_config_unknown_passthrough():
    """Unknown voice names are passed through."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        api_key="test-key",
    )
    assert client._build_voice_config("custom-voice") == "custom-voice"


def test_normalize_audio_event():
    """Audio delta event is normalized."""
    client = _make_client()
    audio_data = b"test-audio"
    event = _mock_event(
        "response.audio.delta",
        delta=audio_data,
    )
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "audio"
    assert result.data["audio"] == audio_data


def test_normalize_audio_event_empty_delta():
    """Empty audio delta returns None."""
    client = _make_client()
    event = _mock_event("response.audio.delta", delta=b"")
    result = client._normalize_event(event)
    assert result is None


def test_normalize_transcript_event():
    """Transcript delta event is normalized."""
    client = _make_client()
    event = _mock_event("response.audio_transcript.delta", delta="Hello world")
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "transcript"
    assert result.data["text"] == "Hello world"


def test_normalize_text_delta_event():
    """Text delta event is normalized as transcript."""
    client = _make_client()
    event = _mock_event("response.text.delta", delta="Some text")
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "transcript"
    assert result.data["text"] == "Some text"


def test_normalize_tool_call_event():
    """Tool call event is normalized."""
    client = _make_client()
    event = _mock_event(
        "response.function_call_arguments.done",
        call_id="call_123",
        name="get_weather",
        arguments='{"location": "Seattle"}',
    )
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "tool_call"
    assert result.data["id"] == "call_123"
    assert result.data["name"] == "get_weather"
    assert result.data["arguments"] == '{"location": "Seattle"}'


def test_normalize_input_audio_transcription_completed():
    """Input audio transcription completed maps to input_transcript."""
    client = _make_client()
    event = _mock_event(
        "conversation.item.input_audio_transcription.completed",
        transcript="Hello, how are you?",
    )
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "input_transcript"
    assert result.data["text"] == "Hello, how are you?"


def test_normalize_response_audio_transcript_done():
    """Response audio transcript done maps to response_transcript."""
    client = _make_client()
    event = _mock_event(
        "response.audio_transcript.done",
        transcript="I'm doing well, thanks!",
    )
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "response_transcript"
    assert result.data["text"] == "I'm doing well, thanks!"


def test_normalize_speech_started():
    """Speech started maps to listening."""
    client = _make_client()
    event = _mock_event("input_audio_buffer.speech_started")
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "listening"


def test_normalize_speech_stopped():
    """Speech stopped maps to interrupted."""
    client = _make_client()
    event = _mock_event("input_audio_buffer.speech_stopped")
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "interrupted"


def test_normalize_response_done():
    """Response done maps to speaking_done."""
    client = _make_client()
    event = _mock_event("response.done")
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "speaking_done"


def test_normalize_audio_done():
    """Audio done maps to speaking_done."""
    client = _make_client()
    event = _mock_event("response.audio.done")
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "speaking_done"


def test_normalize_error_event():
    """Error event is normalized."""
    client = _make_client()
    mock_error = MagicMock()
    mock_error.model_dump.return_value = {"message": "Something went wrong"}
    event = _mock_event("error", error=mock_error)
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "error"
    assert result.data["error"] == {"message": "Something went wrong"}


def test_normalize_error_event_without_model_dump():
    """Error event with plain string error_data (no model_dump) is normalized."""
    client = _make_client()
    error_obj = "Something went wrong"
    event = _mock_event("error", error=error_obj)
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "error"
    assert result.data["error"] == "Something went wrong"


def test_normalize_error_event_with_none_error():
    """Error event with None error_data returns 'Unknown error'."""
    client = _make_client()
    event = _mock_event("error", error=None)
    result = client._normalize_event(event)
    assert result is not None
    assert result.type == "error"
    assert result.data["error"] == "Unknown error"


def test_normalize_session_events():
    """Session created/updated map to session_update."""
    client = _make_client()
    for event_type in ("session.created", "session.updated"):
        event = _mock_event(event_type)
        result = client._normalize_event(event)
        assert result is not None
        assert result.type == "session_update"


def test_normalize_unknown_event():
    """Unknown event returns None."""
    client = _make_client()
    event = _mock_event("unknown.event.type")
    result = client._normalize_event(event)
    assert result is None


@pytest.mark.asyncio
async def test_connect_uses_sdk():
    """Connect calls SDK connect() with correct args."""
    client = _make_client()

    mock_connection = AsyncMock()
    mock_connection.session = MagicMock()
    mock_connection.session.update = AsyncMock()

    mock_manager = AsyncMock()
    mock_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_manager.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("agent_framework_azure_voice_live._client.vl_connect", return_value=mock_manager) as mock_connect,
        patch("agent_framework_azure_voice_live._client.AzureKeyCredential") as MockCred,
    ):
        MockCred.return_value = "mock-credential"

        assert not client.is_connected
        config = RealtimeSessionConfig(instructions="Be helpful", voice="alloy")
        await client.connect(config)

        mock_connect.assert_called_once_with(
            endpoint="https://test.services.ai.azure.com",
            credential="mock-credential",
            model="gpt-4o-realtime-preview",
            api_version="2025-10-01",
        )
        mock_connection.session.update.assert_called_once()
        assert client.is_connected

    await client.disconnect()


@pytest.mark.asyncio
async def test_connect_with_credential():
    """Connect uses credential directly when api_key is not set."""
    mock_cred = MagicMock()
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        model="gpt-4o-realtime-preview",
        credential=mock_cred,
    )

    mock_connection = AsyncMock()
    mock_connection.session = MagicMock()
    mock_connection.session.update = AsyncMock()

    mock_manager = AsyncMock()
    mock_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_manager.__aexit__ = AsyncMock(return_value=False)

    with patch("agent_framework_azure_voice_live._client.vl_connect", return_value=mock_manager) as mock_connect:
        await client.connect(RealtimeSessionConfig(instructions="Be helpful"))

        mock_connect.assert_called_once_with(
            endpoint="https://test.services.ai.azure.com",
            credential=mock_cred,
            model="gpt-4o-realtime-preview",
            api_version="2025-10-01",
        )
        assert client.is_connected

    await client.disconnect()


@pytest.mark.asyncio
async def test_connect_passes_custom_api_version():
    """Connect forwards a custom api_version to the Voice Live SDK."""
    client = AzureVoiceLiveClient(
        endpoint="https://test.services.ai.azure.com",
        api_key="test-key",
        model="gpt-4o-realtime-preview",
        api_version="2026-01-15",
    )

    mock_connection = AsyncMock()
    mock_connection.session = MagicMock()
    mock_connection.session.update = AsyncMock()

    mock_manager = AsyncMock()
    mock_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_manager.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("agent_framework_azure_voice_live._client.vl_connect", return_value=mock_manager) as mock_connect,
        patch("agent_framework_azure_voice_live._client.AzureKeyCredential") as MockCred,
    ):
        MockCred.return_value = "mock-credential"
        await client.connect(RealtimeSessionConfig(instructions="Be helpful"))

        mock_connect.assert_called_once_with(
            endpoint="https://test.services.ai.azure.com",
            credential="mock-credential",
            model="gpt-4o-realtime-preview",
            api_version="2026-01-15",
        )

    await client.disconnect()


@pytest.mark.asyncio
async def test_connect_no_auth_raises():
    """Connect raises ServiceInitializationError when no credential is available."""
    client = _make_client()
    client._api_key = None
    client._credential = None

    with pytest.raises(ServiceInitializationError, match="Authentication credential required"):
        await client.connect(RealtimeSessionConfig())


@pytest.mark.asyncio
async def test_connect_failure_cleans_up():
    """Connect cleans up and raises ServiceInitializationError on failure."""
    client = _make_client()

    mock_manager = AsyncMock()
    mock_manager.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
    mock_manager.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("agent_framework_azure_voice_live._client.vl_connect", return_value=mock_manager),
        patch("agent_framework_azure_voice_live._client.AzureKeyCredential") as MockCred,
    ):
        MockCred.return_value = "mock-credential"

        with pytest.raises(ServiceInitializationError, match="Failed to connect to Azure Voice Live"):
            await client.connect(RealtimeSessionConfig())

        # Verify cleanup happened
        assert not client.is_connected
        assert client._connection is None
        assert client._connection_manager is None


@pytest.mark.asyncio
async def test_disconnect():
    """Disconnect cleans up connection manager and updates state."""
    client = _make_client()

    mock_manager = AsyncMock()
    mock_manager.__aexit__ = AsyncMock(return_value=False)
    client._connection_manager = mock_manager
    client._connection = AsyncMock()
    client._connected = True

    await client.disconnect()

    assert client._connection is None
    assert client._connection_manager is None
    assert not client.is_connected
    mock_manager.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_send_audio():
    """send_audio calls connection.input_audio_buffer.append."""
    client = _make_client()
    mock_connection = AsyncMock()
    mock_connection.input_audio_buffer = MagicMock()
    mock_connection.input_audio_buffer.append = AsyncMock()
    client._connection = mock_connection

    await client.send_audio(b"test-audio-data")

    mock_connection.input_audio_buffer.append.assert_called_once()


@pytest.mark.asyncio
async def test_send_audio_not_connected():
    """send_audio raises RuntimeError when not connected."""
    client = _make_client()
    client._connection = None

    with pytest.raises(RuntimeError, match="Not connected. Call connect\\(\\) first."):
        await client.send_audio(b"test-audio-data")


@pytest.mark.asyncio
async def test_send_text():
    """send_text creates conversation item and triggers response."""
    client = _make_client()
    mock_connection = AsyncMock()
    mock_connection.conversation = MagicMock()
    mock_connection.conversation.item = MagicMock()
    mock_connection.conversation.item.create = AsyncMock()
    mock_connection.response = MagicMock()
    mock_connection.response.create = AsyncMock()
    client._connection = mock_connection

    await client.send_text("Hello")

    mock_connection.conversation.item.create.assert_called_once()
    mock_connection.response.create.assert_called_once()


@pytest.mark.asyncio
async def test_send_text_not_connected():
    """send_text raises RuntimeError when not connected."""
    client = _make_client()
    client._connection = None

    with pytest.raises(RuntimeError, match="Not connected. Call connect\\(\\) first."):
        await client.send_text("Hello")


@pytest.mark.asyncio
async def test_send_tool_result():
    """send_tool_result creates function output item and triggers response."""
    client = _make_client()
    mock_connection = AsyncMock()
    mock_connection.conversation = MagicMock()
    mock_connection.conversation.item = MagicMock()
    mock_connection.conversation.item.create = AsyncMock()
    mock_connection.response = MagicMock()
    mock_connection.response.create = AsyncMock()
    client._connection = mock_connection

    await client.send_tool_result("call_123", "Result value")

    mock_connection.conversation.item.create.assert_called_once()
    mock_connection.response.create.assert_called_once()


@pytest.mark.asyncio
async def test_send_tool_result_not_connected():
    """send_tool_result raises RuntimeError when not connected."""
    client = _make_client()
    client._connection = None

    with pytest.raises(RuntimeError, match="Not connected. Call connect\\(\\) first."):
        await client.send_tool_result("call_123", "Result value")


@pytest.mark.asyncio
async def test_events_yields_normalized():
    """events() yields normalized events from SDK connection."""
    client = _make_client()

    audio_data = b"test-audio"
    mock_event = MagicMock()
    mock_event.type = "response.audio.delta"
    mock_event.delta = audio_data

    # Create an async iterator that yields the mock event
    async def mock_aiter():
        yield mock_event

    mock_connection = MagicMock()
    mock_connection.__aiter__ = lambda self: mock_aiter()
    client._connection = mock_connection

    events = []
    async for event in client.events():
        events.append(event)

    assert len(events) == 1
    assert events[0].type == "audio"
    assert events[0].data["audio"] == audio_data


@pytest.mark.asyncio
async def test_events_no_connection():
    """events() returns immediately when not connected."""
    client = _make_client()
    client._connection = None

    events = []
    async for event in client.events():
        events.append(event)

    assert len(events) == 0


async def test_update_session_not_connected():
    """update_session raises RuntimeError when not connected."""
    client = _make_client()
    client._connection = None

    with pytest.raises(RuntimeError, match="Not connected. Call connect\\(\\) first."):
        await client.update_session(RealtimeSessionConfig(instructions="Updated"))


async def test_update_session_sends_update():
    """update_session calls connection.session.update with a RequestSession."""
    client = _make_client()
    mock_connection = AsyncMock()
    mock_connection.session = MagicMock()
    mock_connection.session.update = AsyncMock()
    client._connection = mock_connection
    client._connected = True

    config = RealtimeSessionConfig(instructions="Updated instructions", voice="coral")
    await client.update_session(config)

    mock_connection.session.update.assert_called_once()
    call_kwargs = mock_connection.session.update.call_args
    assert "session" in call_kwargs.kwargs
