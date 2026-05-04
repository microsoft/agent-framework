# Copyright (c) Microsoft. All rights reserved.

"""Sequential builder for agent/executor workflows with shared conversation context.

Participants (SupportsAgentRun or Executor instances) run in order, sharing a
conversation along the chain. Agents append their assistant messages; custom executors
transform and return a refined `list[Message]`.

Wiring: input -> _InputToConversation -> participant1 -> ... -> participantN

The workflow's final `output` event is the last participant's `yield_output(...)`. For
agent terminators that is an `AgentResponse` (or per-chunk `AgentResponseUpdate`s when
streaming). For custom-executor terminators, the executor itself yields whatever it
produces — by convention an `AgentResponse` so downstream consumers see a uniform shape.
"""

import logging
from collections.abc import Sequence
from typing import Literal

from agent_framework import Message, SupportsAgentRun
from agent_framework._workflows._agent_executor import AgentExecutor
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
    """Normalizes initial input into a list[Message] conversation."""

    @handler
    async def from_str(self, prompt: str, ctx: WorkflowContext[list[Message]]) -> None:
        await ctx.send_message(normalize_messages_input(prompt))

    @handler
    async def from_message(self, message: Message, ctx: WorkflowContext[list[Message]]) -> None:
        await ctx.send_message(normalize_messages_input(message))

    @handler
    async def from_messages(self, messages: list[str | Message], ctx: WorkflowContext[list[Message]]) -> None:
        await ctx.send_message(normalize_messages_input(messages))


class SequentialBuilder:
    r"""High-level builder for sequential agent/executor workflows with shared context.

    - `participants=[...]` accepts a list of SupportsAgentRun (recommended) or Executor instances
    - Executors must define a handler that consumes list[Message] and sends out a list[Message]
    - The workflow wires participants in order, passing a list[Message] down the chain
    - Agents append their assistant messages to the conversation
    - Custom executors can transform/summarize and return a list[Message]
    - The final output is the conversation produced by the last participant

    Usage:

    .. code-block:: python

        from agent_framework_orchestrations import SequentialBuilder

        # With agent instances
        workflow = SequentialBuilder(participants=[agent1, agent2, summarizer_exec]).build()

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
        participants: Sequence[SupportsAgentRun | Executor],
        checkpoint_storage: CheckpointStorage | None = None,
        chain_only_agent_responses: bool = False,
        intermediate_outputs: bool = False,
    ) -> None:
        """Initialize the SequentialBuilder.

        Args:
            participants: Sequence of agent or executor instances to run sequentially.
            checkpoint_storage: Optional checkpoint storage for enabling workflow state persistence.
            chain_only_agent_responses: If True, only agent responses are chained between agents.
                By default, the full conversation context is passed to the next agent. This also applies
                to Executor -> Agent transitions if the executor sends `AgentExecutorResponse`.
            intermediate_outputs: If True, every participant's `yield_output` surfaces as a
                workflow `output` event in addition to the terminator's. By default (False) only
                the last participant's output surfaces.
        """
        self._participants: list[SupportsAgentRun | Executor] = []
        self._checkpoint_storage: CheckpointStorage | None = checkpoint_storage
        self._chain_only_agent_responses: bool = chain_only_agent_responses
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] | None = None
        self._intermediate_outputs: bool = intermediate_outputs

        self._set_participants(participants)

    def _set_participants(self, participants: Sequence[SupportsAgentRun | Executor]) -> None:
        """Set participants (internal)."""
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
        """Resolve participant instances into Executor objects.

        Wraps `SupportsAgentRun` participants as `AgentExecutor` (or `AgentApprovalExecutor`
        when request-info is enabled for that participant). The last participant, when wrapped
        as `AgentApprovalExecutor`, is constructed with `allow_direct_output=True` so the
        approved response surfaces as the workflow's output event instead of being forwarded
        as a message that has nowhere to go.
        """
        if not self._participants:
            raise ValueError("No participants provided. Pass participants to the constructor.")

        participants: list[Executor | SupportsAgentRun] = self._participants

        context_mode: Literal["full", "last_agent", "custom"] | None = (
            "last_agent" if self._chain_only_agent_responses else None
        )

        last_idx = len(participants) - 1
        executors: list[Executor] = []
        for idx, p in enumerate(participants):
            if isinstance(p, Executor):
                executors.append(p)
            elif isinstance(p, SupportsAgentRun):
                if self._request_info_enabled and (
                    not self._request_info_filter or resolve_agent_id(p) in self._request_info_filter
                ):
                    # Handle request info enabled agents
                    executors.append(
                        AgentApprovalExecutor(
                            p,
                            context_mode=context_mode,
                            allow_direct_output=(idx == last_idx),
                        )
                    )
                else:
                    executors.append(AgentExecutor(p, context_mode=context_mode))
            else:
                raise TypeError(f"Participants must be SupportsAgentRun or Executor instances. Got {type(p).__name__}.")

        return executors

    def build(self) -> Workflow:
        """Build and validate the sequential workflow.

        Wiring pattern:
        - `_InputToConversation` normalizes the initial input into `list[Message]`.
        - Each participant runs in order:
            - `AgentExecutor`: receives the conversation / `AgentExecutorResponse` and
              forwards an `AgentExecutorResponse` downstream.
            - Custom `Executor`: receives `list[Message]` and forwards `list[Message]`.
              If used as the terminator, it must call `ctx.yield_output(AgentResponse(...))`
              instead of `ctx.send_message(...)` — its yield becomes the workflow's output.
        - The last participant is registered as the workflow's `output_executor`, so the
          terminator's own `yield_output` is the workflow's terminal output (`AgentResponse`,
          or per-chunk `AgentResponseUpdate` when streaming).
        """
        input_conv = _InputToConversation(id="input-conversation")

        # Resolve participants and participant factories to executors
        participants: list[Executor] = self._resolve_participants()

        builder = WorkflowBuilder(
            start_executor=input_conv,
            checkpoint_storage=self._checkpoint_storage,
            output_executors=[participants[-1]] if not self._intermediate_outputs else None,
        )

        prior: Executor | SupportsAgentRun = input_conv
        for p in participants:
            builder.add_edge(prior, p)
            prior = p

        return builder.build()
