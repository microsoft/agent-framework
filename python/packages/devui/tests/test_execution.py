#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for execution flow functionality."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agent_framework_devui.executors.agent_framework._discovery import AgentFrameworkEntityDiscovery
from agent_framework_devui.executors.agent_framework._executor import AgentFrameworkExecutor
from agent_framework_devui.executors.agent_framework._mapper import AgentFrameworkMessageMapper
from agent_framework_devui.models import AgentFrameworkRequest


@pytest.fixture
def test_entities_dir():
    """Use the examples directory which has proper entity structure."""
    current_dir = Path(__file__).parent
    examples_dir = current_dir.parent / "examples"
    return str(examples_dir.resolve())


@pytest.fixture
async def executor(test_entities_dir):
    """Create configured executor."""
    discovery = AgentFrameworkEntityDiscovery("agent_framework", test_entities_dir)
    mapper = AgentFrameworkMessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    # Discover entities
    await executor.discover_entities()

    return executor


@pytest.mark.asyncio
async def test_executor_entity_discovery(executor):
    """Test executor entity discovery."""
    entities = await executor.discover_entities()

    # Should find entities from examples directory (at least 1 agent, 1+ workflows)
    assert len(entities) >= 2
    entity_types = [e.type for e in entities]
    assert "agent" in entity_types  # WeatherAgent
    assert "workflow" in entity_types  # spam_workflow and/or fanout_workflow


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
        model="agent-framework",
        input="test data",
        stream=False,
        extra_body={"entity_id": agent_id}
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
        extra_body={"entity_id": agent_id}
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
    request = AgentFrameworkRequest(
        model="agent-framework",
        input="test",
        stream=False,
        extra_body={"entity_id": "nonexistent_agent"}
    )

    with pytest.raises(Exception):
        executor.get_entity_info("nonexistent_agent")


@pytest.mark.asyncio
async def test_executor_missing_entity_id(executor):
    """Test execution without entity ID."""
    request = AgentFrameworkRequest(
        model="agent-framework",
        input="test",
        stream=False,
        extra_body={}
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

            print("⚡ Testing execution flow...")

            discovery = AgentFrameworkEntityDiscovery("agent_framework", str(temp_path))
            mapper = AgentFrameworkMessageMapper()
            executor = AgentFrameworkExecutor(discovery, mapper)

            # Test discovery
            entities = await executor.discover_entities()
            print(f"✅ Discovered {len(entities)} entities")

            if entities:
                # Test sync execution
                request = AgentFrameworkRequest(
                    model="agent-framework",
                    input="test input",
                    stream=False,
                    extra_body={"entity_id": entities[0].id}
                )

                response = await executor.execute_sync(request)
                print(f"✅ Sync execution completed: {len(response.output)} outputs")

                # Test streaming execution
                request.stream = True
                event_count = 0
                async for event in executor.execute_streaming(request):
                    event_count += 1
                    if event_count > 5:  # Limit for testing
                        break

                print(f"✅ Streaming execution completed: {event_count} events")

    asyncio.run(run_tests())
