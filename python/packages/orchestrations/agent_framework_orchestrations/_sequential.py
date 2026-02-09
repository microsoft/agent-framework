# Copyright (c) Microsoft. All rights reserved.

"""Sequential builder for agent/executor workflows with shared conversation context.

This module provides a high-level, agent-focused API to assemble a sequential
workflow where:
- Participants can be provided as SupportsAgentRun or Executor instances via `participants=[...]`,
  or as factories returning SupportsAgentRun or Executor via `participant_factories=[...]`
- A shared conversation context (list[ChatMessage]) is passed along the chain
- Agents append their assistant messages to the context
- Custom executors can transform or summarize and return a refined context
- The workflow finishes with the final context produced by the last participant

Typical wiring:
    input -> _InputToConversation -> participant1 -> (agent? -> _ResponseToConversation) -> ... -> participantN -> _EndWithConversation

Notes:
- Participants can mix SupportsAgentRun and Executor objects
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

from agent_framework import ChatMessage, SupportsAgentRun
from agent_framework._workflows._agent_executor import (
    AgentExecutor,
    AgentExecutorResponse,
)
from agent_framework._workflows._agent_utils import resolve_agent_id
from agent_framework._workflows._checkpoint import CheckpointStorage
from agent_framework._workflows._executor import (
    Executor,
    handler,
)
from agent_framework._workflows._message_utils import normalize_messages_input
from agent_framework._workflows._workflow import Workflow
from agent_framework._workflows._workflow_builder import WorkflowBuilder
from agent_framework._workflows._workflow_context import WorkflowContext

from ._orchestration_request_info import AgentApprovalExecutor

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

    - `participants=[...]` accepts a list of SupportsAgentRun (recommended) or Executor instances
    - `participant_factories=[...]` accepts a list of factories for SupportsAgentRun (recommended)
       or Executor factories
    - Executors must define a handler that consumes list[ChatMessage] and sends out a list[ChatMessage]
    - The workflow wires participants in order, passing a list[ChatMessage] down the chain
    - Agents append their assistant messages to the conversation
    - Custom executors can transform/summarize and return a list[ChatMessage]
    - The final output is the conversation produced by the last participant

    Usage:

    .. code-block:: python

        from agent_framework_orchestrations import SequentialBuilder

        # With agent instances
        workflow = SequentialBuilder(participants=[agent1, agent2, summarizer_exec]).build()

        # With agent factories
        workflow = SequentialBuilder(
            participant_factories=[create_agent1, create_agent2, create_summarizer_exec]
        ).build()

        # Enable checkpoint persistence
        workflow = SequentialBuilder(participants=[agent1, agent2], checkpoint_storage=storage).build()

        # Enable request info for mid-workflow feedback (pauses before each agent)
        workflow = SequentialBuilder(participants=[agent1, agent2]).with_request_info().build()

        # Enable request info only for specific agents
        workflow = (
            SequentialBuilder(participants=[agent1, agent2, agent3])
            .with_request_info(agents=[agent2])  # Only pause before agent2
            .build()
        )
    """

    def __init__(
        self,
        *,
        participants: Sequence[SupportsAgentRun | Executor] | None = None,
        participant_factories: Sequence[Callable[[], SupportsAgentRun | Executor]] | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        intermediate_outputs: bool = False,
    ) -> None:
        """Initialize the SequentialBuilder.

        Args:
            participants: Optional sequence of agent or executor instances to run sequentially.
            participant_factories: Optional sequence of callables returning agent or executor instances.
            checkpoint_storage: Optional checkpoint storage for enabling workflow state persistence.
            intermediate_outputs: If True, enables intermediate outputs from agent participants.
        """
        self._participants: list[SupportsAgentRun | Executor] = []
        self._participant_factories: list[Callable[[], SupportsAgentRun | Executor]] = []
        self._checkpoint_storage: CheckpointStorage | None = checkpoint_storage
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] | None = None
        self._intermediate_outputs: bool = intermediate_outputs

        if participants is None and participant_factories is None:
            raise ValueError("Either participants or participant_factories must be provided.")

        if participant_factories is not None:
            self._set_participant_factories(participant_factories)
        if participants is not None:
            self._set_participants(participants)

    def _set_participant_factories(
        self,
        participant_factories: Sequence[Callable[[], SupportsAgentRun | Executor]],
    ) -> None:
        """Set participant factories (internal)."""
        if self._participants:
            raise ValueError("Cannot provide both participants and participant_factories.")

        if self._participant_factories:
            raise ValueError("participant_factories already set.")

        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = list(participant_factories)

    def _set_participants(self, participants: Sequence[SupportsAgentRun | Executor]) -> None:
        """Set participants (internal)."""
        if self._participant_factories:
            raise ValueError("Cannot provide both participants and participant_factories.")

        if self._participants:
            raise ValueError("participants already set.")

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
                # Treat non-Executor as agent-like (SupportsAgentRun). Structural checks can be brittle at runtime.
                pid = id(p)
                if pid in seen_agent_ids:
                    raise ValueError("Duplicate agent participant detected (same agent instance provided twice)")
                seen_agent_ids.add(pid)

        self._participants = list(participants)

    def with_request_info(
        self,
        *,
        agents: Sequence[str | SupportsAgentRun] | None = None,
    ) -> "SequentialBuilder":
        """Enable request info after agent participant responses.

        This enables human-in-the-loop (HIL) scenarios for the sequential orchestration.
        When enabled, the workflow pauses after each agent participant runs, emitting
        a request_info event (type='request_info') that allows the caller to review the conversation and optionally
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
            raise ValueError("No participants provided. Pass participants or participant_factories to the constructor.")
        # We don't need to check if both are set since that is handled in the respective methods

        participants: list[Executor | SupportsAgentRun] = []
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
            elif isinstance(p, SupportsAgentRun):
                if self._request_info_enabled and (
                    not self._request_info_filter or resolve_agent_id(p) in self._request_info_filter
                ):
                    # Handle request info enabled agents
                    executors.append(AgentApprovalExecutor(p))
                else:
                    executors.append(AgentExecutor(p))
            else:
                raise TypeError(f"Participants must be SupportsAgentRun or Executor instances. Got {type(p).__name__}.")

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

        builder = WorkflowBuilder(
            start_executor=input_conv,
            checkpoint_storage=self._checkpoint_storage,
            output_executors=[end] if not self._intermediate_outputs else None,
        )

        # Start of the chain is the input normalizer
        prior: Executor | SupportsAgentRun = input_conv
        for p in participants:
            builder.add_edge(prior, p)
            prior = p
        # Terminate with the final conversation
        builder.add_edge(prior, end)

        return builder.build()
