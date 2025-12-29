# Copyright (c) Microsoft. All rights reserved.

"""Orchestration Support for Durable Agents.

This module provides support for using agents inside Durable Function orchestrations.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias

import azure.durable_functions as df
from agent_framework import AgentThread, get_logger
from agent_framework_durabletask import (
    AgentSessionId,
    DurableAgentExecutor,
    DurableAgentThread,
    RunRequest,
    ensure_response_format,
    load_agent_response,
)
from azure.durable_functions.models import TaskBase
from azure.durable_functions.models.Task import CompoundTask, TaskState
from pydantic import BaseModel

logger = get_logger("agent_framework.azurefunctions.orchestration")

CompoundActionConstructor: TypeAlias = Callable[[list[Any]], Any] | None

if TYPE_CHECKING:
    from azure.durable_functions import DurableOrchestrationContext

    class _TypedCompoundTask(CompoundTask):  # type: ignore[misc]
        _first_error: Any

        def __init__(
            self,
            tasks: list[TaskBase],
            compound_action_constructor: CompoundActionConstructor = None,
        ) -> None: ...

    AgentOrchestrationContextType: TypeAlias = DurableOrchestrationContext
else:
    AgentOrchestrationContextType = Any
    _TypedCompoundTask = CompoundTask


class AgentTask(_TypedCompoundTask):
    """A custom Task that wraps entity calls and provides typed AgentRunResponse results.

    This task wraps the underlying entity call task and intercepts its completion
    to convert the raw result into a typed AgentRunResponse object.
    """

    def __init__(
        self,
        entity_task: TaskBase,
        response_format: type[BaseModel] | None,
        correlation_id: str,
    ):
        """Initialize the AgentTask.

        Args:
            entity_task: The underlying entity call task
            response_format: Optional Pydantic model for response parsing
            correlation_id: Correlation ID for logging
        """
        super().__init__([entity_task])
        self._response_format = response_format
        self._correlation_id = correlation_id

        # Override action_repr to expose the inner task's action directly
        # This ensures compatibility with ReplaySchema V3 which expects Action objects.
        self.action_repr = entity_task.action_repr

        # Also copy the task ID to match the entity task's identity
        self.id = entity_task.id

    def try_set_value(self, child: TaskBase) -> None:
        """Transition the AgentTask to a terminal state and set its value to `AgentRunResponse`.

        Parameters
        ----------
        child : TaskBase
            The entity call task that just completed
        """
        if child.state is TaskState.SUCCEEDED:
            # Delegate to parent class for standard completion logic
            if len(self.pending_tasks) == 0:
                # Transform the raw result before setting it
                raw_result = child.result
                logger.debug(
                    "[AgentTask] Converting raw result for correlation_id %s",
                    self._correlation_id,
                )

                try:
                    response = load_agent_response(raw_result)

                    if self._response_format is not None:
                        ensure_response_format(
                            self._response_format,
                            self._correlation_id,
                            response,
                        )

                    # Set the typed AgentRunResponse as this task's result
                    self.set_value(is_error=False, value=response)
                except Exception as e:
                    logger.exception(
                        "[AgentTask] Failed to convert result for correlation_id: %s",
                        self._correlation_id,
                    )
                    self.set_value(is_error=True, value=e)
        else:
            # If error not handled by the parent, set it explicitly.
            if self._first_error is None:
                self._first_error = child.result
                self.set_value(is_error=True, value=self._first_error)


class AzureFunctionsAgentExecutor(DurableAgentExecutor[AgentTask]):
    """Executor that executes durable agents inside Azure Functions orchestrations."""

    def __init__(self, context: AgentOrchestrationContextType):
        self.context = context

    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        enable_tool_calls: bool | None = None,
        **kwargs: Any,
    ) -> AgentTask:
        # Extract optional parameters
        enable_tools = True if enable_tool_calls is None else enable_tool_calls

        # Resolve session
        if isinstance(thread, DurableAgentThread) and thread.session_id is not None:
            session_id = thread.session_id
        else:
            session_key = str(self.context.new_uuid())
            session_id = AgentSessionId(name=agent_name, key=session_key)
            logger.debug(
                "[AzureFunctionsAgentProvider] No thread provided, created session_id: %s",
                session_id,
            )

        entity_id = df.EntityId(
            name=session_id.entity_name,
            key=session_id.key,
        )
        correlation_id = str(self.context.new_uuid())
        logger.debug(
            "[AzureFunctionsAgentProvider] correlation_id: %s entity_id: %s session_id: %s",
            correlation_id,
            entity_id,
            session_id,
        )

        run_request = RunRequest(
            message=message,
            enable_tool_calls=enable_tools,
            correlation_id=correlation_id,
            response_format=response_format,
            orchestration_id=self.context.instance_id,
            created_at=self.context.current_utc_datetime,
        )

        entity_task = self.context.call_entity(entity_id, "run", run_request.to_dict())
        return AgentTask(
            entity_task=entity_task,
            response_format=response_format,
            correlation_id=correlation_id,
        )

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        session_key = str(self.context.new_uuid())
        session_id = AgentSessionId(name=agent_name, key=session_key)
        return DurableAgentThread.from_session_id(session_id, **kwargs)
