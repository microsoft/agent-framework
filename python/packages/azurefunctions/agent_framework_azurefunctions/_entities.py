# Copyright (c) Microsoft. All rights reserved.

"""Durable Entity for Agent Execution.

This module defines a durable entity that manages agent state and execution.
Using entities instead of orchestrations provides better state management and
allows for long-running agent conversations.
"""

import asyncio
import inspect
from collections.abc import AsyncIterable, Callable
from typing import Any, cast

import azure.durable_functions as df
from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ErrorContent,
    Role,
    get_logger,
)

from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._durable_agent_state import (
    DurableAgentState,
    DurableAgentStateData,
    DurableAgentStateEntry,
    DurableAgentStateRequest,
    DurableAgentStateResponse,
)
from ._models import RunRequest

logger = get_logger("agent_framework.azurefunctions.entities")


class AgentEntity:
    """Durable entity that manages agent execution and conversation state.

    This entity:
    - Maintains conversation history
    - Executes agent with messages
    - Stores agent responses
    - Handles tool execution

    Operations:
    - run_agent: Execute the agent with a message
    - reset: Clear conversation history

    Attributes:
        agent: The AgentProtocol instance
        state: The DurableAgentState managing conversation history
    """

    agent: AgentProtocol
    state: DurableAgentState

    def __init__(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
    ):
        """Initialize the agent entity.

        Args:
            agent: The Microsoft Agent Framework agent instance (must implement AgentProtocol)
            callback: Optional callback invoked during streaming updates and final responses
        """
        self.agent = agent
        self.state = DurableAgentState()
        self.callback = callback

        logger.debug(f"[AgentEntity] Initialized with agent type: {type(agent).__name__}")

    def _is_error_response(self, entry: DurableAgentStateEntry) -> bool:
        """Check if a conversation history entry is an error response.

        Error responses should be kept in history for tracking but not sent to the agent
        since Azure OpenAI doesn't support 'error' content type.

        Args:
            entry: A conversation history entry (DurableAgentStateEntry or dict)

        Returns:
            True if the entry is a response containing error content, False otherwise
        """
        if isinstance(entry, DurableAgentStateResponse):
            return entry.is_error
        return False

    async def run_agent(
        self,
        context: df.DurableEntityContext,
        request: RunRequest | dict[str, Any] | str,
    ) -> AgentRunResponse:
        """Execute the agent with a message directly in the entity.

        Args:
            context: Entity context
            request: RunRequest object, dict, or string message (for backward compatibility)

        Returns:
            AgentRunResponse enriched with execution metadata.
        """
        if isinstance(request, str):
            run_request = RunRequest(message=request, role=Role.USER)
        elif isinstance(request, dict):
            run_request = RunRequest.from_dict(request)
        else:
            run_request = request

        message = run_request.message
        thread_id = run_request.thread_id
        correlation_id = run_request.correlation_id
        if not thread_id:
            raise ValueError("RunRequest must include a thread_id")
        if not correlation_id:
            raise ValueError("RunRequest must include a correlation_id")
        response_format = run_request.response_format
        enable_tool_calls = run_request.enable_tool_calls

        state_request = DurableAgentStateRequest.from_run_request(run_request)
        self.state.data.conversation_history.append(state_request)

        logger.debug(f"[AgentEntity.run_agent] Received Message: {state_request}")

        try:
            # Build messages from conversation history, excluding error responses
            # Error responses are kept in history for tracking but not sent to the agent
            chat_messages: list[ChatMessage] = [
                m.to_chat_message()
                for entry in self.state.data.conversation_history
                if not self._is_error_response(entry)
                for m in entry.messages
            ]

            run_kwargs: dict[str, Any] = {"messages": chat_messages}
            if not enable_tool_calls:
                run_kwargs["tools"] = None
            if response_format:
                run_kwargs["response_format"] = response_format

            agent_run_response: AgentRunResponse = await self._invoke_agent(
                run_kwargs=run_kwargs,
                correlation_id=correlation_id,
                thread_id=thread_id,
                request_message=message,
            )

            logger.debug(
                "[AgentEntity.run_agent] Agent invocation completed - response type: %s",
                type(agent_run_response).__name__,
            )

            try:
                response_text = agent_run_response.text if agent_run_response.text else "No response"
                logger.debug(f"Response: {response_text[:100]}...")
            except Exception as extraction_error:
                logger.error(
                    "Error extracting response text: %s",
                    extraction_error,
                    exc_info=True,
                )

            state_response = DurableAgentStateResponse.from_run_response(correlation_id, agent_run_response)
            self.state.data.conversation_history.append(state_response)

            logger.debug("[AgentEntity.run_agent] AgentRunResponse stored in conversation history")

            return agent_run_response

        except Exception as exc:
            logger.exception("[AgentEntity.run_agent] Agent execution failed.")

            # Create error message
            error_message = ChatMessage(
                role=Role.ASSISTANT, contents=[ErrorContent(message=str(exc), error_code=type(exc).__name__)]
            )

            error_response = AgentRunResponse(messages=[error_message])

            # Create and store error response in conversation history
            error_state_response = DurableAgentStateResponse.from_run_response(correlation_id, error_response)
            error_state_response.is_error = True
            self.state.data.conversation_history.append(error_state_response)

            return error_response

    async def _invoke_agent(
        self,
        run_kwargs: dict[str, Any],
        correlation_id: str,
        thread_id: str,
        request_message: str,
    ) -> AgentRunResponse:
        """Execute the agent, preferring streaming when available."""
        callback_context: AgentCallbackContext | None = None
        if self.callback is not None:
            callback_context = self._build_callback_context(
                correlation_id=correlation_id,
                thread_id=thread_id,
                request_message=request_message,
            )

        run_stream_callable = getattr(self.agent, "run_stream", None)
        if callable(run_stream_callable):
            try:
                stream_candidate = run_stream_callable(**run_kwargs)
                if inspect.isawaitable(stream_candidate):
                    stream_candidate = await stream_candidate

                return await self._consume_stream(
                    stream=cast(AsyncIterable[AgentRunResponseUpdate], stream_candidate),
                    callback_context=callback_context,
                )
            except TypeError as type_error:
                if "__aiter__" not in str(type_error):
                    raise
                logger.debug(
                    "run_stream returned a non-async result; falling back to run(): %s",
                    type_error,
                )
            except Exception as stream_error:
                logger.warning(
                    "run_stream failed; falling back to run(): %s",
                    stream_error,
                    exc_info=True,
                )
        else:
            logger.debug("Agent does not expose run_stream; falling back to run().")

        agent_run_response = await self._invoke_non_stream(run_kwargs)
        await self._notify_final_response(agent_run_response, callback_context)
        return agent_run_response

    async def _consume_stream(
        self,
        stream: AsyncIterable[AgentRunResponseUpdate],
        callback_context: AgentCallbackContext | None = None,
    ) -> AgentRunResponse:
        """Consume streaming responses and build the final AgentRunResponse."""
        updates: list[AgentRunResponseUpdate] = []

        async for update in stream:
            updates.append(update)
            await self._notify_stream_update(update, callback_context)

        if updates:
            response = AgentRunResponse.from_agent_run_response_updates(updates)
        else:
            logger.debug("[AgentEntity] No streaming updates received; creating empty response")
            response = AgentRunResponse(messages=[])

        await self._notify_final_response(response, callback_context)
        return response

    async def _invoke_non_stream(self, run_kwargs: dict[str, Any]) -> AgentRunResponse:
        """Invoke the agent without streaming support."""
        run_callable = getattr(self.agent, "run", None)
        if run_callable is None or not callable(run_callable):
            raise AttributeError("Agent does not implement run() method")

        result = run_callable(**run_kwargs)
        if inspect.isawaitable(result):
            result = await result

        if not isinstance(result, AgentRunResponse):
            raise TypeError(f"Agent run() must return an AgentRunResponse instance; received {type(result).__name__}")

        return result

    async def _notify_stream_update(
        self,
        update: AgentRunResponseUpdate,
        context: AgentCallbackContext | None,
    ) -> None:
        """Invoke the streaming callback if one is registered."""
        if self.callback is None or context is None:
            return

        try:
            callback_result = self.callback.on_streaming_response_update(update, context)
            if inspect.isawaitable(callback_result):
                await callback_result
        except Exception as exc:
            logger.warning(
                "[AgentEntity] Streaming callback raised an exception: %s",
                exc,
                exc_info=True,
            )

    async def _notify_final_response(
        self,
        response: AgentRunResponse,
        context: AgentCallbackContext | None,
    ) -> None:
        """Invoke the final response callback if one is registered."""
        if self.callback is None or context is None:
            return

        try:
            callback_result = self.callback.on_agent_response(response, context)
            if inspect.isawaitable(callback_result):
                await callback_result
        except Exception as exc:
            logger.warning(
                "[AgentEntity] Response callback raised an exception: %s",
                exc,
                exc_info=True,
            )

    def _build_callback_context(
        self,
        correlation_id: str,
        thread_id: str,
        request_message: str,
    ) -> AgentCallbackContext:
        """Create the callback context provided to consumers."""
        agent_name = getattr(self.agent, "name", None) or type(self.agent).__name__
        return AgentCallbackContext(
            agent_name=agent_name,
            correlation_id=correlation_id,
            thread_id=thread_id,
            request_message=request_message,
        )

    def reset(self, context: df.DurableEntityContext) -> None:
        """Reset the entity state (clear conversation history)."""
        logger.debug("[AgentEntity.reset] Resetting entity state")
        self.state.data = DurableAgentStateData(conversation_history=[])
        logger.debug("[AgentEntity.reset] State reset complete")


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
            logger.debug(f"[entity_function] Operation: {context.operation_name}")

            current_state = context.get_state(lambda: None)
            logger.debug("Retrieved state: %s", str(current_state)[:100])
            entity = AgentEntity(agent, callback)

            if current_state is not None:
                entity.state = DurableAgentState.from_dict(current_state)
                logger.debug(
                    "[entity_function] Restored entity from state (message_count: %s)", entity.state.message_count
                )
            else:
                logger.debug("[entity_function] Created new entity instance")

            operation = context.operation_name

            if operation == "run_agent":
                input_data: Any = context.get_input()

                request: str | dict[str, Any]
                if isinstance(input_data, dict) and "message" in input_data:
                    request = cast(dict[str, Any], input_data)
                else:
                    # Fall back to treating input as message string
                    request = "" if input_data is None else str(cast(object, input_data))

                result = await entity.run_agent(context, request)
                context.set_result(result.to_dict())

            elif operation == "reset":
                entity.reset(context)
                context.set_result({"status": "reset"})

            else:
                logger.error("[entity_function] Unknown operation: %s", operation)
                context.set_result({"error": f"Unknown operation: {operation}"})

            serialized_state = entity.state.to_dict()
            logger.debug("State dict: %s", serialized_state)
            context.set_state(serialized_state)
            logger.info(f"[entity_function] Operation {operation} completed successfully")

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
