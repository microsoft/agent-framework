# Copyright (c) Microsoft. All rights reserved.

"""Azure Functions adapter for WorkflowOrchestrationContext.

Wraps ``azure.durable_functions.DurableOrchestrationContext`` to satisfy the
:class:`~agent_framework_durabletask.WorkflowOrchestrationContext` protocol.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agent_framework_durabletask import AgentSessionId, DurableAgentSession, DurableAIAgent
from azure.durable_functions import DurableOrchestrationContext

from ._orchestration import AzureFunctionsAgentExecutor

logger = logging.getLogger(__name__)


class AzureFunctionsWorkflowContext:
    """Adapter that maps ``DurableOrchestrationContext`` to ``WorkflowOrchestrationContext``."""

    def __init__(self, context: DurableOrchestrationContext) -> None:
        self._context = context

    # -- Properties -----------------------------------------------------------

    @property
    def instance_id(self) -> str:
        # Typed local (not cast): mypy sees the untyped context as Any, while
        # pyright sees a concrete str - the annotation satisfies both.
        instance_id: str = self._context.instance_id
        return instance_id

    @property
    def is_replaying(self) -> bool:
        is_replaying: bool = self._context.is_replaying
        return is_replaying

    @property
    def supports_event_streaming(self) -> bool:
        # The Azure Functions host has no workflow event-streaming endpoint, and its
        # Durable Functions custom status is capped at 16 KB by the WebJobs extension.
        # Publishing the accumulating event log would overflow that cap and fail the
        # orchestrator, so events are omitted; state, pending HITL requests, and the
        # final output remain available via the workflow status endpoint.
        return False

    @property
    def current_utc_datetime(self) -> datetime:
        current: datetime = self._context.current_utc_datetime
        return current

    # -- Agent / Activity dispatch --------------------------------------------

    def prepare_agent_task(self, executor_id: str, message: str, orchestration_instance_id: str) -> Any:
        session_id = AgentSessionId(name=executor_id, key=orchestration_instance_id)
        session = DurableAgentSession(durable_session_id=session_id)
        az_executor = AzureFunctionsAgentExecutor(self._context)
        agent = DurableAIAgent(az_executor, executor_id)
        return agent.run(message, session=session)

    def prepare_activity_task(self, activity_name: str, input_json: str) -> Any:
        orchestration_context: Any = self._context
        return orchestration_context.call_activity(activity_name, input_json)

    # -- Composite tasks ------------------------------------------------------

    def task_all(self, tasks: list[Any]) -> Any:
        return self._context.task_all(tasks)

    def task_any(self, tasks: list[Any]) -> Any:
        return self._context.task_any(tasks)

    # -- External events / timers ---------------------------------------------

    def wait_for_external_event(self, name: str) -> Any:
        return self._context.wait_for_external_event(name)

    def create_timer(self, fire_at: datetime) -> Any:
        return self._context.create_timer(fire_at)

    # -- Status / utility -----------------------------------------------------

    def set_custom_status(self, status: Any) -> None:
        self._context.set_custom_status(status)

    def new_uuid(self) -> str:
        new_uuid: str = self._context.new_uuid()
        return new_uuid

    def cancel_task(self, task: Any) -> None:
        cancel_fn = getattr(task, "cancel", None)
        if callable(cancel_fn):
            cancel_fn()

    def get_task_result(self, task: Any) -> Any:
        return getattr(task, "result", None)
