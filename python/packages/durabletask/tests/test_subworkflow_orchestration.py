# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for sub-workflow (child-orchestration) dispatch and result handling.

A ``WorkflowExecutor`` node runs its inner workflow as a durable child
orchestration. These tests cover the host-side glue:

* :func:`_prepare_subworkflow_task` wraps the node's message in a trusted-input
  marker and schedules ``dafx-{innerName}``.
* :func:`_process_subworkflow_result` turns the child's outputs into either
  routed messages (default) or parent outputs (``allow_direct_output``).
* :func:`_try_unwrap_subworkflow_input` / :func:`_coerce_initial_input` reconstruct
  the original typed object on the child side.
"""

from typing import Any
from unittest.mock import Mock

from agent_framework import WorkflowExecutor

from agent_framework_durabletask._workflows.orchestrator import (
    SUBWORKFLOW_INPUT_KEY,
    TaskType,
    _coerce_initial_input,
    _prepare_subworkflow_task,
    _process_subworkflow_result,
    _try_unwrap_subworkflow_input,
    _unpack_subworkflow_result,
)
from agent_framework_durabletask._workflows.serialization import (
    SUBWORKFLOW_RESULT_KEY,
    deserialize_value,
    serialize_value,
)


def _subworkflow_executor(executor_id: str, inner_name: str, *, allow_direct_output: bool = False) -> Mock:
    inner = Mock()
    inner.name = inner_name
    executor = Mock(spec=WorkflowExecutor)
    executor.id = executor_id
    executor.workflow = inner
    executor.allow_direct_output = allow_direct_output
    return executor


def _event(event_type: str, executor_id: str, data: object = None) -> dict[str, Any]:
    """Build a serialized workflow-event dict as the child orchestrator emits it."""
    serialized: dict[str, Any] = {"type": event_type, "executor_id": executor_id}
    if data is not None:
        serialized["data"] = serialize_value(data)
    return serialized


def _result_envelope(outputs: list[Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the SUBWORKFLOW_RESULT_KEY envelope a child orchestration returns."""
    return {SUBWORKFLOW_RESULT_KEY: True, "outputs": outputs, "events": events}


class TestPrepareSubworkflowTask:
    """Dispatch of a ``WorkflowExecutor`` node as a child orchestration."""

    def test_schedules_inner_orchestration_by_scoped_name(self) -> None:
        ctx = Mock()
        ctx.call_sub_orchestrator.return_value = "task-sentinel"
        executor = _subworkflow_executor("sub-node", "inner_wf")

        task = _prepare_subworkflow_task(ctx, executor, "hello", "parent::sub-node::0")

        assert task == "task-sentinel"
        ctx.call_sub_orchestrator.assert_called_once()
        args, kwargs = ctx.call_sub_orchestrator.call_args
        assert args[0] == "dafx-inner_wf"
        assert kwargs["instance_id"] == "parent::sub-node::0"

    def test_wraps_message_in_marker(self) -> None:
        ctx = Mock()
        executor = _subworkflow_executor("sub-node", "inner_wf")

        _prepare_subworkflow_task(ctx, executor, "payload", "child-id")

        args, _ = ctx.call_sub_orchestrator.call_args
        child_input = args[1]
        # The wrapped payload round-trips back to the original message.
        assert deserialize_value(child_input[SUBWORKFLOW_INPUT_KEY]) == "payload"


class TestProcessSubworkflowResult:
    """Conversion of a child orchestration's outputs into an ``ExecutorResult``."""

    def test_default_routes_outputs_as_messages(self) -> None:
        executor = _subworkflow_executor("sub-node", "inner_wf", allow_direct_output=False)
        workflow_outputs: list[object] = []

        result = _process_subworkflow_result(["a", "b"], executor, workflow_outputs)

        assert result.task_type == TaskType.SUBWORKFLOW
        assert workflow_outputs == []
        assert result.activity_result is not None
        sent = result.activity_result["sent_messages"]
        assert [m["message"] for m in sent] == ["a", "b"]
        assert all(m["source_id"] == "sub-node" and m["target_id"] is None for m in sent)

    def test_allow_direct_output_extends_parent_outputs(self) -> None:
        executor = _subworkflow_executor("sub-node", "inner_wf", allow_direct_output=True)
        workflow_outputs: list[object] = ["existing"]

        result = _process_subworkflow_result(["x", "y"], executor, workflow_outputs)

        assert workflow_outputs == ["existing", "x", "y"]
        assert result.activity_result is not None
        assert result.activity_result["sent_messages"] == []

    def test_none_result_produces_no_outputs(self) -> None:
        executor = _subworkflow_executor("sub-node", "inner_wf")
        workflow_outputs: list[object] = []

        result = _process_subworkflow_result(None, executor, workflow_outputs)

        assert result.activity_result is not None
        assert result.activity_result["sent_messages"] == []
        assert workflow_outputs == []

    def test_scalar_result_is_wrapped_as_single_output(self) -> None:
        executor = _subworkflow_executor("sub-node", "inner_wf", allow_direct_output=True)
        workflow_outputs: list[object] = []

        _process_subworkflow_result("solo", executor, workflow_outputs)

        assert workflow_outputs == ["solo"]

    def test_envelope_outputs_routed_as_messages(self) -> None:
        """Outputs carried in a result envelope are routed like a bare-list result."""
        executor = _subworkflow_executor("sub-node", "inner_wf", allow_direct_output=False)
        workflow_outputs: list[object] = []
        envelope = _result_envelope(["a", "b"], events=[])

        result = _process_subworkflow_result(envelope, executor, workflow_outputs)

        assert result.activity_result is not None
        assert [m["message"] for m in result.activity_result["sent_messages"]] == ["a", "b"]
        assert workflow_outputs == []

    def test_envelope_allow_direct_output_extends_parent_outputs(self) -> None:
        executor = _subworkflow_executor("sub-node", "inner_wf", allow_direct_output=True)
        workflow_outputs: list[object] = []
        envelope = _result_envelope(["x", "y"], events=[])

        _process_subworkflow_result(envelope, executor, workflow_outputs)

        assert workflow_outputs == ["x", "y"]

    def test_intermediate_events_bubbled_retagged_with_node_id(self) -> None:
        """A child's intermediate events bubble up re-tagged with the node id.

        Mirrors the in-process WorkflowExecutor, which forwards child intermediate
        emissions as WorkflowEvent("intermediate", executor_id=self.id, ...) so an
        outer observer sees nested progress without the child's internal layout.
        """
        executor = _subworkflow_executor("sub-node", "inner_wf")
        workflow_outputs: list[object] = []
        envelope = _result_envelope(
            outputs=["out"],
            events=[_event("intermediate", "inner-exec", data="progress")],
        )

        result = _process_subworkflow_result(envelope, executor, workflow_outputs)

        assert result.activity_result is not None
        bubbled = result.activity_result["events"]
        assert len(bubbled) == 1
        # Re-tagged with the WorkflowExecutor node id, not the child's executor id.
        assert bubbled[0]["executor_id"] == "sub-node"
        assert bubbled[0]["type"] == "intermediate"
        # Payload is preserved (still serialized for the parent timeline).
        assert deserialize_value(bubbled[0]["data"]) == "progress"

    def test_non_intermediate_child_events_are_not_bubbled(self) -> None:
        """Only intermediate events bubble: lifecycle/output events stay child-internal."""
        executor = _subworkflow_executor("sub-node", "inner_wf")
        workflow_outputs: list[object] = []
        envelope = _result_envelope(
            outputs=["out"],
            events=[
                _event("executor_invoked", "inner-exec"),
                _event("executor_completed", "inner-exec"),
                _event("output", "inner-exec", data="out"),
            ],
        )

        result = _process_subworkflow_result(envelope, executor, workflow_outputs)

        assert result.activity_result is not None
        assert result.activity_result["events"] == []


class TestUnpackSubworkflowResult:
    """Splitting a child orchestration's return value into ``(outputs, events)``."""

    def test_unpacks_result_envelope(self) -> None:
        events = [_event("intermediate", "inner-exec", data="p")]
        envelope = _result_envelope(["a", "b"], events=events)

        outputs, parsed_events = _unpack_subworkflow_result(envelope)

        assert outputs == ["a", "b"]
        assert parsed_events == events

    def test_bare_list_is_outputs_with_no_events(self) -> None:
        assert _unpack_subworkflow_result(["a", "b"]) == (["a", "b"], [])

    def test_none_is_empty_outputs_and_events(self) -> None:
        assert _unpack_subworkflow_result(None) == ([], [])

    def test_scalar_is_single_output(self) -> None:
        assert _unpack_subworkflow_result("solo") == (["solo"], [])

    def test_envelope_with_missing_keys_degrades_gracefully(self) -> None:
        """A malformed envelope (missing outputs/events) yields empty lists, not errors."""
        outputs, events = _unpack_subworkflow_result({SUBWORKFLOW_RESULT_KEY: True})

        assert outputs == []
        assert events == []


class TestSubworkflowInputUnwrap:
    """Child-side reconstruction of the parent-supplied marker payload."""

    def test_unwrap_detects_and_reconstructs_marker(self) -> None:
        marker = {SUBWORKFLOW_INPUT_KEY: "wrapped"}

        unwrapped, inner = _try_unwrap_subworkflow_input(marker)

        assert unwrapped is True
        assert inner == "wrapped"

    def test_unwrap_ignores_non_marker_dict(self) -> None:
        unwrapped, inner = _try_unwrap_subworkflow_input({"some": "data"})

        assert unwrapped is False
        assert inner is None

    def test_unwrap_ignores_non_dict(self) -> None:
        assert _try_unwrap_subworkflow_input("plain") == (False, None)

    def test_coerce_initial_input_returns_unwrapped_inner(self) -> None:
        # When the workflow runs as a child, _coerce_initial_input returns the
        # reconstructed inner object directly, bypassing start-executor coercion.
        workflow = Mock()
        workflow.executors = {}
        marker = {SUBWORKFLOW_INPUT_KEY: "inner-message"}

        assert _coerce_initial_input(workflow, marker) == "inner-message"
