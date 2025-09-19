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
from agent_framework._types import AgentRunResponseUpdate, ErrorContent, FunctionCallContent, Role, TextContent

from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import AgentFrameworkExtraBody, AgentFrameworkRequest


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
    return AgentFrameworkRequest(
        model="agent-framework",
        input="Test input",
        stream=True,
        extra_body=AgentFrameworkExtraBody(entity_id="test_agent"),
    )


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_text_content_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test TextContent mapping."""
    content = create_test_content("text", text="Hello, clean test!")
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_text.delta"
    assert events[0].delta == "Hello, clean test!"


@pytest.mark.asyncio
async def test_function_call_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test FunctionCallContent mapping."""
    content = create_test_content("function_call", name="test_func", arguments={"location": "TestCity"})
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) >= 1
    assert all(event.type == "response.function_call_arguments.delta" for event in events)

    # Check JSON is chunked
    full_json = "".join(event.delta for event in events)
    assert "TestCity" in full_json


@pytest.mark.asyncio
async def test_error_content_mapping(mapper: MessageMapper, test_request: AgentFrameworkRequest) -> None:
    """Test ErrorContent mapping."""
    content = create_test_content("error", message="Test error", code="test_code")
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) == 1
    assert events[0].type == "error"
    assert events[0].message == "Test error"
    assert events[0].code == "test_code"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


if __name__ == "__main__":
    # Simple test runner
    async def run_all_tests() -> None:
        mapper = MessageMapper()
        test_request = AgentFrameworkRequest(
            model="agent-framework", input="Test", stream=True, extra_body=AgentFrameworkExtraBody(entity_id="test")
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
