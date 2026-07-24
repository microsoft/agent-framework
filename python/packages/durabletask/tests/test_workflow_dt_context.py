# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the standalone durabletask workflow-context adapter."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from agent_framework_durabletask._workflows.dt_context import DurableTaskWorkflowContext


class _FakeDurableAIAgent:
    def __init__(self, executor: Any, name: str) -> None:
        self.executor = executor
        self.name = name

    def run(self, message: str, *, session: Any) -> dict[str, Any]:
        return {"message": message, "session": session, "executor": self.executor, "name": self.name}


class _FakeTask:
    def __init__(self, result: Any) -> None:
        self._result = result

    def get_result(self) -> Any:
        return self._result


class TestDurableTaskWorkflowContext:
    """Behavior of the durabletask-host workflow-context adapter."""

    @pytest.fixture
    def orchestration_context(self) -> Mock:
        context = Mock()
        context.instance_id = "instance-456"
        context.is_replaying = False
        context.current_utc_datetime = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
        context.call_activity.return_value = "activity-task"
        context.call_sub_orchestrator.return_value = "sub-task"
        context.wait_for_external_event.return_value = "event-task"
        context.create_timer.return_value = "timer-task"
        context.new_uuid.return_value = "uuid-456"
        return context

    def test_exposes_basic_context_properties(self, orchestration_context: Mock) -> None:
        workflow_context = DurableTaskWorkflowContext(orchestration_context)

        assert workflow_context.instance_id == "instance-456"
        assert workflow_context.is_replaying is False
        assert workflow_context.supports_event_streaming is True
        assert workflow_context.current_utc_datetime == orchestration_context.current_utc_datetime

    def test_prepare_agent_task_wraps_session_and_executor(
        self,
        monkeypatch: pytest.MonkeyPatch,
        orchestration_context: Mock,
    ) -> None:
        monkeypatch.setattr("agent_framework_durabletask._workflows.dt_context.DurableAIAgent", _FakeDurableAIAgent)

        workflow_context = DurableTaskWorkflowContext(orchestration_context)
        result = workflow_context.prepare_agent_task("reviewer", "please approve", "orch-12")

        assert result["message"] == "please approve"
        assert result["name"] == "reviewer"
        assert result["session"].durable_session_id.name == "reviewer"
        assert result["session"].durable_session_id.key == "orch-12"
        assert result["executor"] is workflow_context._executor

    def test_delegates_activity_and_orchestrator_primitives(
        self,
        monkeypatch: pytest.MonkeyPatch,
        orchestration_context: Mock,
    ) -> None:
        monkeypatch.setattr("agent_framework_durabletask._workflows.dt_context.when_all", lambda tasks: ("all", tasks))
        monkeypatch.setattr("agent_framework_durabletask._workflows.dt_context.when_any", lambda tasks: ("any", tasks))

        workflow_context = DurableTaskWorkflowContext(orchestration_context)

        assert workflow_context.prepare_activity_task("activity-name", '{"payload": 1}') == "activity-task"
        orchestration_context.call_activity.assert_called_once_with("activity-name", input='{"payload": 1}')

        assert workflow_context.call_sub_orchestrator("child", {"x": 1}, instance_id="child-2") == "sub-task"
        orchestration_context.call_sub_orchestrator.assert_called_once_with(
            "child", input={"x": 1}, instance_id="child-2"
        )

        assert workflow_context.task_all(["a", "b"]) == ("all", ["a", "b"])
        assert workflow_context.task_any(["a", "b"]) == ("any", ["a", "b"])

        assert workflow_context.wait_for_external_event("approval") == "event-task"
        orchestration_context.wait_for_external_event.assert_called_once_with("approval")

        assert workflow_context.create_timer(orchestration_context.current_utc_datetime) == "timer-task"
        orchestration_context.create_timer.assert_called_once_with(orchestration_context.current_utc_datetime)

    def test_status_uuid_and_task_helpers_delegate(
        self,
        monkeypatch: pytest.MonkeyPatch,
        orchestration_context: Mock,
    ) -> None:
        monkeypatch.setattr("agent_framework_durabletask._workflows.dt_context.Task", _FakeTask)
        workflow_context = DurableTaskWorkflowContext(orchestration_context)

        workflow_context.set_custom_status({"state": "running"})
        orchestration_context.set_custom_status.assert_called_once_with({"state": "running"})
        assert workflow_context.new_uuid() == "uuid-456"

        cancellable = Mock()
        workflow_context.cancel_task(cancellable)
        cancellable.cancel.assert_called_once_with()

        workflow_context.cancel_task(object())

        assert workflow_context.get_task_result(_FakeTask({"answer": 42})) == {"answer": 42}
        assert workflow_context.get_task_result(Mock(result="fallback")) == "fallback"
