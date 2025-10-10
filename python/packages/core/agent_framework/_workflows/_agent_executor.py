# Copyright (c) Microsoft. All rights reserved.

import logging
from dataclasses import dataclass
from typing import Any

from .._agents import AgentProtocol, ChatAgent
from .._threads import AgentThread
from .._types import AgentRunResponse, AgentRunResponseUpdate, ChatMessage
from ._events import (
    AgentRunEvent,
    AgentRunUpdateEvent,  # type: ignore[reportPrivateUsage]
)
from ._executor import Executor, handler
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
        self._cache = [ChatMessage(role="user", text=text)]  # type: ignore[arg-type]
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_message(
        self,
        message: ChatMessage,
        ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse],
    ) -> None:
        """Accept a single ChatMessage as input."""
        self._cache = [message]
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[AgentExecutorResponse, AgentRunResponse],
    ) -> None:
        """Accept a list of ChatMessage objects as conversation context."""
        self._cache = list(messages)
        await self._run_agent_and_emit(ctx)
