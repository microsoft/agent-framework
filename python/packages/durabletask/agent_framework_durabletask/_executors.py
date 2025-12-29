# Copyright (c) Microsoft. All rights reserved.

"""Provider strategies for Durable Agent execution.

These classes are internal execution strategies used by the DurableAIAgent shim.
They are intentionally separate from the public client/orchestration APIs to keep
only `get_agent` exposed to consumers. Providers implement the execution contract
and are injected into the shim.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from agent_framework import AgentRunResponse, AgentThread, get_logger
from durabletask.task import CompositeTask, Task
from pydantic import BaseModel

from ._models import DurableAgentThread
from ._response_utils import ensure_response_format, load_agent_response

if TYPE_CHECKING:  # pragma: no cover
    from durabletask.client import TaskHubGrpcClient
    from durabletask.task import OrchestrationContext

logger = get_logger("agent_framework.durabletask.executors")

# TypeVar for the task type returned by executors
TaskT = TypeVar("TaskT")


class DurableAgentTask(CompositeTask[AgentRunResponse]):
    """A custom Task that wraps entity calls and provides typed AgentRunResponse results.

    This task wraps the underlying entity call task and intercepts its completion
    to convert the raw result into a typed AgentRunResponse object.
    """

    def __init__(
        self,
        entity_task: Task[AgentRunResponse],
        response_format: type[BaseModel] | None,
        correlation_id: str,
    ):
        """Initialize the DurableAgentTask.

        Args:
            entity_task: The underlying entity call task
            response_format: Optional Pydantic model for response parsing
            correlation_id: Correlation ID for logging
        """
        super().__init__([entity_task])  # type: ignore[misc]
        self._response_format = response_format
        self._correlation_id = correlation_id

    def on_child_completed(self, task: Task[Any]) -> None:
        """Handle completion of the underlying entity task.

        Parameters
        ----------
        task : Task
            The entity call task that just completed
        """
        if self.is_complete:
            return

        if task.is_failed:
            # Propagate the failure
            self._exception = task.get_exception()
            self._is_complete = True
            if self._parent is not None:
                self._parent.on_child_completed(self)
            return

        # Task succeeded - transform the raw result
        raw_result = task.get_result()
        logger.debug(
            "[DurableAgentTask] Converting raw result for correlation_id %s",
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
            self._result = response
            self._is_complete = True

            if self._parent is not None:
                self._parent.on_child_completed(self)

        except Exception:
            logger.exception(
                "[DurableAgentTask] Failed to convert result for correlation_id: %s",
                self._correlation_id,
            )
            raise


class DurableAgentExecutor(ABC, Generic[TaskT]):
    """Abstract base class for durable agent execution strategies.

    Type Parameters:
        TaskT: The task type returned by this executor
    """

    @abstractmethod
    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> TaskT:
        """Execute the durable agent.

        Returns:
            TaskT: The task type specific to this executor implementation
        """
        raise NotImplementedError

    @abstractmethod
    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new thread appropriate for the provider context."""
        raise NotImplementedError


class ClientAgentExecutor(DurableAgentExecutor[DurableAgentTask]):
    """Execution strategy for external clients (async)."""

    def __init__(self, client: TaskHubGrpcClient):
        self._client = client
        logger.debug("[ClientAgentExecutor] Initialized with client type: %s", type(client).__name__)

    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> DurableAgentTask:
        """Execute the agent via the durabletask client.

        Note: Implementation is backend-specific and should signal/call the entity
        and await the durable response. This placeholder raises NotImplementedError
        until wired to concrete durabletask calls.
        """
        raise NotImplementedError("ClientAgentProvider.run_durable_agent is not yet implemented")

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new AgentThread for client-side execution."""
        return DurableAgentThread(**kwargs)


class OrchestrationAgentExecutor(DurableAgentExecutor[DurableAgentTask]):
    """Execution strategy for orchestrations (sync/yield)."""

    def __init__(self, context: OrchestrationContext):
        self._context = context
        logger.debug("[OrchestrationAgentExecutor] Initialized")

    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> DurableAgentTask:
        """Execute the agent via orchestration context.

        Note: Implementation should call the entity (e.g., context.call_entity)
        and return the native Task for yielding. Placeholder until wired.
        """
        raise NotImplementedError("OrchestrationAgentProvider.run_durable_agent is not yet implemented")

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new AgentThread for orchestration context."""
        return DurableAgentThread(**kwargs)
