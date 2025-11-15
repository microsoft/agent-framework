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
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest


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
    # Get the samples directory from the main python samples folder
    current_dir = Path(__file__).parent
    # Navigate to python/samples/getting_started/devui
    samples_dir = current_dir.parent.parent.parent / "samples" / "getting_started" / "devui"
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
        # Entities with only an `__init__.py` file cannot have their type determined
        # until the module is imported during lazy loading. This is why 'unknown' type exists.
        assert entity.type in ["agent", "workflow", "unknown"], (
            "Entity should have valid type (unknown allowed during discovery phase)"
        )


async def test_executor_get_entity_info(executor):
    """Test getting entity info by ID."""
    entities = await executor.discover_entities()
    entity_id = entities[0].id

    entity_info = executor.get_entity_info(entity_id)
    assert entity_info is not None
    assert entity_info.id == entity_id
    assert entity_info.type in ["agent", "workflow", "unknown"]


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requires OpenAI API key")
async def test_executor_sync_execution(executor):
    """Test synchronous execution."""
    entities = await executor.discover_entities()
    # Find an agent entity to test with
    agents = [e for e in entities if e.type == "agent"]
    assert len(agents) > 0, "No agent entities found for testing"
    agent_id = agents[0].id

    # Use metadata.entity_id for routing
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        input="test data",
        stream=False,
    )

    response = await executor.execute_sync(request)

    # Response model should be 'devui' when not specified
    assert response.model == "devui"
    assert response.object == "response"
    assert len(response.output) > 0
    assert response.usage.total_tokens > 0


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="requires OpenAI API key")
async def test_executor_sync_execution_with_model(executor):
    """Test synchronous execution with model field specified."""
    entities = await executor.discover_entities()
    # Find an agent entity to test with
    agents = [e for e in entities if e.type == "agent"]
    assert len(agents) > 0, "No agent entities found for testing"
    agent_id = agents[0].id

    # Use metadata.entity_id for routing AND specify a model
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        model="custom-model-name",
        input="test data",
        stream=False,
    )

    response = await executor.execute_sync(request)

    # Response model should reflect the specified model
    assert response.model == "custom-model-name"
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

    # Use metadata.entity_id for routing
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        input="streaming test",
        stream=True,
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
    """Test get_entity_id returns metadata.entity_id."""
    request = AgentFrameworkRequest(
        metadata={"entity_id": "my_agent"},
        input="test",
        stream=False,
    )

    # entity_id is extracted from metadata
    entity_id = request.get_entity_id()
    assert entity_id == "my_agent"


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
    from agent_framework_devui._utils import select_primary_input_type

    placeholder_type = type("Placeholder", (), {})

    chosen = select_primary_input_type([placeholder_type, str])

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


def test_executor_parse_stringified_json_workflow_input():
    """Stringified JSON workflow input (from frontend JSON.stringify) is correctly parsed."""
    from pydantic import BaseModel

    class WorkflowInput(BaseModel):
        input: str
        metadata: dict | None = None

    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())
    start_executor = _DummyStartExecutor(handlers={WorkflowInput: lambda *_: None})
    workflow = _DummyWorkflow(start_executor)

    # Simulate frontend sending JSON.stringify({"input": "testing!", "metadata": {"key": "value"}})
    stringified_json = '{"input": "testing!", "metadata": {"key": "value"}}'

    parsed = executor._parse_raw_workflow_input(workflow, stringified_json)

    # Should parse into WorkflowInput object
    assert isinstance(parsed, WorkflowInput)
    assert parsed.input == "testing!"
    assert parsed.metadata == {"key": "value"}


def test_extract_workflow_hil_responses_handles_stringified_json():
    """Test HIL response extraction handles both stringified and parsed JSON (regression test)."""
    from agent_framework_devui._discovery import EntityDiscovery
    from agent_framework_devui._executor import AgentFrameworkExecutor
    from agent_framework_devui._mapper import MessageMapper

    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())

    # Regression test: Frontend sends stringified JSON via streamWorkflowExecutionOpenAI
    stringified = '[{"type":"message","content":[{"type":"workflow_hil_response","responses":{"req_1":"spam"}}]}]'
    assert executor._extract_workflow_hil_responses(stringified) == {"req_1": "spam"}

    # Ensure parsed format still works
    parsed = [{"type": "message", "content": [{"type": "workflow_hil_response", "responses": {"req_2": "ham"}}]}]
    assert executor._extract_workflow_hil_responses(parsed) == {"req_2": "ham"}

    # Non-HIL inputs should return None
    assert executor._extract_workflow_hil_responses("plain text") is None
    assert executor._extract_workflow_hil_responses({"email": "test"}) is None


async def test_executor_handles_non_streaming_agent():
    """Test executor can handle agents with only run() method (no run_stream)."""
    from agent_framework import AgentRunResponse, AgentThread, ChatMessage, Role, TextContent

    class NonStreamingAgent:
        """Agent with only run() method - does NOT satisfy full AgentProtocol."""

        id = "non_streaming_test"
        name = "Non-Streaming Test Agent"
        description = "Test agent without run_stream()"

        @property
        def display_name(self):
            return self.name

        async def run(self, messages=None, *, thread=None, **kwargs):
            return AgentRunResponse(
                messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=f"Processed: {messages}")])],
                response_id="test_123",
            )

        def get_new_thread(self, **kwargs):
            return AgentThread()

    # Create executor and register agent
    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    agent = NonStreamingAgent()
    entity_info = await discovery.create_entity_info_from_object(agent, source="test")
    discovery.register_entity(entity_info.id, entity_info, agent)

    # Execute non-streaming agent (use metadata.entity_id for routing)
    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_info.id},
        input="hello",
        stream=True,  # DevUI always streams
    )

    events = []
    async for event in executor.execute_streaming(request):
        events.append(event)

    # Should get events even though agent doesn't stream
    assert len(events) > 0
    text_events = [e for e in events if hasattr(e, "type") and e.type == "response.output_text.delta"]
    assert len(text_events) > 0
    assert "Processed: hello" in text_events[0].delta


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
                # Test sync execution (use metadata.entity_id for routing)
                request = AgentFrameworkRequest(
                    metadata={"entity_id": entities[0].id},
                    input="test input",
                    stream=False,
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
