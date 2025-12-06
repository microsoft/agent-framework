# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for execution flow functionality.

Tests include:
- Entity discovery and info retrieval
- Agent execution (sync and streaming) using real ChatAgent with mock LLM
- Workflow execution using real WorkflowBuilder with FunctionExecutor
- Edge cases like non-streaming agents
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from agent_framework import AgentExecutor, ChatAgent, FunctionExecutor, WorkflowBuilder

# Import test utilities
from test_helpers import (
    MockBaseChatClient,
    create_concurrent_workflow,
    create_executor_with_real_agent,
    create_sequential_workflow,
)

from agent_framework_devui._discovery import EntityDiscovery
from agent_framework_devui._executor import AgentFrameworkExecutor, EntityNotFoundError
from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest

# =============================================================================
# Local Fixtures (async factory-based)
# =============================================================================


@pytest_asyncio.fixture
async def executor_with_real_agent():
    """Create an executor with a REAL ChatAgent using mock chat client."""
    return await create_executor_with_real_agent()


@pytest_asyncio.fixture
async def sequential_workflow_fixture():
    """Create a realistic sequential workflow (Writer -> Reviewer)."""
    return await create_sequential_workflow()


@pytest_asyncio.fixture
async def concurrent_workflow_fixture():
    """Create a realistic concurrent workflow (Researcher | Analyst | Summarizer)."""
    return await create_concurrent_workflow()


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


# =============================================================================
# Agent Execution Tests (using real ChatAgent with mock LLM)
# =============================================================================


async def test_agent_sync_execution(executor_with_real_agent):
    """Test synchronous agent execution with REAL ChatAgent (mock LLM).

    This tests the full execution pipeline without needing an API key:
    - Real ChatAgent class with middleware
    - Real message normalization
    - Mock chat client for LLM calls
    """
    executor, entity_id, mock_client = executor_with_real_agent

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_id},
        input="test data",
        stream=False,
    )

    response = await executor.execute_sync(request)

    # Response model should be 'devui' when not specified
    assert response.model == "devui"
    assert response.object == "response"
    assert len(response.output) > 0

    # Verify mock client was called
    assert mock_client.call_count == 1


async def test_agent_sync_execution_respects_model_field(executor_with_real_agent):
    """Test synchronous execution respects the model field in the response."""
    executor, entity_id, mock_client = executor_with_real_agent

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_id},
        model="custom-model-name",
        input="test data",
        stream=False,
    )

    response = await executor.execute_sync(request)

    # Response model should reflect the specified model
    assert response.model == "custom-model-name"
    assert response.object == "response"
    assert len(response.output) > 0


async def test_chat_client_receives_correct_messages(executor_with_real_agent):
    """Verify the mock chat client receives properly formatted messages.

    This tests that the REAL ChatAgent properly:
    - Normalizes input messages
    - Formats messages for the chat client
    """
    executor, entity_id, mock_client = executor_with_real_agent

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_id},
        input="What is 2+2?",
        stream=False,
    )

    await executor.execute_sync(request)

    # Verify chat client was called
    assert mock_client.call_count == 1

    # Verify messages were received
    assert len(mock_client.received_messages) == 1
    messages = mock_client.received_messages[0]

    # Should have at least one message
    assert len(messages) >= 1, f"Expected messages, got: {messages}"

    # Verify the input text is present in the messages
    all_text = " ".join(m.text or "" for m in messages)
    assert "2+2" in all_text, f"Expected '2+2' in messages, got text: '{all_text}'"


# =============================================================================
# Workflow Execution Tests (using real WorkflowBuilder with FunctionExecutor)
# =============================================================================


async def test_workflow_streaming_execution():
    """Test workflow streaming execution with REAL WorkflowBuilder and FunctionExecutor.

    This tests the full workflow execution pipeline without needing an API key.
    Uses a simple function-based workflow that processes input.
    """

    # Create a simple workflow using real agent_framework classes
    def process_input(input_data: str) -> str:
        return f"Processed: {input_data}"

    builder = WorkflowBuilder(name="Test Workflow", description="Test workflow for execution")
    start_executor = FunctionExecutor(id="process", func=process_input)
    builder.set_start_executor(start_executor)
    workflow = builder.build()

    # Create executor and register workflow
    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="test")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    # Execute workflow
    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_info.id},
        input="hello workflow",
        stream=True,
    )

    events = []
    async for event in executor.execute_streaming(request):
        events.append(event)

    # Should get events from workflow execution
    assert len(events) > 0, "Should receive events from workflow"

    # Check for workflow-specific events or completion
    event_types = [getattr(e, "type", None) for e in events]
    assert any(t is not None for t in event_types), f"Should have typed events, got: {event_types}"


async def test_workflow_sync_execution():
    """Test synchronous workflow execution."""

    def echo(text: str) -> str:
        return f"Echo: {text}"

    builder = WorkflowBuilder(name="Echo Workflow", description="Simple echo workflow")
    start_executor = FunctionExecutor(id="echo", func=echo)
    builder.set_start_executor(start_executor)
    workflow = builder.build()

    # Create executor and register workflow
    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="test")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    # Execute workflow synchronously
    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_info.id},
        input="test input",
        stream=False,
    )

    response = await executor.execute_sync(request)

    # Should get a valid response
    assert response.object == "response"
    assert len(response.output) > 0


# =============================================================================
# Full Pipeline Serialization Tests (Run + Map + JSON)
# =============================================================================


async def test_full_pipeline_agent_events_are_json_serializable(executor_with_real_agent):
    """CRITICAL TEST: Verify ALL events from agent execution can be JSON serialized.

    This tests the exact code path that the server uses:
    1. Execute agent via executor.execute_streaming()
    2. Each event is converted by the mapper
    3. Server calls model_dump_json() on each event for SSE

    If any event contains non-serializable objects (like AgentRunResponse),
    this test will fail - catching the bug before it hits production.
    """
    executor, entity_id, mock_client = executor_with_real_agent

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_id},
        input="Test message for serialization",
        stream=True,
    )

    events = []
    serialization_errors = []

    async for event in executor.execute_streaming(request):
        events.append(event)

        # This is EXACTLY what the server does before sending SSE
        try:
            if hasattr(event, "model_dump_json"):
                json_str = event.model_dump_json()
                assert json_str is not None
                assert len(json_str) > 0
        except Exception as e:
            serialization_errors.append(f"Event type={getattr(event, 'type', 'unknown')}: {e}")

    # Should have received events
    assert len(events) > 0, "Should receive events from agent execution"

    # NO serialization errors allowed
    assert len(serialization_errors) == 0, f"Found {len(serialization_errors)} serialization errors:\n" + "\n".join(
        serialization_errors
    )


async def test_full_pipeline_workflow_events_are_json_serializable():
    """CRITICAL TEST: Verify ALL events from workflow execution can be JSON serialized.

    This is particularly important for workflows with AgentExecutor because:
    - AgentExecutor produces ExecutorCompletedEvent with AgentExecutorResponse
    - AgentExecutorResponse contains AgentRunResponse and ChatMessage objects
    - These are SerializationMixin objects, not Pydantic, which caused the original bug

    This test ensures the ENTIRE streaming pipeline works end-to-end.
    """
    # Create a workflow with AgentExecutor (the problematic case)
    mock_client = MockBaseChatClient()
    agent = ChatAgent(
        id="serialization_test_agent",
        name="Serialization Test Agent",
        description="Agent for testing serialization",
        chat_client=mock_client,
        system_message="You are a test assistant.",
    )

    builder = WorkflowBuilder(name="Serialization Test Workflow", description="Test workflow")
    agent_executor = AgentExecutor(id="agent_node", agent=agent)
    builder.set_start_executor(agent_executor)
    workflow = builder.build()

    # Create executor and register
    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="test")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_info.id},
        input="Test workflow serialization",
        stream=True,
    )

    events = []
    serialization_errors = []
    event_types_seen = []

    async for event in executor.execute_streaming(request):
        events.append(event)
        event_type = getattr(event, "type", "unknown")
        event_types_seen.append(event_type)

        # This is EXACTLY what the server does before sending SSE
        try:
            if hasattr(event, "model_dump_json"):
                json_str = event.model_dump_json()
                assert json_str is not None
                assert len(json_str) > 0
        except Exception as e:
            serialization_errors.append(f"Event type={event_type}: {e}")

    # Should have received events
    assert len(events) > 0, "Should receive events from workflow execution"

    # Verify we got workflow events (not just generic ones)
    assert any("output_item" in str(t) for t in event_types_seen), (
        f"Should see output_item events, got: {event_types_seen}"
    )

    # NO serialization errors allowed - this is the critical assertion
    assert len(serialization_errors) == 0, (
        f"Found {len(serialization_errors)} serialization errors:\n"
        + "\n".join(serialization_errors)
        + f"\n\nEvent types seen: {event_types_seen}"
    )

    # Also verify aggregate_to_response works (server calls this after streaming)
    final_response = await mapper.aggregate_to_response(events, request)
    assert final_response is not None


async def test_get_entity_info_raises_for_invalid_id(executor):
    """Test that get_entity_info raises EntityNotFoundError for invalid ID."""
    with pytest.raises(EntityNotFoundError):
        executor.get_entity_info("nonexistent_agent")


async def test_request_extracts_entity_id_from_metadata(executor):
    """Test that AgentFrameworkRequest extracts entity_id from metadata."""
    request = AgentFrameworkRequest(
        metadata={"entity_id": "my_agent"},
        input="test",
        stream=False,
    )

    # entity_id is extracted from metadata
    entity_id = request.get_entity_id()
    assert entity_id == "my_agent"


@pytest.mark.asyncio
async def test_executor_get_start_executor_message_types(sequential_workflow_fixture):
    """Test _get_start_executor_message_types with real workflow."""
    executor, _entity_id, _mock_client, workflow = sequential_workflow_fixture

    start_exec, message_types = executor._get_start_executor_message_types(workflow)

    assert start_exec is not None
    assert len(message_types) > 0
    # Real sequential workflows accept str input
    assert str in message_types


def test_executor_select_primary_input_prefers_string():
    """Select string input even when discovered after other handlers."""
    from agent_framework_devui._utils import select_primary_input_type

    placeholder_type = type("Placeholder", (), {})

    chosen = select_primary_input_type([placeholder_type, str])

    assert chosen is str


@pytest.mark.asyncio
async def test_executor_parse_structured_extracts_input_for_string_workflow():
    """Structured payloads extract 'input' field when workflow expects str."""
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

    class StringInputExecutor(Executor):
        """Executor that accepts string input directly."""

        @handler
        async def process(self, text: str, ctx: WorkflowContext[Any, Any]) -> None:
            await ctx.yield_output(f"Got: {text}")

    workflow = (
        WorkflowBuilder(name="String Workflow", description="Accepts string")
        .set_start_executor(StringInputExecutor(id="str_exec"))
        .build()
    )

    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())

    # When workflow expects str and receives {"input": "hello"}, extract "hello"
    parsed = executor._parse_structured_workflow_input(workflow, {"input": "hello"})
    assert parsed == "hello"


@pytest.mark.asyncio
async def test_executor_parse_raw_string_for_string_workflow():
    """Raw string inputs pass through for string-accepting workflows."""
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

    class StringInputExecutor(Executor):
        """Executor that accepts string input directly."""

        @handler
        async def process(self, text: str, ctx: WorkflowContext[Any, Any]) -> None:
            await ctx.yield_output(f"Got: {text}")

    workflow = (
        WorkflowBuilder(name="String Workflow", description="Accepts string")
        .set_start_executor(StringInputExecutor(id="str_exec"))
        .build()
    )

    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())

    # Raw string should pass through unchanged
    parsed = executor._parse_raw_workflow_input(workflow, "hi there")
    assert parsed == "hi there"


@pytest.mark.asyncio
async def test_executor_parse_converts_to_chat_message_for_sequential_workflow(sequential_workflow_fixture):
    """Sequential workflows convert string input to ChatMessage."""
    from agent_framework import ChatMessage

    executor, _entity_id, _mock_client, workflow = sequential_workflow_fixture

    # Sequential workflows expect ChatMessage, so raw string becomes ChatMessage
    parsed = executor._parse_raw_workflow_input(workflow, "hello")

    assert isinstance(parsed, ChatMessage)
    assert parsed.text == "hello"


@pytest.mark.asyncio
async def test_executor_parse_stringified_json_workflow_input():
    """Stringified JSON workflow input is parsed when workflow expects Pydantic model."""
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
    from pydantic import BaseModel

    class WorkflowInput(BaseModel):
        input: str
        metadata: dict | None = None

    class PydanticInputExecutor(Executor):
        """Executor that accepts a Pydantic model input."""

        @handler
        async def process(self, data: WorkflowInput, ctx: WorkflowContext[Any, Any]) -> None:
            await ctx.yield_output(f"Got: {data.input}")

    # Build workflow with Pydantic input type
    workflow = (
        WorkflowBuilder(name="Pydantic Workflow", description="Accepts Pydantic input")
        .set_start_executor(PydanticInputExecutor(id="pydantic_exec"))
        .build()
    )

    executor = AgentFrameworkExecutor(EntityDiscovery(None), MessageMapper())

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


# =============================================================================
# Full Pipeline Tests for SequentialBuilder
# =============================================================================


@pytest.mark.asyncio
async def test_full_pipeline_sequential_workflow(sequential_workflow_fixture):
    """Test SequentialBuilder workflow full pipeline with JSON serialization.

    Uses the shared sequential_workflow_fixture (Writer → Reviewer) from conftest.
    Tests that all events can be JSON serialized for SSE streaming.
    """
    executor, entity_id, mock_client, _workflow = sequential_workflow_fixture

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_id},
        input="Write about testing best practices",
        stream=True,
    )

    events = []
    serialization_errors = []

    async for event in executor.execute_streaming(request):
        events.append(event)
        event_type = getattr(event, "type", "unknown")

        # Verify JSON serialization (exactly what server does for SSE)
        try:
            if hasattr(event, "model_dump_json"):
                json_str = event.model_dump_json()
                assert json_str is not None
        except Exception as e:
            serialization_errors.append(f"Event type={event_type}: {e}")

    assert len(events) > 0, "Should receive events from sequential workflow"
    assert len(serialization_errors) == 0, f"Serialization errors: {serialization_errors}"
    assert mock_client.call_count >= 2, f"Expected both agents called, got {mock_client.call_count}"


@pytest.mark.asyncio
async def test_full_pipeline_concurrent_workflow(concurrent_workflow_fixture):
    """Test ConcurrentBuilder workflow full pipeline with JSON serialization.

    Uses the shared concurrent_workflow_fixture (Researcher | Analyst | Summarizer) from conftest.
    Tests fan-out/fan-in pattern with parallel agent execution.
    """
    executor, entity_id, mock_client, _workflow = concurrent_workflow_fixture

    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_id},
        input="Analyze market trends for Q4",
        stream=True,
    )

    events = []
    serialization_errors = []

    async for event in executor.execute_streaming(request):
        events.append(event)
        event_type = getattr(event, "type", "unknown")

        # Verify JSON serialization
        try:
            if hasattr(event, "model_dump_json"):
                json_str = event.model_dump_json()
                assert json_str is not None
        except Exception as e:
            serialization_errors.append(f"Event type={event_type}: {e}")

    assert len(events) > 0, "Should receive events from concurrent workflow"
    assert len(serialization_errors) == 0, f"Serialization errors: {serialization_errors}"
    assert mock_client.call_count >= 3, f"Expected all 3 agents called, got {mock_client.call_count}"


# =============================================================================
# Full Pipeline Test for Workflow with Output Events
# =============================================================================


@pytest.mark.asyncio
async def test_full_pipeline_workflow_output_event_serialization():
    """Test that WorkflowOutputEvent from ctx.yield_output() serializes correctly.

    This tests the pattern where executors yield output via ctx.yield_output(),
    which emits WorkflowOutputEvent that DevUI must serialize for SSE.
    """
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

    class OutputtingExecutor(Executor):
        """Executor that yields multiple outputs."""

        @handler
        async def process(self, input_text: str, ctx: WorkflowContext[Any, Any]) -> None:
            await ctx.yield_output(f"First output: {input_text}")
            await ctx.yield_output("Second output: processed")
            await ctx.yield_output({"final": "result", "data": [1, 2, 3]})

    # Build workflow
    workflow = (
        WorkflowBuilder(name="Output Workflow", description="Tests yield_output")
        .set_start_executor(OutputtingExecutor(id="outputter"))
        .build()
    )

    # Create DevUI executor and register workflow
    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="test")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    # Execute with streaming
    request = AgentFrameworkRequest(
        metadata={"entity_id": entity_info.id},
        input="Test output events",
        stream=True,
    )

    events = []
    output_events = []
    serialization_errors = []

    async for event in executor.execute_streaming(request):
        events.append(event)
        event_type = getattr(event, "type", "")

        # Track output item events
        if "output_item" in event_type:
            output_events.append(event)

        try:
            if hasattr(event, "model_dump_json"):
                event.model_dump_json()
        except Exception as e:
            serialization_errors.append(f"Event type={event_type}: {e}")

    assert len(events) > 0, "Should receive events"
    assert len(serialization_errors) == 0, f"Serialization errors: {serialization_errors}"

    # Should have received output events for the yield_output calls
    assert len(output_events) >= 3, f"Expected 3+ output events for yield_output calls, got {len(output_events)}"


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
