# Copyright (c) Microsoft. All rights reserved.

import logging
from dataclasses import dataclass
from typing import Any

from .._agents import AgentProtocol, ChatAgent
from .._threads import AgentThread
from .._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage
from ._conversation_state import encode_chat_messages
from ._events import (
    AgentRunEvent,
    AgentRunUpdateEvent,  # type: ignore[reportPrivateUsage]
)
from ._executor import Executor, handler
from ._message_utils import normalize_messages_input
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


@dataclass
class AgentExecutorRequest:
    """A request to an agent executor.

    Attributes:
        messages: A list of chat messages to be processed by the agent.
        should_respond: A flag indicating whether the agent should respond to the messages.
            If False, the messages will be saved to the executor's cache but not sent to the agent.
    """

    messages: list[ChatMessage]
    should_respond: bool = True


@dataclass
class AgentExecutorResponse:
    """A response from an agent executor.

    Attributes:
        executor_id: The ID of the executor that generated the response.
        agent_run_response: The underlying agent run response (unaltered from client).
        full_conversation: The full conversation context (prior inputs + all assistant/tool outputs) that
            should be used when chaining to another AgentExecutor. This prevents downstream agents losing
            user prompts while keeping the emitted AgentRunEvent text faithful to the raw agent output.
    """

    executor_id: str
    agent_run_response: AgentRunResponse
    full_conversation: list[ChatMessage] | None = None


class AgentExecutor(Executor):
    """built-in executor that wraps an agent for handling messages.

    AgentExecutor adapts its behavior based on the workflow execution mode:
    - run_stream(): Emits incremental AgentRunUpdateEvent events as the agent produces tokens
    - run(): Emits a single AgentRunEvent containing the complete response

    The executor automatically detects the mode via WorkflowContext.is_streaming().
    """

    def __init__(
        self,
        agent: AgentProtocol,
        *,
        agent_thread: AgentThread | None = None,
        output_response: bool = False,
        id: str | None = None,
    ):
        """Initialize the executor with a unique identifier.

        Args:
            agent: The agent to be wrapped by this executor.
            agent_thread: The thread to use for running the agent. If None, a new thread will be created.
            output_response: Whether to yield an AgentRunResponse as a workflow output when the agent completes.
            id: A unique identifier for the executor. If None, the agent's name will be used if available.
        """
        # Prefer provided id; else use agent.name if present; else generate deterministic prefix
        exec_id = id or agent.name
        if not exec_id:
            raise ValueError("Agent must have a name or an explicit id must be provided.")
        super().__init__(exec_id)
        self._agent = agent
        self._agent_thread = agent_thread or self._agent.get_new_thread()
        self._output_response = output_response
        self._cache: list[ChatMessage] = []

    @property
    def workflow_output_types(self) -> list[type[Any]]:
        # Override to declare AgentRunResponse as a possible output type only if enabled.
        if self._output_response:
            return [AgentRunResponse]
        return []

    async def _run_agent_and_emit(self, ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse]) -> None:
        """Execute the underlying agent, emit events, and enqueue response.

        Checks ctx.is_streaming() to determine whether to emit incremental AgentRunUpdateEvent
        events (streaming mode) or a single AgentRunEvent (non-streaming mode).
        """
        if ctx.is_streaming():
            # Streaming mode: emit incremental updates
            updates: list[AgentRunResponseUpdate] = []
            async for update in self._agent.run_stream(
                self._cache,
                thread=self._agent_thread,
            ):
                updates.append(update)
                await ctx.add_event(AgentRunUpdateEvent(self.id, update))

            if isinstance(self._agent, ChatAgent):
                response_format = self._agent.chat_options.response_format
                response = AgentRunResponse.from_agent_run_response_updates(
                    updates,
                    output_format_type=response_format,
                )
            else:
                response = AgentRunResponse.from_agent_run_response_updates(updates)
        else:
            # Non-streaming mode: use run() and emit single event
            response = await self._agent.run(
                self._cache,
                thread=self._agent_thread,
            )
            await ctx.add_event(AgentRunEvent(self.id, response))

        if self._output_response:
            await ctx.yield_output(response)

        # Always construct a full conversation snapshot from inputs (cache)
        # plus agent outputs (agent_run_response.messages). Do not mutate
        # response.messages so AgentRunEvent remains faithful to the raw output.
        full_conversation: list[ChatMessage] = list(self._cache) + list(response.messages)

        agent_response = AgentExecutorResponse(self.id, response, full_conversation=full_conversation)
        await ctx.send_message(agent_response)
        self._cache.clear()

    @handler
    async def run(
        self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse]
    ) -> None:
        """Handle an AgentExecutorRequest (canonical input).

        This is the standard path: extend cache with provided messages; if should_respond
        run the agent and emit an AgentExecutorResponse downstream.
        """
        self._cache.extend(request.messages)
        if request.should_respond:
            await self._run_agent_and_emit(ctx)

    @handler
    async def from_response(
        self, prior: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse]
    ) -> None:
        """Enable seamless chaining: accept a prior AgentExecutorResponse as input.

        Strategy: treat the prior response's messages as the conversation state and
        immediately run the agent to produce a new response.
        """
        # Replace cache with full conversation if available, else fall back to agent_run_response messages.
        if prior.full_conversation is not None:
            self._cache = list(prior.full_conversation)
        else:
            self._cache = list(prior.agent_run_response.messages)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_str(self, text: str, ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse]) -> None:
        """Accept a raw user prompt string and run the agent (one-shot)."""
        self._cache = normalize_messages_input(text)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_message(
        self,
        message: ChatMessage,
        ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse],
    ) -> None:
        """Accept a single ChatMessage as input."""
        self._cache = normalize_messages_input(message)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_messages(
        self,
        messages: list[str | ChatMessage],
        ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse],
    ) -> None:
        """Accept a list of chat inputs (strings or ChatMessage) as conversation context."""
        self._cache = normalize_messages_input(messages)
        await self._run_agent_and_emit(ctx)

    async def snapshot_state(self) -> dict[str, Any]:
        """Capture current executor state for checkpointing.

        NOTE: if the thread storage is on the server side, the full thread state
        may not be serialized locally. Therefore, we are relying on the server-side
        to ensure the thread state is preserved and immutable across checkpoints.
        This is not the case for AzureAI Agents, but works for the Responses API.

        Returns:
            Dict containing serialized cache and thread state
        """
        # Check if using AzureAIAgentClient with server-side thread and warn about checkpointing limitations
        if isinstance(self._agent, ChatAgent) and self._agent_thread.service_thread_id is not None:
            client_class_name = self._agent.chat_client.__class__.__name__
            client_module = self._agent.chat_client.__class__.__module__

            if client_class_name == "AzureAIAgentClient" and "azure_ai" in client_module:
                # TODO(TaoChenOSU): update this warning when we surface the hooks for
                # custom executor checkpointing.
                # https://github.com/microsoft/agent-framework/issues/1816
                logger.warning(
                    "Checkpointing an AgentExecutor with AzureAIAgentClient that uses server-side threads. "
                    "Currently, checkpointing does not capture messages from server-side threads "
                    "(service_thread_id: %s). The thread state in checkpoints is not immutable and can be "
                    "modified by subsequent runs. If you need reliable checkpointing with Azure AI agents, "
                    "consider implementing a custom executor and managing the thread state yourself.",
                    self._agent_thread.service_thread_id,
                )

        serialized_thread = await self._agent_thread.serialize()

        return {
            "cache": encode_chat_messages(self._cache),
            "agent_thread": serialized_thread,
        }

    async def restore_state(self, state: dict[str, Any]) -> None:
        """Restore executor state from checkpoint.

        Args:
            state: Checkpoint data dict
        """
        from ._conversation_state import decode_chat_messages

        cache_payload = state.get("cache")
        if cache_payload:
            try:
                self._cache = decode_chat_messages(cache_payload)
            except Exception as exc:
                logger.warning("Failed to restore cache: %s", exc)
                self._cache = []
        else:
            self._cache = []

        thread_payload = state.get("agent_thread")
        if thread_payload:
            try:
                # Deserialize the thread state directly
                self._agent_thread = await AgentThread.deserialize(thread_payload)

            except Exception as exc:
                logger.warning("Failed to restore agent thread: %s", exc)
                self._agent_thread = self._agent.get_new_thread()
        else:
            self._agent_thread = self._agent.get_new_thread()

    def reset(self) -> None:
        """Reset the internal cache of the executor."""
        logger.debug("AgentExecutor %s: Resetting cache", self.id)
        self._cache.clear()
