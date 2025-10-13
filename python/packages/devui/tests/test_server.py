# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for server functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui import DevServer
from agent_framework_devui._utils import extract_executor_message_types, select_primary_input_type
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest


class _StubExecutor:
    """Simple executor stub exposing handler metadata."""

    def __init__(self, *, input_types=None, handlers=None):
        if input_types is not None:
            self.input_types = list(input_types)
        if handlers is not None:
            self._handlers = dict(handlers)


@pytest.fixture
def test_entities_dir():
    """Use the samples directory which has proper entity structure."""
    # Get the samples directory from the main python samples folder
    current_dir = Path(__file__).parent
    # Navigate to python/samples/getting_started/devui
    samples_dir = current_dir.parent.parent.parent / "samples" / "getting_started" / "devui"
    return str(samples_dir.resolve())


async def test_server_health_endpoint(test_entities_dir):
    """Test /health endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    # Test entity count
    entities = await executor.discover_entities()
    assert len(entities) > 0
    # Framework name is now hardcoded since we simplified to single framework


@pytest.mark.skip("Skipping while we fix discovery")
async def test_server_entities_endpoint(test_entities_dir):
    """Test /v1/entities endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    assert len(entities) >= 1
    # Should find at least the weather agent
    agent_entities = [e for e in entities if e.type == "agent"]
    assert len(agent_entities) >= 1
    agent_names = [e.name for e in agent_entities]
    assert "WeatherAgent" in agent_names


async def test_server_execution_sync(test_entities_dir):
    """Test sync execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    # Use model as entity_id (new simplified routing)
    request = AgentFrameworkRequest(
        model=agent_id,  # model IS the entity_id now!
        input="San Francisco",
        stream=False,
    )

    response = await executor.execute_sync(request)
    assert response.model == agent_id  # Should echo back the model (entity_id)
    assert len(response.output) > 0


async def test_server_execution_streaming(test_entities_dir):
    """Test streaming execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    # Use model as entity_id (new simplified routing)
    request = AgentFrameworkRequest(
        model=agent_id,  # model IS the entity_id now!
        input="New York",
        stream=True,
    )

    event_count = 0
    async for _event in executor.execute_streaming(request):
        event_count += 1
        if event_count > 5:  # Limit for testing
            break

    assert event_count > 0


def test_configuration():
    """Test basic configuration."""
    server = DevServer(entities_dir="test", port=9000, host="localhost")
    assert server.port == 9000
    assert server.host == "localhost"
    assert server.entities_dir == "test"
    assert server.cors_origins == ["*"]
    assert server.ui_enabled


def test_extract_executor_message_types_prefers_input_types():
    """Input types property is used when available."""
    stub = _StubExecutor(input_types=[str, dict])

    types = extract_executor_message_types(stub)

    assert types == [str, dict]


def test_extract_executor_message_types_falls_back_to_handlers():
    """Handlers provide message metadata when input_types missing."""
    stub = _StubExecutor(handlers={str: object(), int: object()})

    types = extract_executor_message_types(stub)

    assert str in types
    assert int in types


def test_select_primary_input_type_prefers_string_and_dict():
    """Primary type selection prefers user-friendly primitives."""
    string_first = select_primary_input_type([dict[str, str], str])
    dict_first = select_primary_input_type([dict[str, str]])
    fallback = select_primary_input_type([int, float])

    assert string_first is str
    assert dict_first is dict
    assert fallback is int


if __name__ == "__main__":
    # Simple test runner
    async def run_tests():
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test agent
            agent_file = temp_path / "weather_agent.py"
            agent_file.write_text("""
class WeatherAgent:
    name = "Weather Agent"
    description = "Gets weather information"

    def run_stream(self, input_str):
        return f"Weather in {input_str} is sunny"
""")

            server = DevServer(entities_dir=str(temp_path))
            executor = await server._ensure_executor()

            entities = await executor.discover_entities()

            if entities:
                request = AgentFrameworkRequest(
                    model=entities[0].id,  # model IS the entity_id now!
                    input="test location",
                    stream=False,
                )

                await executor.execute_sync(request)

    asyncio.run(run_tests())
