# Copyright (c) Microsoft. All rights reserved.

"""Durable Task entity implementations for Microsoft Agent Framework."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterable
from typing import Any, cast

from agent_framework import (
    AgentProtocol,
    AgentResponse,
    AgentResponseUpdate,
    ChatMessage,
    Content,
    Role,
    get_logger,
)
from durabletask.entities import DurableEntity

from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
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
    ) -> None:
        self.agent = agent
        self.callback = callback
        self._state_provider = state_provider

        logger.debug("[AgentEntity] Initialized with agent type: %s", type(agent).__name__)

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
    ) -> AgentResponse:
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
        options: dict[str, Any] = dict(run_request.options)
        options.setdefault("response_format", run_request.response_format)
        if not run_request.enable_tool_calls:
            options.setdefault("tools", None)

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

            run_kwargs: dict[str, Any] = {"messages": chat_messages, "options": options}

            agent_run_response: AgentResponse = await self._invoke_agent(
                run_kwargs=run_kwargs,
                correlation_id=correlation_id,
                thread_id=thread_id,
                request_message=message,
            )

            state_response = DurableAgentStateResponse.from_run_response(correlation_id, agent_run_response)
            self.state.data.conversation_history.append(state_response)
            self.persist_state()

            return agent_run_response

        except Exception as exc:
            logger.exception("[AgentEntity.run] Agent execution failed.")

            error_message = ChatMessage(
                role=Role.ASSISTANT, contents=[Content.from_error(message=str(exc), error_code=type(exc).__name__)]
            )
            error_response = AgentResponse(messages=[error_message])

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
    ) -> AgentResponse:
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
                    stream=cast(AsyncIterable[AgentResponseUpdate], stream_candidate),
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
        stream: AsyncIterable[AgentResponseUpdate],
        callback_context: AgentCallbackContext | None = None,
    ) -> AgentResponse:
        """Consume streaming responses and build the final AgentResponse."""
        updates: list[AgentResponseUpdate] = []

        async for update in stream:
            updates.append(update)
            await self._notify_stream_update(update, callback_context)

        if updates:
            response = AgentResponse.from_agent_run_response_updates(updates)
        else:
            logger.debug("[AgentEntity] No streaming updates received; creating empty response")
            response = AgentResponse(messages=[])

        await self._notify_final_response(response, callback_context)
        return response

    async def _invoke_non_stream(self, run_kwargs: dict[str, Any]) -> AgentResponse:
        """Invoke the agent without streaming support."""
        run_callable = getattr(self.agent, "run", None)
        if run_callable is None or not callable(run_callable):
            raise AttributeError("Agent does not implement run() method")

        result = run_callable(**run_kwargs)
        if inspect.isawaitable(result):
            result = await result

        if not isinstance(result, AgentResponse):
            raise TypeError(f"Agent run() must return an AgentResponse instance; received {type(result).__name__}")

        return result

    async def _notify_stream_update(
        self,
        update: AgentResponseUpdate,
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
        response: AgentResponse,
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
