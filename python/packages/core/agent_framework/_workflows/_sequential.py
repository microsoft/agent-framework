# Copyright (c) Microsoft. All rights reserved.

"""Sequential builder for agent/executor workflows with shared conversation context.

This module provides a high-level, agent-focused API to assemble a sequential
workflow where:
- Participants can be provided as AgentProtocol or Executor instances via `.participants()`,
  or as factories returning AgentProtocol or Executor via `.register_participants()`
- A shared conversation context (list[ChatMessage]) is passed along the chain
- Agents append their assistant messages to the context
- Custom executors can transform or summarize and return a refined context
- The workflow finishes with the final context produced by the last participant

Typical wiring:
    input -> _InputToConversation -> participant1 -> (agent? -> _ResponseToConversation) -> ... -> participantN -> _EndWithConversation

Notes:
- Participants can mix AgentProtocol and Executor objects
- Agents are auto-wrapped by WorkflowBuilder as AgentExecutor (unless already wrapped)
- AgentExecutor produces AgentExecutorResponse; _ResponseToConversation converts this to list[ChatMessage]
- Non-agent executors must define a handler that consumes `list[ChatMessage]` and sends back
  the updated `list[ChatMessage]` via their workflow context

Why include the small internal adapter executors?
- Input normalization ("input-conversation"): ensures the workflow always starts with a
  `list[ChatMessage]` regardless of whether callers pass a `str`, a single `ChatMessage`,
  or a list. This keeps the first hop strongly typed and avoids boilerplate in participants.
- Agent response adaptation ("to-conversation:<participant>"): agents (via AgentExecutor)
  emit `AgentExecutorResponse`. The adapter converts that to a `list[ChatMessage]`
  using `full_conversation` so original prompts aren't lost when chaining.
- Result output ("end"): yields the final conversation list and the workflow becomes idle
  giving a consistent terminal payload shape for both agents and custom executors.

These adapters are first-class executors by design so they are type-checked at edges,
observable (ExecutorInvoke/Completed events), and easily testable/reusable. Their IDs are
deterministic and self-describing (for example, "to-conversation:writer") to reduce event-log
confusion and to mirror how the concurrent builder uses explicit dispatcher/aggregator nodes.
"""  # noqa: E501

import logging
from collections.abc import Callable, Sequence
from typing import Any

from agent_framework import AgentProtocol, ChatMessage

from ._agent_executor import (
    AgentExecutor,
    AgentExecutorResponse,
)
from ._agent_utils import resolve_agent_id
from ._checkpoint import CheckpointStorage
from ._executor import (
    Executor,
    handler,
)
from ._message_utils import normalize_messages_input
from ._orchestration_request_info import AgentApprovalExecutor
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


class _InputToConversation(Executor):
    """Normalizes initial input into a list[ChatMessage] conversation."""

    @handler
    async def from_str(self, prompt: str, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        await ctx.send_message(normalize_messages_input(prompt))

    @handler
    async def from_message(self, message: ChatMessage, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        await ctx.send_message(normalize_messages_input(message))

    @handler
    async def from_messages(self, messages: list[str | ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        await ctx.send_message(normalize_messages_input(messages))


class _EndWithConversation(Executor):
    """Terminates the workflow by emitting the final conversation context."""

    @handler
    async def end_with_messages(
        self,
        conversation: list[ChatMessage],
        ctx: WorkflowContext[Any, list[ChatMessage]],
    ) -> None:
        """Handler for ending with a list of ChatMessage.

        This is used when the last participant is a custom executor.
        """
        await ctx.yield_output(list(conversation))

    @handler
    async def end_with_agent_executor_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[Any, list[ChatMessage] | None],
    ) -> None:
        """Handle case where last participant is an agent.

        The agent is wrapped by AgentExecutor and emits AgentExecutorResponse.
        """
        await ctx.yield_output(response.full_conversation)


class SequentialBuilder:
    r"""High-level builder for sequential agent/executor workflows with shared context.

    - `participants([...])` accepts a list of AgentProtocol (recommended) or Executor instances
    - `register_participants([...])` accepts a list of factories for AgentProtocol (recommended)
       or Executor factories
    - Executors must define a handler that consumes list[ChatMessage] and sends out a list[ChatMessage]
    - The workflow wires participants in order, passing a list[ChatMessage] down the chain
    - Agents append their assistant messages to the conversation
    - Custom executors can transform/summarize and return a list[ChatMessage]
    - The final output is the conversation produced by the last participant

    Usage:

    .. code-block:: python

        from agent_framework import SequentialBuilder

        # With agent instances
        workflow = SequentialBuilder().participants([agent1, agent2, summarizer_exec]).build()

        # With agent factories
        workflow = (
            SequentialBuilder().register_participants([create_agent1, create_agent2, create_summarizer_exec]).build()
        )

        # Enable checkpoint persistence
        workflow = SequentialBuilder().participants([agent1, agent2]).with_checkpointing(storage).build()

        # Enable request info for mid-workflow feedback (pauses before each agent)
        workflow = SequentialBuilder().participants([agent1, agent2]).with_request_info().build()

        # Enable request info only for specific agents
        workflow = (
            SequentialBuilder()
            .participants([agent1, agent2, agent3])
            .with_request_info(agents=[agent2])  # Only pause before agent2
            .build()
        )
    """

    def __init__(self) -> None:
        self._participants: list[AgentProtocol | Executor] = []
        self._participant_factories: list[Callable[[], AgentProtocol | Executor]] = []
        self._checkpoint_storage: CheckpointStorage | None = None
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] | None = None

    def register_participants(
        self,
        participant_factories: Sequence[Callable[[], AgentProtocol | Executor]],
    ) -> "SequentialBuilder":
        """Register participant factories for this sequential workflow."""
        if self._participants:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participant_factories:
            raise ValueError("register_participants() has already been called on this builder instance.")

        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = list(participant_factories)
        return self

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "SequentialBuilder":
        """Define the ordered participants for this sequential workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.
        Raises if empty or duplicates are provided for clarity.
        """
        if self._participant_factories:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participants:
            raise ValueError("participants() has already been called on this builder instance.")

        if not participants:
            raise ValueError("participants cannot be empty")

        # Defensive duplicate detection
        seen_agent_ids: set[int] = set()
        seen_executor_ids: set[str] = set()
        for p in participants:
            if isinstance(p, Executor):
                if p.id in seen_executor_ids:
                    raise ValueError(f"Duplicate executor participant detected: id '{p.id}'")
                seen_executor_ids.add(p.id)
            else:
                # Treat non-Executor as agent-like (AgentProtocol). Structural checks can be brittle at runtime.
                pid = id(p)
                if pid in seen_agent_ids:
                    raise ValueError("Duplicate agent participant detected (same agent instance provided twice)")
                seen_agent_ids.add(pid)

        self._participants = list(participants)
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "SequentialBuilder":
        """Enable checkpointing for the built workflow using the provided storage."""
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_info(
        self,
        *,
        agents: Sequence[str | AgentProtocol] | None = None,
    ) -> "SequentialBuilder":
        """Enable request info after agent participant responses.

        This enables human-in-the-loop (HIL) scenarios for the sequential orchestration.
        When enabled, the workflow pauses after each agent participant runs, emitting
        a RequestInfoEvent that allows the caller to review the conversation and optionally
        inject guidance for the agent participant to iterate. The caller provides input via
        the standard response_handler/request_info pattern.

        Simulated flow with HIL:
        Input -> [Agent Participant <-> Request Info] -> [Agent Participant <-> Request Info] -> ...

        Note: This is only available for agent participants. Executor participants can incorporate
        request info handling in their own implementation if desired.

        Args:
            agents: Optional list of agents names or agent factories to enable request info for.
                    If None, enables HIL for all agent participants.

        Returns:
            Self for fluent chaining
        """
        from ._orchestration_request_info import resolve_request_info_filter

        self._request_info_enabled = True
        self._request_info_filter = resolve_request_info_filter(list(agents) if agents else None)

        return self

    def _resolve_participants(self) -> list[Executor]:
        """Resolve participant instances into Executor objects."""
        if not self._participants and not self._participant_factories:
            raise ValueError("No participants provided. Call .participants() or .register_participants() first.")
        # We don't need to check if both are set since that is handled in the respective methods

        participants: list[Executor | AgentProtocol] = []
        if self._participant_factories:
            # Resolve the participant factories now. This doesn't break the factory pattern
            # since the Sequential builder still creates new instances per workflow build.
            for factory in self._participant_factories:
                p = factory()
                participants.append(p)
        else:
            participants = self._participants

        executors: list[Executor] = []
        for p in participants:
            if isinstance(p, Executor):
                executors.append(p)
            elif isinstance(p, AgentProtocol):
                if self._request_info_enabled and (
                    not self._request_info_filter or resolve_agent_id(p) in self._request_info_filter
                ):
                    # Handle request info enabled agents
                    executors.append(AgentApprovalExecutor(p))
                else:
                    executors.append(AgentExecutor(p))
            else:
                raise TypeError(f"Participants must be AgentProtocol or Executor instances. Got {type(p).__name__}.")

        return executors

    def build(self) -> Workflow:
        """Build and validate the sequential workflow.

        Wiring pattern:
        - _InputToConversation normalizes the initial input into list[ChatMessage]
        - For each participant in order:
            - If Agent (or AgentExecutor): pass conversation to the agent, then optionally
              route through a request info interceptor, then convert response to conversation
              via _ResponseToConversation
            - Else (custom Executor): pass conversation directly to the executor
        - _EndWithConversation yields the final conversation and the workflow becomes idle
        """
        # Internal nodes
        input_conv = _InputToConversation(id="input-conversation")
        end = _EndWithConversation(id="end")

        # Resolve participants and participant factories to executors
        participants: list[Executor] = self._resolve_participants()

        builder = WorkflowBuilder()
        builder.set_start_executor(input_conv)

        # Start of the chain is the input normalizer
        prior: Executor | AgentProtocol = input_conv
        for p in participants:
            builder.add_edge(prior, p)
            prior = p
        # Terminate with the final conversation
        builder.add_edge(prior, end)

        if self._checkpoint_storage is not None:
            builder = builder.with_checkpointing(self._checkpoint_storage)

        return builder.build()
