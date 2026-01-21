# Copyright (c) Microsoft. All rights reserved.

"""Tests for message mapping functionality.

This module tests the MessageMapper which converts Agent Framework events
to OpenAI-compatible streaming events. Tests use REAL classes from
agent_framework, not mocks, to ensure proper serialization.
"""

from typing import Any

import pytest

# Import Agent Framework types
from agent_framework._types import (
    AgentResponseUpdate,
    Content,
    Role,
)

# Import real workflow event classes - NOT mocks!
from agent_framework._workflows._events import (
    ExecutorCompletedEvent,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
)

# Import test utilities
from test_helpers import (
    create_agent_run_response,
    create_executor_completed_event,
    create_executor_failed_event,
    create_executor_invoked_event,
    create_mapper,
    create_test_request,
)

from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import (
    AgentCompletedEvent,
    AgentFailedEvent,
    AgentFrameworkRequest,
    AgentStartedEvent,
)

# =============================================================================
# Local Fixtures (to replace conftest.py fixtures)
# =============================================================================


@pytest.fixture
def mapper() -> MessageMapper:
    """Create a fresh MessageMapper for each test."""
    return create_mapper()


@pytest.fixture
def test_request() -> AgentFrameworkRequest:
    """Create a standard test request."""
    return create_test_request()


# =============================================================================
# Test Helpers
# =============================================================================


def create_test_content(content_type: str, **kwargs: Any) -> Any:
    """Create test content objects."""
    if content_type == "text":
        return Content.from_text(text=kwargs.get("text", "Hello, world!"))
    if content_type == "function_call":
        return Content.from_function_call(
            call_id=kwargs.get("call_id", "test_call_id"),
            name=kwargs.get("name", "test_func"),
            arguments=kwargs.get("arguments", {"param": "value"}),
        )
    if content_type == "error":
        return Content.from_error(
            message=kwargs.get("message", "Test error"), error_code=kwargs.get("code", "test_error")
        )
    raise ValueError(f"Unknown content type: {content_type}")


def create_test_agent_update(contents: list[Any]) -> AgentResponseUpdate:
    """Create test AgentResponseUpdate."""
    return AgentResponseUpdate(contents=contents, role=Role.ASSISTANT, message_id="test_msg", response_id="test_resp")


# =============================================================================
# Basic Content Mapping Tests
# =============================================================================


async def test_critical_isinstance_bug_detection(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """CRITICAL: Test that would have caught the isinstance vs hasattr bug."""
    content = create_test_content("text", text="Bug detection test")
    update = create_test_agent_update([content])

    # Key assertions that would have caught the bug
    assert hasattr(update, "contents")  # Real attribute
    assert not hasattr(update, "response")  # Fake attribute should not exist

    # Test isinstance works with real types
    assert isinstance(update, AgentResponseUpdate)

    # Test mapper conversion - should NOT produce "Unknown event"
    events = await mapper.convert_event(update, test_request)

    assert len(events) > 0
    assert all(hasattr(event, "type") for event in events)
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
    content = Content.from_function_result(
        call_id="test_call_123",
        result="Hello, World!",
    )
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) >= 1
    result_events = [e for e in events if e.type == "response.function_result.complete"]
    assert len(result_events) == 1
    assert result_events[0].output == "Hello, World!"
    assert result_events[0].call_id == "test_call_123"
    assert result_events[0].status == "completed"


async def test_function_result_content_with_nested_content_objects(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test FunctionResultContent with nested Content objects (MCP tools case)."""
    content = Content.from_function_result(
        call_id="mcp_call_456",
        result=[Content.from_text(text="Hello from MCP!")],
    )
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) >= 1
    result_events = [e for e in events if e.type == "response.function_result.complete"]
    assert len(result_events) == 1
    assert "Hello from MCP!" in result_events[0].output
    assert result_events[0].call_id == "mcp_call_456"


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
    event_types = {event.type for event in events}
    assert "response.output_text.delta" in event_types
    assert "response.function_call_arguments.delta" in event_types


# =============================================================================
# Agent Lifecycle Event Tests
# =============================================================================


async def test_agent_lifecycle_events(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that agent lifecycle events are properly converted to OpenAI format."""
    # Test AgentStartedEvent
    start_event = AgentStartedEvent()
    events = await mapper.convert_event(start_event, test_request)

    assert len(events) == 2  # response.created and response.in_progress
    assert events[0].type == "response.created"
    assert events[1].type == "response.in_progress"
    assert events[0].response.model == "devui"
    assert events[0].response.status == "in_progress"

    # Test AgentCompletedEvent
    complete_event = AgentCompletedEvent()
    events = await mapper.convert_event(complete_event, test_request)
    # AgentCompletedEvent no longer emits response.completed to avoid duplicates
    assert len(events) == 0

    # Test AgentFailedEvent
    error = Exception("Test error")
    failed_event = AgentFailedEvent(error=error)
    events = await mapper.convert_event(failed_event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.failed"
    assert events[0].response.status == "failed"
    assert events[0].response.error.message == "Test error"


async def test_agent_run_response_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that mapper handles complete AgentResponse (non-streaming)."""
    response = create_agent_run_response("Complete response from run()")

    events = await mapper.convert_event(response, test_request)

    assert len(events) > 0
    text_events = [e for e in events if e.type == "response.output_text.delta"]
    assert len(text_events) > 0
    assert text_events[0].delta == "Complete response from run()"


# =============================================================================
# Workflow Executor Event Tests (using REAL classes, not mocks!)
# =============================================================================


async def test_executor_invoked_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test ExecutorInvokedEvent using the REAL class from agent_framework."""
    # Use real class, not mock!
    event = create_executor_invoked_event(executor_id="exec_123")

    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.added"
    # Access as dict since item might be ExecutorActionItem
    item = events[0].item if isinstance(events[0].item, dict) else events[0].item.model_dump()
    assert item["type"] == "executor_action"
    assert item["executor_id"] == "exec_123"
    assert item["status"] == "in_progress"


async def test_executor_completed_event_simple_data(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test ExecutorCompletedEvent with simple dict data."""
    # Create event with simple data
    event = ExecutorCompletedEvent(executor_id="exec_123", data={"simple": "result"})

    # First need to invoke the executor to set up context
    invoke_event = create_executor_invoked_event(executor_id="exec_123")
    await mapper.convert_event(invoke_event, test_request)

    # Now complete it
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.done"
    item = events[0].item if isinstance(events[0].item, dict) else events[0].item.model_dump()
    assert item["type"] == "executor_action"
    assert item["executor_id"] == "exec_123"
    assert item["status"] == "completed"
    # Result should be serialized
    assert item["result"] == {"simple": "result"}


async def test_executor_completed_event_with_agent_response(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test ExecutorCompletedEvent with nested AgentExecutorResponse.

    This is a REGRESSION TEST for the serialization bug where
    ExecutorCompletedEvent.data contained AgentExecutorResponse with nested
    AgentResponse and ChatMessage objects (SerializationMixin) that
    Pydantic couldn't serialize.
    """
    # Create event with realistic nested data - the exact structure that caused the bug
    event = create_executor_completed_event(executor_id="exec_agent", with_agent_response=True)

    # Verify the data has the problematic structure
    assert hasattr(event.data, "agent_response")
    assert hasattr(event.data, "full_conversation")

    # First invoke the executor
    invoke_event = create_executor_invoked_event(executor_id="exec_agent")
    await mapper.convert_event(invoke_event, test_request)

    # Now complete - this should NOT raise serialization errors
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.done"

    # Get the item (might be Pydantic model or dict)
    item = events[0].item if isinstance(events[0].item, dict) else events[0].item.model_dump()
    assert item["type"] == "executor_action"
    assert item["executor_id"] == "exec_agent"
    assert item["status"] == "completed"

    # The result should be serialized (converted to dict)
    result = item["result"]
    assert result is not None
    # Should be a dict or list, not the original object
    assert isinstance(result, (dict, list))


async def test_executor_completed_event_serialization_to_json(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """REGRESSION TEST: Verify the full JSON serialization works.

    This tests the exact failure mode from the bug: calling model_dump_json()
    on the event containing nested SerializationMixin objects.
    """
    # Create the problematic event
    event = create_executor_completed_event(executor_id="exec_json_test", with_agent_response=True)

    # Invoke first
    invoke_event = create_executor_invoked_event(executor_id="exec_json_test")
    await mapper.convert_event(invoke_event, test_request)

    # Complete
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    done_event = events[0]

    # This is the critical test - model_dump_json() should NOT raise
    # "Unable to serialize unknown type: <class 'agent_framework._types.AgentResponse'>"
    try:
        json_str = done_event.model_dump_json()
        assert json_str is not None
        assert len(json_str) > 0
        # Verify it's valid JSON by checking it contains expected fields
        assert "executor_action" in json_str
        assert "exec_json_test" in json_str
        assert "completed" in json_str
    except Exception as e:
        pytest.fail(f"model_dump_json() raised an exception: {e}")


async def test_executor_failed_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test ExecutorFailedEvent using the REAL class."""
    # First invoke the executor
    invoke_event = create_executor_invoked_event(executor_id="exec_fail")
    await mapper.convert_event(invoke_event, test_request)

    # Now fail it
    event = create_executor_failed_event(executor_id="exec_fail", error_message="Executor failed")
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.done"
    item = events[0].item if isinstance(events[0].item, dict) else events[0].item.model_dump()
    assert item["type"] == "executor_action"
    assert item["executor_id"] == "exec_fail"
    assert item["status"] == "failed"
    assert "Executor failed" in str(item["error"])


# =============================================================================
# Workflow Lifecycle Event Tests
# =============================================================================


async def test_workflow_started_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowStartedEvent using the REAL class."""

    event = WorkflowStartedEvent(data=None)
    events = await mapper.convert_event(event, test_request)

    # WorkflowStartedEvent should emit response.created and response.in_progress
    assert len(events) == 2
    assert events[0].type == "response.created"
    assert events[1].type == "response.in_progress"


async def test_workflow_status_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowStatusEvent using the REAL class."""
    from agent_framework._workflows._events import WorkflowRunState

    event = WorkflowStatusEvent(state=WorkflowRunState.IN_PROGRESS)
    events = await mapper.convert_event(event, test_request)

    # Should emit some status-related event
    assert len(events) >= 0  # May emit events or may be filtered


# =============================================================================
# Magentic Event Tests - Testing REAL AgentRunUpdateEvent with additional_properties
# =============================================================================


async def test_magentic_agent_run_update_event_with_agent_delta_metadata(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Test that AgentRunUpdateEvent with magentic_event_type='agent_delta' is handled correctly.

    This tests the ACTUAL event format Magentic emits - not a fake MagenticAgentDeltaEvent class.
    Magentic uses AgentRunUpdateEvent with additional_properties containing magentic_event_type.
    """
    from agent_framework._types import AgentResponseUpdate, Role
    from agent_framework._workflows._events import AgentRunUpdateEvent

    # Create the REAL event format that Magentic emits
    update = AgentResponseUpdate(
        contents=[Content.from_text(text="Hello from agent")],
        role=Role.ASSISTANT,
        author_name="Writer",
        additional_properties={
            "magentic_event_type": "agent_delta",
            "agent_id": "writer_agent",
        },
    )
    event = AgentRunUpdateEvent(executor_id="magentic_executor", data=update)

    events = await mapper.convert_event(event, test_request)

    # Should be treated as a regular AgentRunUpdateEvent with text content
    # The mapper should emit text delta events
    assert len(events) >= 1
    text_events = [e for e in events if getattr(e, "type", "") == "response.output_text.delta"]
    assert len(text_events) >= 1
    assert text_events[0].delta == "Hello from agent"


async def test_magentic_orchestrator_message_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test that AgentRunUpdateEvent with magentic_event_type='orchestrator_message' is handled.

    Magentic emits orchestrator planning/instruction messages using AgentRunUpdateEvent
    with additional_properties containing magentic_event_type='orchestrator_message'.
    """
    from agent_framework._types import AgentResponseUpdate, Role
    from agent_framework._workflows._events import AgentRunUpdateEvent

    # Create orchestrator message event (REAL format from Magentic)
    update = AgentResponseUpdate(
        contents=[Content.from_text(text="Planning: First, the writer will create content...")],
        role=Role.ASSISTANT,
        author_name="Orchestrator",
        additional_properties={
            "magentic_event_type": "orchestrator_message",
            "orchestrator_message_kind": "task_ledger",
            "orchestrator_id": "magentic_orchestrator",
        },
    )
    event = AgentRunUpdateEvent(executor_id="magentic_orchestrator", data=update)

    events = await mapper.convert_event(event, test_request)

    # Currently, mapper treats this as regular AgentRunUpdateEvent (no special handling)
    # This test documents the current behavior
    assert len(events) >= 1
    text_events = [e for e in events if getattr(e, "type", "") == "response.output_text.delta"]
    assert len(text_events) >= 1
    assert "Planning:" in text_events[0].delta


async def test_magentic_events_use_same_event_class_as_other_workflows(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """Verify Magentic uses the same AgentRunUpdateEvent class as other workflows.

    This test documents that Magentic does NOT define separate event classes like
    MagenticAgentDeltaEvent - it reuses AgentRunUpdateEvent with metadata in
    additional_properties. Any mapper code checking for 'MagenticAgentDeltaEvent'
    class names is dead code.
    """
    from agent_framework._types import AgentResponseUpdate, Role
    from agent_framework._workflows._events import AgentRunUpdateEvent

    # Create events the way different workflows do it
    # 1. Regular workflow (no additional_properties)
    regular_update = AgentResponseUpdate(
        contents=[Content.from_text(text="Regular workflow response")],
        role=Role.ASSISTANT,
    )
    regular_event = AgentRunUpdateEvent(executor_id="regular_executor", data=regular_update)

    # 2. Magentic workflow (with additional_properties)
    magentic_update = AgentResponseUpdate(
        contents=[Content.from_text(text="Magentic workflow response")],
        role=Role.ASSISTANT,
        additional_properties={"magentic_event_type": "agent_delta"},
    )
    magentic_event = AgentRunUpdateEvent(executor_id="magentic_executor", data=magentic_update)

    # Both should be the SAME class
    assert type(regular_event) is type(magentic_event)
    assert isinstance(regular_event, AgentRunUpdateEvent)
    assert isinstance(magentic_event, AgentRunUpdateEvent)

    # Both should be handled by the same isinstance check in mapper
    regular_events = await mapper.convert_event(regular_event, test_request)
    magentic_events = await mapper.convert_event(magentic_event, test_request)

    # Both produce text delta events
    regular_text = [e for e in regular_events if getattr(e, "type", "") == "response.output_text.delta"]
    magentic_text = [e for e in magentic_events if getattr(e, "type", "") == "response.output_text.delta"]

    assert len(regular_text) >= 1
    assert len(magentic_text) >= 1


# =============================================================================
# Unknown Content Fallback Tests
# =============================================================================


async def test_unknown_content_fallback(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test graceful handling of unknown content types."""

    class MockUnknownContent:
        def __init__(self):
            self.__class__.__name__ = "WeirdUnknownContent"

    context = mapper._get_or_create_context(test_request)
    unknown_content = MockUnknownContent()

    event = await mapper._create_unknown_content_event(unknown_content, context)

    assert event.type == "response.output_text.delta"
    assert "Unknown content type" in event.delta
    assert "WeirdUnknownContent" in event.delta


# =============================================================================
# WorkflowOutputEvent Tests
# =============================================================================


async def test_workflow_output_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowOutputEvent is converted to output_item.added."""
    from agent_framework._workflows._events import WorkflowOutputEvent

    event = WorkflowOutputEvent(data="Final workflow output", executor_id="final_executor")
    events = await mapper.convert_event(event, test_request)

    # WorkflowOutputEvent should emit output_item.added
    assert len(events) == 1
    assert events[0].type == "response.output_item.added"
    # Check item contains the output text
    item = events[0].item
    assert item.type == "message"
    assert any("Final workflow output" in str(c) for c in item.content)


async def test_workflow_output_event_with_list_data(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowOutputEvent with list data (common for sequential/concurrent workflows)."""
    from agent_framework import ChatMessage, Role
    from agent_framework._workflows._events import WorkflowOutputEvent

    # Sequential/Concurrent workflows often output list[ChatMessage]
    messages = [
        ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(text="World")]),
    ]
    event = WorkflowOutputEvent(data=messages, executor_id="complete")
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_item.added"


# =============================================================================
# WorkflowFailedEvent Tests
# =============================================================================


async def test_workflow_failed_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowFailedEvent is converted to response.failed."""
    from agent_framework._workflows._events import WorkflowErrorDetails, WorkflowFailedEvent

    details = WorkflowErrorDetails(
        error_type="TestError",
        message="Workflow failed due to test error",
        executor_id="failing_executor",
    )
    event = WorkflowFailedEvent(details=details)
    events = await mapper.convert_event(event, test_request)

    # WorkflowFailedEvent should emit response.failed
    assert len(events) >= 1
    # Find the failed event
    failed_events = [e for e in events if getattr(e, "type", "") == "response.failed"]
    assert len(failed_events) == 1, f"Expected response.failed, got types: {[getattr(e, 'type', '') for e in events]}"
    # Check response contains error info
    response = failed_events[0].response
    assert response.status == "failed"
    assert response.error is not None
    # Verify error message is correctly extracted from details.message (not "Unknown error")
    assert "Workflow failed due to test error" in response.error.message
    assert "Unknown error" not in response.error.message


async def test_workflow_failed_event_with_extra(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowFailedEvent includes extra context when available."""
    from agent_framework._workflows._events import WorkflowErrorDetails, WorkflowFailedEvent

    details = WorkflowErrorDetails(
        error_type="ValidationError",
        message="Input validation failed",
        executor_id="validation_executor",
        extra={"field": "email", "reason": "invalid format"},
    )
    event = WorkflowFailedEvent(details=details)
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.failed"
    response = events[0].response
    # Verify both the message and extra context are included
    assert "Input validation failed" in response.error.message
    assert "extra:" in response.error.message
    assert "email" in response.error.message


async def test_workflow_failed_event_with_traceback(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowFailedEvent includes traceback when available."""
    from agent_framework._workflows._events import WorkflowErrorDetails, WorkflowFailedEvent

    details = WorkflowErrorDetails(
        error_type="ValueError",
        message="Invalid input provided",
        traceback="Traceback (most recent call last):\n  File ...\nValueError: Invalid input",
        executor_id="validation_executor",
    )
    event = WorkflowFailedEvent(details=details)
    events = await mapper.convert_event(event, test_request)

    assert len(events) == 1
    assert events[0].type == "response.failed"


# =============================================================================
# WorkflowWarningEvent and WorkflowErrorEvent Tests
# =============================================================================


async def test_workflow_warning_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowWarningEvent is converted to trace event."""
    from agent_framework._workflows._events import WorkflowWarningEvent

    event = WorkflowWarningEvent(data="This is a warning message")
    events = await mapper.convert_event(event, test_request)

    # WorkflowWarningEvent should emit a trace event
    assert len(events) == 1
    assert events[0].type == "response.trace.completed"
    assert events[0].data["event_type"] == "WorkflowWarningEvent"


async def test_workflow_error_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test WorkflowErrorEvent is converted to trace event."""
    from agent_framework._workflows._events import WorkflowErrorEvent

    event = WorkflowErrorEvent(data=ValueError("Something went wrong"))
    events = await mapper.convert_event(event, test_request)

    # WorkflowErrorEvent should emit a trace event
    assert len(events) == 1
    assert events[0].type == "response.trace.completed"
    assert events[0].data["event_type"] == "WorkflowErrorEvent"


# =============================================================================
# RequestInfoEvent Tests (Human-in-the-Loop)
# =============================================================================


async def test_request_info_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test RequestInfoEvent is converted to HIL request event."""
    from agent_framework._workflows._events import RequestInfoEvent

    event = RequestInfoEvent(
        request_id="req_123",
        source_executor_id="approval_executor",
        request_data={"action": "approve", "details": "Please approve this action"},
        response_type=str,
    )
    events = await mapper.convert_event(event, test_request)

    # RequestInfoEvent should emit response.request_info.requested
    assert len(events) >= 1
    # Check that request info is captured
    has_hil_event = any(getattr(e, "type", "") == "response.request_info.requested" for e in events)
    assert has_hil_event, f"Expected response.request_info.requested, got: {[getattr(e, 'type', '') for e in events]}"

    # Verify the event contains the expected data
    hil_event = [e for e in events if getattr(e, "type", "") == "response.request_info.requested"][0]
    assert hil_event.request_id == "req_123"
    assert hil_event.source_executor_id == "approval_executor"


# =============================================================================
# SuperStep Event Tests
# =============================================================================


async def test_superstep_started_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test SuperStepStartedEvent is handled gracefully."""
    from agent_framework._workflows._events import SuperStepStartedEvent

    event = SuperStepStartedEvent(iteration=1)
    events = await mapper.convert_event(event, test_request)

    # SuperStepStartedEvent may not emit events (internal workflow signal)
    # Just ensure it doesn't crash
    assert isinstance(events, list)


async def test_superstep_completed_event(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test SuperStepCompletedEvent is handled gracefully."""
    from agent_framework._workflows._events import SuperStepCompletedEvent

    event = SuperStepCompletedEvent(iteration=1)
    events = await mapper.convert_event(event, test_request)

    # SuperStepCompletedEvent may not emit events (internal workflow signal)
    # Just ensure it doesn't crash
    assert isinstance(events, list)
