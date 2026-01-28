# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
import logging
from collections.abc import Callable, Sequence
from typing import Any

from typing_extensions import Never

from agent_framework import AgentProtocol, ChatMessage, Role

from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._agent_utils import resolve_agent_id
from ._checkpoint import CheckpointStorage
from ._executor import Executor, handler
from ._message_utils import normalize_messages_input
from ._orchestration_request_info import AgentApprovalExecutor
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)

"""Concurrent builder for agent-only fan-out/fan-in workflows.

This module provides a high-level, agent-focused API to quickly assemble a
parallel workflow with:
- a default dispatcher that broadcasts the input to all agent participants
- a default aggregator that combines all agent conversations and completes the workflow

Notes:
- Participants can be provided as AgentProtocol or Executor instances via `.participants()`,
  or as factories returning AgentProtocol or Executor via `.register_participants()`.
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
        request = AgentExecutorRequest(messages=normalize_messages_input(prompt), should_respond=True)
        await ctx.send_message(request)

    @handler
    async def from_message(self, message: ChatMessage, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        request = AgentExecutorRequest(messages=normalize_messages_input(message), should_respond=True)
        await ctx.send_message(request)

    @handler
    async def from_messages(
        self,
        messages: list[str | ChatMessage],
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        request = AgentExecutorRequest(messages=normalize_messages_input(messages), should_respond=True)
        await ctx.send_message(request)


class _AggregateAgentConversations(Executor):
    """Aggregates agent responses and completes with combined ChatMessages.

    Emits a list[ChatMessage] shaped as:
      [ single_user_prompt?, agent1_final_assistant, agent2_final_assistant, ... ]

    - Extracts a single user prompt (first user message seen across results).
    - For each result, selects the final assistant message (prefers agent_response.messages).
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
            resp_messages = list(getattr(r.agent_response, "messages", []) or [])
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
    - `register_participants([...])` accepts a list of factories for AgentProtocol (recommended)
       or Executor factories
    - `build()` wires: dispatcher -> fan-out -> participants -> fan-in -> aggregator.
    - `with_aggregator(...)` overrides the default aggregator with an Executor or callback.
    - `register_aggregator(...)` accepts a factory for an Executor as custom aggregator.

    Usage:

    .. code-block:: python

        from agent_framework import ConcurrentBuilder

        # Minimal: use default aggregator (returns list[ChatMessage])
        workflow = ConcurrentBuilder().participants([agent1, agent2, agent3]).build()

        # With agent factories
        workflow = ConcurrentBuilder().register_participants([create_agent1, create_agent2, create_agent3]).build()


        # Custom aggregator via callback (sync or async). The callback receives
        # list[AgentExecutorResponse] and its return value becomes the workflow's output.
        def summarize(results: list[AgentExecutorResponse]) -> str:
            return " | ".join(r.agent_response.messages[-1].text for r in results)


        workflow = ConcurrentBuilder().participants([agent1, agent2, agent3]).with_aggregator(summarize).build()


        # Custom aggregator via a factory
        class MyAggregator(Executor):
            @handler
            async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
                await ctx.yield_output(" | ".join(r.agent_response.messages[-1].text for r in results))


        workflow = (
            ConcurrentBuilder()
            .register_participants([create_agent1, create_agent2, create_agent3])
            .register_aggregator(lambda: MyAggregator(id="my_aggregator"))
            .build()
        )


        # Enable checkpoint persistence so runs can resume
        workflow = ConcurrentBuilder().participants([agent1, agent2, agent3]).with_checkpointing(storage).build()

        # Enable request info before aggregation
        workflow = ConcurrentBuilder().participants([agent1, agent2]).with_request_info().build()
    """

    def __init__(self) -> None:
        self._participants: list[AgentProtocol | Executor] = []
        self._participant_factories: list[Callable[[], AgentProtocol | Executor]] = []
        self._aggregator: Executor | None = None
        self._aggregator_factory: Callable[[], Executor] | None = None
        self._checkpoint_storage: CheckpointStorage | None = None
        self._request_info_enabled: bool = False
        self._request_info_filter: set[str] | None = None

    def register_participants(
        self,
        participant_factories: Sequence[Callable[[], AgentProtocol | Executor]],
    ) -> "ConcurrentBuilder":
        r"""Define the parallel participants for this concurrent workflow.

        Accepts factories (callables) that return AgentProtocol instances (e.g., created
        by a chat client) or Executor instances. Each participant created by a factory
        is wired as a parallel branch using fan-out edges from an internal dispatcher.

        Args:
            participant_factories: Sequence of callables returning AgentProtocol or Executor instances

        Raises:
            ValueError: if `participant_factories` is empty or `.participants()`
                       or `.register_participants()` were already called

        Example:

        .. code-block:: python

            def create_researcher() -> ChatAgent:
                return ...


            def create_marketer() -> ChatAgent:
                return ...


            def create_legal() -> ChatAgent:
                return ...


            class MyCustomExecutor(Executor): ...


            wf = ConcurrentBuilder().register_participants([create_researcher, create_marketer, create_legal]).build()

            # Mixing agent(s) and executor(s) is supported
            wf2 = ConcurrentBuilder().register_participants([create_researcher, MyCustomExecutor]).build()
        """
        if self._participants:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participant_factories:
            raise ValueError("register_participants() has already been called on this builder instance.")

        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = list(participant_factories)
        return self

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> "ConcurrentBuilder":
        r"""Define the parallel participants for this concurrent workflow.

        Accepts AgentProtocol instances (e.g., created by a chat client) or Executor
        instances. Each participant is wired as a parallel branch using fan-out edges
        from an internal dispatcher.

        Args:
            participants: Sequence of AgentProtocol or Executor instances

        Raises:
            ValueError: if `participants` is empty, contains duplicates, or `.register_participants()`
                       or `.participants()` were already called
            TypeError: if any entry is not AgentProtocol or Executor

        Example:

        .. code-block:: python

            wf = ConcurrentBuilder().participants([researcher_agent, marketer_agent, legal_agent]).build()

            # Mixing agent(s) and executor(s) is supported
            wf2 = ConcurrentBuilder().participants([researcher_agent, my_custom_executor]).build()
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
            elif isinstance(p, AgentProtocol):
                pid = id(p)
                if pid in seen_agent_ids:
                    raise ValueError("Duplicate agent participant detected (same agent instance provided twice)")
                seen_agent_ids.add(pid)
            else:
                raise TypeError(f"participants must be AgentProtocol or Executor instances; got {type(p).__name__}")

        self._participants = list(participants)
        return self

    def register_aggregator(self, aggregator_factory: Callable[[], Executor]) -> "ConcurrentBuilder":
        r"""Define a custom aggregator for this concurrent workflow.

        Accepts a factory (callable) that returns an Executor instance. The executor
        should handle `list[AgentExecutorResponse]` and yield output using `ctx.yield_output(...)`.

        Args:
            aggregator_factory: Callable that returns an Executor instance

        Example:
        .. code-block:: python

            class MyCustomExecutor(Executor): ...


            wf = (
                ConcurrentBuilder()
                .register_participants([create_researcher, create_marketer, create_legal])
                .register_aggregator(lambda: MyCustomExecutor(id="my_aggregator"))
                .build()
            )
        """
        if self._aggregator is not None:
            raise ValueError(
                "Cannot mix .with_aggregator(...) and .register_aggregator(...) in the same builder instance."
            )

        if self._aggregator_factory is not None:
            raise ValueError("register_aggregator() has already been called on this builder instance.")

        self._aggregator_factory = aggregator_factory
        return self

    def with_aggregator(
        self,
        aggregator: Executor
        | Callable[[list[AgentExecutorResponse]], Any]
        | Callable[[list[AgentExecutorResponse], WorkflowContext[Never, Any]], Any],
    ) -> "ConcurrentBuilder":
        r"""Override the default aggregator with an executor or a callback.

        - Executor: must handle `list[AgentExecutorResponse]` and yield output using `ctx.yield_output(...)`
        - Callback: sync or async callable with one of the signatures:
          `(results: list[AgentExecutorResponse]) -> Any | None` or
          `(results: list[AgentExecutorResponse], ctx: WorkflowContext) -> Any | None`.
          If the callback returns a non-None value, it becomes the workflow's output.

        Args:
            aggregator: Executor instance, or callback function

        Example:

        .. code-block:: python
            # Executor-based aggregator
            class CustomAggregator(Executor):
                @handler
                async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext) -> None:
                    await ctx.yield_output(" | ".join(r.agent_response.messages[-1].text for r in results))


            wf = ConcurrentBuilder().participants([a1, a2, a3]).with_aggregator(CustomAggregator()).build()


            # Callback-based aggregator (string result)
            async def summarize(results: list[AgentExecutorResponse]) -> str:
                return " | ".join(r.agent_response.messages[-1].text for r in results)


            wf = ConcurrentBuilder().participants([a1, a2, a3]).with_aggregator(summarize).build()


            # Callback-based aggregator (yield result)
            async def summarize(results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
                await ctx.yield_output(" | ".join(r.agent_response.messages[-1].text for r in results))


            wf = ConcurrentBuilder().participants([a1, a2, a3]).with_aggregator(summarize).build()
        """
        if self._aggregator_factory is not None:
            raise ValueError(
                "Cannot mix .with_aggregator(...) and .register_aggregator(...) in the same builder instance."
            )

        if self._aggregator is not None:
            raise ValueError("with_aggregator() has already been called on this builder instance.")

        if isinstance(aggregator, Executor):
            self._aggregator = aggregator
        elif callable(aggregator):
            self._aggregator = _CallbackAggregator(aggregator)
        else:
            raise TypeError("aggregator must be an Executor or a callable")

        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "ConcurrentBuilder":
        """Enable checkpoint persistence using the provided storage backend.

        Args:
            checkpoint_storage: CheckpointStorage instance for persisting workflow state
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_request_info(
        self,
        *,
        agents: Sequence[str | AgentProtocol] | None = None,
    ) -> "ConcurrentBuilder":
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
        r"""Build and validate the concurrent workflow.

        Wiring pattern:
        - Dispatcher (internal) fans out the input to all `participants`
        - Fan-in collects `AgentExecutorResponse` objects from all participants
        - If request info is enabled, the orchestration emits a request info event with outputs from all participants
            before sending the outputs to the aggregator
        - Aggregator yields output and the workflow becomes idle. The output is either:
          - list[ChatMessage] (default aggregator: one user + one assistant per agent)
          - custom payload from the provided aggregator

        Returns:
            Workflow: a ready-to-run workflow instance

        Raises:
            ValueError: if no participants were defined

        Example:

        .. code-block:: python

            workflow = ConcurrentBuilder().participants([agent1, agent2]).build()
        """
        # Internal nodes
        dispatcher = _DispatchToAllParticipants(id="dispatcher")
        aggregator = (
            self._aggregator
            if self._aggregator is not None
            else (
                self._aggregator_factory()
                if self._aggregator_factory is not None
                else _AggregateAgentConversations(id="aggregator")
            )
        )

        # Resolve participants and participant factories to executors
        participants: list[Executor] = self._resolve_participants()

        builder = WorkflowBuilder()
        builder.set_start_executor(dispatcher)
        # Fan-out for parallel execution
        builder.add_fan_out_edges(dispatcher, participants)
        # Direct fan-in to aggregator
        builder.add_fan_in_edges(participants, aggregator)

        if self._checkpoint_storage is not None:
            builder = builder.with_checkpointing(self._checkpoint_storage)

        return builder.build()
