# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the durable workflow naming helpers.

These helpers derive the **stable** durable names a hosted workflow registers
under. Stability matters: durable replay resumes an in-flight orchestration only
if the orchestration name still resolves, so the round-trip
(``workflow_orchestrator_name`` ↔ ``workflow_name_from_orchestrator``) and the
validation rules (reject empty / malformed / auto-generated names) are the
contract the multi-workflow hosting builds on.
"""

import uuid

import pytest

from agent_framework_durabletask import (
    DURABLE_NAME_PREFIX,
    is_auto_generated_workflow_name,
    validate_executor_id,
    validate_workflow_name,
    workflow_name_from_orchestrator,
    workflow_orchestrator_name,
)
from agent_framework_durabletask._workflows.naming import (
    MAX_EXECUTOR_ID_LENGTH,
    SUBWORKFLOW_REQUEST_SEPARATOR,
    qualify_subworkflow_request_id,
    split_subworkflow_request_id,
)


class TestWorkflowOrchestratorName:
    """``workflow_orchestrator_name`` derives ``dafx-{name}`` for valid names."""

    def test_prepends_prefix(self) -> None:
        assert workflow_orchestrator_name("orders") == "dafx-orders"

    def test_uses_shared_prefix_constant(self) -> None:
        assert workflow_orchestrator_name("orders") == f"{DURABLE_NAME_PREFIX}orders"

    @pytest.mark.parametrize("name", ["a", "Order_Processor", "spam-detection", "wf123"])
    def test_accepts_valid_names(self, name: str) -> None:
        assert workflow_orchestrator_name(name) == f"dafx-{name}"

    @pytest.mark.parametrize("name", ["", "1abc", "has space", "bad/char", "emoji😀"])
    def test_rejects_invalid_names(self, name: str) -> None:
        with pytest.raises(ValueError):
            workflow_orchestrator_name(name)


class TestWorkflowNameRoundTrip:
    """``workflow_name_from_orchestrator`` inverts ``workflow_orchestrator_name``."""

    @pytest.mark.parametrize("name", ["orders", "Order_Processor", "spam-detection", "wf123"])
    def test_round_trips(self, name: str) -> None:
        orchestrator = workflow_orchestrator_name(name)
        assert workflow_name_from_orchestrator(orchestrator) == name

    def test_returns_none_without_prefix(self) -> None:
        # A bare orchestration name (no dafx- prefix) is "not one of ours".
        assert workflow_name_from_orchestrator("workflow_orchestrator") is None


class TestValidateExecutorId:
    """``validate_executor_id`` guards the durable-naming / nested-HITL contract."""

    @pytest.mark.parametrize("executor_id", ["router", "agent_node", "reviewer-node", "a", "Step1"])
    def test_accepts_ordinary_ids(self, executor_id: str) -> None:
        validate_executor_id(executor_id)  # does not raise

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            validate_executor_id("")

    def test_rejects_id_containing_separator(self) -> None:
        bad = f"a{SUBWORKFLOW_REQUEST_SEPARATOR}b"
        with pytest.raises(ValueError, match="reserved sub-workflow request separator"):
            validate_executor_id(bad)

    def test_rejects_overly_long_id(self) -> None:
        with pytest.raises(ValueError, match="too long"):
            validate_executor_id("x" * (MAX_EXECUTOR_ID_LENGTH + 1))


class TestSubworkflowRequestIdQualification:
    """Round-trip of the ``{executor}~{ordinal}~{leaf}`` qualified-request-id scheme."""

    def test_separator_is_url_safe_tilde(self) -> None:
        # '~' is RFC 3986 unreserved and (unlike '::') never appears in core request ids.
        assert SUBWORKFLOW_REQUEST_SEPARATOR == "~"

    def test_qualify_then_split_round_trips(self) -> None:
        qualified = qualify_subworkflow_request_id("sub", 2, "req-9")
        assert qualified == "sub~2~req-9"
        assert split_subworkflow_request_id(qualified) == ("sub", 2, "req-9")

    def test_split_returns_none_for_bare_id(self) -> None:
        assert split_subworkflow_request_id("req-9") is None

    def test_split_preserves_double_colon_leaf(self) -> None:
        # A functional workflow's ``auto::0`` leaf survives one peel as the remainder.
        assert split_subworkflow_request_id("sub~0~auto::0") == ("sub", 0, "auto::0")

    def test_split_treats_double_colon_only_id_as_bare(self) -> None:
        # ``auto::0`` has no '~', so it is a bare leaf, not a nested hop.
        assert split_subworkflow_request_id("auto::0") is None

    def test_split_treats_non_integer_ordinal_as_bare(self) -> None:
        # A value whose second segment is not an integer is not a structural hop.
        assert split_subworkflow_request_id("a~b~c") is None

    def test_nested_qualification_round_trips(self) -> None:
        deep = qualify_subworkflow_request_id("mid", 0, qualify_subworkflow_request_id("leaf", 1, "deep"))
        assert deep == "mid~0~leaf~1~deep"
        hop = split_subworkflow_request_id(deep)
        assert hop is not None
        executor_id, ordinal, remainder = hop
        assert (executor_id, ordinal) == ("mid", 0)
        assert split_subworkflow_request_id(remainder) == ("leaf", 1, "deep")

    def test_returns_none_for_prefix_only(self) -> None:
        assert workflow_name_from_orchestrator(DURABLE_NAME_PREFIX) is None

    def test_strips_only_leading_prefix(self) -> None:
        # Reverse is meant for orchestration names; it strips just the prefix, so a
        # scoped activity-style name returns the remainder verbatim.
        assert workflow_name_from_orchestrator("dafx-orders-translator") == "orders-translator"


class TestValidateWorkflowName:
    """``validate_workflow_name`` rejects unstable / unsafe identities."""

    @pytest.mark.parametrize("name", ["a", "A", "wf", "Order_Processor", "spam-detection", "x" * 63])
    def test_accepts_valid(self, name: str) -> None:
        validate_workflow_name(name)  # should not raise

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            validate_workflow_name("")

    @pytest.mark.parametrize("name", ["1abc", "-abc", "_abc", "has space", "bad/char", "a.b", "x" * 64])
    def test_rejects_malformed(self, name: str) -> None:
        with pytest.raises(ValueError, match="invalid"):
            validate_workflow_name(name)

    def test_rejects_auto_generated(self) -> None:
        name = f"WorkflowBuilder-{uuid.uuid4()}"
        with pytest.raises(ValueError, match="auto-generated"):
            validate_workflow_name(name)


class TestIsAutoGeneratedWorkflowName:
    """``is_auto_generated_workflow_name`` detects WorkflowBuilder defaults."""

    def test_detects_uuid_default(self) -> None:
        assert is_auto_generated_workflow_name(f"WorkflowBuilder-{uuid.uuid4()}") is True

    def test_detects_uppercase_hex_uuid(self) -> None:
        assert is_auto_generated_workflow_name(f"WorkflowBuilder-{str(uuid.uuid4()).upper()}") is True

    @pytest.mark.parametrize(
        "name",
        [
            "orders",
            "WorkflowBuilder",
            "WorkflowBuilder-not-a-uuid",
            "MyWorkflowBuilder-3f2b1c0a-1234-5678-9abc-def012345678",
        ],
    )
    def test_ignores_explicit_names(self, name: str) -> None:
        assert is_auto_generated_workflow_name(name) is False
