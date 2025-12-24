# Copyright (c) Microsoft. All rights reserved.

"""Provider strategies for Durable Agent execution.

These classes are internal execution strategies used by the DurableAIAgent shim.
They are intentionally separate from the public client/orchestration APIs to keep
only `get_agent` exposed to consumers. Providers implement the execution contract
and are injected into the shim.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from agent_framework import AgentThread, get_logger
from pydantic import BaseModel

from ._models import DurableAgentThread

if TYPE_CHECKING:  # pragma: no cover
    from durabletask.client import TaskHubGrpcClient
    from durabletask.task import OrchestrationContext

logger = get_logger("agent_framework.durabletask.executors")


class DurableAgentExecutor(ABC):
    """Abstract base class for durable agent execution strategies."""

    @abstractmethod
    def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute the durable agent.

        Returns:
            Any: Either an awaitable AgentRunResponse (Client) or a yieldable Task (Orchestrator).
        """
        raise NotImplementedError

    @abstractmethod
    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new thread appropriate for the provider context."""
        raise NotImplementedError


class ClientAgentExecutor(DurableAgentExecutor):
    """Execution strategy for external clients (async)."""

    def __init__(self, client: TaskHubGrpcClient):
        self._client = client
        logger.debug("[ClientAgentExecutor] Initialized with client type: %s", type(client).__name__)

    async def run_durable_agent(
        self,
        agent_name: str,
        message: str,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute the agent via the durabletask client.

        Note: Implementation is backend-specific and should signal/call the entity
        and await the durable response. This placeholder raises NotImplementedError
        until wired to concrete durabletask calls.
        """
        raise NotImplementedError("ClientAgentProvider.run_durable_agent is not yet implemented")

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new AgentThread for client-side execution."""
        return DurableAgentThread(**kwargs)


class OrchestrationAgentExecutor(DurableAgentExecutor):
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
    ) -> Any:
        """Execute the agent via orchestration context.

        Note: Implementation should call the entity (e.g., context.call_entity)
        and return the native Task for yielding. Placeholder until wired.
        """
        raise NotImplementedError("OrchestrationAgentProvider.run_durable_agent is not yet implemented")

    def get_new_thread(self, agent_name: str, **kwargs: Any) -> DurableAgentThread:
        """Create a new AgentThread for orchestration context."""
        return DurableAgentThread(**kwargs)
