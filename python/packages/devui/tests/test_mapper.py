# Copyright (c) Microsoft. All rights reserved.

"""Clean focused tests for message mapping functionality."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

# Add the main agent_framework package for real types
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "main"))

# Import Agent Framework types (assuming they are always available)
from agent_framework._types import (
    AgentRunResponseUpdate,
    ErrorContent,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
)

from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest


def create_test_content(content_type: str, **kwargs: Any) -> Any:
    """Create test content objects."""
    if content_type == "text":
        return TextContent(text=kwargs.get("text", "Hello, world!"))
    if content_type == "function_call":
        return FunctionCallContent(
            call_id=kwargs.get("call_id", "test_call_id"),
            name=kwargs.get("name", "test_func"),
            arguments=kwargs.get("arguments", {"param": "value"}),
        )
    if content_type == "error":
        return ErrorContent(message=kwargs.get("message", "Test error"), error_code=kwargs.get("code", "test_error"))
    raise ValueError(f"Unknown content type: {content_type}")


def create_test_agent_update(contents: list[Any]) -> Any:
    """Create test AgentRunResponseUpdate - NO fake attributes!"""
    return AgentRunResponseUpdate(
        contents=contents, role=Role.ASSISTANT, message_id="test_msg", response_id="test_resp"
    )


@pytest.fixture
def mapper() -> MessageMapper:
    return MessageMapper()


@pytest.fixture
def test_request() -> AgentFrameworkRequest:
    # Use metadata.entity_id for routing
    return AgentFrameworkRequest(
        metadata={"entity_id": "test_agent"},
        input="Test input",
        stream=True,
    )


async def test_critical_isinstance_bug_detection(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """CRITICAL: Test that would have caught the isinstance vs hasattr bug."""

    content = create_test_content("text", text="Bug detection test")
    update = create_test_agent_update([content])

    # Key assertions that would have caught the bug
    assert hasattr(update, "contents")  # Real attribute ✅
    assert not hasattr(update, "response")  # Fake attribute should not exist ✅

    # Test isinstance works with real types
    assert isinstance(update, AgentRunResponseUpdate)

    # Test mapper conversion - should NOT produce "Unknown event"
    events = await mapper.convert_event(update, test_request)

    assert len(events) > 0
    assert all(hasattr(event, "type") for event in events)
    # Should never get unknown events with proper types
    assert all(event.type != "unknown" for event in events)


async def test_text_content_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test TextContent mapping with proper OpenAI event hierarchy."""
    content = create_test_content("text", text="Hello, clean test!")
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    # With proper OpenAI hierarchy, we expect 3 events:
    # 1. response.output_item.added (message)
    # 2. response.content_part.added (text part)
    # 3. response.output_text.delta (actual text)
    assert len(events) == 3

    # Check message output item
    assert events[0].type == "response.output_item.added"
    assert events[0].item.type == "message"
    assert events[0].item.role == "assistant"

    # Check content part
    assert events[1].type == "response.content_part.added"
    assert events[1].part.type == "output_text"

    # Check text delta
    assert events[2].type == "response.output_text.delta"
    assert events[2].delta == "Hello, clean test!"


async def test_function_call_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test FunctionCallContent mapping."""
    content = create_test_content("function_call", name="test_func", arguments={"location": "TestCity"})
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    # Should generate: response.output_item.added + response.function_call_arguments.delta
    assert len(events) >= 2
    assert events[0].type == "response.output_item.added"
    assert events[1].type == "response.function_call_arguments.delta"

    # Check JSON is in delta event
    delta_events = [e for e in events if e.type == "response.function_call_arguments.delta"]
    full_json = "".join(event.delta for event in delta_events)
    assert "TestCity" in full_json


async def test_function_result_content_with_string_result(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test FunctionResultContent with plain string result (regular tools)."""
    content = FunctionResultContent(
        call_id="test_call_123",
        result="Hello, World!",  # Plain string like regular Python function tools
    )
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    # Should produce response.function_result.complete event
    assert len(events) >= 1
    result_events = [e for e in events if e.type == "response.function_result.complete"]
    assert len(result_events) == 1
    assert result_events[0].output == "Hello, World!"
    assert result_events[0].call_id == "test_call_123"
    assert result_events[0].status == "completed"


async def test_function_result_content_with_nested_content_objects(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test FunctionResultContent with nested Content objects (MCP tools case).

    This tests the issue from GitHub #1476 where MCP tools return FunctionResultContent
    with nested TextContent objects that fail to serialize properly.
    """
    # This is what MCP tools return - result contains nested Content objects
    content = FunctionResultContent(
        call_id="mcp_call_456",
        result=[TextContent(text="Hello from MCP!")],  # List containing TextContent object
    )
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    # Should successfully serialize the nested Content object
    assert len(events) >= 1
    result_events = [e for e in events if e.type == "response.function_result.complete"]
    assert len(result_events) == 1

    # The output should contain the text from the nested TextContent
    # Should not have TypeError or empty output
    assert result_events[0].output != ""
    assert "Hello from MCP!" in result_events[0].output
    assert result_events[0].call_id == "mcp_call_456"


async def test_function_result_content_with_multiple_nested_content_objects(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test FunctionResultContent with multiple nested Content objects."""
    # MCP tools can return multiple Content objects
    content = FunctionResultContent(
        call_id="mcp_call_789",
        result=[
            TextContent(text="First result"),
            TextContent(text="Second result"),
        ],
    )
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) >= 1
    result_events = [e for e in events if e.type == "response.function_result.complete"]
    assert len(result_events) == 1

    # Should serialize all nested Content objects
    output = result_events[0].output
    assert output != ""
    assert "First result" in output
    assert "Second result" in output


async def test_error_content_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test ErrorContent mapping."""
    content = create_test_content("error", message="Test error", code="test_code")
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) == 1
    assert events[0].type == "error"
    assert events[0].message == "Test error"
    assert events[0].code == "test_code"


async def test_mixed_content_types(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test multiple content types together."""
    contents = [
        create_test_content("text", text="Starting..."),
        create_test_content("function_call", name="process", arguments={"data": "test"}),
        create_test_content("text", text="Done!"),
    ]
    update = create_test_agent_update(contents)

    events = await mapper.convert_event(update, test_request)

    assert len(events) >= 3

    # Should have both types of events
    event_types = {event.type for event in events}
    assert "response.output_text.delta" in event_types
    assert "response.function_call_arguments.delta" in event_types


async def test_unknown_content_fallback(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test graceful handling of unknown content types."""
    # Test the fallback path directly since we can't create invalid AgentRunResponseUpdate
    # due to Pydantic validation. Instead, test the content mapper's unknown content handling.

    class MockUnknownContent:
        def __init__(self):
            self.__class__.__name__ = "WeirdUnknownContent"  # Not in content_mappers

    # Test the content mapper directly
    context = mapper._get_or_create_context(test_request)
    unknown_content = MockUnknownContent()

    # This should trigger the unknown content fallback in _convert_agent_update
    event = await mapper._create_unknown_content_event(unknown_content, context)

    assert event.type == "response.output_text.delta"
    assert "Unknown content type" in event.delta
    assert "WeirdUnknownContent" in event.delta


async def test_agent_run_response_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that mapper handles complete AgentRunResponse (non-streaming)."""
    from agent_framework import AgentRunResponse, ChatMessage, Role, TextContent

    # Create a complete response like agent.run() would return
    message = ChatMessage(
        role=Role.ASSISTANT,
        contents=[TextContent(text="Complete response from run()")],
    )
    response = AgentRunResponse(messages=[message], response_id="test_resp_123")

    # Mapper should convert it to streaming events
    events = await mapper.convert_event(response, test_request)

    assert len(events) > 0
    # Should produce text delta events
    text_events = [e for e in events if e.type == "response.output_text.delta"]
    assert len(text_events) > 0
    assert text_events[0].delta == "Complete response from run()"


async def test_agent_lifecycle_events(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that agent lifecycle events are properly converted to OpenAI format."""
    from agent_framework_devui.models._openai_custom import AgentCompletedEvent, AgentFailedEvent, AgentStartedEvent

    # Test AgentStartedEvent
    start_event = AgentStartedEvent()
    events = await mapper.convert_event(start_event, test_request)

    assert len(events) == 2  # Should emit response.created and response.in_progress
    assert events[0].type == "response.created"
    assert events[1].type == "response.in_progress"
    assert events[0].response.model == "devui"  # Should use 'devui' when model not specified in request
    assert events[0].response.status == "in_progress"

    # Test AgentCompletedEvent
    complete_event = AgentCompletedEvent()
    events = await mapper.convert_event(complete_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.completed"
    assert events[0].response.status == "completed"

    # Test AgentFailedEvent
    error = Exception("Test error")
    failed_event = AgentFailedEvent(error=error)
    events = await mapper.convert_event(failed_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.failed"
    assert events[0].response.status == "failed"
    assert events[0].response.error.message == "Test error"
    assert events[0].response.error.code == "server_error"


@pytest.mark.skip(reason="Workflow events need real classes from agent_framework.workflows")
async def test_workflow_lifecycle_events(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that workflow lifecycle events are properly converted to OpenAI format."""

    # Create mock workflow events (since we don't have access to the real ones in tests)
    class WorkflowStartedEvent:  # noqa: B903
        def __init__(self, workflow_id: str):
            self.workflow_id = workflow_id

    class WorkflowCompletedEvent:  # noqa: B903
        def __init__(self, workflow_id: str):
            self.workflow_id = workflow_id

    class WorkflowFailedEvent:  # noqa: B903
        def __init__(self, workflow_id: str, error_info: dict | None = None):
            self.workflow_id = workflow_id
            self.error_info = error_info

    # Test WorkflowStartedEvent
    start_event = WorkflowStartedEvent(workflow_id="test_workflow_123")
    events = await mapper.convert_event(start_event, test_request)

    assert len(events) == 2  # Should emit response.created and response.in_progress
    assert events[0].type == "response.created"
    assert events[1].type == "response.in_progress"
    assert events[0].response.model == "test_agent"  # Should use model from request
    assert events[0].response.status == "in_progress"

    # Test WorkflowCompletedEvent
    complete_event = WorkflowCompletedEvent(workflow_id="test_workflow_123")
    events = await mapper.convert_event(complete_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.completed"
    assert events[0].response.status == "completed"

    # Test WorkflowFailedEvent with error info
    failed_event = WorkflowFailedEvent(workflow_id="test_workflow_123", error_info={"message": "Workflow failed"})
    events = await mapper.convert_event(failed_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.failed"
    assert events[0].response.status == "failed"
    assert events[0].response.error.message == "{'message': 'Workflow failed'}"
    assert events[0].response.error.code == "server_error"


@pytest.mark.skip(reason="Executor events need real classes from agent_framework.workflows")
async def test_executor_action_events(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that workflow executor events are properly converted to custom output item events."""

    # Create mock executor events (since we don't have access to the real ones in tests)
    class ExecutorInvokedEvent:  # noqa: B903
        def __init__(self, executor_id: str, executor_type: str = "test"):
            self.executor_id = executor_id
            self.executor_type = executor_type

    class ExecutorCompletedEvent:  # noqa: B903
        def __init__(self, executor_id: str, result: Any = None):
            self.executor_id = executor_id
            self.result = result

    class ExecutorFailedEvent:  # noqa: B903
        def __init__(self, executor_id: str, error: Exception | None = None):
            self.executor_id = executor_id
            self.error = error

    # Test ExecutorInvokedEvent
    invoked_event = ExecutorInvokedEvent(executor_id="exec_123", executor_type="test_executor")
    events = await mapper.convert_event(invoked_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.added"
    assert events[0].item["type"] == "executor_action"
    assert events[0].item["executor_id"] == "exec_123"
    assert events[0].item["status"] == "in_progress"

    # Test ExecutorCompletedEvent
    complete_event = ExecutorCompletedEvent(executor_id="exec_123", result={"data": "success"})
    events = await mapper.convert_event(complete_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.done"
    assert events[0].item["type"] == "executor_action"
    assert events[0].item["executor_id"] == "exec_123"
    assert events[0].item["status"] == "completed"
    assert events[0].item["result"] == {"data": "success"}

    # Test ExecutorFailedEvent
    failed_event = ExecutorFailedEvent(executor_id="exec_123", error=Exception("Executor failed"))
    events = await mapper.convert_event(failed_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.done"
    assert events[0].item["type"] == "executor_action"
    assert events[0].item["executor_id"] == "exec_123"
    assert events[0].item["status"] == "failed"
    assert "Executor failed" in str(events[0].item["error"]["message"])


async def test_magentic_agent_delta_creates_message_container(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test that MagenticAgentDeltaEvent creates message containers (Option A implementation)."""

    # Create mock MagenticAgentDeltaEvent that mimics the real class
    from dataclasses import dataclass

    try:
        from agent_framework import WorkflowEvent

        @dataclass
        class MagenticAgentDeltaEvent(WorkflowEvent):  # Inherit from WorkflowEvent
            agent_id: str
            text: str | None = None

    except ImportError:
        # Fallback if WorkflowEvent is not available
        @dataclass
        class MagenticAgentDeltaEvent:  # Use the expected name directly
            agent_id: str
            text: str | None = None

    # First delta should create message container
    first_delta = MagenticAgentDeltaEvent(agent_id="test_agent", text="Hello ")
    events = await mapper.convert_event(first_delta, test_request)

    # Should emit 3 events: message container, content part, and text delta
    assert len(events) == 3
    assert events[0].type == "response.output_item.added"
    assert events[0].item.type == "message"  # Message, not executor_action!
    assert events[0].item.metadata["agent_id"] == "test_agent"
    assert events[0].item.metadata["source"] == "magentic"
    message_id = events[0].item.id

    # Check text delta references the message ID
    assert events[2].type == "response.output_text.delta"
    assert events[2].item_id == message_id
    assert events[2].delta == "Hello "

    # Second delta should NOT create new container
    second_delta = MagenticAgentDeltaEvent(agent_id="test_agent", text="world!")
    events = await mapper.convert_event(second_delta, test_request)

    # Only text delta, no new container
    assert len(events) == 1
    assert events[0].type == "response.output_text.delta"
    assert events[0].item_id == message_id


if __name__ == "__main__":
    # Simple test runner
    async def run_all_tests() -> None:
        mapper = MessageMapper()
        test_request = AgentFrameworkRequest(
            metadata={"entity_id": "test"},
            input="Test",
            stream=True,
        )

        tests = [
            ("Critical isinstance bug detection", test_critical_isinstance_bug_detection),
            ("Text content mapping", test_text_content_mapping),
            ("Function call mapping", test_function_call_mapping),
            ("Error content mapping", test_error_content_mapping),
            ("Mixed content types", test_mixed_content_types),
            ("Unknown content fallback", test_unknown_content_fallback),
        ]

        passed = 0
        for _test_name, test_func in tests:
            try:
                await test_func(mapper, test_request)
                passed += 1
            except Exception:
                pass

    asyncio.run(run_all_tests())
