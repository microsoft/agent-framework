# Copyright (c) Microsoft. All rights reserved.

"""Worker wrapper for Durable Task Agent Framework.

This module provides the DurableAIAgentWorker class that wraps a durabletask worker
and enables registration of agents as durable entities.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_framework import AgentProtocol, get_logger
from durabletask.worker import TaskHubGrpcWorker

from ._callbacks import AgentResponseCallbackProtocol
from ._entities import AgentEntity, DurableTaskEntityStateProvider

logger = get_logger("agent_framework.durabletask.worker")


class DurableAIAgentWorker:
    """Wrapper for durabletask worker that enables agent registration.

    This class wraps an existing TaskHubGrpcWorker instance and provides
    a convenient interface for registering agents as durable entities.

    Example:
        ```python
        from durabletask import TaskHubGrpcWorker
        from agent_framework import ChatAgent
        from agent_framework.azure import DurableAIAgentWorker

        # Create the underlying worker
        worker = TaskHubGrpcWorker(host_address="localhost:4001")

        # Wrap it with the agent worker
        agent_worker = DurableAIAgentWorker(worker)

        # Register agents
        my_agent = ChatAgent(chat_client=client, name="assistant")
        agent_worker.add_agent(my_agent)

        # Start the worker
        worker.start()
        ```
    """

    def __init__(
        self,
        worker: TaskHubGrpcWorker,
        callback: AgentResponseCallbackProtocol | None = None,
    ):
        """Initialize the worker wrapper.

        Args:
            worker: The durabletask worker instance to wrap
            callback: Optional callback for agent response notifications
        """
        self._worker = worker
        self._callback = callback
        self._registered_agents: dict[str, AgentProtocol] = {}
        logger.debug("[DurableAIAgentWorker] Initialized with worker type: %s", type(worker).__name__)

    def add_agent(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
    ) -> None:
        """Register an agent with the worker.

        This method creates a durable entity class for the agent and registers
        it with the underlying durabletask worker. The entity will be accessible
        by the name "dafx-{agent_name}".

        Args:
            agent: The agent to register (must have a name)
            callback: Optional callback for this specific agent (overrides worker-level callback)

        Raises:
            ValueError: If the agent doesn't have a name or is already registered
        """
        agent_name = agent.name
        if not agent_name:
            raise ValueError("Agent must have a name to be registered")

        if agent_name in self._registered_agents:
            raise ValueError(f"Agent '{agent_name}' is already registered")

        logger.info("[DurableAIAgentWorker] Registering agent: %s as entity: dafx-%s", agent_name, agent_name)

        # Store the agent reference
        self._registered_agents[agent_name] = agent

        # Use agent-specific callback if provided, otherwise use worker-level callback
        effective_callback = callback or self._callback

        # Create a configured entity class using the factory
        entity_class = self.__create_agent_entity(agent, effective_callback)

        # Register the entity class with the worker
        # The worker.add_entity method takes a class
        entity_registered: str = self._worker.add_entity(entity_class)  # pyright: ignore[reportUnknownMemberType]

        logger.debug(
            "[DurableAIAgentWorker] Successfully registered entity class %s for agent: %s",
            entity_registered,
            agent_name,
        )

    def start(self) -> None:
        """Start the worker to begin processing tasks.

        Note:
            This method delegates to the underlying worker's start method.
            The worker will block until stopped.
        """
        logger.info("[DurableAIAgentWorker] Starting worker with %d registered agents", len(self._registered_agents))
        self._worker.start()  # type: ignore[no-untyped-call]

    def stop(self) -> None:
        """Stop the worker gracefully.

        Note:
            This method delegates to the underlying worker's stop method.
        """
        logger.info("[DurableAIAgentWorker] Stopping worker")
        self._worker.stop()  # type: ignore[no-untyped-call]

    @property
    def registered_agent_names(self) -> list[str]:
        """Get the names of all registered agents.

        Returns:
            List of agent names (without the dafx- prefix)
        """
        return list(self._registered_agents.keys())

    def __create_agent_entity(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
    ) -> type[DurableTaskEntityStateProvider]:
        """Factory function to create a DurableEntity class configured with an agent.

        This factory creates a new class that combines the entity state provider
        with the agent execution logic. Each agent gets its own entity class.

        Args:
            agent: The agent instance to wrap
            callback: Optional callback for agent responses

        Returns:
            A new DurableEntity subclass configured for this agent
        """
        agent_name = agent.name or type(agent).__name__
        entity_name = f"dafx-{agent_name}"

        class ConfiguredAgentEntity(DurableTaskEntityStateProvider):
            """Durable entity configured with a specific agent instance."""

            def __init__(self) -> None:
                super().__init__()
                # Create the AgentEntity with this state provider
                self._agent_entity = AgentEntity(
                    agent=agent,
                    callback=callback,
                    state_provider=self,
                )
                logger.debug(
                    "[ConfiguredAgentEntity] Initialized entity for agent: %s (entity name: %s)",
                    agent_name,
                    entity_name,
                )

            def run(self, request: Any) -> Any:
                """Handle run requests from clients or orchestrations.

                Args:
                    request: RunRequest as dict or string

                Returns:
                    AgentResponse as dict
                """
                logger.debug("[ConfiguredAgentEntity.run] Executing agent: %s", agent_name)
                response = asyncio.run(self._agent_entity.run(request))
                return response.to_dict()

            def reset(self) -> None:
                """Reset the agent's conversation history."""
                logger.debug("[ConfiguredAgentEntity.reset] Resetting agent: %s", agent_name)
                self._agent_entity.reset()

        # Set the entity name to match the prefixed agent name
        # This is used by durabletask to register the entity
        ConfiguredAgentEntity.__name__ = entity_name
        ConfiguredAgentEntity.__qualname__ = entity_name

        return ConfiguredAgentEntity
