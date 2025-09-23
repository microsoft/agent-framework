# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
import logging
from collections.abc import Callable, Sequence
from typing import Any

from typing_extensions import Never

from agent_framework import AgentProtocol, ChatMessage, Role

from ._executor import AgentExecutorRequest, AgentExecutorResponse, Executor, handler
from ._workflow import Workflow, WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)

"""Concurrent builder for agent-only fan-out/fan-in workflows.

This module provides a high-level, agent-focused API to quickly assemble a
parallel workflow with:
- a default dispatcher that broadcasts the input to all agent participants
- a default aggregator that combines all agent conversations and completes the workflow

Notes:
- Participants should be AgentProtocol instances or Executors.
- A custom aggregator can be provided as:
  - an Executor instance (it should handle list[AgentExecutorResponse],
    yield output), or
  - a callback function with signature:
        def cb(results: list[AgentExecutorResponse]) -> Any | None
        def cb(results: list[AgentExecutorResponse], ctx: WorkflowContext) -> Any | None
    The callback is wrapped in _CallbackAggregator.
    If the callback returns a non-None value, _CallbackAggregator yields that as output.
    If it returns None, the callback may have already yielded an output via ctx, so no further action is taken.
"""


class _DispatchToAllParticipants(Executor):
    """Broadcasts input to all downstream participants (via fan-out edges)."""

    @handler
    async def from_request(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        # No explicit target: edge routing delivers to all connected participants.
        await ctx.send_message(request)

    @handler
    async def from_str(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        request = AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=prompt)], should_respond=True)
        await ctx.send_message(request)

    @handler
    async def from_message(self, message: ChatMessage, ctx: WorkflowContext[AgentExecutorRequest]) -> None:  # type: ignore[name-defined]
        request = AgentExecutorRequest(messages=[message], should_respond=True)
        await ctx.send_message(request)

    @handler
    async def from_messages(self, messages: list[ChatMessage], ctx: WorkflowContext[AgentExecutorRequest]) -> None:  # type: ignore[name-defined]
        request = AgentExecutorRequest(messages=list(messages), should_respond=True)
        await ctx.send_message(request)


class _AggregateAgentConversations(Executor):
    """Aggregates agent responses and completes with combined ChatMessages.

    Emits a list[ChatMessage] shaped as:
      [ single_user_prompt?, agent1_final_assistant, agent2_final_assistant, ... ]

    - Extracts a single user prompt (first user message seen across results).
    - For each result, selects the final assistant message (prefers agent_run_response.messages).
    - Avoids duplicating the same user message per agent.
    """

    @handler
    async def aggregate(
        self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, list[ChatMessage]]
    ) -> None:
        if not results:
            logger.error("Concurrent aggregator received empty results list")
            raise ValueError("Aggregation failed: no results provided")

        def _is_role(msg: Any, role: Role) -> bool:
            r = getattr(msg, "role", None)
            if r is None:
                return False
            # Normalize both r and role to lowercase strings for comparison
            r_str = str(r).lower() if isinstance(r, str) or hasattr(r, "__str__") else r
            role_str = getattr(role, "value", None)
            if role_str is None:
                role_str = str(role)
            role_str = role_str.lower()
            return r_str == role_str

        prompt_message: ChatMessage | None = None
        assistant_replies: list[ChatMessage] = []

        for r in results:
            resp_messages = list(getattr(r.agent_run_response, "messages", []) or [])
            conv = r.full_conversation if r.full_conversation is not None else resp_messages

            logger.debug(
                f"Aggregating executor {getattr(r, 'executor_id', '<unknown>')}: "
                f"{len(resp_messages)} response msgs, {len(conv)} conversation msgs"
            )

            # Capture a single user prompt (first encountered across any conversation)
            if prompt_message is None:
                found_user = next((m for m in conv if _is_role(m, Role.USER)), None)
                if found_user is not None:
                    prompt_message = found_user

            # Pick the final assistant message from the response; fallback to conversation search
            final_assistant = next((m for m in reversed(resp_messages) if _is_role(m, Role.ASSISTANT)), None)
            if final_assistant is None:
                final_assistant = next((m for m in reversed(conv) if _is_role(m, Role.ASSISTANT)), None)

            if final_assistant is not None:
                assistant_replies.append(final_assistant)
            else:
                logger.warning(
                    f"No assistant reply found for executor {getattr(r, 'executor_id', '<unknown>')}; skipping"
                )

        if not assistant_replies:
            logger.error(f"Aggregation failed: no assistant replies found across {len(results)} results")
            raise RuntimeError("Aggregation failed: no assistant replies found")

        output: list[ChatMessage] = []
        if prompt_message is not None:
            output.append(prompt_message)
        else:
            logger.warning("No user prompt found in any conversation; emitting assistants only")
        output.extend(assistant_replies)

        await ctx.yield_output(output)


class _CallbackAggregator(Executor):
    """Wraps a Python callback as an aggregator.

    Accepts either an async or sync callback with one of the signatures:
      - (results: list[AgentExecutorResponse]) -> Any | None
      - (results: list[AgentExecutorResponse], ctx: WorkflowContext[Any]) -> Any | None

    Notes:
    - Async callbacks are awaited directly.
    - Sync callbacks are executed via asyncio.to_thread to avoid blocking the event loop.
    - If the callback returns a non-None value, it is yielded as an output.
    """

    def __init__(self, callback: Callable[..., Any], id: str | None = None) -> None:
        derived_id = getattr(callback, "__name__", "") or ""
        if not derived_id or derived_id == "<lambda>":
            derived_id = f"{type(self).__name__}_unnamed"
        super().__init__(id or derived_id)
        self._callback = callback
        self._param_count = len(inspect.signature(callback).parameters)

    @handler
    async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, Any]) -> None:
        # Call according to provided signature, always non-blocking for sync callbacks
        if self._param_count >= 2:
            if inspect.iscoroutinefunction(self._callback):
                ret = await self._callback(results, ctx)  # type: ignore[misc]
            else:
                ret = await asyncio.to_thread(self._callback, results, ctx)
        else:
            if inspect.iscoroutinefunction(self._callback):
                ret = await self._callback(results)  # type: ignore[misc]
            else:
                ret = await asyncio.to_thread(self._callback, results)

        # If the callback returned a value, finalize the workflow with it
        if ret is not None:
            await ctx.yield_output(ret)


class ConcurrentBuilder:
    r"""High-level builder for concurrent agent workflows.

    - `participants([...])` accepts a list of AgentProtocol (recommended) or Executor.
    - `build()` wires: dispatcher -> fan-out -> participants -> fan-in -> aggregator.
    - `with_custom_aggregator(...)` overrides the default aggregator with an Executor or callback.

    Usage:
    ```python
    from agent_framework import ConcurrentBuilder

    # Minimal: use default aggregator (returns list[ChatMessage])
    workflow = ConcurrentBuilder().participants([agent1, agent2, agent3]).build()


    # Custom aggregator via callback (sync or async). The callback receives
    # list[AgentExecutorResponse] and its return value becomes the workflow's output.
    def summarize(results):
        return " | ".join(r.agent_run_response.messages[-1].text for r in results)


    workflow = ConcurrentBuilder().participants([agent1, agent2, agent3]).with_custom_aggregator(summarize).build()
    ```
    """

    def __init__(self) -> None:
        self._participants: list[AgentProtocol | Executor] = []
        self._aggregator: Executor | None = None

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "ConcurrentBuilder":
        r"""Define the parallel participants for this concurrent workflow.

        Accepts AgentProtocol instances (e.g., created by a chat client) or Executor
        instances. Each participant is wired as a parallel branch using fan-out edges
        from an internal dispatcher.

        Raises:
            ValueError: if `participants` is empty or contains duplicates
            TypeError: if any entry is not AgentProtocol or Executor

        Example:
        ```python
        wf = ConcurrentBuilder().participants([researcher_agent, marketer_agent, legal_agent]).build()

        # Mixing agent(s) and executor(s) is supported
        wf2 = ConcurrentBuilder().participants([researcher_agent, my_custom_executor]).build()
        ```
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
            elif isinstance(p, AgentProtocol):
                pid = id(p)
                if pid in seen_agent_ids:
                    raise ValueError("Duplicate agent participant detected (same agent instance provided twice)")
                seen_agent_ids.add(pid)
            else:
                raise TypeError(f"participants must be AgentProtocol or Executor instances; got {type(p).__name__}")

        self._participants = list(participants)
        return self

    def with_aggregator(self, aggregator: Executor | Callable[..., Any]) -> "ConcurrentBuilder":
        r"""Override the default aggregator with an Executor or a callback.

        - Executor: must handle `list[AgentExecutorResponse]` and
            yield output using `ctx.yield_output(...)` and add a
          output and the workflow becomes idle.
        - Callback: sync or async callable with one of the signatures:
          `(results: list[AgentExecutorResponse]) -> Any | None` or
          `(results: list[AgentExecutorResponse], ctx: WorkflowContext) -> Any | None`.
          If the callback returns a non-None value, it becomes the workflow's output.

        Example:
        ```python
        # Callback-based aggregator (string result)
        async def summarize(results):
            return " | ".join(r.agent_run_response.messages[-1].text for r in results)


        wf = ConcurrentBuilder().participants([a1, a2, a3]).with_custom_aggregator(summarize).build()
        ```
        """
        if isinstance(aggregator, Executor):
            self._aggregator = aggregator
        elif callable(aggregator):
            self._aggregator = _CallbackAggregator(aggregator)
        else:
            raise TypeError("aggregator must be an Executor or a callable")
        return self

    def build(self) -> Workflow:
        r"""Build and validate the concurrent workflow.

        Wiring pattern:
        - Dispatcher (internal) fans out the input to all `participants`
        - Fan-in aggregator collects `AgentExecutorResponse` objects
        - Aggregator yields output and the workflow becomes idle. The output is either:
          - list[ChatMessage] (default aggregator: one user + one assistant per agent)
          - custom payload from the provided callback/executor

        Returns:
            Workflow: a ready-to-run workflow instance

        Raises:
            ValueError: if no participants were defined

        Example:
        ```python
        workflow = ConcurrentBuilder().participants([agent1, agent2]).build()
        ```
        """
        if not self._participants:
            raise ValueError("No participants provided. Call .participants([...]) first.")

        dispatcher = _DispatchToAllParticipants(id="dispatcher")
        aggregator = self._aggregator or _AggregateAgentConversations(id="aggregator")

        builder = WorkflowBuilder()
        return (
            builder.set_start_executor(dispatcher)
            .add_fan_out_edges(dispatcher, list(self._participants))
            .add_fan_in_edges(list(self._participants), aggregator)
            .build()
        )
