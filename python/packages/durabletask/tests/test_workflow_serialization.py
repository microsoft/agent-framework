# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow serialization helpers.

``resolve_type`` is annotated ``type | None`` and its result flows into
``reconstruct_to_type``, which calls ``issubclass``. A non-class attribute
(function, module member, etc.) would raise ``TypeError`` there, so the
resolver must only ever return actual classes.

``deserialize_workflow_output`` reverses the per-output ``serialize_value``
encoding the shared activity applies, so typed outputs are returned as the
original objects rather than checkpoint-marker dicts.

``serialize_value`` / ``deserialize_value`` are the internal codec; the
round-trip, ``reconstruct_to_type``, and ``strip_pickle_markers`` suites below
guard the type fidelity and the trust-boundary defense that neutralizes
attacker-injected pickle/type markers before they can reach ``pickle.loads()``.
"""

import json
from collections import OrderedDict
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Message,
    WorkflowEvent,
)
from pydantic import BaseModel

from agent_framework_durabletask._workflows.serialization import (
    deserialize_value,
    deserialize_workflow_event,
    deserialize_workflow_output,
    reconstruct_to_type,
    resolve_type,
    serialize_value,
    serialize_workflow_event,
    strip_pickle_markers,
)


@dataclass
class _Decision:
    """Module-level dataclass so it is picklable by serialize_value."""

    approved: bool
    note: str


class TestResolveType:
    """Test that resolve_type only returns real classes."""

    def test_resolves_a_real_class(self) -> None:
        assert resolve_type("collections:OrderedDict") is OrderedDict

    def test_returns_none_for_non_class_attribute(self) -> None:
        # json.dumps is a function; if resolve_type returned it, issubclass()
        # inside reconstruct_to_type() would raise TypeError at runtime.
        assert resolve_type("json:dumps") is None

    def test_returns_none_for_unknown_attribute(self) -> None:
        assert resolve_type("json:DoesNotExist") is None

    def test_returns_none_for_malformed_key(self) -> None:
        assert resolve_type("not-a-valid-key") is None


class TestDeserializeWorkflowOutput:
    """Reconstruction of stored workflow outputs."""

    def test_primitives_pass_through(self) -> None:
        # Mirror the stored shape: a list of yielded outputs, JSON round-tripped.
        stored = json.loads(json.dumps([serialize_value("hello"), serialize_value(42)]))

        assert deserialize_workflow_output(stored) == ["hello", 42]

    def test_typed_outputs_are_reconstructed(self) -> None:
        # A typed object is stored as a checkpoint-marker dict; it must come back
        # as the original object, not the marker dict.
        decision = _Decision(approved=True, note="ok")
        stored = json.loads(json.dumps([serialize_value(decision)]))

        result = deserialize_workflow_output(stored)

        assert result == [decision]
        assert isinstance(result[0], _Decision)

    def test_none_passes_through(self) -> None:
        assert deserialize_workflow_output(None) is None


@dataclass
class _Approval:
    """Module-level dataclass so it is picklable by serialize_value."""

    reason: str


def _roundtrip(event: WorkflowEvent) -> WorkflowEvent:
    # Mirror the real path: serialize, JSON round-trip through the custom status,
    # then reconstruct on the client.
    return deserialize_workflow_event(json.loads(json.dumps(serialize_workflow_event(event))))


class TestWorkflowEventRoundtrip:
    """serialize_workflow_event / deserialize_workflow_event preserve event identity."""

    def test_output_event_reconstructs_typed_data(self) -> None:
        result = _roundtrip(WorkflowEvent("output", data=_Approval(reason="ok"), executor_id="writer"))

        assert result.type == "output"
        assert result.executor_id == "writer"
        assert result.data == _Approval(reason="ok")
        assert isinstance(result.data, _Approval)

    def test_executor_completed_without_data_roundtrips_to_none(self) -> None:
        result = _roundtrip(WorkflowEvent.executor_completed("reviewer"))

        assert result.type == "executor_completed"
        assert result.executor_id == "reviewer"
        assert result.data is None

    def test_iteration_tag_is_preserved(self) -> None:
        # The orchestrator tags each event with its superstep before publishing.
        serialized = serialize_workflow_event(WorkflowEvent.executor_invoked("writer"))
        serialized["iteration"] = 3

        result = deserialize_workflow_event(json.loads(json.dumps(serialized)))

        assert result.type == "executor_invoked"
        assert result.iteration == 3

    def test_request_info_event_roundtrips(self) -> None:
        event: WorkflowEvent = WorkflowEvent.request_info(
            request_id="req-1",
            source_executor_id="approver",
            request_data=_Approval(reason="needs sign-off"),
            response_type=bool,
        )

        result = _roundtrip(event)

        assert result.type == "request_info"
        assert result.request_id == "req-1"
        assert result.source_executor_id == "approver"
        assert result.response_type is bool
        assert result.data == _Approval(reason="needs sign-off")


# Module-level test types (must be importable for checkpoint encoding roundtrip).
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


class TestSerializationRoundtrip:
    """``serialize_value`` / ``deserialize_value`` round-trip the typed objects used in workflows."""

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
