# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterator

import pytest

from agent_framework import tool
from agent_framework._realtime_agent import RealtimeAgent
from agent_framework._realtime_client import RealtimeClientProtocol
from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig
from agent_framework._threads import AgentThread


@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Weather in {location}: Sunny, 72F"


class MockRealtimeClient:
    """Mock client for testing RealtimeAgent."""

    def __init__(self, events_to_yield: list[RealtimeEvent] | None = None):
        self._connected = False
        self._events_to_yield = events_to_yield or []
        self._config: RealtimeSessionConfig | None = None
        self._sent_audio: list[bytes] = []
        self._tool_results: list[tuple[str, str]] = []
        self.additional_properties: dict = {}

    async def connect(self, config: RealtimeSessionConfig) -> None:
        self._connected = True
        self._config = config

    async def disconnect(self) -> None:
        self._connected = False

    async def send_audio(self, audio: bytes) -> None:
        self._sent_audio.append(audio)

    async def send_tool_result(self, tool_call_id: str, result: str) -> None:
        self._tool_results.append((tool_call_id, result))

    async def send_text(self, text: str) -> None:
        pass

    async def update_session(self, config: RealtimeSessionConfig) -> None:
        pass

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        for event in self._events_to_yield:
            yield event

    @property
    def is_connected(self) -> bool:
        return self._connected


def test_realtime_agent_creation():
    """Test RealtimeAgent can be created with minimal config."""
    client = MockRealtimeClient()
    agent = RealtimeAgent(realtime_client=client)
    assert agent._client is client
    assert agent.name is None
    assert agent.instructions is None


def test_realtime_agent_with_full_config():
    """Test RealtimeAgent accepts all configuration options."""
    client = MockRealtimeClient()
    agent = RealtimeAgent(
        realtime_client=client,
        name="TestAgent",
        instructions="Be helpful.",
        voice="nova",
    )
    assert agent.name == "TestAgent"
    assert agent.instructions == "Be helpful."
    assert agent.voice == "nova"


@pytest.mark.asyncio
async def test_realtime_agent_run_connects_client():
    """Test that run() connects the client."""
    client = MockRealtimeClient(events_to_yield=[RealtimeEvent(type="speaking_done", data={})])
    agent = RealtimeAgent(realtime_client=client, instructions="Test")

    async def empty_audio():
        return
        yield  # Make it an async generator

    events = []
    async for event in agent.run(audio_input=empty_audio()):
        events.append(event)

    # Client should have been connected with config
    assert client._config is not None
    assert client._config.instructions == "Test"
    # Client should be disconnected after run completes
    assert not client.is_connected


@pytest.mark.asyncio
async def test_realtime_agent_yields_events():
    """Test that run() yields events from the client."""
    expected_events = [
        RealtimeEvent(type="audio", data={"chunk": 1}),
        RealtimeEvent(type="transcript", data={"text": "Hello"}),
    ]
    client = MockRealtimeClient(events_to_yield=expected_events)
    agent = RealtimeAgent(realtime_client=client)

    async def empty_audio():
        return
        yield

    received = []
    async for event in agent.run(audio_input=empty_audio()):
        received.append(event)

    assert len(received) == 2
    assert received[0].type == "audio"
    assert received[1].type == "transcript"


@pytest.mark.asyncio
async def test_realtime_agent_executes_tools():
    """Test that RealtimeAgent executes tool calls."""
    tool_call_event = RealtimeEvent(
        type="tool_call", data={"id": "call_123", "name": "get_weather", "arguments": '{"location": "Seattle"}'}
    )
    client = MockRealtimeClient(
        events_to_yield=[
            tool_call_event,
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )

    agent = RealtimeAgent(
        realtime_client=client,
        tools=[get_weather],
    )

    async def empty_audio():
        return
        yield

    events = []
    async for event in agent.run(audio_input=empty_audio()):
        events.append(event)

    # Should have sent tool result back
    assert len(client._tool_results) == 1
    tool_call_id, result = client._tool_results[0]
    assert tool_call_id == "call_123"
    assert "Seattle" in result
    assert "Sunny" in result


@pytest.mark.asyncio
async def test_realtime_agent_unknown_tool():
    """Test that RealtimeAgent handles unknown tool calls gracefully."""
    tool_call_event = RealtimeEvent(
        type="tool_call", data={"id": "call_456", "name": "unknown_tool", "arguments": "{}"}
    )
    client = MockRealtimeClient(
        events_to_yield=[
            tool_call_event,
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )

    agent = RealtimeAgent(realtime_client=client)

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio()):
        pass

    assert len(client._tool_results) == 1
    _, result = client._tool_results[0]
    assert "Unknown tool" in result


@pytest.mark.asyncio
async def test_realtime_agent_streams_audio():
    """Test that RealtimeAgent streams audio to client."""
    import asyncio

    # Track when audio is sent
    audio_sent_event = asyncio.Event()

    class AudioTrackingClient(MockRealtimeClient):
        async def events(self) -> AsyncIterator[RealtimeEvent]:
            # Wait for audio to be sent before yielding events
            await audio_sent_event.wait()
            for event in self._events_to_yield:
                yield event

    client = AudioTrackingClient(
        events_to_yield=[
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )
    agent = RealtimeAgent(realtime_client=client)

    audio_chunks = [b"chunk1", b"chunk2", b"chunk3"]

    async def audio_generator():
        for chunk in audio_chunks:
            yield chunk
        # Signal that all audio has been sent
        audio_sent_event.set()

    async for _ in agent.run(audio_input=audio_generator()):
        pass

    # All audio chunks should have been sent
    assert client._sent_audio == audio_chunks


@pytest.mark.asyncio
async def test_realtime_agent_invalid_tool_arguments():
    """Test that RealtimeAgent handles invalid JSON in tool arguments."""
    tool_call_event = RealtimeEvent(
        type="tool_call", data={"id": "call_789", "name": "get_weather", "arguments": "invalid json"}
    )
    client = MockRealtimeClient(
        events_to_yield=[
            tool_call_event,
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )

    agent = RealtimeAgent(realtime_client=client, tools=[get_weather])

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio()):
        pass

    assert len(client._tool_results) == 1
    _, result = client._tool_results[0]
    assert "Invalid arguments" in result


@tool
def calculator(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@pytest.mark.asyncio
async def test_realtime_agent_multiple_tools():
    """Test that RealtimeAgent can handle multiple tool calls in sequence."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(
                type="tool_call", data={"id": "call_1", "name": "get_weather", "arguments": '{"location": "NYC"}'}
            ),
            RealtimeEvent(
                type="tool_call", data={"id": "call_2", "name": "calculator", "arguments": '{"a": 5, "b": 3}'}
            ),
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )

    agent = RealtimeAgent(
        realtime_client=client,
        tools=[get_weather, calculator],
    )

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio()):
        pass

    assert len(client._tool_results) == 2
    # First result should be weather
    assert "NYC" in client._tool_results[0][1]
    # Second result should be calculation
    assert "8" in client._tool_results[1][1]


@pytest.mark.asyncio
async def test_realtime_agent_tools_passed_to_config():
    """Test that tools are correctly passed to session config."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )

    agent = RealtimeAgent(
        realtime_client=client,
        tools=[get_weather],
    )

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio()):
        pass

    # Verify tools were passed in config
    assert client._config is not None
    assert client._config.tools is not None
    assert len(client._config.tools) == 1
    assert client._config.tools[0]["name"] == "get_weather"


@pytest.mark.asyncio
async def test_realtime_agent_voice_passed_to_config():
    """Test that voice setting is correctly passed to session config."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )

    agent = RealtimeAgent(
        realtime_client=client,
        voice="alloy",
    )

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio()):
        pass

    assert client._config is not None
    assert client._config.voice == "alloy"


@pytest.mark.asyncio
async def test_realtime_agent_client_protocol_compliance():
    """Test that MockRealtimeClient satisfies RealtimeClientProtocol."""
    client = MockRealtimeClient()
    # This should pass type checking - verifies protocol compliance
    assert isinstance(client, RealtimeClientProtocol)


def test_realtime_agent_extends_base_agent():
    """Test RealtimeAgent extends BaseAgent."""
    from agent_framework._agents import BaseAgent
    from agent_framework._realtime_agent import RealtimeAgent

    assert issubclass(RealtimeAgent, BaseAgent)


def test_realtime_agent_has_id():
    """Test RealtimeAgent has auto-generated id."""
    client = MockRealtimeClient()
    agent = RealtimeAgent(realtime_client=client)

    assert hasattr(agent, "id")
    assert agent.id is not None
    assert len(agent.id) > 0


def test_realtime_agent_has_description():
    """Test RealtimeAgent accepts description."""
    client = MockRealtimeClient()
    agent = RealtimeAgent(
        realtime_client=client,
        name="Test",
        description="A test agent",
    )

    assert agent.description == "A test agent"


def test_realtime_agent_serialization():
    """Test RealtimeAgent can be serialized."""
    client = MockRealtimeClient()
    agent = RealtimeAgent(
        realtime_client=client,
        name="TestAgent",
        instructions="Be helpful",
    )

    serialized = agent.to_dict()
    assert serialized["name"] == "TestAgent"
    assert "id" in serialized


def test_realtime_agent_as_tool_raises():
    """Test RealtimeAgent.as_tool() raises NotImplementedError."""
    client = MockRealtimeClient()
    agent = RealtimeAgent(
        realtime_client=client,
        name="voice-assistant",
        description="A voice assistant",
    )

    with pytest.raises(NotImplementedError) as exc_info:
        agent.as_tool()

    assert "audio streams" in str(exc_info.value)
    assert "ChatAgent" in str(exc_info.value)


def test_realtime_agent_has_provider_name():
    """Test RealtimeAgent has AGENT_PROVIDER_NAME for telemetry."""
    assert hasattr(RealtimeAgent, "AGENT_PROVIDER_NAME")
    assert RealtimeAgent.AGENT_PROVIDER_NAME == "microsoft.agent_framework"


def test_realtime_agent_exported_from_package():
    """Test RealtimeAgent is exported from main package."""
    from agent_framework import RealtimeAgent as ExportedRealtimeAgent

    assert ExportedRealtimeAgent is RealtimeAgent


@pytest.mark.asyncio
async def test_realtime_agent_stores_transcripts_in_thread():
    """Test that run() stores input and response transcripts in the thread."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(type="input_transcript", data={"text": "What is the weather?"}),
            RealtimeEvent(type="response_transcript", data={"text": "It is sunny today."}),
            RealtimeEvent(type="speaking_done", data={}),
        ]
    )
    agent = RealtimeAgent(realtime_client=client)
    thread = AgentThread()

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio(), thread=thread):
        pass

    messages = await thread.message_store.list_messages()
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].text == "What is the weather?"
    assert messages[1].role == "assistant"
    assert messages[1].text == "It is sunny today."


@pytest.mark.asyncio
async def test_realtime_agent_creates_thread_when_none_provided():
    """Test that run() creates a new thread when none is given."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(type="input_transcript", data={"text": "Hello"}),
            RealtimeEvent(type="response_transcript", data={"text": "Hi there"}),
        ]
    )
    agent = RealtimeAgent(realtime_client=client)

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio()):
        pass


@pytest.mark.asyncio
async def test_realtime_agent_skips_empty_transcripts():
    """Test that empty transcripts are not stored in the thread."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(type="input_transcript", data={"text": ""}),
            RealtimeEvent(type="input_transcript", data={"text": "Hello"}),
            RealtimeEvent(type="response_transcript", data={"text": ""}),
            RealtimeEvent(type="response_transcript", data={"text": "Hi"}),
        ]
    )
    agent = RealtimeAgent(realtime_client=client)
    thread = AgentThread()

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio(), thread=thread):
        pass

    messages = await thread.message_store.list_messages()
    assert len(messages) == 2
    assert messages[0].text == "Hello"
    assert messages[1].text == "Hi"


@pytest.mark.asyncio
async def test_realtime_agent_stores_multiple_turns():
    """Test that multiple conversation turns are stored in order."""
    client = MockRealtimeClient(
        events_to_yield=[
            RealtimeEvent(type="input_transcript", data={"text": "What time is it?"}),
            RealtimeEvent(type="response_transcript", data={"text": "It is 3 PM."}),
            RealtimeEvent(type="input_transcript", data={"text": "Thanks!"}),
            RealtimeEvent(type="response_transcript", data={"text": "You're welcome."}),
        ]
    )
    agent = RealtimeAgent(realtime_client=client)
    thread = AgentThread()

    async def empty_audio():
        return
        yield

    async for _ in agent.run(audio_input=empty_audio(), thread=thread):
        pass

    messages = await thread.message_store.list_messages()
    assert len(messages) == 4
    assert messages[0].role == "user"
    assert messages[0].text == "What time is it?"
    assert messages[1].role == "user"
    assert messages[1].text == "Thanks!"
    assert messages[2].role == "assistant"
    assert messages[2].text == "It is 3 PM."
    assert messages[3].role == "assistant"
    assert messages[3].text == "You're welcome."
