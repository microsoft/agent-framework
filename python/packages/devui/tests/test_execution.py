# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for execution flow functionality."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui._discovery import EntityDiscovery
from agent_framework_devui._executor import AgentFrameworkExecutor, EntityNotFoundError
from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import AgentFrameworkExtraBody, AgentFrameworkRequest


@pytest.fixture
def test_entities_dir():
    """Use the samples directory which has proper entity structure."""
    current_dir = Path(__file__).parent
    samples_dir = current_dir.parent / "samples"
    return str(samples_dir.resolve())


@pytest.fixture
async def executor(test_entities_dir):
    """Create configured executor."""
    discovery = EntityDiscovery(test_entities_dir)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    # Discover entities
    await executor.discover_entities()

    return executor


@pytest.mark.asyncio
async def test_executor_entity_discovery(executor):
    """Test executor entity discovery."""
    entities = await executor.discover_entities()

    # Should find entities from samples directory
    assert len(entities) > 0, "Should discover at least one entity"

    entity_types = [e.type for e in entities]
    assert "agent" in entity_types, "Should find at least one agent"
    assert "workflow" in entity_types, "Should find at least one workflow"

    # Test entity structure
    for entity in entities:
        assert entity.id, "Entity should have an ID"
        assert entity.name, "Entity should have a name"
        assert entity.type in ["agent", "workflow"], "Entity should have valid type"


@pytest.mark.asyncio
async def test_executor_get_entity_info(executor):
    """Test getting entity info by ID."""
    entities = await executor.discover_entities()
    entity_id = entities[0].id

    entity_info = executor.get_entity_info(entity_id)
    assert entity_info is not None
    assert entity_info.id == entity_id
    assert entity_info.type in ["agent", "workflow"]


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requires OpenAI API key")
@pytest.mark.asyncio
async def test_executor_sync_execution(executor):
    """Test synchronous execution."""
    entities = await executor.discover_entities()
    # Find an agent entity to test with
    agents = [e for e in entities if e.type == "agent"]
    assert len(agents) > 0, "No agent entities found for testing"
    agent_id = agents[0].id

    request = AgentFrameworkRequest(
        model="agent-framework", input="test data", stream=False, extra_body=AgentFrameworkExtraBody(entity_id=agent_id)
    )

    response = await executor.execute_sync(request)

    assert response.model == "agent-framework"
    assert response.object == "response"
    assert len(response.output) > 0
    assert response.usage.total_tokens > 0


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requires OpenAI API key")
@pytest.mark.asyncio
async def test_executor_streaming_execution(executor):
    """Test streaming execution."""
    entities = await executor.discover_entities()
    # Find an agent entity to test with
    agents = [e for e in entities if e.type == "agent"]
    assert len(agents) > 0, "No agent entities found for testing"
    agent_id = agents[0].id

    request = AgentFrameworkRequest(
        model="agent-framework",
        input="streaming test",
        stream=True,
        extra_body=AgentFrameworkExtraBody(entity_id=agent_id),
    )

    event_count = 0
    text_events = []

    async for event in executor.execute_streaming(request):
        event_count += 1
        if hasattr(event, "type") and event.type == "response.output_text.delta":
            text_events.append(event.delta)

        if event_count > 10:  # Limit for testing
            break

    assert event_count > 0
    assert len(text_events) > 0


@pytest.mark.asyncio
async def test_executor_invalid_entity_id(executor):
    """Test execution with invalid entity ID."""
    with pytest.raises(EntityNotFoundError):
        executor.get_entity_info("nonexistent_agent")


@pytest.mark.asyncio
async def test_executor_missing_entity_id(executor):
    """Test execution without entity ID."""
    request = AgentFrameworkRequest(
        model="agent-framework",
        input="test",
        stream=False,
        extra_body=None,  # Test case for missing entity_id
    )

    entity_id = request.get_entity_id()
    assert entity_id is None


if __name__ == "__main__":
    # Simple test runner
    async def run_tests():
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test agent
            agent_file = temp_path / "streaming_agent.py"
            agent_file.write_text("""
class StreamingAgent:
    name = "Streaming Test Agent"
    description = "Test agent for streaming"

    async def run_stream(self, input_str):
        for i, word in enumerate(f"Processing {input_str}".split()):
            yield f"word_{i}: {word} "
""")

            discovery = EntityDiscovery(str(temp_path))
            mapper = MessageMapper()
            executor = AgentFrameworkExecutor(discovery, mapper)

            # Test discovery
            entities = await executor.discover_entities()

            if entities:
                # Test sync execution
                request = AgentFrameworkRequest(
                    model="agent-framework",
                    input="test input",
                    stream=False,
                    extra_body=AgentFrameworkExtraBody(entity_id=entities[0].id),
                )

                await executor.execute_sync(request)

                # Test streaming execution
                request.stream = True
                event_count = 0
                async for _event in executor.execute_streaming(request):
                    event_count += 1
                    if event_count > 5:  # Limit for testing
                        break

    asyncio.run(run_tests())
