# Copyright (c) Microsoft. All rights reserved.

"""Worker wrapper for Durable Task Agent Framework.

This module provides the DurableAIAgentWorker class that wraps a durabletask worker
and enables registration of agents as durable entities, and optionally workflows
as durable orchestrations with automatically generated activity functions.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import SupportsAgentRun, Workflow
from durabletask.task import ActivityContext, OrchestrationContext
from durabletask.worker import TaskHubGrpcWorker

from ._async_bridge import run_agent_coroutine
from ._callbacks import AgentResponseCallbackProtocol
from ._entities import AgentEntity, DurableTaskEntityStateProvider
from ._workflows.activity import execute_workflow_activity
from ._workflows.dt_context import DurableTaskWorkflowContext
from ._workflows.orchestrator import WORKFLOW_ORCHESTRATOR_NAME, run_workflow_orchestrator
from ._workflows.registration import plan_workflow_registration

logger = logging.getLogger("agent_framework.durabletask")


class DurableAIAgentWorker:
    """Wrapper for a durabletask worker that hosts agents and workflows.

    This class wraps an existing TaskHubGrpcWorker instance and is the single
    host-side registration surface for a worker process. It supports two
    complementary kinds of work:

    - **Agents** via :meth:`add_agent`, which registers each agent as a durable entity.
    - **Workflows** via :meth:`configure_workflow`, which registers a MAF
      ``Workflow`` (its agent executors as entities, its non-agent executors as
      activities, and the workflow orchestrator).

    A single worker process commonly hosts both, so registration is intentionally
    aggregated on one object rather than split per kind. (On the *client* side the
    surfaces are split into :class:`DurableAIAgentClient` and ``DurableWorkflowClient``,
    because a caller invokes one or the other.)

    Example:
        ```python
        from durabletask.worker import TaskHubGrpcWorker
        from agent_framework import Agent
        from agent_framework.openai import OpenAIChatCompletionClient
        from agent_framework_durabletask import DurableAIAgentWorker

        # Create the underlying worker
        worker = TaskHubGrpcWorker(host_address="localhost:4001")

        # Wrap it with the agent worker
        agent_worker = DurableAIAgentWorker(worker)

        # Register agents (or call configure_workflow(workflow) to host a workflow)
        client = OpenAIChatCompletionClient()
        my_agent = Agent(client=client, name="assistant")
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
        self._registered_agents: dict[str, SupportsAgentRun] = {}
        self._workflow: Workflow | None = None
        logger.debug("[DurableAIAgentWorker] Initialized with worker type: %s", type(worker).__name__)

    def add_agent(
        self,
        agent: SupportsAgentRun,
        callback: AgentResponseCallbackProtocol | None = None,
        *,
        entity_id: str | None = None,
    ) -> None:
        """Register an agent with the worker.

        This method creates a durable entity class for the agent and registers
        it with the underlying durabletask worker. The entity will be accessible
        by the name "dafx-{entity_id or agent_name}".

        Args:
            agent: The agent to register (must have a name)
            callback: Optional callback for this specific agent (overrides worker-level callback)
            entity_id: Optional identity to register the entity under instead of
                ``agent.name``. Workflow hosting passes the executor's ``id`` so the
                entity matches the identity the orchestrator dispatches to.

        Raises:
            ValueError: If the agent doesn't have a name or is already registered
        """
        registration_name = entity_id or agent.name
        if not registration_name:
            raise ValueError("Agent must have a name to be registered")

        if registration_name in self._registered_agents:
            raise ValueError(f"Agent '{registration_name}' is already registered")

        logger.info(
            "[DurableAIAgentWorker] Registering agent: %s as entity: dafx-%s", registration_name, registration_name
        )

        # Store the agent reference
        self._registered_agents[registration_name] = agent

        # Use agent-specific callback if provided, otherwise use worker-level callback
        effective_callback = callback or self._callback

        # Create a configured entity class using the factory
        entity_class = self.__create_agent_entity(agent, effective_callback, entity_id=registration_name)

        # Register the entity class with the worker
        # The worker.add_entity method takes a class
        entity_registered: str = self._worker.add_entity(entity_class)

        logger.debug(
            "[DurableAIAgentWorker] Successfully registered entity class %s for agent: %s",
            entity_registered,
            registration_name,
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

    # -----------------------------------------------------------------
    # Workflow support
    # -----------------------------------------------------------------

    def configure_workflow(
        self,
        workflow: Workflow,
        callback: AgentResponseCallbackProtocol | None = None,
    ) -> None:
        """Register a :class:`Workflow` for automatic orchestration.

        This extracts agents from the workflow and registers them as durable
        entities, registers non-agent executors as activities, and creates an
        orchestrator function that drives the workflow graph.

        Args:
            workflow: The MAF :class:`Workflow` to register.
            callback: Optional callback for agent response notifications.
        """
        self._workflow = workflow

        # The "what to register" decision (agent -> entity, non-agent -> activity)
        # is shared with the Azure Functions host via plan_workflow_registration.
        plan = plan_workflow_registration(workflow)

        # Register agent executors as durable entities. Each entity is keyed by
        # the executor's id (the identity the orchestrator dispatches to) so
        # AgentExecutor(agent, id=...) works even when the id differs from the
        # agent's name.
        for agent_executor in plan.agent_executors:
            if agent_executor.id not in self._registered_agents:
                self.add_agent(agent_executor.agent, callback=callback, entity_id=agent_executor.id)

        # Register non-agent executors as durable activities.
        for executor in plan.activity_executors:
            self._register_executor_activity(executor)

        # Register the workflow orchestrator.
        self._register_workflow_orchestrator()

        logger.info(
            "[DurableAIAgentWorker] Workflow configured with %d executors (%d agents, %d activities)",
            len(workflow.executors),
            len(plan.agent_executors),
            len(plan.activity_executors),
        )

    def _register_executor_activity(self, executor: Any) -> None:
        """Register a non-agent executor as a durabletask activity."""
        captured_executor = executor
        captured_workflow = self._workflow
        activity_name = f"dafx-{executor.id}"

        def executor_activity(ctx: ActivityContext, input_data: str) -> str:
            return execute_workflow_activity(captured_executor, input_data, captured_workflow)

        # Give the function the expected name for registration
        executor_activity.__name__ = activity_name
        executor_activity.__qualname__ = activity_name

        self._worker.add_activity(executor_activity)
        logger.debug("[DurableAIAgentWorker] Registered activity: %s", activity_name)

    def _register_workflow_orchestrator(self) -> None:
        """Register the workflow orchestrator function with the worker."""
        captured_workflow = self._workflow

        def workflow_orchestrator(context: OrchestrationContext, input_data: Any) -> Any:
            if captured_workflow is None:
                raise RuntimeError("Workflow not configured")

            # Pass the deserialized client input straight to the shared engine, which
            # reconstructs the start executor's declared type (see _coerce_initial_input).
            initial_message = input_data
            shared_state: dict[str, Any] = {}

            dt_ctx = DurableTaskWorkflowContext(context)
            outputs = yield from run_workflow_orchestrator(dt_ctx, captured_workflow, initial_message, shared_state)
            return outputs  # noqa: B901

        workflow_orchestrator.__name__ = WORKFLOW_ORCHESTRATOR_NAME
        workflow_orchestrator.__qualname__ = WORKFLOW_ORCHESTRATOR_NAME

        self._worker.add_orchestrator(workflow_orchestrator)
        logger.debug("[DurableAIAgentWorker] Registered workflow orchestrator")

    def __create_agent_entity(
        self,
        agent: SupportsAgentRun,
        callback: AgentResponseCallbackProtocol | None = None,
        *,
        entity_id: str | None = None,
    ) -> type[DurableTaskEntityStateProvider]:
        """Factory function to create a DurableEntity class configured with an agent.

        This factory creates a new class that combines the entity state provider
        with the agent execution logic. Each agent gets its own entity class.

        Args:
            agent: The agent instance to wrap
            callback: Optional callback for agent responses
            entity_id: Optional identity to register the entity under instead of
                ``agent.name`` (used by workflow hosting to key entities by
                executor id).

        Returns:
            A new DurableEntity subclass configured for this agent
        """
        agent_name = entity_id or agent.name or type(agent).__name__
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
                # Run on the shared persistent loop so async resources created by
                # shared agent clients/credentials stay bound to a live loop across
                # successive entity invocations (avoids cross-loop hangs).
                response = run_agent_coroutine(self._agent_entity.run(request))
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
