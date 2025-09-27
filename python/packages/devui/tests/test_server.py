# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for server functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui import DevServer
from agent_framework_devui.models._openai_custom import AgentFrameworkExtraBody, AgentFrameworkRequest


@pytest.fixture
def test_entities_dir():
    """Use the samples directory which has proper entity structure."""
    current_dir = Path(__file__).parent
    samples_dir = current_dir.parent / "samples"
    return str(samples_dir.resolve())


@pytest.mark.asyncio
async def test_server_health_endpoint(test_entities_dir):
    """Test /health endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    # Test entity count
    entities = await executor.discover_entities()
    assert len(entities) > 0
    # Framework name is now hardcoded since we simplified to single framework


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_server_execution_sync(test_entities_dir):
    """Test sync execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    request = AgentFrameworkRequest(
        model="agent-framework",
        input="San Francisco",
        stream=False,
        extra_body=AgentFrameworkExtraBody(entity_id=agent_id),
    )

    response = await executor.execute_sync(request)
    assert response.model == "agent-framework"
    assert len(response.output) > 0


@pytest.mark.asyncio
async def test_server_execution_streaming(test_entities_dir):
    """Test streaming execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    request = AgentFrameworkRequest(
        model="agent-framework", input="New York", stream=True, extra_body=AgentFrameworkExtraBody(entity_id=agent_id)
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
                    model="agent-framework",
                    input="test location",
                    stream=False,
                    extra_body=AgentFrameworkExtraBody(entity_id=entities[0].id),
                )

                await executor.execute_sync(request)

    asyncio.run(run_tests())
