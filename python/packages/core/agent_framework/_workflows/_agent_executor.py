# Copyright (c) Microsoft. All rights reserved.

import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from typing_extensions import Never

from agent_framework import Content

from .._agents import SupportsAgentRun
from .._sessions import AgentSession
from .._types import AgentResponse, AgentResponseUpdate, Message, ResponseStream
from ._agent_utils import resolve_agent_id
from ._const import GLOBAL_KWARGS_KEY, WORKFLOW_RUN_KWARGS_KEY
from ._executor import Executor, handler
from ._message_utils import normalize_messages_input
from ._request_info_mixin import response_handler
from ._typing_utils import is_chat_agent
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover

logger = logging.getLogger(__name__)


@dataclass
class AgentExecutorRequest:
    """A request to an agent executor.

    Attributes:
        messages: A list of chat messages to be processed by the agent.
        should_respond: A flag indicating whether the agent should respond to the messages.
            If False, the messages will be saved to the executor's cache but not sent to the agent.
    """

    messages: list[Message]
    should_respond: bool = True


@dataclass
class AgentExecutorResponse:
    """A response from an agent executor.

    Attributes:
        executor_id: The ID of the executor that generated the response.
        agent_response: The underlying agent run response (unaltered from client).
        full_conversation: The full conversation context (prior inputs + all assistant/tool outputs) that
            should be used when chaining to another AgentExecutor. This prevents downstream agents losing
            user prompts.
    """

    executor_id: str
    agent_response: AgentResponse
    full_conversation: list[Message]

    def with_text(self, text: str) -> "AgentExecutorResponse":
        """Create a new AgentExecutorResponse with replaced text, preserving the conversation history.

        Use this in custom executors that transform agent output text (e.g. upper-casing, summarising)
        when you need downstream AgentExecutors to still have access to the full prior conversation.

        Without this helper, sending a plain ``str`` from a custom executor breaks the context chain:
        the downstream ``AgentExecutor.from_str`` handler only adds that one string to its cache and
        loses all prior messages.  By using ``with_text`` the response type stays
        ``AgentExecutorResponse``, so ``AgentExecutor.from_response`` is invoked instead and the full
        conversation is preserved.

        Args:
            text: The replacement assistant message text.

        Returns:
            A new ``AgentExecutorResponse`` whose ``agent_response`` contains a single assistant
            message with ``text``, and whose ``full_conversation`` is the prior conversation
            (everything before the original agent turn) followed by the new assistant message.

        Example:
            .. code-block:: python

                from agent_framework import AgentExecutorResponse, WorkflowContext, executor


                @executor(
                    id="upper_case_executor",
                    input=AgentExecutorResponse,
                    output=AgentExecutorResponse,
                    workflow_output=str,
                )
                async def upper_case(
                    response: AgentExecutorResponse,
                    ctx: WorkflowContext[AgentExecutorResponse, str],
                ) -> None:
                    upper_text = response.agent_response.text.upper()
                    await ctx.send_message(response.with_text(upper_text))
                    await ctx.yield_output(upper_text)
        """
        new_message = Message("assistant", [text])
        new_agent_response = AgentResponse(messages=[new_message])

        # Strip off the original agent turn and replace with the new text.
        n_agent_messages = len(self.agent_response.messages)
        prior_messages = (
            self.full_conversation[:-n_agent_messages] if n_agent_messages else list(self.full_conversation)
        )
        new_full_conversation = [*prior_messages, new_message]

        return AgentExecutorResponse(
            executor_id=self.executor_id,
            agent_response=new_agent_response,
            full_conversation=new_full_conversation,
        )


class AgentExecutor(Executor):
    """built-in executor that wraps an agent for handling messages.

    AgentExecutor adapts its behavior based on the workflow execution mode:
    - run(stream=True): Emits incremental output events (type='output') as the agent produces tokens
    - run(): Emits a single output event (type='output') containing the complete response

    Use `with_output_from` in WorkflowBuilder to control whether the AgentResponse
    or AgentResponseUpdate objects are yielded as workflow outputs.

    Messages sent to downstream executors will always be the complete AgentResponse. In
    streaming mode, incremental AgentResponseUpdates will be concatenated to form the full
    response to be sent downstream.

    The executor automatically detects the mode via WorkflowContext.is_streaming().
    """

    def __init__(
        self,
        agent: SupportsAgentRun,
        *,
        session: AgentSession | None = None,
        id: str | None = None,
        context_mode: Literal["full", "last_agent", "custom"] | None = None,
        context_filter: Callable[[list[Message]], list[Message]] | None = None,
    ):
        """Initialize the executor with a unique identifier.

        Args:
            agent: The agent to be wrapped by this executor.
            session: The session to use for running the agent. If None, a new session will be created.
            id: A unique identifier for the executor. If None, the agent's name will be used if available.
            context_mode: Configuration for how the executor should manage conversation context upon
                receiving an AgentExecutorResponse as input. Options:
                - "full": append the full conversation (all prior messages + latest agent response) to the
                   cache for the agent run. This is the default mode.
                - "last_agent": provide only the messages from the latest agent response as context for
                   the agent run.
                - "custom": use the provided context_filter function to determine which messages to include
                   as context for the agent run.
            context_filter: A function that takes the full conversation (list of Messages) as input and returns
                a filtered list of Messages to be used as context for the agent run. This is required
                if context_mode is set to "custom".
        """
        # Prefer provided id; else use agent.name if present; else generate deterministic prefix
        exec_id = id or resolve_agent_id(agent)
        if not exec_id:
            raise ValueError("Agent must have a non-empty name or id or an explicit id must be provided.")
        super().__init__(exec_id)
        self._agent = agent
        self._session = session or self._agent.create_session()

        self._pending_agent_requests: dict[str, Content] = {}
        self._pending_responses_to_agent: list[Content] = []

        # AgentExecutor maintains an internal cache of messages in between runs
        self._cache: list[Message] = []
        # This tracks the full conversation after each run
        self._full_conversation: list[Message] = []

        # Context mode validation
        self._context_mode = context_mode or "full"
        self._context_filter = context_filter
        if self._context_mode not in {"full", "last_agent", "custom"}:
            raise ValueError("context_mode must be one of 'full', 'last_agent', or 'custom'.")
        if self._context_mode == "custom" and not self._context_filter:
            raise ValueError("context_filter must be provided when context_mode is set to 'custom'.")

    @property
    def agent(self) -> SupportsAgentRun:
        """Get the underlying agent wrapped by this executor."""
        return self._agent

    @property
    def description(self) -> str | None:
        """Get the description of the underlying agent."""
        return self._agent.description

    @handler
    async def run(
        self,
        request: AgentExecutorRequest,
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
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
        self,
        prior: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Enable seamless chaining: accept a prior AgentExecutorResponse as input.

        Strategy: treat the prior response's messages as the conversation state and
        immediately run the agent to produce a new response.
        """
        if self._context_mode == "full":
            self._cache.extend(prior.full_conversation)
        elif self._context_mode == "last_agent":
            self._cache.extend(prior.agent_response.messages)
        else:
            if not self._context_filter:
                # This should never happen due to validation in __init__, but mypy doesn't track that well
                raise ValueError("context_filter function must be provided for 'custom' context_mode.")
            self._cache.extend(self._context_filter(prior.full_conversation))

        await self._run_agent_and_emit(ctx)

    @handler
    async def from_str(
        self, text: str, ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate]
    ) -> None:
        """Accept a raw user prompt string and run the agent.

        The new string input will be added to the cache which is used as the conversation context for the agent run.

        Warning:
            If the upstream executor received an ``AgentExecutorResponse`` but emits a plain
            ``str``, this handler will be invoked instead of ``from_response``. This resets
            the conversation context because only the new string is added to the cache and
            all prior messages from the upstream agent are lost.

            To preserve the full conversation when transforming agent output in a custom
            executor, use ``AgentExecutorResponse.with_text(...)`` so that the message type
            stays ``AgentExecutorResponse`` and ``from_response`` is called instead.
        """
        if not self._cache and ctx.source_executor_ids != ["Workflow"]:
            logger.warning(
                "AgentExecutor '%s': from_str handler invoked with an empty cache. "
                "If you are chaining from an AgentExecutor, the upstream custom executor may be "
                "emitting a plain str instead of using AgentExecutorResponse.with_text(...), "
                "which causes the full conversation context to be lost.",
                self.id,
            )
        self._cache.extend(normalize_messages_input(text))
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_message(
        self,
        message: Message,
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Accept a single Message as input.

        The new message will be added to the cache which is used as the conversation context for the agent run.
        """
        self._cache.extend(normalize_messages_input(message))
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_messages(
        self,
        messages: list[str | Message],
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Accept a list of chat inputs (strings or Message) as conversation context.

        The new messages will be added to the cache which is used as the conversation context for the agent run.
        """
        self._cache.extend(normalize_messages_input(messages))
        await self._run_agent_and_emit(ctx)

    @response_handler
    async def handle_user_input_response(
        self,
        original_request: Content,
        response: Content,
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Handle user input responses for function approvals during agent execution.

        This will hold the executor's execution until all pending user input requests are resolved.

        Args:
            original_request: The original function approval request sent by the agent.
            response: The user's response to the function approval request.
            ctx: The workflow context for emitting events and outputs.
        """
        self._pending_responses_to_agent.append(response)
        self._pending_agent_requests.pop(original_request.id, None)  # type: ignore[arg-type]

        if not self._pending_agent_requests:
            # All pending requests have been resolved; resume agent execution.
            # Use role="tool" for function_result responses (from declaration-only tools)
            # so the LLM receives proper tool results instead of orphaned tool_calls.
            role = "tool" if all(r.type == "function_result" for r in self._pending_responses_to_agent) else "user"
            self._cache = normalize_messages_input(Message(role=role, contents=self._pending_responses_to_agent))
            self._pending_responses_to_agent.clear()
            await self._run_agent_and_emit(ctx)

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Capture current executor state for checkpointing.

        NOTE: if the session uses service-side storage, the full session state
        may not be serialized locally.

        Returns:
            Dict containing serialized cache and session state
        """
        serialized_session = self._session.to_dict()

        return {
            "cache": self._cache,
            "full_conversation": self._full_conversation,
            "agent_session": serialized_session,
            "pending_agent_requests": self._pending_agent_requests,
            "pending_responses_to_agent": self._pending_responses_to_agent,
        }

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore executor state from checkpoint.

        Args:
            state: Checkpoint data dict
        """
        cache_payload = state.get("cache")
        self._cache = cache_payload or []

        full_conversation_payload = state.get("full_conversation")
        self._full_conversation = full_conversation_payload or []

        session_payload = state.get("agent_session")
        if session_payload:
            try:
                self._session = AgentSession.from_dict(session_payload)
            except Exception as exc:
                logger.warning("Failed to restore agent session: %s", exc)
                self._session = self._agent.create_session()
        else:
            self._session = self._agent.create_session()

        pending_requests_payload = state.get("pending_agent_requests")
        self._pending_agent_requests = pending_requests_payload or {}

        pending_responses_payload = state.get("pending_responses_to_agent")
        self._pending_responses_to_agent = pending_responses_payload or []

    def reset(self) -> None:
        """Reset the internal cache of the executor."""
        logger.debug("AgentExecutor %s: Resetting cache", self.id)
        self._cache.clear()

    async def _run_agent_and_emit(
        self,
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Execute the underlying agent, emit events, and enqueue response.

        Checks ctx.is_streaming() to determine whether to emit output events (type='output')
        containing incremental updates (streaming mode) or a single output event (type='output')
        containing the complete response (non-streaming mode).
        """
        if ctx.is_streaming():
            # Streaming mode: emit incremental updates
            response = await self._run_agent_streaming(cast(WorkflowContext[Never, AgentResponseUpdate], ctx))
        else:
            # Non-streaming mode: use run() and emit single event
            response = await self._run_agent(cast(WorkflowContext[Never, AgentResponse], ctx))

        # Snapshot current conversation as cache + latest agent outputs.
        # Do not append to prior snapshots: callers may provide full-history messages
        # in request.messages, and extending would duplicate prior turns.
        self._full_conversation = [*self._cache, *(list(response.messages) if response else [])]

        if response is None:
            # Agent did not complete (e.g., waiting for user input); do not emit response
            logger.info("AgentExecutor %s: Agent did not complete, awaiting user input", self.id)
            return

        agent_response = AgentExecutorResponse(self.id, response, full_conversation=self._full_conversation)
        await ctx.send_message(agent_response)
        self._cache.clear()

    async def _run_agent(self, ctx: WorkflowContext[Never, AgentResponse]) -> AgentResponse | None:
        """Execute the underlying agent in non-streaming mode.

        Args:
            ctx: The workflow context for emitting events.

        Returns:
            The complete AgentResponse, or None if waiting for user input.
        """
        function_invocation_kwargs, client_kwargs = self._prepare_agent_run_args(
            ctx.get_state(WORKFLOW_RUN_KWARGS_KEY, {})
        )

        if not self._cache:
            logger.warning(
                "AgentExecutor %s: Running agent with empty message cache. "
                "This could lead to service error for some LLM providers.",
                self.id,
            )

        run_agent = cast(Callable[..., Awaitable[AgentResponse[Any]]], self._agent.run)
        response = await run_agent(
            self._cache,
            stream=False,
            session=self._session,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        )
        await ctx.yield_output(response)

        # Handle any user input requests
        if response.user_input_requests:
            for user_input_request in response.user_input_requests:
                self._pending_agent_requests[user_input_request.id] = user_input_request  # type: ignore[index]
                await ctx.request_info(user_input_request, Content)
            return None

        return response

    async def _run_agent_streaming(self, ctx: WorkflowContext[Never, AgentResponseUpdate]) -> AgentResponse | None:
        """Execute the underlying agent in streaming mode and collect the full response.

        Args:
            ctx: The workflow context for emitting events.

        Returns:
            The complete AgentResponse, or None if waiting for user input.
        """
        function_invocation_kwargs, client_kwargs = self._prepare_agent_run_args(
            ctx.get_state(WORKFLOW_RUN_KWARGS_KEY, {})
        )

        if not self._cache:
            logger.warning(
                "AgentExecutor %s: Running agent with empty message cache. "
                "This could lead to service error for some LLM providers.",
                self.id,
            )

        updates: list[AgentResponseUpdate] = []
        streamed_user_input_requests: list[Content] = []
        run_agent_stream = cast(Callable[..., ResponseStream[AgentResponseUpdate, AgentResponse[Any]]], self._agent.run)
        stream = run_agent_stream(
            self._cache,
            stream=True,
            session=self._session,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        )
        async for update in stream:
            updates.append(update)
            await ctx.yield_output(update)
            if update.user_input_requests:
                streamed_user_input_requests.extend(update.user_input_requests)

        # Prefer stream finalization when available so result hooks run
        # (e.g., thread conversation updates). Fall back to reconstructing from updates
        # for legacy/custom agents that return a plain async iterable.
        # TODO(evmattso): Integrate workflow agent run handling around ResponseStream so
        # AgentExecutor does not need this conditional stream-finalization branch.
        maybe_get_final_response = getattr(stream, "get_final_response", None)
        get_final_response = maybe_get_final_response if callable(maybe_get_final_response) else None
        response: AgentResponse[Any]
        if get_final_response is not None:
            response = await cast(Callable[[], Awaitable[AgentResponse[Any]]], get_final_response)()
        elif is_chat_agent(self._agent):
            response_format = self._agent.default_options.get("response_format")
            response = AgentResponse.from_updates(
                updates,
                output_format_type=response_format,
            )
        else:
            response = AgentResponse.from_updates(updates)

        # Handle any user input requests after the streaming completes
        user_input_requests: list[Content] = []
        seen_request_ids: set[str] = set()
        for user_input_request in [*streamed_user_input_requests, *response.user_input_requests]:
            request_id = getattr(user_input_request, "id", None)
            if isinstance(request_id, str) and request_id:
                if request_id in seen_request_ids:
                    continue
                seen_request_ids.add(request_id)
            user_input_requests.append(user_input_request)

        if user_input_requests:
            for user_input_request in user_input_requests:
                self._pending_agent_requests[user_input_request.id] = user_input_request  # type: ignore[index]
                await ctx.request_info(user_input_request, Content)
            return None

        return response

    def _prepare_agent_run_args(
        self,
        raw_run_kwargs: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Prepare function_invocation_kwargs and client_kwargs for agent.run().

        Extracts ``function_invocation_kwargs`` and ``client_kwargs`` from the
        workflow state dict, resolving per-executor entries using ``self.id``. The
        ``__global__`` sentinel key (set by ``Workflow._resolve_invocation_kwargs``) denotes
        global kwargs that apply to all executors. Per-executor dicts use executor IDs as
        keys; this executor extracts only its own entry.

        Returns:
            A 2-tuple of (function_invocation_kwargs, client_kwargs).
        """
        fi_resolved = raw_run_kwargs.get("function_invocation_kwargs")
        ci_resolved = raw_run_kwargs.get("client_kwargs")

        function_invocation_kwargs = self._resolve_executor_kwargs(fi_resolved)
        client_kwargs = self._resolve_executor_kwargs(ci_resolved)

        return function_invocation_kwargs, client_kwargs

    def _resolve_executor_kwargs(self, resolved: dict[str, Any] | None) -> dict[str, Any] | None:
        """Extract this executor's kwargs from a resolved invocation kwargs dict.

        Args:
            resolved: The resolved dict produced by ``Workflow._resolve_invocation_kwargs``,
                containing either a ``__global__`` key (global kwargs) or executor-ID keys
                (per-executor kwargs). May also be ``None``.

        Returns:
            The kwargs for this executor, or ``None`` if not applicable.
        """
        if not isinstance(resolved, dict):
            return None
        # Use explicit key-presence checks so that an empty per-executor dict is
        # honoured (e.g. to clear kwargs) instead of falling through to global.
        if self.id in resolved:
            executor_kwargs = resolved[self.id]
        elif GLOBAL_KWARGS_KEY in resolved:
            executor_kwargs = resolved[GLOBAL_KWARGS_KEY]
        else:
            return None

        if not isinstance(executor_kwargs, dict):
            logger.warning(
                "Executor %s expected a dict for its kwargs, but got %s. Ignoring.",
                self.id,
                type(executor_kwargs),  # type: ignore
            )

            return None

        return executor_kwargs  # type: ignore
