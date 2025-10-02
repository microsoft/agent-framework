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
    """Test TextContent mapping."""
    content = create_test_content("text", text="Hello, clean test!")
    update = create_test_agent_update([content])

    events = await mapper.convert_event(update, test_request)

    assert len(events) == 1
    assert events[0].type == "response.output_text.delta"
    assert events[0].delta == "Hello, clean test!"


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


def test_serialize_payload_primitives(mapper: MessageMapper) -> None:
    """Test serialization of primitive types."""
    assert mapper._serialize_payload(None) is None
    assert mapper._serialize_payload("test") == "test"
    assert mapper._serialize_payload(42) == 42
    assert mapper._serialize_payload(3.14) == 3.14
    assert mapper._serialize_payload(True) is True
    assert mapper._serialize_payload(False) is False


def test_serialize_payload_sequences(mapper: MessageMapper) -> None:
    """Test serialization of lists, tuples, and sets."""
    # List
    result = mapper._serialize_payload([1, 2, "three"])
    assert result == [1, 2, "three"]
    assert isinstance(result, list)

    # Tuple - should convert to list
    result = mapper._serialize_payload((1, 2, "three"))
    assert result == [1, 2, "three"]
    assert isinstance(result, list)

    # Set - should convert to list (order may vary)
    result = mapper._serialize_payload({1, 2, 3})
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}

    # Nested sequences
    result = mapper._serialize_payload([1, [2, 3], (4, 5)])
    assert result == [1, [2, 3], [4, 5]]


def test_serialize_payload_dicts(mapper: MessageMapper) -> None:
    """Test serialization of dictionaries."""
    # Simple dict
    result = mapper._serialize_payload({"a": 1, "b": 2})
    assert result == {"a": 1, "b": 2}

    # Dict with non-string keys (should convert to string)
    result = mapper._serialize_payload({1: "one", 2: "two"})
    assert result == {"1": "one", "2": "two"}

    # Nested dicts
    result = mapper._serialize_payload({"outer": {"inner": {"deep": 42}}})
    assert result == {"outer": {"inner": {"deep": 42}}}

    # Dict with mixed value types
    result = mapper._serialize_payload({"str": "text", "num": 123, "list": [1, 2], "dict": {"nested": True}})
    assert result == {"str": "text", "num": 123, "list": [1, 2], "dict": {"nested": True}}


def test_serialize_payload_dataclass(mapper: MessageMapper) -> None:
    """Test serialization of dataclasses."""
    from dataclasses import dataclass

    @dataclass
    class Person:
        name: str
        age: int
        active: bool = True

    person = Person(name="Alice", age=30)
    result = mapper._serialize_payload(person)

    assert result == {"name": "Alice", "age": 30, "active": True}
    assert isinstance(result, dict)


def test_serialize_payload_pydantic_model(mapper: MessageMapper) -> None:
    """Test serialization of Pydantic models."""
    from pydantic import BaseModel

    class User(BaseModel):
        username: str
        email: str
        is_active: bool = True

    user = User(username="testuser", email="test@example.com")
    result = mapper._serialize_payload(user)

    assert result == {"username": "testuser", "email": "test@example.com", "is_active": True}
    assert isinstance(result, dict)


def test_serialize_payload_nested_pydantic(mapper: MessageMapper) -> None:
    """Test serialization of nested Pydantic models."""
    from pydantic import BaseModel

    class Address(BaseModel):
        street: str
        city: str

    class Person(BaseModel):
        name: str
        address: Address

    person = Person(name="Bob", address=Address(street="123 Main St", city="Springfield"))
    result = mapper._serialize_payload(person)

    assert result == {"name": "Bob", "address": {"street": "123 Main St", "city": "Springfield"}}


def test_serialize_payload_object_with_dict_method(mapper: MessageMapper) -> None:
    """Test serialization of objects with dict() method."""

    class CustomObject:
        def __init__(self):
            self.value = 42

        def dict(self):
            return {"value": self.value, "type": "custom"}

    obj = CustomObject()
    result = mapper._serialize_payload(obj)

    assert result == {"value": 42, "type": "custom"}


def test_serialize_payload_object_with_to_dict_method(mapper: MessageMapper) -> None:
    """Test serialization of objects with to_dict() method."""

    class CustomObject:
        def __init__(self):
            self.value = 42

        def to_dict(self):
            return {"value": self.value, "type": "custom_to_dict"}

    obj = CustomObject()
    result = mapper._serialize_payload(obj)

    assert result == {"value": 42, "type": "custom_to_dict"}


def test_serialize_payload_object_with_model_dump_json(mapper: MessageMapper) -> None:
    """Test serialization of objects with model_dump_json() method."""
    import json

    class CustomObject:
        def __init__(self):
            self.value = 42

        def model_dump_json(self):
            return json.dumps({"value": self.value, "type": "json_dump"})

    obj = CustomObject()
    result = mapper._serialize_payload(obj)

    assert result == {"value": 42, "type": "json_dump"}


def test_serialize_payload_object_with_dict_attr(mapper: MessageMapper) -> None:
    """Test serialization of objects with __dict__ attribute."""

    class SimpleObject:
        def __init__(self):
            self.public_value = 42
            self._private_value = 100  # Should be excluded

    obj = SimpleObject()
    result = mapper._serialize_payload(obj)

    assert "public_value" in result
    assert result["public_value"] == 42
    assert "_private_value" not in result


def test_serialize_payload_fallback_to_string(mapper: MessageMapper) -> None:
    """Test that unserializable objects fall back to string representation."""

    class WeirdObject:
        __slots__ = ()  # Prevent __dict__ attribute

        def __str__(self):
            return "weird_object_string"

    obj = WeirdObject()
    result = mapper._serialize_payload(obj)

    assert result == "weird_object_string"


def test_serialize_payload_complex_nested(mapper: MessageMapper) -> None:
    """Test serialization of complex nested structures."""
    from dataclasses import dataclass

    from pydantic import BaseModel

    @dataclass
    class DataItem:
        value: int

    class ConfigModel(BaseModel):
        enabled: bool
        count: int

    complex_data = {
        "items": [DataItem(value=1), DataItem(value=2)],
        "config": ConfigModel(enabled=True, count=5),
        "nested": {"list": [1, 2, 3], "tuple": (4, 5, 6)},
        "primitive": 42,
    }

    result = mapper._serialize_payload(complex_data)

    assert result["items"] == [{"value": 1}, {"value": 2}]
    assert result["config"] == {"enabled": True, "count": 5}
    assert result["nested"] == {"list": [1, 2, 3], "tuple": [4, 5, 6]}
    assert result["primitive"] == 42


if __name__ == "__main__":
    # Simple test runner
    async def run_all_tests() -> None:
        mapper = MessageMapper()
        test_request = AgentFrameworkRequest(
            model="agent-framework", input="Test", stream=True, extra_body=AgentFrameworkExtraBody(entity_id="test")
        )

        async_tests = [
            ("Critical isinstance bug detection", test_critical_isinstance_bug_detection),
            ("Text content mapping", test_text_content_mapping),
            ("Function call mapping", test_function_call_mapping),
            ("Error content mapping", test_error_content_mapping),
            ("Mixed content types", test_mixed_content_types),
            ("Unknown content fallback", test_unknown_content_fallback),
        ]

        sync_tests = [
            ("Serialize primitives", test_serialize_payload_primitives),
            ("Serialize sequences", test_serialize_payload_sequences),
            ("Serialize dicts", test_serialize_payload_dicts),
            ("Serialize dataclass", test_serialize_payload_dataclass),
            ("Serialize pydantic model", test_serialize_payload_pydantic_model),
            ("Serialize nested pydantic", test_serialize_payload_nested_pydantic),
            ("Serialize dict method", test_serialize_payload_object_with_dict_method),
            ("Serialize to_dict method", test_serialize_payload_object_with_to_dict_method),
            ("Serialize model_dump_json", test_serialize_payload_object_with_model_dump_json),
            ("Serialize __dict__ attr", test_serialize_payload_object_with_dict_attr),
            ("Serialize fallback to string", test_serialize_payload_fallback_to_string),
            ("Serialize complex nested", test_serialize_payload_complex_nested),
        ]

        passed = 0
        for _test_name, test_func in async_tests:
            try:
                await test_func(mapper, test_request)
                passed += 1
            except Exception:
                pass

        for _test_name, test_func in sync_tests:
            try:
                test_func(mapper)
                passed += 1
            except Exception:
                pass

    asyncio.run(run_all_tests())
