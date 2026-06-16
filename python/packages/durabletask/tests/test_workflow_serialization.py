# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow serialization helpers.

``resolve_type`` is annotated ``type | None`` and its result flows into
``reconstruct_to_type``, which calls ``issubclass``. A non-class attribute
(function, module member, etc.) would raise ``TypeError`` there, so the
resolver must only ever return actual classes.

``deserialize_workflow_output`` reverses the per-output ``serialize_value``
encoding the shared activity applies, so typed outputs are returned as the
original objects rather than checkpoint-marker dicts.
"""

import json
from collections import OrderedDict
from dataclasses import dataclass

from agent_framework import WorkflowEvent

from agent_framework_durabletask._workflows.serialization import (
    deserialize_workflow_event,
    deserialize_workflow_output,
    resolve_type,
    serialize_value,
    serialize_workflow_event,
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
