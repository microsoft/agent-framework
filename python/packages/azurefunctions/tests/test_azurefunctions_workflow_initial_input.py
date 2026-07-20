# Copyright (c) Microsoft. All rights reserved.

"""Behavioral tests for Azure Functions workflow HTTP initial input."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar
from unittest.mock import AsyncMock, Mock, patch

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from agent_framework_azurefunctions import AgentFunctionApp

FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def _identity_decorator(*args: Any, **kwargs: Any) -> Callable[[FuncT], FuncT]:
    def decorator(func: FuncT) -> FuncT:
        return func

    return decorator


class _Start(Executor):
    def __init__(self) -> None:
        super().__init__(id="start")

    @handler(input=str | dict, workflow_output=str)
    async def run(self, message: str | dict, ctx: WorkflowContext) -> None:
        pass


def _capture_run_handler(workflow: Workflow) -> Callable[..., Any]:
    captured_routes: dict[str, Callable[..., Any]] = {}

    def capture_route(*args: Any, **kwargs: Any) -> Callable[[FuncT], FuncT]:
        def decorator(func: FuncT) -> FuncT:
            captured_routes[kwargs["route"]] = func
            return func

        return decorator

    with (
        patch.object(AgentFunctionApp, "function_name", new=_identity_decorator),
        patch.object(AgentFunctionApp, "route", new=capture_route),
        patch.object(AgentFunctionApp, "durable_client_input", new=_identity_decorator),
        patch.object(AgentFunctionApp, "activity_trigger", new=_identity_decorator),
        patch.object(AgentFunctionApp, "orchestration_trigger", new=_identity_decorator),
    ):
        AgentFunctionApp(workflow=workflow, enable_health_check=False)

    return captured_routes[f"workflow/{workflow.name}/run"]


async def test_workflow_run_route_neutralizes_reserved_marker_shaped_input() -> None:
    """The workflow run route schedules neutralized framework-reserved metadata."""
    executor = _Start()
    workflow = WorkflowBuilder(name="input_boundary", start_executor=executor, output_from=[executor]).build()
    handler = _capture_run_handler(workflow)
    request = Mock()
    request.get_json.return_value = {
        "__pickled__": "not-checkpoint-data",
        "__type__": "builtins:int",
    }
    request.url = "https://example.test/api/workflow/input_boundary/run"
    client = AsyncMock()
    client.start_new.return_value = "instance-1"

    await handler(request, client)

    assert client.start_new.await_args.kwargs["client_input"] is None
