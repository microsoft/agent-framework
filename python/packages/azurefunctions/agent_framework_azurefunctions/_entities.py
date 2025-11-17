# Copyright (c) Microsoft. All rights reserved.

"""Durable Entity for Agent Execution.

This module defines a durable entity that manages agent state and execution.
Using entities instead of orchestrations provides better state management and
allows for long-running agent conversations.
"""

import asyncio
import inspect
import json
from collections.abc import AsyncIterable, Callable
from typing import Any, cast

import azure.durable_functions as df
from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, Role, get_logger

from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._models import AgentResponse, RunRequest
from ._state import AgentState

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
        state: The AgentState managing conversation history
    """

    agent: AgentProtocol
    state: AgentState

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
        self.state = AgentState()
        self.callback = callback

        logger.debug(f"[AgentEntity] Initialized with agent type: {type(agent).__name__}")

    async def run_agent(
        self,
        context: df.DurableEntityContext,
        request: RunRequest | dict[str, Any] | str,
    ) -> dict[str, Any]:
        """Execute the agent with a message directly in the entity.

        Args:
            context: Entity context
            request: RunRequest object, dict, or string message (for backward compatibility)

        Returns:
            Dict with status information and response (serialized AgentResponse)

        Note:
            The agent returns an AgentRunResponse object which is stored in state.
            This method extracts the text/structured response and returns an AgentResponse dict.
        """
        # Convert string or dict to RunRequest
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
        role = run_request.role or Role.USER
        response_format = run_request.response_format
        enable_tool_calls = run_request.enable_tool_calls

        logger.debug(f"[AgentEntity.run_agent] Received message: {message}")
        logger.debug(f"[AgentEntity.run_agent] Thread ID: {thread_id}")
        logger.debug(f"[AgentEntity.run_agent] Correlation ID: {correlation_id}")
        logger.debug(f"[AgentEntity.run_agent] Role: {role.value}")
        logger.debug(f"[AgentEntity.run_agent] Enable tool calls: {enable_tool_calls}")
        logger.debug(f"[AgentEntity.run_agent] Response format: {'provided' if response_format else 'none'}")

        # Store message in history with role
        self.state.add_user_message(message, role=role, correlation_id=correlation_id)

        logger.debug("[AgentEntity.run_agent] Executing agent...")

        try:
            logger.debug("[AgentEntity.run_agent] Starting agent invocation")

            run_kwargs: dict[str, Any] = {"messages": self.state.get_chat_messages()}
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

            response_text = None
            structured_response = None

            response_str: str | None = None
            try:
                if response_format:
                    try:
                        response_str = agent_run_response.text
                        structured_response = json.loads(response_str)
                        logger.debug("Parsed structured JSON response")
                    except json.JSONDecodeError as decode_error:
                        logger.warning(f"Failed to parse JSON response: {decode_error}")
                        response_text = response_str
                else:
                    raw_text = agent_run_response.text
                    response_text = raw_text if raw_text else "No response"
                    preview = response_text
                    logger.debug(f"Response: {preview[:100]}..." if len(preview) > 100 else f"Response: {preview}")
            except Exception as extraction_error:
                logger.error(
                    f"Error extracting response: {extraction_error}",
                    exc_info=True,
                )
                response_text = "Error extracting response"

            agent_response = AgentResponse(
                response=response_text,
                message=str(message),
                thread_id=str(thread_id),
                status="success",
                message_count=self.state.message_count,
                structured_response=structured_response,
            )
            result = agent_response.to_dict()

            content = json.dumps(structured_response) if structured_response else (response_text or "")
            self.state.add_assistant_message(content, agent_run_response, correlation_id)
            logger.debug("[AgentEntity.run_agent] AgentRunResponse stored in conversation history")

            return result

        except Exception as exc:
            import traceback

            error_traceback = traceback.format_exc()
            logger.error("[AgentEntity.run_agent] Agent execution failed")
            logger.error(f"Error: {exc!s}")
            logger.error(f"Error type: {type(exc).__name__}")
            logger.error(f"Full traceback:\n{error_traceback}")

            error_response = AgentResponse(
                response=f"Error: {exc!s}",
                message=str(message),
                thread_id=str(thread_id),
                status="error",
                message_count=self.state.message_count,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return error_response.to_dict()

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
        self.state.reset()
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
                entity.state.restore_state(current_state)
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
                context.set_result(result)

            elif operation == "reset":
                entity.reset(context)
                context.set_result({"status": "reset"})

            else:
                logger.error("[entity_function] Unknown operation: %s", operation)
                context.set_result({"error": f"Unknown operation: {operation}"})

            context.set_state(entity.state.to_dict())
            logger.debug(f"[entity_function] Operation {operation} completed successfully")

        except Exception as exc:
            import traceback

            logger.error("[entity_function] Error in entity: %s", exc)
            logger.error(f"[entity_function] Traceback:\n{traceback.format_exc()}")
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
