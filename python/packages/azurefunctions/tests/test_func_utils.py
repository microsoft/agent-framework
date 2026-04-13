# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow utility functions."""

from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Message,
    WorkflowEvent,
    WorkflowMessage,
)
from pydantic import BaseModel

from agent_framework_azurefunctions._context import CapturingRunnerContext
from agent_framework_azurefunctions._serialization import (
    deserialize_value,
    reconstruct_to_type,
    serialize_value,
    strip_pickle_markers,
)


# Module-level test types (must be importable for checkpoint encoding roundtrip)
@dataclass
class SampleData:
    """Sample dataclass for testing checkpoint encoding roundtrip."""

    name: str
    value: int


class SampleModel(BaseModel):
    """Sample Pydantic model for testing checkpoint encoding roundtrip."""

    title: str
    count: int


@dataclass
class DataclassWithPydanticField:
    """Dataclass containing a Pydantic model field for testing nested serialization."""

    label: str
    model: SampleModel


class TestCapturingRunnerContext:
    """Test suite for CapturingRunnerContext."""

    @pytest.fixture
    def context(self) -> CapturingRunnerContext:
        """Create a fresh CapturingRunnerContext for each test."""
        return CapturingRunnerContext()

    @pytest.mark.asyncio
    async def test_send_message_captures_message(self, context: CapturingRunnerContext) -> None:
        """Test that send_message captures messages correctly."""
        message = WorkflowMessage(data="test data", target_id="target_1", source_id="source_1")

        await context.send_message(message)

        messages = await context.drain_messages()
        assert "source_1" in messages
        assert len(messages["source_1"]) == 1
        assert messages["source_1"][0].data == "test data"

    @pytest.mark.asyncio
    async def test_send_multiple_messages_groups_by_source(self, context: CapturingRunnerContext) -> None:
        """Test that messages are grouped by source_id."""
        msg1 = WorkflowMessage(data="msg1", target_id="target", source_id="source_a")
        msg2 = WorkflowMessage(data="msg2", target_id="target", source_id="source_a")
        msg3 = WorkflowMessage(data="msg3", target_id="target", source_id="source_b")

        await context.send_message(msg1)
        await context.send_message(msg2)
        await context.send_message(msg3)

        messages = await context.drain_messages()
        assert len(messages["source_a"]) == 2
        assert len(messages["source_b"]) == 1

    @pytest.mark.asyncio
    async def test_drain_messages_clears_messages(self, context: CapturingRunnerContext) -> None:
        """Test that drain_messages clears the message store."""
        message = WorkflowMessage(data="test", target_id="t", source_id="s")
        await context.send_message(message)

        await context.drain_messages()  # First drain
        messages = await context.drain_messages()  # Second drain

        assert messages == {}

    @pytest.mark.asyncio
    async def test_has_messages_returns_correct_status(self, context: CapturingRunnerContext) -> None:
        """Test has_messages returns correct boolean."""
        assert await context.has_messages() is False

        await context.send_message(WorkflowMessage(data="test", target_id="t", source_id="s"))

        assert await context.has_messages() is True

    @pytest.mark.asyncio
    async def test_add_event_queues_event(self, context: CapturingRunnerContext) -> None:
        """Test that add_event queues events correctly."""
        event = WorkflowEvent.output(executor_id="exec_1", data="output")

        await context.add_event(event)

        events = await context.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowEvent)
        assert events[0].type == "output"
        assert events[0].data == "output"

    @pytest.mark.asyncio
    async def test_drain_events_clears_queue(self, context: CapturingRunnerContext) -> None:
        """Test that drain_events clears the event queue."""
        await context.add_event(WorkflowEvent.output(executor_id="e", data="test"))

        await context.drain_events()  # First drain
        events = await context.drain_events()  # Second drain

        assert events == []

    @pytest.mark.asyncio
    async def test_has_events_returns_correct_status(self, context: CapturingRunnerContext) -> None:
        """Test has_events returns correct boolean."""
        assert await context.has_events() is False

        await context.add_event(WorkflowEvent.output(executor_id="e", data="test"))

        assert await context.has_events() is True

    @pytest.mark.asyncio
    async def test_next_event_waits_for_event(self, context: CapturingRunnerContext) -> None:
        """Test that next_event returns queued events."""
        event = WorkflowEvent.output(executor_id="e", data="waited")
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
        await context.send_message(WorkflowMessage(data="test", target_id="t", source_id="s"))
        await context.add_event(WorkflowEvent.output(executor_id="e", data="event"))
        context.set_streaming(True)

        context.reset_for_new_run()

        assert await context.has_messages() is False
        assert await context.has_events() is False
        assert context.is_streaming() is False

    @pytest.mark.asyncio
    async def test_create_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that checkpointing methods raise NotImplementedError."""
        from agent_framework._workflows._state import State

        with pytest.raises(NotImplementedError):
            await context.create_checkpoint("test_workflow", "abc123", State(), None, 1)

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


class TestSerializationRoundtrip:
    """Test that serialization roundtrips correctly for types used in Azure Functions workflows."""

    def test_roundtrip_chat_message(self) -> None:
        """Test Message survives encode → decode roundtrip."""
        original = Message(role="user", contents=["Hello"])
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, Message)
        assert decoded.role == "user"

    def test_roundtrip_agent_executor_request(self) -> None:
        """Test AgentExecutorRequest with nested Messages roundtrips."""
        original = AgentExecutorRequest(
            messages=[Message(role="user", contents=["Hi"])],
            should_respond=True,
        )
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, AgentExecutorRequest)
        assert len(decoded.messages) == 1
        assert isinstance(decoded.messages[0], Message)
        assert decoded.should_respond is True

    def test_roundtrip_agent_executor_response(self) -> None:
        """Test AgentExecutorResponse with nested AgentResponse roundtrips."""
        original = AgentExecutorResponse(
            executor_id="test_exec",
            agent_response=AgentResponse(messages=[Message(role="assistant", contents=["Reply"])]),
            full_conversation=[Message(role="assistant", contents=["Reply"])],
        )
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, AgentExecutorResponse)
        assert decoded.executor_id == "test_exec"
        assert isinstance(decoded.agent_response, AgentResponse)

    def test_roundtrip_dataclass(self) -> None:
        """Test custom dataclass roundtrips."""
        original = SampleData(name="test", value=42)
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, SampleData)
        assert decoded.name == "test"
        assert decoded.value == 42

    def test_roundtrip_pydantic_model(self) -> None:
        """Test Pydantic model roundtrips."""
        original = SampleModel(title="Hello", count=5)
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, SampleModel)
        assert decoded.title == "Hello"
        assert decoded.count == 5

    def test_roundtrip_primitives(self) -> None:
        """Test primitives pass through unchanged."""
        assert serialize_value(None) is None
        assert serialize_value("hello") == "hello"
        assert serialize_value(42) == 42
        assert serialize_value(3.14) == 3.14
        assert serialize_value(True) is True

    def test_roundtrip_list_of_objects(self) -> None:
        """Test list of typed objects roundtrips."""
        original = [
            Message(role="user", contents=["Q"]),
            Message(role="assistant", contents=["A"]),
        ]
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, list)
        assert len(decoded) == 2
        assert all(isinstance(m, Message) for m in decoded)

    def test_roundtrip_dict_of_objects(self) -> None:
        """Test dict with typed values roundtrips (used for shared state)."""
        original = {"count": 42, "msg": Message(role="user", contents=["Hi"])}
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert decoded["count"] == 42
        assert isinstance(decoded["msg"], Message)

    def test_roundtrip_dataclass_with_nested_pydantic(self) -> None:
        """Test dataclass containing a Pydantic model field roundtrips correctly.

        This covers the HITL pattern where AnalysisWithSubmission (dataclass)
        contains a ContentAnalysisResult (Pydantic BaseModel) field.
        """
        original = DataclassWithPydanticField(label="test", model=SampleModel(title="Nested", count=99))
        encoded = serialize_value(original)
        decoded = deserialize_value(encoded)

        assert isinstance(decoded, DataclassWithPydanticField)
        assert decoded.label == "test"
        assert isinstance(decoded.model, SampleModel)
        assert decoded.model.title == "Nested"
        assert decoded.model.count == 99


class TestReconstructToType:
    """Test suite for reconstruct_to_type function (used for HITL responses)."""

    def test_none_returns_none(self) -> None:
        """Test that None input returns None."""
        assert reconstruct_to_type(None, str) is None

    def test_already_correct_type(self) -> None:
        """Test that values already of the correct type are returned as-is."""
        assert reconstruct_to_type("hello", str) == "hello"
        assert reconstruct_to_type(42, int) == 42

    def test_non_dict_returns_original(self) -> None:
        """Test that non-dict values are returned as-is."""
        assert reconstruct_to_type("hello", int) == "hello"
        assert reconstruct_to_type([1, 2], dict) == [1, 2]

    def test_reconstruct_pydantic_model(self) -> None:
        """Test reconstruction of Pydantic model from plain dict."""

        class ApprovalResponse(BaseModel):
            approved: bool
            reason: str

        data = {"approved": True, "reason": "Looks good"}
        result = reconstruct_to_type(data, ApprovalResponse)

        assert isinstance(result, ApprovalResponse)
        assert result.approved is True
        assert result.reason == "Looks good"

    def test_reconstruct_dataclass(self) -> None:
        """Test reconstruction of dataclass from plain dict."""

        @dataclass
        class Feedback:
            score: int
            comment: str

        data = {"score": 5, "comment": "Great"}
        result = reconstruct_to_type(data, Feedback)

        assert isinstance(result, Feedback)
        assert result.score == 5
        assert result.comment == "Great"

    def test_reconstruct_from_checkpoint_markers(self) -> None:
        """Test that data with checkpoint markers is decoded via deserialize_value.

        reconstruct_to_type is general-purpose and handles trusted checkpoint
        data.  Untrusted HITL callers must call strip_pickle_markers() first.
        """
        original = SampleData(value=99, name="marker-test")
        encoded = serialize_value(original)

        result = reconstruct_to_type(encoded, SampleData)
        assert isinstance(result, SampleData)
        assert result.value == 99

    def test_unrecognized_dict_returns_original(self) -> None:
        """Test that unrecognized dicts are returned as-is."""

        @dataclass
        class Unrelated:
            completely_different: str

        data = {"some_key": "some_value"}
        result = reconstruct_to_type(data, Unrelated)

        assert result == data

    def test_reconstruct_strips_injected_pickle_markers(self) -> None:
        """End-to-end: strip_pickle_markers + reconstruct_to_type blocks attack.

        This mirrors the real HITL flow where callers sanitize before reconstruction.
        """
        malicious = {"__pickled__": "gASVDgAAAAAAAACMBHRlc3SULg==", "__type__": "builtins:str"}
        sanitized = strip_pickle_markers(malicious)
        result = reconstruct_to_type(sanitized, str)
        assert result is None


class TestStripPickleMarkers:
    """Security tests for strip_pickle_markers — the defence-in-depth layer
    that prevents untrusted HTTP input from reaching pickle.loads()."""

    def test_strips_top_level_pickle_marker(self) -> None:
        """A dict containing __pickled__ must be replaced with None."""
        data = {"__pickled__": "PAYLOAD", "__type__": "os:system"}
        assert strip_pickle_markers(data) is None

    def test_strips_top_level_type_marker_only(self) -> None:
        """Even __type__ alone (without __pickled__) must be neutralised."""
        data = {"__type__": "os:system", "other": "value"}
        assert strip_pickle_markers(data) is None

    def test_strips_nested_pickle_marker(self) -> None:
        """Pickle markers nested inside a dict must be neutralised."""
        data = {"safe": "value", "nested": {"__pickled__": "PAYLOAD", "__type__": "os:system"}}
        result = strip_pickle_markers(data)
        assert result == {"safe": "value", "nested": None}

    def test_strips_pickle_marker_in_list(self) -> None:
        """Pickle markers inside a list element must be neutralised."""
        data = [{"__pickled__": "PAYLOAD"}, "safe"]
        result = strip_pickle_markers(data)
        assert result == [None, "safe"]

    def test_strips_deeply_nested_marker(self) -> None:
        """Deeply nested pickle markers must be neutralised."""
        data = {"a": {"b": {"c": {"__pickled__": "deep"}}}}
        result = strip_pickle_markers(data)
        assert result == {"a": {"b": {"c": None}}}

    def test_preserves_safe_dict(self) -> None:
        """Dicts without pickle markers must be left untouched."""
        data = {"approved": True, "reason": "Looks good"}
        assert strip_pickle_markers(data) == data

    def test_preserves_primitives(self) -> None:
        """Primitive values must pass through unchanged."""
        assert strip_pickle_markers("hello") == "hello"
        assert strip_pickle_markers(42) == 42
        assert strip_pickle_markers(None) is None
        assert strip_pickle_markers(True) is True

    def test_preserves_safe_list(self) -> None:
        """Lists without pickle markers must be left untouched."""
        data = [1, "two", {"key": "value"}]
        assert strip_pickle_markers(data) == data

    def test_mixed_safe_and_malicious(self) -> None:
        """Only the malicious entries should be stripped; safe entries remain."""
        data = {
            "user_input": "hello",
            "evil": {"__pickled__": "PAYLOAD", "__type__": "os:system"},
            "count": 42,
        }
        result = strip_pickle_markers(data)
        assert result == {"user_input": "hello", "evil": None, "count": 42}
