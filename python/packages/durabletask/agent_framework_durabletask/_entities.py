# Copyright (c) Microsoft. All rights reserved.

"""Durable Task entity implementations for Microsoft Agent Framework."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterable
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ErrorContent,
    Role,
    get_logger,
)
from durabletask.entities import DurableEntity

from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._constants import MINIMUM_TTL_SIGNAL_DELAY_MINUTES
from ._durable_agent_state import (
    DurableAgentState,
    DurableAgentStateEntry,
    DurableAgentStateRequest,
    DurableAgentStateResponse,
)
from ._models import RunRequest

logger = get_logger("agent_framework.durabletask.entities")


class AgentEntityStateProviderMixin:
    """Mixin implementing durable agent state caching + (de)serialization + persistence.

    Concrete classes must implement:
    - _get_state_dict(): fetch raw persisted state dict (default should be {})
    - _set_state_dict(): persist raw state dict
    - _get_thread_id_from_entity(): fetch the thread ID from the underlying context
    """

    _state_cache: DurableAgentState | None = None

    def _get_state_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    def _set_state_dict(self, state: dict[str, Any]) -> None:
        raise NotImplementedError

    def _get_thread_id_from_entity(self) -> str:
        raise NotImplementedError

    @property
    def thread_id(self) -> str:
        return self._get_thread_id_from_entity()

    @property
    def state(self) -> DurableAgentState:
        if self._state_cache is None:
            raw_state = self._get_state_dict()
            self._state_cache = DurableAgentState.from_dict(raw_state) if raw_state else DurableAgentState()
        return self._state_cache

    @state.setter
    def state(self, value: DurableAgentState) -> None:
        self._state_cache = value
        self.persist_state()

    def persist_state(self) -> None:
        """Persist the current state to the underlying storage provider."""
        if self._state_cache is None:
            self._state_cache = DurableAgentState()
        self._set_state_dict(self._state_cache.to_dict())

    def reset(self) -> None:
        """Clear conversation history by resetting state to a fresh DurableAgentState."""
        self._state_cache = DurableAgentState()
        self.persist_state()
        logger.debug("[AgentEntityStateProviderMixin.reset] State reset complete")


class AgentEntity:
    """Platform-agnostic agent execution logic.

    This class encapsulates the core logic for executing an agent within a durable entity context.
    """

    agent: AgentProtocol
    callback: AgentResponseCallbackProtocol | None

    def __init__(
        self,
        agent: AgentProtocol,
        callback: AgentResponseCallbackProtocol | None = None,
        *,
        state_provider: AgentEntityStateProviderMixin,
        time_to_live: timedelta | None = None,
        minimum_ttl_signal_delay: timedelta = timedelta(minutes=MINIMUM_TTL_SIGNAL_DELAY_MINUTES),
    ) -> None:
        self.agent = agent
        self.callback = callback
        self._state_provider = state_provider
        self._time_to_live = time_to_live
        self._minimum_ttl_signal_delay = minimum_ttl_signal_delay

        logger.debug(
            "[AgentEntity] Initialized with agent type: %s, TTL: %s",
            type(agent).__name__,
            time_to_live,
        )

    @property
    def state(self) -> DurableAgentState:
        return self._state_provider.state

    @state.setter
    def state(self, value: DurableAgentState) -> None:
        self._state_provider.state = value

    def persist_state(self) -> None:
        self._state_provider.persist_state()

    def reset(self) -> None:
        self._state_provider.reset()

    def _is_error_response(self, entry: DurableAgentStateEntry) -> bool:
        """Check if a conversation history entry is an error response."""
        if isinstance(entry, DurableAgentStateResponse):
            return entry.is_error
        return False

    async def run(
        self,
        request: RunRequest | dict[str, Any] | str,
    ) -> AgentRunResponse:
        """Execute the agent with a message."""
        if isinstance(request, str):
            run_request = RunRequest.from_json(request)
        elif isinstance(request, dict):
            run_request = RunRequest.from_dict(request)
        else:
            run_request = request

        message = run_request.message
        thread_id = self._state_provider.thread_id
        correlation_id = run_request.correlation_id
        if not thread_id:
            raise ValueError("Entity State Provider must provide a thread_id")
        response_format = run_request.response_format
        enable_tool_calls = run_request.enable_tool_calls

        logger.debug("[AgentEntity.run] Received ThreadId %s Message: %s", thread_id, run_request)

        state_request = DurableAgentStateRequest.from_run_request(run_request)
        self.state.data.conversation_history.append(state_request)

        try:
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

            state_response = DurableAgentStateResponse.from_run_response(correlation_id, agent_run_response)
            self.state.data.conversation_history.append(state_response)

            # Update TTL expiration time
            self._update_ttl_expiration()

            self.persist_state()

            return agent_run_response

        except Exception as exc:
            logger.exception("[AgentEntity.run] Agent execution failed.")

            error_message = ChatMessage(
                role=Role.ASSISTANT, contents=[ErrorContent(message=str(exc), error_code=type(exc).__name__)]
            )
            error_response = AgentRunResponse(messages=[error_message])

            error_state_response = DurableAgentStateResponse.from_run_response(correlation_id, error_response)
            error_state_response.is_error = True
            self.state.data.conversation_history.append(error_state_response)
            self.persist_state()

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

    # TTL (Time-To-Live) Methods
    def _update_ttl_expiration(self) -> None:
        """Update the TTL expiration time after an interaction.

        If TTL is configured:
        - Sets/updates the expiration time to now + TTL
        - On first interaction, schedules a deletion check signal

        If TTL is disabled (None):
        - Clears any previously set expiration time
        """
        if self._time_to_live is not None:
            current_time = datetime.now(timezone.utc)
            new_expiration_time = current_time + self._time_to_live
            is_first_interaction = self.state.data.expiration_time_utc is None

            self.state.data.expiration_time_utc = new_expiration_time

            logger.debug(
                "[AgentEntity] TTL expiration time updated to %s (first_interaction: %s)",
                new_expiration_time.isoformat(),
                is_first_interaction,
            )

            # Only schedule deletion check on the first interaction when entity is created.
            # On subsequent interactions, we just update the expiration time. The scheduled
            # check_and_delete_if_expired will reschedule itself if the entity hasn't expired.
            if is_first_interaction:
                self._schedule_deletion_check()
        else:
            # TTL is disabled. Clear the expiration time if it was previously set.
            if self.state.data.expiration_time_utc is not None:
                logger.debug("[AgentEntity] TTL disabled, clearing expiration time")
                self.state.data.expiration_time_utc = None

    def check_and_delete_if_expired(self) -> None:
        """Check if the entity has expired and delete it if so, otherwise reschedule.

        This method is called by a scheduled signal to check TTL expiration.
        If the entity has expired (current time >= expiration time), the state is deleted.
        If not expired, a new deletion check is scheduled for the updated expiration time.
        """
        current_time = datetime.now(timezone.utc)
        expiration_time = self.state.data.expiration_time_utc

        logger.debug(
            "[AgentEntity] TTL deletion check: expiration=%s, current=%s",
            expiration_time.isoformat() if expiration_time else "None",
            current_time.isoformat(),
        )

        if expiration_time is not None:
            if current_time >= expiration_time:
                # Entity has expired, delete it by resetting state
                logger.info(
                    "[AgentEntity] Entity expired at %s, deleting state",
                    expiration_time.isoformat(),
                )
                self._delete_entity_state()
            else:
                # Entity hasn't expired yet, reschedule the deletion check
                if self._time_to_live is not None:
                    logger.debug("[AgentEntity] Entity not expired, rescheduling deletion check")
                    self._schedule_deletion_check()

    def _schedule_deletion_check(self) -> None:
        """Schedule a signal to self to check for expiration.

        Note: The Python durabletask SDK does not currently support scheduled signals.
        This method logs a warning and skips scheduling. The expiration time is still
        tracked in state for potential external cleanup or future SDK support.

        See: https://github.com/Azure/azure-functions-durable-extension/issues/1554
        """
        if not isinstance(self._state_provider, DurableTaskEntityStateProvider):
            logger.warning(
                "[AgentEntity] Cannot schedule deletion check: state provider does not support entity signaling"
            )
            return

        current_time = datetime.now(timezone.utc)
        expiration_time = self.state.data.expiration_time_utc

        if expiration_time is None and self._time_to_live is not None:
            expiration_time = current_time + self._time_to_live

        if expiration_time is None:
            return

        # To avoid excessive scheduling, we schedule the deletion check for no less than the minimum delay
        minimum_scheduled_time = current_time + self._minimum_ttl_signal_delay
        scheduled_time = max(expiration_time, minimum_scheduled_time)

        logger.warning(
            "[AgentEntity] TTL scheduled deletion is not yet supported in the Python durabletask SDK. "
            "Expiration time set to %s but automatic deletion will not occur. "
            "Consider implementing external cleanup based on expiration_time_utc in entity state.",
            scheduled_time.isoformat(),
        )

    def _delete_entity_state(self) -> None:
        """Delete the entity state to remove the entity."""
        # Reset the state cache to clear all data
        self._state_provider._state_cache = None
        # Set empty state to trigger deletion
        self._state_provider._set_state_dict({})


class DurableTaskEntityStateProvider(DurableEntity, AgentEntityStateProviderMixin):
    """DurableTask Durable Entity state provider for AgentEntity.

    This class utilizes the Durable Entity context from `durabletask` package
    to get and set the state of the agent entity.
    """

    def __init__(self) -> None:
        super().__init__()

    def _get_state_dict(self) -> dict[str, Any]:
        raw = self.get_state(dict, default={})
        return cast(dict[str, Any], raw)

    def _set_state_dict(self, state: dict[str, Any]) -> None:
        self.set_state(state)

    def _get_thread_id_from_entity(self) -> str:
        return self.entity_context.entity_id.key
