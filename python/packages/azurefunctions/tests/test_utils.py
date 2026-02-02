# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow utility functions."""

from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    ChatMessage,
    Message,
    WorkflowOutputEvent,
)
from pydantic import BaseModel

from agent_framework_azurefunctions._utils import (
    CapturingRunnerContext,
    deserialize_value,
    reconstruct_agent_executor_request,
    reconstruct_agent_executor_response,
    reconstruct_message_for_handler,
    serialize_message,
)


class TestCapturingRunnerContext:
    """Test suite for CapturingRunnerContext."""

    @pytest.fixture
    def context(self) -> CapturingRunnerContext:
        """Create a fresh CapturingRunnerContext for each test."""
        return CapturingRunnerContext()

    @pytest.mark.asyncio
    async def test_send_message_captures_message(self, context: CapturingRunnerContext) -> None:
        """Test that send_message captures messages correctly."""
        message = Message(data="test data", target_id="target_1", source_id="source_1")

        await context.send_message(message)

        messages = await context.drain_messages()
        assert "source_1" in messages
        assert len(messages["source_1"]) == 1
        assert messages["source_1"][0].data == "test data"

    @pytest.mark.asyncio
    async def test_send_multiple_messages_groups_by_source(self, context: CapturingRunnerContext) -> None:
        """Test that messages are grouped by source_id."""
        msg1 = Message(data="msg1", target_id="target", source_id="source_a")
        msg2 = Message(data="msg2", target_id="target", source_id="source_a")
        msg3 = Message(data="msg3", target_id="target", source_id="source_b")

        await context.send_message(msg1)
        await context.send_message(msg2)
        await context.send_message(msg3)

        messages = await context.drain_messages()
        assert len(messages["source_a"]) == 2
        assert len(messages["source_b"]) == 1

    @pytest.mark.asyncio
    async def test_drain_messages_clears_messages(self, context: CapturingRunnerContext) -> None:
        """Test that drain_messages clears the message store."""
        message = Message(data="test", target_id="t", source_id="s")
        await context.send_message(message)

        await context.drain_messages()  # First drain
        messages = await context.drain_messages()  # Second drain

        assert messages == {}

    @pytest.mark.asyncio
    async def test_has_messages_returns_correct_status(self, context: CapturingRunnerContext) -> None:
        """Test has_messages returns correct boolean."""
        assert await context.has_messages() is False

        await context.send_message(Message(data="test", target_id="t", source_id="s"))

        assert await context.has_messages() is True

    @pytest.mark.asyncio
    async def test_add_event_queues_event(self, context: CapturingRunnerContext) -> None:
        """Test that add_event queues events correctly."""
        event = WorkflowOutputEvent(data="output", executor_id="exec_1")

        await context.add_event(event)

        events = await context.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowOutputEvent)
        assert events[0].data == "output"

    @pytest.mark.asyncio
    async def test_drain_events_clears_queue(self, context: CapturingRunnerContext) -> None:
        """Test that drain_events clears the event queue."""
        await context.add_event(WorkflowOutputEvent(data="test", executor_id="e"))

        await context.drain_events()  # First drain
        events = await context.drain_events()  # Second drain

        assert events == []

    @pytest.mark.asyncio
    async def test_has_events_returns_correct_status(self, context: CapturingRunnerContext) -> None:
        """Test has_events returns correct boolean."""
        assert await context.has_events() is False

        await context.add_event(WorkflowOutputEvent(data="test", executor_id="e"))

        assert await context.has_events() is True

    @pytest.mark.asyncio
    async def test_next_event_waits_for_event(self, context: CapturingRunnerContext) -> None:
        """Test that next_event returns queued events."""
        event = WorkflowOutputEvent(data="waited", executor_id="e")
        await context.add_event(event)

        result = await context.next_event()

        assert result.data == "waited"

    def test_has_checkpointing_returns_false(self, context: CapturingRunnerContext) -> None:
        """Test that checkpointing is not supported."""
        assert context.has_checkpointing() is False

    def test_is_streaming_returns_false_by_default(self, context: CapturingRunnerContext) -> None:
        """Test streaming is disabled by default."""
        assert context.is_streaming() is False

    def test_set_streaming(self, context: CapturingRunnerContext) -> None:
        """Test setting streaming mode."""
        context.set_streaming(True)
        assert context.is_streaming() is True

        context.set_streaming(False)
        assert context.is_streaming() is False

    def test_set_workflow_id(self, context: CapturingRunnerContext) -> None:
        """Test setting workflow ID."""
        context.set_workflow_id("workflow-123")
        assert context._workflow_id == "workflow-123"

    @pytest.mark.asyncio
    async def test_reset_for_new_run_clears_state(self, context: CapturingRunnerContext) -> None:
        """Test that reset_for_new_run clears all state."""
        await context.send_message(Message(data="test", target_id="t", source_id="s"))
        await context.add_event(WorkflowOutputEvent(data="event", executor_id="e"))
        context.set_streaming(True)

        context.reset_for_new_run()

        assert await context.has_messages() is False
        assert await context.has_events() is False
        assert context.is_streaming() is False

    @pytest.mark.asyncio
    async def test_create_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that checkpointing methods raise NotImplementedError."""
        from agent_framework import SharedState

        with pytest.raises(NotImplementedError):
            await context.create_checkpoint(SharedState(), 1)

    @pytest.mark.asyncio
    async def test_load_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that load_checkpoint raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await context.load_checkpoint("some-id")

    @pytest.mark.asyncio
    async def test_apply_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that apply_checkpoint raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await context.apply_checkpoint(Mock())


class TestSerializeMessage:
    """Test suite for serialize_message function."""

    def test_serialize_none(self) -> None:
        """Test serializing None."""
        assert serialize_message(None) is None

    def test_serialize_primitive_types(self) -> None:
        """Test serializing primitive types."""
        assert serialize_message("hello") == "hello"
        assert serialize_message(42) == 42
        assert serialize_message(3.14) == 3.14
        assert serialize_message(True) is True

    def test_serialize_list(self) -> None:
        """Test serializing lists."""
        result = serialize_message([1, 2, 3])
        assert result == [1, 2, 3]

    def test_serialize_dict(self) -> None:
        """Test serializing dicts."""
        result = serialize_message({"key": "value", "num": 42})
        assert result == {"key": "value", "num": 42}

    def test_serialize_dataclass(self) -> None:
        """Test serializing dataclasses with type metadata."""

        @dataclass
        class TestData:
            name: str
            value: int

        data = TestData(name="test", value=123)
        result = serialize_message(data)

        assert result["name"] == "test"
        assert result["value"] == 123
        assert result["__type__"] == "TestData"
        assert "__module__" in result

    def test_serialize_pydantic_model(self) -> None:
        """Test serializing Pydantic models with type metadata."""

        class TestModel(BaseModel):
            title: str
            count: int

        model = TestModel(title="Hello", count=5)
        result = serialize_message(model)

        assert result["title"] == "Hello"
        assert result["count"] == 5
        assert result["__type__"] == "TestModel"
        assert "__module__" in result

    def test_serialize_nested_structures(self) -> None:
        """Test serializing nested structures."""

        @dataclass
        class Inner:
            x: int

        @dataclass
        class Outer:
            inner: Inner
            items: list[int]

        outer = Outer(inner=Inner(x=10), items=[1, 2, 3])
        result = serialize_message(outer)

        assert result["__type__"] == "Outer"
        # Nested dataclass is serialized via asdict, which doesn't add __type__ recursively
        assert result["inner"]["x"] == 10
        assert result["items"] == [1, 2, 3]

    def test_serialize_object_with_to_dict(self) -> None:
        """Test serializing objects with to_dict method."""
        message = ChatMessage(role="user", text="Hello")
        result = serialize_message(message)

        # ChatMessage has to_dict() method which returns a specific structure
        assert isinstance(result, dict)
        assert "contents" in result  # ChatMessage uses contents structure


class TestDeserializeValue:
    """Test suite for deserialize_value function."""

    def test_deserialize_non_dict_returns_original(self) -> None:
        """Test that non-dict values are returned as-is."""
        assert deserialize_value("string") == "string"
        assert deserialize_value(42) == 42
        assert deserialize_value([1, 2, 3]) == [1, 2, 3]

    def test_deserialize_dict_without_type_returns_original(self) -> None:
        """Test that dicts without type metadata are returned as-is."""
        data = {"key": "value", "num": 42}
        result = deserialize_value(data)
        assert result == data

    def test_deserialize_agent_executor_request(self) -> None:
        """Test deserializing AgentExecutorRequest."""
        data = {
            "messages": [{"type": "chat_message", "role": "user", "contents": [{"type": "text", "text": "Hello"}]}],
            "should_respond": True,
        }

        result = deserialize_value(data)

        assert isinstance(result, AgentExecutorRequest)
        assert len(result.messages) == 1
        assert result.should_respond is True

    def test_deserialize_agent_executor_response(self) -> None:
        """Test deserializing AgentExecutorResponse."""
        data = {
            "executor_id": "test_exec",
            "agent_response": {
                "type": "agent_response",
                "messages": [
                    {"type": "chat_message", "role": "assistant", "contents": [{"type": "text", "text": "Hi there"}]}
                ],
            },
        }

        result = deserialize_value(data)

        assert isinstance(result, AgentExecutorResponse)
        assert result.executor_id == "test_exec"

    def test_deserialize_with_type_registry(self) -> None:
        """Test deserializing with type registry."""

        @dataclass
        class CustomType:
            name: str

        data = {"name": "test", "__type__": "CustomType"}
        result = deserialize_value(data, type_registry={"CustomType": CustomType})

        assert isinstance(result, CustomType)
        assert result.name == "test"


class TestReconstructAgentExecutorRequest:
    """Test suite for reconstruct_agent_executor_request function."""

    def test_reconstruct_with_chat_messages(self) -> None:
        """Test reconstructing request with ChatMessage dicts."""
        data = {
            "messages": [
                {"type": "chat_message", "role": "user", "contents": [{"type": "text", "text": "Hello"}]},
                {"type": "chat_message", "role": "assistant", "contents": [{"type": "text", "text": "Hi"}]},
            ],
            "should_respond": True,
        }

        result = reconstruct_agent_executor_request(data)

        assert isinstance(result, AgentExecutorRequest)
        assert len(result.messages) == 2
        assert result.should_respond is True

    def test_reconstruct_defaults_should_respond_to_true(self) -> None:
        """Test that should_respond defaults to True."""
        data = {"messages": []}

        result = reconstruct_agent_executor_request(data)

        assert result.should_respond is True


class TestReconstructAgentExecutorResponse:
    """Test suite for reconstruct_agent_executor_response function."""

    def test_reconstruct_with_agent_response(self) -> None:
        """Test reconstructing response with agent_response."""
        data = {
            "executor_id": "my_executor",
            "agent_response": {
                "type": "agent_response",
                "messages": [
                    {"type": "chat_message", "role": "assistant", "contents": [{"type": "text", "text": "Response"}]}
                ],
            },
            "full_conversation": [],
        }

        result = reconstruct_agent_executor_response(data)

        assert isinstance(result, AgentExecutorResponse)
        assert result.executor_id == "my_executor"
        assert isinstance(result.agent_response, AgentResponse)

    def test_reconstruct_with_full_conversation(self) -> None:
        """Test reconstructing response with full_conversation."""
        data = {
            "executor_id": "exec",
            "agent_response": {"type": "agent_response", "messages": []},
            "full_conversation": [
                {"type": "chat_message", "role": "user", "contents": [{"type": "text", "text": "Q"}]},
                {"type": "chat_message", "role": "assistant", "contents": [{"type": "text", "text": "A"}]},
            ],
        }

        result = reconstruct_agent_executor_response(data)

        assert result.full_conversation is not None
        assert len(result.full_conversation) == 2


class TestReconstructMessageForHandler:
    """Test suite for reconstruct_message_for_handler function."""

    def test_reconstruct_non_dict_returns_original(self) -> None:
        """Test that non-dict messages are returned as-is."""
        assert reconstruct_message_for_handler("string", []) == "string"
        assert reconstruct_message_for_handler(42, []) == 42

    def test_reconstruct_agent_executor_response(self) -> None:
        """Test reconstructing AgentExecutorResponse."""
        data = {
            "executor_id": "exec",
            "agent_response": {"type": "agent_response", "messages": []},
        }

        result = reconstruct_message_for_handler(data, [AgentExecutorResponse])

        assert isinstance(result, AgentExecutorResponse)

    def test_reconstruct_agent_executor_request(self) -> None:
        """Test reconstructing AgentExecutorRequest."""
        data = {
            "messages": [{"type": "chat_message", "role": "user", "contents": [{"type": "text", "text": "Hi"}]}],
            "should_respond": True,
        }

        result = reconstruct_message_for_handler(data, [AgentExecutorRequest])

        assert isinstance(result, AgentExecutorRequest)

    def test_reconstruct_with_type_metadata(self) -> None:
        """Test reconstructing using __type__ metadata."""

        @dataclass
        class CustomMsg:
            content: str

        # Serialize includes type metadata
        serialized = serialize_message(CustomMsg(content="test"))

        result = reconstruct_message_for_handler(serialized, [CustomMsg])

        assert isinstance(result, CustomMsg)
        assert result.content == "test"

    def test_reconstruct_matches_dataclass_fields(self) -> None:
        """Test reconstruction by matching dataclass field names."""

        @dataclass
        class MyData:
            field_a: str
            field_b: int

        data = {"field_a": "hello", "field_b": 42}

        result = reconstruct_message_for_handler(data, [MyData])

        assert isinstance(result, MyData)
        assert result.field_a == "hello"
        assert result.field_b == 42

    def test_reconstruct_returns_original_if_no_match(self) -> None:
        """Test that original dict is returned if no type matches."""

        @dataclass
        class UnrelatedType:
            completely_different_field: str

        data = {"some_key": "some_value"}

        result = reconstruct_message_for_handler(data, [UnrelatedType])

        assert result == data
