# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableWorkflowClient.

Covers starting workflows, awaiting output (including error/timeout paths),
parsing pending human-in-the-loop (HITL) requests from custom status, and
sanitizing HITL responses before delivery.
"""

import json
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from agent_framework_durabletask import DurableWorkflowClient
from agent_framework_durabletask._workflows.orchestrator import WORKFLOW_ORCHESTRATOR_NAME
from agent_framework_durabletask._workflows.serialization import serialize_value


@dataclass
class _Receipt:
    """Module-level dataclass so it is picklable by serialize_value."""

    order_id: int
    total: float


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock TaskHubGrpcClient."""
    return Mock()


@pytest.fixture
def workflow_client(mock_client: Mock) -> DurableWorkflowClient:
    """Create a DurableWorkflowClient wrapping the mock client."""
    return DurableWorkflowClient(mock_client)


class TestStartWorkflow:
    """Test starting workflow orchestrations."""

    def test_start_workflow_schedules_orchestrator(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """start_workflow schedules the auto-registered orchestrator by name."""
        mock_client.schedule_new_orchestration.return_value = "instance-1"

        result = workflow_client.start_workflow(input="hello")

        assert result == "instance-1"
        mock_client.schedule_new_orchestration.assert_called_once_with(
            WORKFLOW_ORCHESTRATOR_NAME, input="hello", instance_id=None
        )

    def test_start_workflow_passes_non_string_input_unchanged(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """Non-string payloads are forwarded as-is (no string coercion)."""
        mock_client.schedule_new_orchestration.return_value = "instance-2"
        payload = {"order_id": 42, "items": ["a", "b"]}

        workflow_client.start_workflow(input=payload)

        _, kwargs = mock_client.schedule_new_orchestration.call_args
        assert kwargs["input"] == payload

    def test_start_workflow_forwards_instance_id(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """An explicit instance id is forwarded to the underlying client."""
        mock_client.schedule_new_orchestration.return_value = "explicit-id"

        workflow_client.start_workflow(input="x", instance_id="explicit-id")

        _, kwargs = mock_client.schedule_new_orchestration.call_args
        assert kwargs["instance_id"] == "explicit-id"


class TestAwaitWorkflowOutput:
    """Test awaiting workflow completion and output."""

    def test_returns_deserialized_output_on_completion(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """A COMPLETED workflow returns its deserialized output."""
        metadata = Mock()
        metadata.runtime_status.name = "COMPLETED"
        metadata.serialized_output = json.dumps(["result"])
        mock_client.wait_for_orchestration_completion.return_value = metadata

        output = workflow_client.await_workflow_output("instance-1")

        assert output == ["result"]

    def test_returns_none_when_no_output(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """A COMPLETED workflow with no output returns None."""
        metadata = Mock()
        metadata.runtime_status.name = "COMPLETED"
        metadata.serialized_output = None
        mock_client.wait_for_orchestration_completion.return_value = metadata

        assert workflow_client.await_workflow_output("instance-1") is None

    def test_reconstructs_typed_outputs(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """Typed outputs encoded by the activity come back as objects, not marker dicts."""
        receipt = _Receipt(order_id=7, total=19.99)
        # The shared activity stores each yielded output via serialize_value(), so a
        # typed object is persisted as a checkpoint-marker dict.
        metadata = Mock()
        metadata.runtime_status.name = "COMPLETED"
        metadata.serialized_output = json.dumps([serialize_value(receipt)])
        mock_client.wait_for_orchestration_completion.return_value = metadata

        output = workflow_client.await_workflow_output("instance-1")

        assert output == [receipt]
        assert isinstance(output[0], _Receipt)

    def test_raises_timeout_when_not_completed(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """A None metadata (no completion) raises TimeoutError."""
        mock_client.wait_for_orchestration_completion.return_value = None

        with pytest.raises(TimeoutError, match="did not complete"):
            workflow_client.await_workflow_output("instance-1", timeout_seconds=5)

    def test_raises_runtime_error_on_failed_status(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """A non-COMPLETED status raises RuntimeError."""
        metadata = Mock()
        metadata.runtime_status.name = "FAILED"
        metadata.serialized_output = "boom"
        mock_client.wait_for_orchestration_completion.return_value = metadata

        with pytest.raises(RuntimeError, match="status FAILED"):
            workflow_client.await_workflow_output("instance-1")


class TestGetPendingHitlRequests:
    """Test parsing pending HITL requests from custom status."""

    def _state_with_status(self, status: object) -> Mock:
        state = Mock()
        state.serialized_custom_status = json.dumps(status) if status is not None else None
        return state

    def test_returns_empty_when_no_state(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """No orchestration state yields an empty list."""
        mock_client.get_orchestration_state.return_value = None

        assert workflow_client.get_pending_hitl_requests("instance-1") == []

    def test_returns_empty_when_status_blank(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """A blank custom status yields an empty list."""
        state = Mock()
        state.serialized_custom_status = ""
        mock_client.get_orchestration_state.return_value = state

        assert workflow_client.get_pending_hitl_requests("instance-1") == []

    def test_returns_empty_on_invalid_json(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """Malformed custom status JSON yields an empty list."""
        state = Mock()
        state.serialized_custom_status = "{not-json"
        mock_client.get_orchestration_state.return_value = state

        assert workflow_client.get_pending_hitl_requests("instance-1") == []

    def test_parses_pending_requests(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """Pending requests are normalized into the documented shape."""
        status = {
            "pending_requests": {
                "req-1": {
                    "request_id": "req-1",
                    "source_executor_id": "approver",
                    "data": {"prompt": "approve?"},
                    "request_type": "ApprovalRequest",
                    "response_type": "ApprovalResponse",
                }
            }
        }
        mock_client.get_orchestration_state.return_value = self._state_with_status(status)

        requests = workflow_client.get_pending_hitl_requests("instance-1")

        assert requests == [
            {
                "request_id": "req-1",
                "source_executor_id": "approver",
                "data": {"prompt": "approve?"},
                "request_type": "ApprovalRequest",
                "response_type": "ApprovalResponse",
            }
        ]

    def test_falls_back_to_dict_key_for_request_id(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """When a request omits request_id, the dict key is used."""
        status = {"pending_requests": {"req-key": {"source_executor_id": "x"}}}
        mock_client.get_orchestration_state.return_value = self._state_with_status(status)

        requests = workflow_client.get_pending_hitl_requests("instance-1")

        assert requests[0]["request_id"] == "req-key"

    def test_ignores_non_dict_entries(self, workflow_client: DurableWorkflowClient, mock_client: Mock) -> None:
        """Non-dict request entries are skipped."""
        status = {"pending_requests": {"req-1": "not-a-dict"}}
        mock_client.get_orchestration_state.return_value = self._state_with_status(status)

        assert workflow_client.get_pending_hitl_requests("instance-1") == []

    def test_returns_empty_when_pending_not_dict(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """A non-dict pending_requests field yields an empty list."""
        status = {"pending_requests": ["unexpected"]}
        mock_client.get_orchestration_state.return_value = self._state_with_status(status)

        assert workflow_client.get_pending_hitl_requests("instance-1") == []


class TestSendHitlResponse:
    """Test delivering HITL responses."""

    def test_raises_orchestration_event_with_request_id(
        self, workflow_client: DurableWorkflowClient, mock_client: Mock
    ) -> None:
        """The response is delivered as an external event named by request id."""
        workflow_client.send_hitl_response("instance-1", "req-1", {"approved": True})

        mock_client.raise_orchestration_event.assert_called_once()
        _, kwargs = mock_client.raise_orchestration_event.call_args
        assert kwargs["event_name"] == "req-1"
        assert kwargs["data"] == {"approved": True}
