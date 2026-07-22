# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the Azure Functions workflow-context adapter."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from agent_framework_azurefunctions._workflow import run_workflow_orchestrator
from agent_framework_azurefunctions._workflow_af_context import AzureFunctionsWorkflowContext


class _FakeDurableAIAgent:
    def __init__(self, executor: Any, name: str) -> None:
        self.executor = executor
        self.name = name
        self.calls: list[tuple[str, Any]] = []

    def run(self, message: str, *, session: Any) -> dict[str, Any]:
        self.calls.append((message, session))
        return {"message": message, "session": session, "executor": self.executor, "name": self.name}


class TestAzureFunctionsWorkflowContext:
    """Behavior of the Azure Functions orchestration-context adapter."""

    @pytest.fixture
    def orchestration_context(self) -> Mock:
        context = Mock()
        context.instance_id = "instance-123"
        context.is_replaying = True
        context.current_utc_datetime = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        context.call_activity.return_value = "activity-task"
        context.call_sub_orchestrator.return_value = "sub-task"
        context.task_all.return_value = "all-task"
        context.task_any.return_value = "any-task"
        context.wait_for_external_event.return_value = "event-task"
        context.create_timer.return_value = "timer-task"
        context.new_uuid.return_value = "uuid-123"
        return context

    def test_exposes_basic_context_properties(self, orchestration_context: Mock) -> None:
        workflow_context = AzureFunctionsWorkflowContext(orchestration_context)

        assert workflow_context.instance_id == "instance-123"
        assert workflow_context.is_replaying is True
        assert workflow_context.supports_event_streaming is False
        assert workflow_context.current_utc_datetime == orchestration_context.current_utc_datetime

    def test_prepare_agent_task_wraps_session_and_executor(
        self,
        monkeypatch: pytest.MonkeyPatch,
        orchestration_context: Mock,
    ) -> None:
        executor_sentinel = object()
        monkeypatch.setattr(
            "agent_framework_azurefunctions._workflow_af_context.AzureFunctionsAgentExecutor",
            lambda context: executor_sentinel if context is orchestration_context else None,
        )
        monkeypatch.setattr("agent_framework_azurefunctions._workflow_af_context.DurableAIAgent", _FakeDurableAIAgent)

        workflow_context = AzureFunctionsWorkflowContext(orchestration_context)
        result = workflow_context.prepare_agent_task("reviewer", "please approve", "orch-9")

        assert result["message"] == "please approve"
        assert result["executor"] is executor_sentinel
        assert result["name"] == "reviewer"
        assert result["session"].durable_session_id.name == "reviewer"
        assert result["session"].durable_session_id.key == "orch-9"

    def test_delegates_activity_and_orchestrator_primitives(self, orchestration_context: Mock) -> None:
        workflow_context = AzureFunctionsWorkflowContext(orchestration_context)

        assert workflow_context.prepare_activity_task("activity-name", '{"payload": 1}') == "activity-task"
        orchestration_context.call_activity.assert_called_once_with("activity-name", '{"payload": 1}')

        assert workflow_context.call_sub_orchestrator("child", {"x": 1}, instance_id="child-1") == "sub-task"
        orchestration_context.call_sub_orchestrator.assert_called_once_with(
            "child", input_={"x": 1}, instance_id="child-1"
        )

        assert workflow_context.task_all(["a", "b"]) == "all-task"
        orchestration_context.task_all.assert_called_once_with(["a", "b"])

        assert workflow_context.task_any(["a", "b"]) == "any-task"
        orchestration_context.task_any.assert_called_once_with(["a", "b"])

        assert workflow_context.wait_for_external_event("approval") == "event-task"
        orchestration_context.wait_for_external_event.assert_called_once_with("approval")

        assert workflow_context.create_timer(orchestration_context.current_utc_datetime) == "timer-task"
        orchestration_context.create_timer.assert_called_once_with(orchestration_context.current_utc_datetime)

    def test_status_uuid_and_task_helpers_delegate(self, orchestration_context: Mock) -> None:
        workflow_context = AzureFunctionsWorkflowContext(orchestration_context)

        workflow_context.set_custom_status({"state": "running"})
        orchestration_context.set_custom_status.assert_called_once_with({"state": "running"})
        assert workflow_context.new_uuid() == "uuid-123"

        cancellable = Mock()
        workflow_context.cancel_task(cancellable)
        cancellable.cancel.assert_called_once_with()

        non_cancellable = object()
        workflow_context.cancel_task(non_cancellable)

        done_task = Mock()
        done_task.result = {"answer": 42}
        assert workflow_context.get_task_result(done_task) == {"answer": 42}
        assert workflow_context.get_task_result(object()) is None


def test_run_workflow_orchestrator_wraps_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Azure Functions wrapper delegates to the shared durabletask orchestrator."""

    def _shared_runner(context: Any, workflow: Any, initial_message: Any, shared_state: dict[str, Any] | None) -> Any:
        return context, workflow, initial_message, shared_state

    monkeypatch.setattr("agent_framework_azurefunctions._workflow._run_workflow_orchestrator_shared", _shared_runner)

    df_context = Mock()
    workflow = Mock()

    wrapped_context, passed_workflow, passed_message, passed_state = run_workflow_orchestrator(
        df_context,
        workflow,
        "hello",
        {"x": 1},
    )

    assert isinstance(wrapped_context, AzureFunctionsWorkflowContext)
    assert wrapped_context.instance_id == df_context.instance_id
    assert passed_workflow is workflow
    assert passed_message == "hello"
    assert passed_state == {"x": 1}
