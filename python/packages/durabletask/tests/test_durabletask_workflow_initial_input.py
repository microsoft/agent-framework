# Copyright (c) Microsoft. All rights reserved.

"""Behavioral tests for Durable Task workflow initial input."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from agent_framework_durabletask import execute_workflow_activity, run_workflow_orchestrator


class _InlineWorkflowHost:
    """Run activity tasks inline while exercising the public orchestration surface."""

    def __init__(self, workflow: Workflow) -> None:
        self.workflow = workflow

    @property
    def instance_id(self) -> str:
        return "test-instance"

    @property
    def is_replaying(self) -> bool:
        return False

    @property
    def supports_event_streaming(self) -> bool:
        return False

    @property
    def current_utc_datetime(self) -> datetime:
        return datetime.now(timezone.utc)

    def prepare_agent_task(self, executor_id: str, message: str, orchestration_instance_id: str) -> Any:
        raise AssertionError("This test workflow has no agent executors")

    def prepare_activity_task(self, activity_name: str, input_json: str) -> str:
        activity_input = json.loads(input_json)
        executor = self.workflow.executors[activity_input["executor_id"]]
        return execute_workflow_activity(executor, input_json, self.workflow)

    def call_sub_orchestrator(self, name: str, input: Any, instance_id: str | None = None) -> Any:
        raise AssertionError("This test workflow has no sub-workflows")

    def task_all(self, tasks: list[Any]) -> list[Any]:
        return tasks

    def task_any(self, tasks: list[Any]) -> Any:
        raise AssertionError("This test workflow does not wait for competing tasks")

    def wait_for_external_event(self, name: str) -> Any:
        raise AssertionError("This test workflow has no external events")

    def create_timer(self, fire_at: datetime) -> Any:
        raise AssertionError("This test workflow has no timers")

    def set_custom_status(self, status: Any) -> None:
        pass

    def new_uuid(self) -> str:
        return "test-uuid"

    def cancel_task(self, task: Any) -> None:
        pass

    def get_task_result(self, task: Any) -> Any:
        return task


class _NullableUnionStart(Executor):
    def __init__(self) -> None:
        super().__init__(id="start")

    @handler(input=str | dict | None, workflow_output=str)
    async def run(self, message: str | dict[str, Any] | None, ctx: WorkflowContext[Any, str]) -> None:
        await ctx.yield_output("neutralized" if message is None else "accepted")


def _run_inline(workflow: Workflow, initial_input: Any) -> list[Any] | dict[str, Any]:
    host = _InlineWorkflowHost(workflow)
    orchestration = run_workflow_orchestrator(host, workflow, initial_input)
    yielded = next(orchestration)

    while True:
        try:
            yielded = orchestration.send(yielded)
        except StopIteration as completed:
            return completed.value


def test_reserved_marker_shaped_initial_input_is_neutralized() -> None:
    """Framework-reserved serialization metadata is not delivered as application input."""
    executor = _NullableUnionStart()
    workflow = WorkflowBuilder(start_executor=executor, output_from=[executor]).build()
    initial_input = {
        "__pickled__": "not-checkpoint-data",
        "__type__": "builtins:int",
    }

    assert _run_inline(workflow, initial_input) == ["neutralized"]


def test_regular_union_initial_input_is_preserved() -> None:
    """Ordinary JSON input keeps the union-typed workflow's existing behavior."""
    executor = _NullableUnionStart()
    workflow = WorkflowBuilder(start_executor=executor, output_from=[executor]).build()

    assert _run_inline(workflow, {"message": "hello"}) == ["accepted"]
