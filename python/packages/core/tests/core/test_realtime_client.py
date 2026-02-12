# Copyright (c) Microsoft. All rights reserved.

"""Tests for RealtimeClientProtocol."""

from collections.abc import AsyncIterator

import pytest

from agent_framework._realtime_client import RealtimeClientProtocol
from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig


class MockRealtimeClient:
    """Mock implementation for testing protocol compliance."""

    def __init__(self):
        self.additional_properties: dict = {}

    async def connect(self, config: RealtimeSessionConfig) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def send_audio(self, audio: bytes) -> None:
        pass

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        pass

    async def send_text(self, text: str) -> None:
        pass

    async def update_session(self, config: RealtimeSessionConfig) -> None:
        pass

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        yield RealtimeEvent(type="audio", data={})


async def test_update_session_in_protocol():
    """Test that update_session is callable on protocol-implementing clients."""
    client = MockRealtimeClient()
    assert isinstance(client, RealtimeClientProtocol)
    # Should be callable with a RealtimeSessionConfig
    config = RealtimeSessionConfig(instructions="Updated instructions")
    await client.update_session(config)


def test_mock_client_implements_protocol():
    """Test that MockRealtimeClient satisfies RealtimeClientProtocol."""
    client = MockRealtimeClient()
    assert isinstance(client, RealtimeClientProtocol)


@pytest.mark.asyncio
async def test_events_yields_realtime_events():
    """Test that events() yields RealtimeEvent objects."""
    client = MockRealtimeClient()
    async for event in client.events():
        assert isinstance(event, RealtimeEvent)
        break


def test_base_realtime_client_serialization():
    """Test that BaseRealtimeClient supports serialization."""
    from agent_framework._realtime_client import BaseRealtimeClient
    from agent_framework._serialization import SerializationMixin

    assert issubclass(BaseRealtimeClient, SerializationMixin)


def test_realtime_client_has_additional_properties():
    """Test that realtime clients have additional_properties."""
    from agent_framework._realtime_client import BaseRealtimeClient

    assert hasattr(BaseRealtimeClient, "DEFAULT_EXCLUDE")
    assert "additional_properties" in BaseRealtimeClient.DEFAULT_EXCLUDE


def test_realtime_client_as_agent():
    """Test BaseRealtimeClient.as_agent() creates a RealtimeAgent."""
    from agent_framework._realtime_agent import RealtimeAgent
    from agent_framework._realtime_client import BaseRealtimeClient

    class ConcreteRealtimeClient(BaseRealtimeClient):
        async def connect(self, config):
            pass

        async def disconnect(self):
            pass

        async def send_audio(self, audio):
            pass

        async def send_tool_result(self, tool_call_id, result):
            pass

        async def update_session(self, config):
            pass

        async def events(self):
            return
            yield  # Make it an async generator

    client = ConcreteRealtimeClient()
    agent = client.as_agent(
        name="test-agent",
        instructions="Be helpful",
        voice="nova",
    )

    assert isinstance(agent, RealtimeAgent)
    assert agent.name == "test-agent"
    assert agent.instructions == "Be helpful"
    assert agent.voice == "nova"


def test_build_session_config_minimal():
    """Test _build_session_config with minimal config."""
    from agent_framework._realtime_client import BaseRealtimeClient

    class ConcreteClient(BaseRealtimeClient):
        async def connect(self, config):
            pass

        async def disconnect(self):
            pass

        async def send_audio(self, audio):
            pass

        async def send_tool_result(self, tool_call_id, result):
            pass

        async def update_session(self, config):
            pass

        async def events(self):
            return
            yield

    client = ConcreteClient()
    config = RealtimeSessionConfig()
    result = client._build_session_config(config)

    assert result["input_audio_format"] == "pcm16"
    assert result["output_audio_format"] == "pcm16"
    assert result["modalities"] == ["text", "audio"]
    assert result["turn_detection"] == {"type": "server_vad"}
    assert "voice" not in result
    assert "instructions" not in result
    assert "tools" not in result


def test_build_session_config_full():
    """Test _build_session_config with all fields populated."""
    from agent_framework._realtime_client import BaseRealtimeClient

    class ConcreteClient(BaseRealtimeClient):
        async def connect(self, config):
            pass

        async def disconnect(self):
            pass

        async def send_audio(self, audio):
            pass

        async def send_tool_result(self, tool_call_id, result):
            pass

        async def update_session(self, config):
            pass

        async def events(self):
            return
            yield

    client = ConcreteClient()
    tools = [{"name": "get_weather", "description": "Get weather"}]
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

    assert result["instructions"] == "Be helpful"
    assert result["voice"] == "nova"
    assert result["tools"] == tools
    assert result["turn_detection"] == turn_detection
    assert result["input_audio_format"] == "pcm16"
    assert result["output_audio_format"] == "pcm16"
