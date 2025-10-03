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


class _DummyStartExecutor:
    """Minimal executor stub exposing handler metadata for tests."""

    def __init__(self, *, input_types=None, handlers=None):
        if input_types is not None:
            self.input_types = list(input_types)
        if handlers is not None:
            self._handlers = dict(handlers)


class _DummyWorkflow:
    """Simple workflow stub returning configured start executor."""

    def __init__(self, start_executor):
        self._start_executor = start_executor

    def get_start_executor(self):
        return self._start_executor


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


async def test_executor_get_entity_info(executor):
    """Test getting entity info by ID."""
    entities = await executor.discover_entities()
    entity_id = entities[0].id

    entity_info = executor.get_entity_info(entity_id)
    assert entity_info is not None
    assert entity_info.id == entity_id
    assert entity_info.type in ["agent", "workflow"]


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requires OpenAI API key")
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
@pytest.mark.skip("Skipping while we fix discovery")
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


async def test_executor_invalid_entity_id(executor):
    """Test execution with invalid entity ID."""
    with pytest.raises(EntityNotFoundError):
        executor.get_entity_info("nonexistent_agent")


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


def test_executor_get_start_executor_message_types_uses_handlers():
    """Ensure handler metadata is surfaced when input_types missing."""
    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())
    start_executor = _DummyStartExecutor(handlers={str: lambda *_: None})
    workflow = _DummyWorkflow(start_executor)

    start, message_types = executor._get_start_executor_message_types(workflow)

    assert start is start_executor
    assert str in message_types


def test_executor_select_primary_input_prefers_string():
    """Select string input even when discovered after other handlers."""
    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())
    placeholder_type = type("Placeholder", (), {})

    chosen = executor._select_primary_input_type([placeholder_type, str])

    assert chosen is str


def test_executor_parse_structured_prefers_input_field():
    """Structured payloads map to string when agent start requires text."""
    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())
    start_executor = _DummyStartExecutor(handlers={type("Req", (), {}): None, str: lambda *_: None})
    workflow = _DummyWorkflow(start_executor)

    parsed = executor._parse_structured_workflow_input(workflow, {"input": "hello"})

    assert parsed == "hello"


def test_executor_parse_raw_falls_back_to_string():
    """Raw inputs remain untouched when start executor expects text."""
    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())
    start_executor = _DummyStartExecutor(handlers={str: lambda *_: None})
    workflow = _DummyWorkflow(start_executor)

    parsed = executor._parse_raw_workflow_input(workflow, "hi there")

    assert parsed == "hi there"


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
