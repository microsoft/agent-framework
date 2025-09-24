# Copyright (c) Microsoft. All rights reserved.

"""Sequential builder for agent/executor workflows with shared conversation context.

This module provides a high-level, agent-focused API to assemble a sequential
workflow where:
- Participants are a sequence of AgentProtocol instances or Executors
- A shared conversation context (list[ChatMessage]) is passed along the chain
- Agents append their assistant messages to the context
- Custom executors can transform or summarize and return a refined context
- The workflow finishes with the final context produced by the last participant

Typical wiring:
    input -> _InputToConversation -> participant1 -> (agent? -> _ResponseToConversation) -> ... -> participantN -> _EndWithConversation

Notes:
- Participants can mix AgentProtocol and Executor objects
- Agents are auto-wrapped by WorkflowBuilder as AgentExecutor
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
from collections.abc import Sequence
from typing import Any

from agent_framework import AgentProtocol, ChatMessage, Role

from ._executor import (
    AgentExecutor,
    AgentExecutorResponse,
    Executor,
    handler,
)
from ._workflow import Workflow, WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)


class _InputToConversation(Executor):
    """Normalizes initial input into a list[ChatMessage] conversation."""

    @handler
    async def from_str(self, prompt: str, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        await ctx.send_message([ChatMessage(Role.USER, text=prompt)])

    @handler
    async def from_message(self, message: ChatMessage, ctx: WorkflowContext[list[ChatMessage]]) -> None:  # type: ignore[name-defined]
        await ctx.send_message([message])

    @handler
    async def from_messages(self, messages: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:  # type: ignore[name-defined]
        # Make a copy to avoid mutation downstream
        await ctx.send_message(list(messages))


class _ResponseToConversation(Executor):
    """Converts AgentExecutorResponse to list[ChatMessage] conversation for chaining."""

    @handler
    async def convert(self, response: AgentExecutorResponse, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        # Always use full_conversation; AgentExecutor guarantees it is populated.
        if response.full_conversation is None:  # Defensive: indicates a contract violation
            raise RuntimeError("AgentExecutorResponse.full_conversation missing. AgentExecutor must populate it.")
        await ctx.send_message(list(response.full_conversation))


class _EndWithConversation(Executor):
    """Terminates the workflow by emitting the final conversation context."""

    @handler
    async def end(self, conversation: list[ChatMessage], ctx: WorkflowContext[Any, list[ChatMessage]]) -> None:
        await ctx.yield_output(list(conversation))


class SequentialBuilder:
    r"""High-level builder for sequential agent/executor workflows with shared context.

    - `participants([...])` accepts a list of AgentProtocol (recommended) or Executor
    - The workflow wires participants in order, passing a list[ChatMessage] down the chain
    - Agents append their assistant messages to the conversation
    - Custom executors can transform/summarize and return a list[ChatMessage]
    - The final output is the conversation produced by the last participant

    Usage:
    ```python
    from agent_framework import SequentialBuilder

    workflow = SequentialBuilder().participants([agent1, agent2, summarizer_exec]).build()
    ```
    """

    def __init__(self) -> None:
        self._participants: list[AgentProtocol | Executor] = []

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "SequentialBuilder":
        """Define the ordered participants for this sequential workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.
        Raises if empty or duplicates are provided for clarity.
        """
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

    def build(self) -> Workflow:
        """Build and validate the sequential workflow.

        Wiring pattern:
        - _InputToConversation normalizes the initial input into list[ChatMessage]
        - For each participant in order:
            - If Agent (or AgentExecutor): pass conversation to the agent, then convert response
              to conversation via _ResponseToConversation
            - Else (custom Executor): pass conversation directly to the executor
        - _EndWithConversation yields the final conversation and the workflow becomes idle
        """
        if not self._participants:
            raise ValueError("No participants provided. Call .participants([...]) first.")

        # Internal nodes
        input_conv = _InputToConversation(id="input-conversation")
        end = _EndWithConversation(id="end")

        builder = WorkflowBuilder()
        builder.set_start_executor(input_conv)

        # Start of the chain is the input normalizer
        prior: Executor | AgentProtocol = input_conv

        for p in self._participants:
            # Agent-like branch: either explicitly an AgentExecutor or any non-AgentExecutor
            if not (isinstance(p, Executor) and not isinstance(p, AgentExecutor)):
                # input conversation -> (agent) -> response -> conversation
                builder.add_edge(prior, p)
                # Give the adapter a deterministic, self-describing id
                label: str
                label = p.id if isinstance(p, Executor) else getattr(p, "name", None) or p.__class__.__name__
                resp_to_conv = _ResponseToConversation(id=f"to-conversation:{label}")
                builder.add_edge(p, resp_to_conv)
                prior = resp_to_conv
            elif isinstance(p, Executor):
                # Custom executor operates on list[ChatMessage]
                builder.add_edge(prior, p)
                prior = p
            else:  # pragma: no cover - defensive
                raise TypeError(f"Unsupported participant type: {type(p).__name__}")

        # Terminate with the final conversation
        builder.add_edge(prior, end)

        return builder.build()
