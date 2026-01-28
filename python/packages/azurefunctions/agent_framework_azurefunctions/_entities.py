# Copyright (c) Microsoft. All rights reserved.

"""Durable Entity for Agent Execution.

This module defines a durable entity that manages agent state and execution.
Using entities instead of orchestrations provides better state management and
allows for long-running agent conversations.
"""

import asyncio
from collections.abc import Callable
from typing import Any, cast

import azure.durable_functions as df
from agent_framework import AgentProtocol, get_logger
from agent_framework_durabletask import (
    AgentEntity,
    AgentEntityStateProviderMixin,
    AgentResponseCallbackProtocol,
)

logger = get_logger("agent_framework.azurefunctions.entities")


class AzureFunctionEntityStateProvider(AgentEntityStateProviderMixin):
    """Azure Functions Durable Entity state provider for AgentEntity.

    This class utilizes the Durable Entity context from `azure-functions-durable` package
    to get and set the state of the agent entity.
    """

    def __init__(self, context: df.DurableEntityContext) -> None:
        self._context = context

    def _get_state_dict(self) -> dict[str, Any]:
        raw_state = self._context.get_state(lambda: {})
        if not isinstance(raw_state, dict):
            return {}
        return cast(dict[str, Any], raw_state)

    def _set_state_dict(self, state: dict[str, Any]) -> None:
        self._context.set_state(state)

    def _get_thread_id_from_entity(self) -> str:
        return str(self._context.entity_key)


def create_agent_entity(
    agent: AgentProtocol,
    callback: AgentResponseCallbackProtocol | None = None,
) -> Callable[[df.DurableEntityContext], None]:
    """Factory function to create an agent entity class.

    Args:
        agent: The Microsoft Agent Framework agent instance (must implement AgentProtocol)
        callback: Optional callback invoked during streaming and final responses

    Returns:
        Entity function configured with the agent
    """

    async def _entity_coroutine(context: df.DurableEntityContext) -> None:
        """Async handler that executes the entity operations."""
        try:
            logger.debug("[entity_function] Entity triggered")
            logger.debug("[entity_function] Operation: %s", context.operation_name)

            state_provider = AzureFunctionEntityStateProvider(context)
            entity = AgentEntity(agent, callback, state_provider=state_provider)

            operation = context.operation_name

            if operation == "run" or operation == "run_agent":
                input_data: Any = context.get_input()

                request: str | dict[str, Any]
                if isinstance(input_data, dict) and "message" in input_data:
                    request = cast(dict[str, Any], input_data)
                else:
                    # Fall back to treating input as message string
                    request = "" if input_data is None else str(cast(object, input_data))

                result = await entity.run(request)
                context.set_result(result.to_dict())

            elif operation == "reset":
                entity.reset()
                context.set_result({"status": "reset"})

            else:
                logger.error("[entity_function] Unknown operation: %s", operation)
                context.set_result({"error": f"Unknown operation: {operation}"})

            logger.info("[entity_function] Operation %s completed successfully", operation)

        except Exception as exc:
            logger.exception("[entity_function] Error executing entity operation %s", exc)
            context.set_result({"error": str(exc), "status": "error"})

    def entity_function(context: df.DurableEntityContext) -> None:
        """Synchronous wrapper invoked by the Durable Functions runtime."""
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                temp_loop = asyncio.new_event_loop()
                try:
                    temp_loop.run_until_complete(_entity_coroutine(context))
                finally:
                    temp_loop.close()
            else:
                loop.run_until_complete(_entity_coroutine(context))

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("[entity_function] Unexpected error executing entity: %s", exc, exc_info=True)
            context.set_result({"error": str(exc), "status": "error"})

    return entity_function
