# Copyright (c) Microsoft. All rights reserved.

"""Worker wrapper for Durable Task Agent Framework.

This module provides the DurableAIAgentWorker class that wraps a durabletask worker
and enables registration of agents as durable entities.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from agent_framework import AgentProtocol, get_logger
from durabletask.worker import TaskHubGrpcWorker

from ._callbacks import AgentResponseCallbackProtocol
from ._constants import DEFAULT_TIME_TO_LIVE_DAYS, MINIMUM_TTL_SIGNAL_DELAY_MINUTES
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
        from agent_framework_durabletask import DurableAIAgentWorker

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
        default_time_to_live: timedelta | None = timedelta(days=DEFAULT_TIME_TO_LIVE_DAYS),
        minimum_ttl_signal_delay: timedelta = timedelta(minutes=MINIMUM_TTL_SIGNAL_DELAY_MINUTES),
    ):
        """Initialize the worker wrapper.

        Args:
            worker: The durabletask worker instance to wrap
            callback: Optional callback for agent response notifications
            default_time_to_live: Default TTL for agent entities. If an agent entity is idle
                for this duration, it will be automatically deleted. Defaults to 14 days.
                Set to None to disable TTL for agents without explicit TTL configuration.
            minimum_ttl_signal_delay: Minimum delay for scheduling TTL deletion signals.
                Defaults to 5 minutes. This prevents excessive scheduling overhead.

        Raises:
            ValueError: If minimum_ttl_signal_delay exceeds 5 minutes.
        """
        max_delay = timedelta(minutes=5)
        if minimum_ttl_signal_delay > max_delay:
            raise ValueError(f"minimum_ttl_signal_delay cannot exceed {max_delay}. Got: {minimum_ttl_signal_delay}")

        self._worker = worker
        self._callback = callback
        self._default_time_to_live = default_time_to_live
        self._minimum_ttl_signal_delay = minimum_ttl_signal_delay
        self._registered_agents: dict[str, AgentProtocol] = {}
        self._agent_time_to_live: dict[str, timedelta | None] = {}
        logger.debug("[DurableAIAgentWorker] Initialized with worker type: %s", type(worker).__name__)

    def add_agent(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
        time_to_live: timedelta | None = None,
    ) -> None:
        """Register an agent with the worker.

        This method creates a durable entity class for the agent and registers
        it with the underlying durabletask worker. The entity will be accessible
        by the name "dafx-{agent_name}".

        Args:
            agent: The agent to register (must have a name)
            callback: Optional callback for this specific agent (overrides worker-level callback)
            time_to_live: Optional TTL for this agent's entities. If an entity is idle for
                this duration, it will be automatically deleted. If not specified, uses
                the worker's default_time_to_live. Pass a sentinel value to explicitly
                disable TTL for this agent.

        Raises:
            ValueError: If the agent doesn't have a name or is already registered
        """
        agent_name = agent.name
        if not agent_name:
            raise ValueError("Agent must have a name to be registered")

        if agent_name in self._registered_agents:
            raise ValueError(f"Agent '{agent_name}' is already registered")

        logger.info("[DurableAIAgentWorker] Registering agent: %s as entity: dafx-%s", agent_name, agent_name)

        # Store the agent reference and TTL configuration
        self._registered_agents[agent_name] = agent
        if time_to_live is not None:
            self._agent_time_to_live[agent_name] = time_to_live

        # Use agent-specific callback if provided, otherwise use worker-level callback
        effective_callback = callback or self._callback

        # Get the effective TTL for this agent
        effective_ttl = self.get_time_to_live(agent_name)

        # Create a configured entity class using the factory
        entity_class = self.__create_agent_entity(agent, effective_callback, effective_ttl)

        # Register the entity class with the worker
        # The worker.add_entity method takes a class
        entity_registered: str = self._worker.add_entity(entity_class)  # pyright: ignore[reportUnknownMemberType]

        logger.debug(
            "[DurableAIAgentWorker] Successfully registered entity class %s for agent: %s (TTL: %s)",
            entity_registered,
            agent_name,
            effective_ttl,
        )

    def start(self) -> None:
        """Start the worker to begin processing tasks.

        Note:
            This method delegates to the underlying worker's start method.
            The worker will block until stopped.
        """
        logger.info("[DurableAIAgentWorker] Starting worker with %d registered agents", len(self._registered_agents))
        self._worker.start()

    def stop(self) -> None:
        """Stop the worker gracefully.

        Note:
            This method delegates to the underlying worker's stop method.
        """
        logger.info("[DurableAIAgentWorker] Stopping worker")
        self._worker.stop()

    @property
    def registered_agent_names(self) -> list[str]:
        """Get the names of all registered agents.

        Returns:
            List of agent names (without the dafx- prefix)
        """
        return list(self._registered_agents.keys())

    def get_time_to_live(self, agent_name: str) -> timedelta | None:
        """Get the TTL for a specific agent.

        Args:
            agent_name: The name of the agent

        Returns:
            The TTL for the agent, or the default TTL if not specified.
            Returns None if TTL is disabled for this agent.
        """
        if agent_name in self._agent_time_to_live:
            return self._agent_time_to_live[agent_name]
        return self._default_time_to_live

    @property
    def minimum_ttl_signal_delay(self) -> timedelta:
        """Get the minimum delay for TTL deletion signals."""
        return self._minimum_ttl_signal_delay

    def __create_agent_entity(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
        time_to_live: timedelta | None = None,
    ) -> type[DurableTaskEntityStateProvider]:
        """Factory function to create a DurableEntity class configured with an agent.

        This factory creates a new class that combines the entity state provider
        with the agent execution logic. Each agent gets its own entity class.

        Args:
            agent: The agent instance to wrap
            callback: Optional callback for agent responses
            time_to_live: Optional TTL for this agent's entities

        Returns:
            A new DurableEntity subclass configured for this agent
        """
        agent_name = agent.name or type(agent).__name__
        entity_name = f"dafx-{agent_name}"
        minimum_signal_delay = self._minimum_ttl_signal_delay

        class ConfiguredAgentEntity(DurableTaskEntityStateProvider):
            """Durable entity configured with a specific agent instance."""

            def __init__(self) -> None:
                super().__init__()
                # Create the AgentEntity with this state provider
                self._agent_entity = AgentEntity(
                    agent=agent,
                    callback=callback,
                    state_provider=self,
                    time_to_live=time_to_live,
                    minimum_ttl_signal_delay=minimum_signal_delay,
                )
                logger.debug(
                    "[ConfiguredAgentEntity] Initialized entity for agent: %s (entity name: %s, TTL: %s)",
                    agent_name,
                    entity_name,
                    time_to_live,
                )

            def run(self, request: Any) -> Any:
                """Handle run requests from clients or orchestrations.

                Args:
                    request: RunRequest as dict or string

                Returns:
                    AgentRunResponse as dict
                """
                logger.debug("[ConfiguredAgentEntity.run] Executing agent: %s", agent_name)
                # Get or create event loop for async execution
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Run the async agent execution synchronously
                if loop.is_running():
                    # If loop is already running (shouldn't happen in entity context),
                    # create a temporary loop
                    temp_loop = asyncio.new_event_loop()
                    try:
                        response = temp_loop.run_until_complete(self._agent_entity.run(request))
                    finally:
                        temp_loop.close()
                else:
                    response = loop.run_until_complete(self._agent_entity.run(request))

                return response.to_dict()

            def reset(self) -> None:
                """Reset the agent's conversation history."""
                logger.debug("[ConfiguredAgentEntity.reset] Resetting agent: %s", agent_name)
                self._agent_entity.reset()

            def check_and_delete_if_expired(self) -> None:
                """Check if the entity has expired and delete it if so.

                This method is called by a scheduled signal to check TTL expiration.
                """
                logger.debug(
                    "[ConfiguredAgentEntity.check_and_delete_if_expired] Checking expiration for agent: %s", agent_name
                )
                self._agent_entity.check_and_delete_if_expired()

        # Set the entity name to match the prefixed agent name
        # This is used by durabletask to register the entity
        ConfiguredAgentEntity.__name__ = entity_name
        ConfiguredAgentEntity.__qualname__ = entity_name

        return ConfiguredAgentEntity
