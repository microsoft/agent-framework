# Copyright (c) Microsoft. All rights reserved.

"""Orchestration Support for Durable Agents.

This module provides support for using agents inside Durable Function orchestrations.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias

import azure.durable_functions as df
from agent_framework import AgentThread, get_logger
from agent_framework_durabletask import (
    DurableAgentExecutor,
    RunRequest,
    ensure_response_format,
    load_agent_response,
)
from azure.durable_functions.models import TaskBase
from azure.durable_functions.models.actions.NoOpAction import NoOpAction
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


class PreCompletedTask(TaskBase):  # type: ignore[misc]
    """A simple task that is already completed with a result.

    Used for fire-and-forget mode where we want to return immediately
    with an acceptance response without waiting for entity processing.
    """

    def __init__(self, result: Any):
        """Initialize with a completed result.

        Args:
            result: The result value for this completed task
        """
        # Initialize with a NoOp action since we don't need actual orchestration actions
        super().__init__(-1, NoOpAction())
        # Immediately mark as completed with the result
        self.set_value(is_error=False, value=result)


class AgentTask(_TypedCompoundTask):
    """A custom Task that wraps entity calls and provides typed AgentResponse results.

    This task wraps the underlying entity call task and intercepts its completion
    to convert the raw result into a typed AgentResponse object.
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
        # Set instance variables BEFORE calling super().__init__
        # because super().__init__ may trigger try_set_value for pre-completed tasks
        self._response_format = response_format
        self._correlation_id = correlation_id

        super().__init__([entity_task])

        # Override action_repr to expose the inner task's action directly
        # This ensures compatibility with ReplaySchema V3 which expects Action objects.
        self.action_repr = entity_task.action_repr

        # Also copy the task ID to match the entity task's identity
        self.id = entity_task.id

    def try_set_value(self, child: TaskBase) -> None:
        """Transition the AgentTask to a terminal state and set its value to `AgentResponse`.

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

                    # Set the typed AgentResponse as this task's result
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

    def generate_unique_id(self) -> str:
        return str(self.context.new_uuid())

    def get_run_request(
        self,
        message: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> RunRequest:
        """Get the current run request from the orchestration context.

        Args:
            message: The message to send to the agent
            options: Optional options dictionary. Supported keys include
                ``response_format``, ``enable_tool_calls``, and ``wait_for_response``.
                Additional keys are forwarded to the agent execution.

        Returns:
            RunRequest: The current run request

        Raises:
            ValueError: If wait_for_response=False (not supported in orchestrations)
        """
        # Create a copy to avoid modifying the caller's dict

        request = super().get_run_request(message, options=options)
        request.orchestration_id = self.context.instance_id
        return request

    def run_durable_agent(
        self,
        agent_name: str,
        run_request: RunRequest,
        thread: AgentThread | None = None,
    ) -> AgentTask:

        # Resolve session
        session_id = self._create_session_id(agent_name, thread)

        entity_id = df.EntityId(
            name=session_id.entity_name,
            key=session_id.key,
        )

        logger.debug(
            "[AzureFunctionsAgentProvider] correlation_id: %s entity_id: %s session_id: %s",
            run_request.correlation_id,
            entity_id,
            session_id,
        )

        # Branch based on wait_for_response
        if not run_request.wait_for_response:
            # Fire-and-forget mode: signal entity and return pre-completed task
            logger.debug(
                "[AzureFunctionsAgentExecutor] Fire-and-forget mode: signaling entity (correlation: %s)",
                run_request.correlation_id,
            )
            self.context.signal_entity(entity_id, "run", run_request.to_dict())

            # Create acceptance response using base class helper
            acceptance_response = self._create_acceptance_response(run_request.correlation_id)

            # Create a pre-completed task with the acceptance response
            entity_task = PreCompletedTask(acceptance_response)
        else:
            # Blocking mode: call entity and wait for response
            entity_task = self.context.call_entity(entity_id, "run", run_request.to_dict())

        return AgentTask(
            entity_task=entity_task,
            response_format=run_request.response_format,
            correlation_id=run_request.correlation_id,
        )
