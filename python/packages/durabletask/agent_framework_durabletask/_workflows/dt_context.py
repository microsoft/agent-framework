# Copyright (c) Microsoft. All rights reserved.

"""DurableTask SDK adapter for WorkflowOrchestrationContext.

Wraps ``durabletask.task.OrchestrationContext`` to satisfy the
:class:`WorkflowOrchestrationContext` protocol.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

from durabletask.task import (
    OrchestrationContext,
    Task,
    when_all,
    when_any,
)

from .._executors import OrchestrationAgentExecutor
from .._models import AgentSessionId, DurableAgentSession
from .._shim import DurableAIAgent
from .context import WorkflowOrchestrationContext

logger = logging.getLogger(__name__)


class DurableTaskWorkflowContext:
    """Adapter that maps ``OrchestrationContext`` to :class:`WorkflowOrchestrationContext`."""

    def __init__(self, context: OrchestrationContext) -> None:
        self._context = context
        self._executor = OrchestrationAgentExecutor(context)

    # -- Properties -----------------------------------------------------------

    @property
    def instance_id(self) -> str:
        return self._context.instance_id

    @property
    def is_replaying(self) -> bool:
        return self._context.is_replaying

    @property
    def supports_event_streaming(self) -> bool:
        # The standalone DurableTask host exposes the event timeline to clients via
        # DurableWorkflowClient.stream_workflow, and its DTS backend imposes no 16 KB
        # custom-status cap, so the full accumulated event stream is published.
        return True

    @property
    def current_utc_datetime(self) -> datetime:
        return self._context.current_utc_datetime

    # -- Agent / Activity dispatch --------------------------------------------

    def prepare_agent_task(self, executor_id: str, message: str, orchestration_instance_id: str) -> Any:
        session_id = AgentSessionId(name=executor_id, key=orchestration_instance_id)
        session = DurableAgentSession(durable_session_id=session_id)
        agent = DurableAIAgent(self._executor, executor_id)
        return agent.run(message, session=session)

    def prepare_activity_task(self, activity_name: str, input_json: str) -> Any:
        return cast(Any, self._context.call_activity(activity_name, input=input_json))

    # -- Composite tasks ------------------------------------------------------

    def task_all(self, tasks: list[Any]) -> Any:
        return when_all(tasks)

    def task_any(self, tasks: list[Any]) -> Any:
        return when_any(tasks)

    # -- External events / timers ---------------------------------------------

    def wait_for_external_event(self, name: str) -> Any:
        return cast(Any, self._context).wait_for_external_event(name)

    def create_timer(self, fire_at: datetime) -> Any:
        return cast(Any, self._context).create_timer(fire_at)

    # -- Status / utility -----------------------------------------------------

    def set_custom_status(self, status: Any) -> None:
        self._context.set_custom_status(status)

    def new_uuid(self) -> str:
        return self._context.new_uuid()

    def cancel_task(self, task: Any) -> None:
        # durabletask Task doesn't expose cancel(); this is a best-effort no-op.
        cancel_fn = getattr(task, "cancel", None)
        if callable(cancel_fn):
            cancel_fn()

    def get_task_result(self, task: Any) -> Any:
        if isinstance(task, Task):
            return cast(Any, task.get_result())
        return getattr(task, "result", None)


# Ensure the adapter satisfies the protocol. Validated statically by the type
# checker (and at every ``run_workflow_orchestrator`` call site) with no runtime cost.
_protocol_check: type[WorkflowOrchestrationContext] = DurableTaskWorkflowContext
