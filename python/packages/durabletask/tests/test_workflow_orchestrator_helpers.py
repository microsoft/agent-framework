# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for shared durable workflow-orchestrator helper functions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, Mock

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
)
from agent_framework._workflows._edge import FanInEdgeGroup, SingleEdgeGroup
from agent_framework._workflows._state import State
from pydantic import BaseModel

from agent_framework_durabletask._workflows.orchestrator import (
    SOURCE_HITL_RESPONSE,
    ExecutorResult,
    PendingHITLRequest,
    TaskType,
    _check_fan_in_ready,
    _collect_hitl_requests,
    _deserialize_hitl_response,
    _prepare_activity_task,
    _prepare_agent_task,
    _prepare_all_tasks,
    _process_activity_result,
    _route_hitl_response,
    _route_result_messages,
    _select_primary_input_type,
    execute_hitl_response_handler,
)
from agent_framework_durabletask._workflows.serialization import serialize_value


class _ApprovalModel(BaseModel):
    approved: bool


def _agent_response(text: str) -> AgentExecutorResponse:
    assistant = Message(role="assistant", contents=[text])
    return AgentExecutorResponse(
        executor_id="exec",
        agent_response=AgentResponse(messages=[assistant]),
        full_conversation=[assistant],
    )


class TestPrepareTaskHelpers:
    """Preparation helpers scope names and package activity input correctly."""

    def test_prepare_agent_task_scopes_executor_id_and_extracts_message_text(self) -> None:
        ctx = Mock()
        ctx.instance_id = "instance-1"
        ctx.prepare_agent_task.return_value = "agent-task"
        request = AgentExecutorRequest(messages=[Message(role="user", contents=["hello there"])])

        task = _prepare_agent_task(ctx, "reviewer", request, "moderation")

        assert task == "agent-task"
        ctx.prepare_agent_task.assert_called_once_with("moderation-reviewer", "hello there", "instance-1")

    def test_prepare_activity_task_serializes_message_state_and_host_context(self) -> None:
        ctx = Mock()
        ctx.prepare_activity_task.return_value = "activity-task"

        task = _prepare_activity_task(
            ctx,
            "router",
            {"payload": 1},
            "start",
            {"existing": True},
            "moderation",
            {
                "root_instance_id": "root-1",
                "root_workflow_name": "outer-workflow",
                "request_path_prefix": "review~0~",
            },
        )

        assert task == "activity-task"
        activity_name, activity_input_json = ctx.prepare_activity_task.call_args[0]
        assert activity_name == "dafx-moderation-router"

        activity_input = json.loads(activity_input_json)
        assert activity_input["executor_id"] == "router"
        assert activity_input["message"] == serialize_value({"payload": 1})
        assert activity_input["shared_state_snapshot"] == {"existing": True}
        assert activity_input["source_executor_ids"] == ["start"]
        assert activity_input["host_context"] == {
            "instance_id": "root-1",
            "workflow_name": "outer-workflow",
            "request_path_prefix": "review~0~",
        }

    def test_prepare_all_tasks_groups_agent_messages_for_sequential_followup(self) -> None:
        ctx = Mock()
        ctx.instance_id = "instance-9"
        ctx.prepare_agent_task.return_value = "agent-task"
        ctx.prepare_activity_task.return_value = "activity-task"

        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = "reviewer"
        activity_executor = Mock(spec=Executor)
        activity_executor.id = "router"

        workflow = Mock()
        workflow.name = "moderation"
        workflow.executors = {
            "reviewer": agent_executor,
            "router": activity_executor,
        }

        tasks, metadata, remaining = _prepare_all_tasks(
            ctx,
            workflow,
            {
                "reviewer": [("first", "start"), ("second", "other")],
                "router": [(False, "reviewer")],
            },
            {"x": 1},
            [0],
            {
                "root_instance_id": "root-9",
                "root_workflow_name": "moderation",
                "request_path_prefix": "",
            },
        )

        assert tasks == ["activity-task", "agent-task"]
        assert [item.task_type for item in metadata] == [TaskType.ACTIVITY, TaskType.AGENT]
        assert remaining == [("reviewer", "second", "other")]


class TestHitlHelpers:
    """HITL helper functions sanitize, reconstruct, and route responses."""

    def test_deserialize_hitl_response_handles_none_scalar_and_marker_rejection(self) -> None:
        assert _deserialize_hitl_response(None, None) is None
        assert _deserialize_hitl_response("approved", None) == "approved"
        assert _deserialize_hitl_response({"__pickled__": "evil"}, None) is None

    def test_deserialize_hitl_response_reconstructs_typed_payload(self) -> None:
        result = _deserialize_hitl_response({"approved": True}, f"{__name__}:_ApprovalModel")

        assert isinstance(result, _ApprovalModel)
        assert result.approved is True

    def test_deserialize_hitl_response_returns_sanitized_dict_when_type_unknown(self) -> None:
        payload = {"approved": False}

        assert _deserialize_hitl_response(payload, "missing.module:Type") == payload

    async def test_execute_hitl_response_handler_invokes_selected_handler(self) -> None:
        handler = AsyncMock()
        executor = Mock()
        executor.id = "reviewer"
        executor._find_response_handler.return_value = handler
        shared_state = State()
        runner_context = Mock()

        await execute_hitl_response_handler(
            executor,
            {
                "original_request": {"question": "approve?"},
                "response": {"approved": True},
                "response_type": f"{__name__}:_ApprovalModel",
            },
            shared_state,
            runner_context,
        )

        assert handler.await_args is not None
        response, workflow_context = handler.await_args.args
        assert isinstance(response, _ApprovalModel)
        assert response.approved is True
        assert workflow_context._executor is executor
        assert workflow_context._runner_context is runner_context
        assert workflow_context.state is shared_state
        executor._find_response_handler.assert_called_once()

    async def test_execute_hitl_response_handler_returns_when_no_handler_exists(self) -> None:
        executor = Mock()
        executor.id = "reviewer"
        executor._find_response_handler.return_value = None

        await execute_hitl_response_handler(
            executor,
            {"original_request": {"question": "approve?"}, "response": "yes", "response_type": None},
            State(),
            Mock(),
        )

        executor._find_response_handler.assert_called_once()

    def test_collect_hitl_requests_records_pending_entries(self) -> None:
        pending: dict[str, PendingHITLRequest] = {}

        _collect_hitl_requests(
            ExecutorResult(
                executor_id="reviewer",
                output_message=None,
                activity_result={
                    "pending_request_info_events": [
                        {
                            "request_id": "req-1",
                            "data": {"question": "approve?"},
                            "request_type": "ApprovalRequest",
                            "response_type": "ApprovalResponse",
                        }
                    ]
                },
                task_type=TaskType.ACTIVITY,
            ),
            pending,
        )

        assert pending["req-1"] == PendingHITLRequest(
            request_id="req-1",
            source_executor_id="reviewer",
            request_data={"question": "approve?"},
            request_type="ApprovalRequest",
            response_type="ApprovalResponse",
        )

    def test_route_hitl_response_enqueues_message_for_source_executor(self) -> None:
        pending_messages: dict[str, list[tuple[Any, str]]] = {}

        _route_hitl_response(
            PendingHITLRequest(
                request_id="req-2",
                source_executor_id="reviewer",
                request_data={"question": "approve?"},
                request_type="ApprovalRequest",
                response_type="ApprovalResponse",
            ),
            {"approved": True},
            pending_messages,
        )

        assert pending_messages == {
            "reviewer": [
                (
                    {
                        "request_id": "req-2",
                        "original_request": {"question": "approve?"},
                        "response": {"approved": True},
                        "response_type": "ApprovalResponse",
                    },
                    f"{SOURCE_HITL_RESPONSE}_req-2",
                )
            ]
        }


class TestResultRoutingHelpers:
    """Result-processing helpers update state and feed routing queues correctly."""

    def test_process_activity_result_applies_state_updates_and_outputs(self) -> None:
        shared_state = {"keep": 1, "drop": 2}
        workflow_outputs: list[Any] = []

        result = _process_activity_result(
            json.dumps({
                "shared_state_updates": {"added": 3},
                "shared_state_deletes": ["drop"],
                "outputs": ["out-1"],
            }),
            "router",
            shared_state,
            workflow_outputs,
        )

        assert result.task_type == TaskType.ACTIVITY
        assert shared_state == {"keep": 1, "added": 3}
        assert workflow_outputs == ["out-1"]

    def test_route_result_messages_handles_output_messages_explicit_targets_and_fanin(self) -> None:
        fan_in_group = FanInEdgeGroup(source_ids=["router", "other"], target_id="joined")
        edge_group = SingleEdgeGroup(source_id="router", target_id="next", condition=lambda _message: True)
        workflow = Mock()
        workflow.edge_groups = [fan_in_group, edge_group]

        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}
        fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]] = {fan_in_group.id: defaultdict(list)}

        _route_result_messages(
            ExecutorResult(
                executor_id="router",
                output_message=_agent_response("assistant said hello"),
                activity_result={
                    "sent_messages": [
                        {
                            "message": serialize_value(0),
                            "target_id": "explicit",
                            "source_id": "router",
                        }
                    ]
                },
                task_type=TaskType.ACTIVITY,
            ),
            workflow,
            next_pending_messages,
            fan_in_pending,
        )

        assert next_pending_messages["next"][0][1] == "router"
        assert next_pending_messages["explicit"] == [(0, "router")]
        assert fan_in_pending[fan_in_group.id]["router"][0][1] == "router"

    def test_check_fan_in_ready_delivers_aggregated_messages(self) -> None:
        fan_in_group = FanInEdgeGroup(source_ids=["a", "b"], target_id="joined")
        workflow = Mock()
        workflow.edge_groups = [fan_in_group]
        fan_in_pending = {
            fan_in_group.id: {
                "a": [("from-a", "a")],
                "b": [("from-b", "b")],
            }
        }
        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}

        _check_fan_in_ready(workflow, fan_in_pending, next_pending_messages)

        assert next_pending_messages == {"joined": [(["from-a", "from-b"], "a")]}
        assert fan_in_pending[fan_in_group.id] == defaultdict(list)

    def test_check_fan_in_ready_waits_for_all_sources(self) -> None:
        fan_in_group = FanInEdgeGroup(source_ids=["a", "b"], target_id="joined")
        workflow = Mock()
        workflow.edge_groups = [fan_in_group]
        fan_in_pending = {fan_in_group.id: {"a": [("from-a", "a")]}}
        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}

        _check_fan_in_ready(workflow, fan_in_pending, next_pending_messages)

        assert next_pending_messages == {}


class TestPrimaryInputSelection:
    """Primary-input type selection skips non-concrete declarations."""

    def test_returns_first_concrete_type(self) -> None:
        executor = Mock()
        executor.input_types = ["not-a-type", dict, str]

        assert _select_primary_input_type(executor) is dict

    def test_returns_none_when_no_concrete_type_exists(self) -> None:
        executor = Mock()
        executor.input_types = ["not-a-type", Mock()]

        assert _select_primary_input_type(executor) is None
