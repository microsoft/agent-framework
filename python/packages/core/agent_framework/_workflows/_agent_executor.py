# Copyright (c) Microsoft. All rights reserved.

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from typing_extensions import Never

from agent_framework import Content

from .._agents import SupportsAgentRun
from .._sessions import AgentSession
from .._types import AgentResponse, AgentResponseUpdate, Message
from ._agent_utils import resolve_agent_id
from ._const import WORKFLOW_RUN_KWARGS_KEY
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
    full_conversation: list[Message] | None = None


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
    ):
        """Initialize the executor with a unique identifier.

        Args:
            agent: The agent to be wrapped by this executor.
            session: The session to use for running the agent. If None, a new session will be created.
            id: A unique identifier for the executor. If None, the agent's name will be used if available.
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
        # Replace cache with full conversation if available, else fall back to agent_response messages.
        if prior.full_conversation is not None:
            self._cache = list(prior.full_conversation)
        else:
            self._cache = list(prior.agent_response.messages)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_str(
        self, text: str, ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate]
    ) -> None:
        """Accept a raw user prompt string and run the agent (one-shot)."""
        self._cache = normalize_messages_input(text)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_message(
        self,
        message: Message,
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Accept a single Message as input."""
        self._cache = normalize_messages_input(message)
        await self._run_agent_and_emit(ctx)

    @handler
    async def from_messages(
        self,
        messages: list[str | Message],
        ctx: WorkflowContext[AgentExecutorResponse, AgentResponse | AgentResponseUpdate],
    ) -> None:
        """Accept a list of chat inputs (strings or Message) as conversation context."""
        self._cache = normalize_messages_input(messages)
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
        # Check if using AzureAIAgentClient with server-side session and warn about checkpointing limitations
        if is_chat_agent(self._agent) and self._session.service_session_id is not None:
            client_class_name = self._agent.client.__class__.__name__
            client_module = self._agent.client.__class__.__module__

            if client_class_name == "AzureAIAgentClient" and "azure_ai" in client_module:
                logger.warning(
                    "Checkpointing an AgentExecutor with AzureAIAgentClient that uses server-side sessions. "
                    "Currently, checkpointing does not capture messages from server-side sessions "
                    "(service_session_id: %s). The session state in checkpoints is not immutable and can be "
                    "modified by subsequent runs. If you need reliable checkpointing with Azure AI agents, "
                    "consider implementing a custom executor and managing the session state yourself.",
                    self._session.service_session_id,
                )

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
        if cache_payload:
            try:
                self._cache = cache_payload
            except Exception as exc:
                logger.warning("Failed to restore cache: %s", exc)
                self._cache = []
        else:
            self._cache = []

        full_conversation_payload = state.get("full_conversation")
        if full_conversation_payload:
            try:
                self._full_conversation = full_conversation_payload
            except Exception as exc:
                logger.warning("Failed to restore full conversation: %s", exc)
                self._full_conversation = []
        else:
            self._full_conversation = []

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
        if pending_requests_payload:
            self._pending_agent_requests = pending_requests_payload

        pending_responses_payload = state.get("pending_responses_to_agent")
        if pending_responses_payload:
            self._pending_responses_to_agent = pending_responses_payload

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
        self._full_conversation = list(self._cache) + (list(response.messages) if response else [])

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
        run_kwargs, options = self._prepare_agent_run_args(ctx.get_state(WORKFLOW_RUN_KWARGS_KEY, {}))

        response = await self._agent.run(
            self._cache,
            stream=False,
            session=self._session,
            options=options,
            **run_kwargs,
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
        run_kwargs, options = self._prepare_agent_run_args(ctx.get_state(WORKFLOW_RUN_KWARGS_KEY) or {})

        updates: list[AgentResponseUpdate] = []
        streamed_user_input_requests: list[Content] = []
        stream = self._agent.run(
            self._cache,
            stream=True,
            session=self._session,
            options=options,
            **run_kwargs,
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

    @staticmethod
    def _prepare_agent_run_args(raw_run_kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Prepare kwargs and options for agent.run(), avoiding duplicate option passing.

        Workflow-level kwargs are propagated to tool calls through
        `options.additional_function_arguments`. If workflow kwargs include an
        `options` key, merge it into the final options object and remove it from
        kwargs before spreading `**run_kwargs`.
        """
        run_kwargs = dict(raw_run_kwargs)
        options_from_workflow = run_kwargs.pop("options", None)
        workflow_additional_args = run_kwargs.pop("additional_function_arguments", None)

        options: dict[str, Any] = {}
        if options_from_workflow is not None:
            if isinstance(options_from_workflow, Mapping):
                for key, value in options_from_workflow.items():
                    if isinstance(key, str):
                        options[key] = value
            else:
                logger.warning(
                    "Ignoring non-mapping workflow 'options' kwarg of type %s for AgentExecutor %s.",
                    type(options_from_workflow).__name__,
                    AgentExecutor.__name__,
                )

        existing_additional_args = options.get("additional_function_arguments")
        if isinstance(existing_additional_args, Mapping):
            additional_args = {key: value for key, value in existing_additional_args.items() if isinstance(key, str)}
        else:
            additional_args = {}

        if workflow_additional_args is not None:
            if isinstance(workflow_additional_args, Mapping):
                additional_args.update({
                    key: value for key, value in workflow_additional_args.items() if isinstance(key, str)
                })
            else:
                logger.warning(
                    "Ignoring non-mapping workflow 'additional_function_arguments' kwarg of type %s for AgentExecutor %s.",  # noqa: E501
                    type(workflow_additional_args).__name__,
                    AgentExecutor.__name__,
                )

        if run_kwargs:
            additional_args.update(run_kwargs)

        if additional_args:
            options["additional_function_arguments"] = additional_args

        return run_kwargs, options or None
