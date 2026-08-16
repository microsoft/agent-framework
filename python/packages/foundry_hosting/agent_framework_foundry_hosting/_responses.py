# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from collections.abc import AsyncIterable, AsyncIterator, Generator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from dataclasses import asdict, dataclass, is_dataclass
from typing import Literal, cast

from agent_framework import (
    ChatOptions,
    CheckpointStorage,
    Content,
    ContextProvider,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    SessionStore,
    SupportsAgentRun,
    WorkflowAgent,
)
from agent_framework._telemetry import mark_feature_used
from agent_framework.exceptions import AgentFrameworkException
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.responses import (
    ResponseContext,
    ResponseProviderProtocol,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses._id_generator import IdGenerator
from azure.ai.agentserver.responses.aio import ResponseEventStream
from azure.ai.agentserver.responses.hosting import ResponsesAgentServerHost
from azure.ai.agentserver.responses.models import (
    CreateResponse,
    FunctionShellAction,
    FunctionShellCallOutputContent,
    FunctionShellCallOutputExitOutcome,
    Item,
    ItemReasoningItem,
    LocalEnvironmentResource,
    MessageContent,
    OAuthConsentRequestOutputItem,
    OutputItem,
    OutputItemReasoningItem,
    OutputMessageContent,
    ResponseStreamEvent,
)
from azure.ai.agentserver.responses.streaming._builders import (
    OutputItemBuilder,
    OutputItemFunctionCallBuilder,
    OutputItemMcpCallBuilder,
    OutputItemMessageBuilder,
    ReasoningSummaryPartBuilder,
    TextContentBuilder,
)
from mcp import McpError
from typing_extensions import Any

from ._feature_usage import FeatureIndex
from ._state_store import (
    AgentSessionStoreProvider,
    CheckpointStoreProvider,
    ContextScopedStoreProvider,
    FunctionApprovalStore,
    FunctionApprovalStoreProvider,
    StoreProvider,
)

logger = logging.getLogger(__name__)

_HOSTED_RESPONSES_HISTORY_SOURCE_ID = "_foundry_responses_history"


def _validate_checkpoint_context_id(context_id: str) -> None:
    """Validate that a checkpoint context ID is a single safe path component in case file-based storage is used."""
    if (
        not context_id
        or "/" in context_id
        or "\\" in context_id
        or "\x00" in context_id
        or context_id.strip(".") == ""
        or os.path.isabs(context_id)
        or os.path.splitdrive(context_id)[0]
    ):
        raise RuntimeError(f"Invalid context id: {context_id!r}")


def _is_hosted_responses_history_sentinel(provider: ContextProvider) -> bool:
    """Return whether ``provider`` is the host's transient history buffer."""
    return (
        isinstance(provider, InMemoryHistoryProvider)
        and provider.source_id == _HOSTED_RESPONSES_HISTORY_SOURCE_ID
        and provider.load_messages
        and provider.store_inputs
        and not provider.store_context_messages
        and provider.store_outputs
    )


# Foundry Toolbox Auth integration
# Consent-URL error code returned by the Foundry MCP gateway when calling `/list`
CONSENT_ERROR_CODE = -32006


@dataclass
class ConsentError:
    name: str
    consent_url: str


def consent_url_from_error(exc: BaseException) -> list[ConsentError] | None:
    """Return the consent URLs when ``exc`` wraps Foundry MCP gateway consent errors.

    Args:
        exc: The exception to inspect.

    Returns:
        The consent URL(s) extracted from the error, or ``None`` if no consent error was found.
    """
    inner_exception = next((arg for arg in exc.args if isinstance(arg, McpError)), None)
    if inner_exception is not None and inner_exception.error.code == CONSENT_ERROR_CODE:
        # Parse the error message
        # The error message is structured with the following format:
        # "tools/list failed for 1 tool source(s), succeeded for 0 tool source(s) {"errors":[{"name": ..."
        # where the second part is a JSON string that can be deserialized into an object with the following shape:
        # ruff: disable[commented-out-code]
        # {
        #   "errors" : [
        #       {
        #           "name": "Name of the MCP tool that requires consent",
        #           "type" : "mcp",
        #           "error": {
        #               "code": "CONSENT_REQUIRED",
        #               "message": consent_url,
        #           }
        #       }
        #   ]
        # }
        # ruff: enable[commented-out-code]
        try:
            consent_errors: list[ConsentError] = []
            error_message_start = inner_exception.error.message.find("{")
            if error_message_start == -1:
                logger.warning("Consent error message does not contain JSON: %s", inner_exception.error.message)
                return None
            consent_details_json = inner_exception.error.message[error_message_start:]
            consent_details = json.loads(consent_details_json)
            if "errors" not in consent_details or not isinstance(consent_details["errors"], list):
                logger.warning("Consent error message JSON does not contain 'errors' list: %s", consent_details_json)
                return None
            for error in consent_details["errors"]:
                if (
                    isinstance(error, dict)
                    and error.get("type") == "mcp"  # type: ignore
                    and "error" in error
                    and isinstance(error["error"], dict)
                    and error["error"].get("code") == "CONSENT_REQUIRED"  # type: ignore
                    and "message" in error["error"]
                ):
                    consent_url = error["error"]["message"]  # type: ignore
                    if isinstance(consent_url, str):
                        consent_errors.append(ConsentError(name=error.get("name", "Unknown"), consent_url=consent_url))  # type: ignore
                    else:
                        logger.warning("Consent URL in error message is not a valid URL: %s", consent_url)  # type: ignore
            if consent_errors:
                return consent_errors
        except json.JSONDecodeError:
            logger.warning("Failed to parse consent details JSON: %s", inner_exception.error.message)
    return None


# endregion Foundry Toolbox Auth integration


# region ResponsesHostServer
class ResponsesHostServer(ResponsesAgentServerHost):
    """A responses server host for an agent."""

    def __init__(
        self,
        agent: SupportsAgentRun,
        *,
        prefix: str = "",
        options: ResponsesServerOptions | None = None,
        store: ResponseProviderProtocol | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage] | None = None,
        function_approval_store_provider: StoreProvider[FunctionApprovalStore] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for.
            prefix: The URL prefix for the server.
            options: Optional server options.
            store: Optional response store for input and history look up.
            agent_session_store_provider: Optional provider for MAF agent session storage.
                If not provided, a default `AgentSessionStoreProvider` will be used.
            checkpoint_store_provider: Optional provider for workflow checkpoint storage.
                If not provided, a default `CheckpointStoreProvider` will be used.
            function_approval_store_provider: Optional provider for function approval storage.
                If not provided, a default `FunctionApprovalStoreProvider` will be used.
            **kwargs: Additional keyword arguments.

        Note:
            1. The agent must not have a history provider with `load_messages=True`,
               because history is managed by the hosting infrastructure.
            2. The agent must not have any context providers that maintain context
               in memory, because the hosting environment may get deactivated between
               requests, and any in-memory context would be lost.
        """
        super().__init__(prefix=prefix, options=options, store=store, **kwargs)

        for provider in getattr(agent, "context_providers", []):
            if isinstance(provider, HistoryProvider) and provider.load_messages:
                if _is_hosted_responses_history_sentinel(provider):
                    continue
                raise RuntimeError(
                    "There shouldn't be a history provider with `load_messages=True` already present. "
                    "History is managed by the hosting infrastructure."
                )
            provider = cast(ContextProvider, provider)
            logger.warning(
                "Context provider %s is present. If it maintains context in memory, "
                "the context may be lost between requests. Use with caution.",
                provider.source_id,
            )

        self._is_workflow_agent = False
        if isinstance(agent, WorkflowAgent):
            if agent.workflow._runner_context.has_checkpointing():  # pyright: ignore[reportPrivateUsage]
                raise RuntimeError(
                    "There should not be a checkpoint storage already present in the workflow agent. "
                    "The hosting infrastructure will manage checkpoints instead."
                )
            self._is_workflow_agent = True

        self._uses_hosted_responses_history = False
        if not self._is_workflow_agent and isinstance(agent, RawAgent):
            self._uses_hosted_responses_history = True
            if not any(
                _is_hosted_responses_history_sentinel(provider)
                for provider in cast(Sequence[ContextProvider], agent.context_providers)
            ):
                # The Responses provider already supplies the complete transcript on every
                # call. Agent.run would otherwise mutate the same user-owned agent by
                # auto-injecting its default InMemoryHistoryProvider. Install a transient
                # buffer that carries history within a function-call loop, then discard its
                # state before persisting the session so the transcript is not replayed twice.
                agent.context_providers.append(
                    InMemoryHistoryProvider(
                        source_id=_HOSTED_RESPONSES_HISTORY_SOURCE_ID,
                    )
                )

        self._agent: SupportsAgentRun = agent

        # Storage providers
        self._checkpoint_storage_provider = (
            CheckpointStoreProvider() if checkpoint_store_provider is None else checkpoint_store_provider
        )
        self._session_storage_provider = (
            AgentSessionStoreProvider() if agent_session_store_provider is None else agent_session_store_provider
        )
        self._function_approval_storage_provider = (
            FunctionApprovalStoreProvider()
            if function_approval_store_provider is None
            else function_approval_store_provider
        )

        # Lazy agent lifecycle: the agent (and any MCP tools it owns) is entered on
        # the first request rather than at server startup, so that authentication
        # failures during MCP connect can be surfaced to the client as an
        # `oauth_consent_request` stream event instead of crashing the server.
        self._agent_stack: AsyncExitStack | None = None
        self._agent_init_lock = asyncio.Lock()

        self.shutdown_handler(self._cleanup_agent)
        self.response_handler(self._handle_response)

        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    async def _ensure_agent_ready(self) -> None:
        """Lazily enter the agent's async context exactly once.

        On failure the partial exit stack is closed and ``_agent_stack`` is left
        as ``None`` so a subsequent request (e.g. after the user completes OAuth
        consent) can retry the connection.
        """
        if self._agent_stack is not None:
            return
        async with self._agent_init_lock:
            if self._agent_stack is not None:
                return
            stack = AsyncExitStack()
            try:
                if isinstance(self._agent, AbstractAsyncContextManager):
                    await stack.enter_async_context(cast(AbstractAsyncContextManager[Any], self._agent))
            except BaseException:
                await stack.aclose()
                raise
            self._agent_stack = stack

    async def _cleanup_agent(self) -> None:
        """Close the agent's async context. Registered as the server shutdown handler."""
        stack = self._agent_stack
        if stack is not None:
            self._agent_stack = None
            await stack.aclose()

    async def _handle_response(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response."""
        if self._is_workflow_agent:
            # Workflow agents are handled differently because they require checkpoint restoration
            return self._handle_inner_workflow(request, context)
        return self._handle_inner_agent(request, context)

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle a regular agent with Responses-managed MAF session continuity.

        Conversation mode reads and writes one MAF session snapshot under
        ``conversation_id``. Response chaining reads the snapshot under
        ``previous_response_id`` and writes the updated session under the current
        ``response_id``, allowing branches without changing the MAF session's own
        identifier. Hosted storage uses the request user as its isolation boundary.
        """
        response_event_stream = ResponseEventStream(response_id=context.response_id)
        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        # Lazy-enter the agent (and any MCP tools it owns). The MCP client wraps gateway
        # consent failures (and other connection-time errors) in AgentFrameworkException; if
        # one of those is a consent error we surface the consent link to the client through
        # the already-opened response stream instead of failing the request. Other exception
        # types fall through to the outer handler below and become ``response.failed``.
        try:
            await self._ensure_agent_ready()
        except AgentFrameworkException as ex:
            consent_errors_to_emit = consent_url_from_error(ex)
            if consent_errors_to_emit is None or len(consent_errors_to_emit) == 0:
                logger.error("Failed to prepare agent: %s", ex, exc_info=(type(ex), ex, ex.__traceback__))
                for event in self._emit_failure(response_event_stream, None, ex):
                    yield event
                return

            for consent_error in consent_errors_to_emit:
                logger.warning("Consent URL for tool '%s': %s", consent_error.name, consent_error.consent_url)
                oauth_item = OAuthConsentRequestOutputItem(
                    id=IdGenerator.new_id("oacr"),
                    response_id=context.response_id,
                    type="oauth_consent_request",
                    consent_link=consent_error.consent_url,
                    server_label=consent_error.name,
                )
                builder = response_event_stream.add_output_item(oauth_item["id"])
                yield builder.emit_added(oauth_item)
                yield builder.emit_done(oauth_item)

            yield response_event_stream.emit_incomplete(
                reason=f"OAuth consent required for {len(consent_errors_to_emit)} tool(s)."
            )
            return

        try:
            request_context = get_request_context()
            approval_storage = self._function_approval_storage_provider.get_store(
                config=self.config, platform_context=request_context
            )
            session_storage = self._session_storage_provider.get_store(
                config=self.config, platform_context=request_context
            )

            previous_response_id = request.get("previous_response_id")
            session_load_id = context.conversation_id or previous_response_id
            session = await session_storage.get(session_load_id) if session_load_id is not None else None
            if session is None:
                if previous_response_id is not None and context.conversation_id is None:
                    raise RuntimeError(
                        f"Cannot find an existing agent session for previous_response_id={previous_response_id}."
                    )
                session = self._agent.create_session()
            session_save_id = context.conversation_id or context.response_id
        except Exception as ex:
            logger.error("Failed to prepare state storage: %s", ex, exc_info=(type(ex), ex, ex.__traceback__))
            for event in self._emit_failure(response_event_stream, None, ex):
                yield event
            return

        tracker = _OutputItemTracker(response_event_stream)
        request_failure: Exception | None = None
        save_failure: Exception | None = None
        request_interrupted = False

        try:
            if self._uses_hosted_responses_history:
                session.state.pop(_HOSTED_RESPONSES_HISTORY_SOURCE_ID, None)

            input_items = await context.get_input_items()
            input_messages = await _items_to_messages(input_items, approval_storage=approval_storage)

            history = await context.get_history()
            run_kwargs: dict[str, Any] = {
                "messages": [
                    *(await _output_items_to_messages(history, approval_storage=approval_storage)),
                    *input_messages,
                ],
                "session": session,
            }
            chat_options, are_options_set = _to_chat_options(request)

            if are_options_set and not isinstance(self._agent, RawAgent):
                logger.warning("Agent doesn't support runtime options. They will be ignored.")
            else:
                run_kwargs["options"] = chat_options

            async for update in self._agent.run(stream=True, **run_kwargs):  # type: ignore[reportUnknownMemberType]
                for content in update.contents:
                    for event in tracker.handle(content):
                        yield event
                    if tracker.needs_async:
                        async for item in _to_outputs(
                            response_event_stream,
                            content,
                            approval_storage=approval_storage,
                        ):
                            yield item
                        tracker.needs_async = False
            for event in tracker.close():
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            request_interrupted = True
            raise
        except Exception as ex:
            request_failure = ex
            logger.error(
                "Failed to produce response for agent",
                exc_info=(type(ex), ex, ex.__traceback__),
            )
        finally:
            if self._uses_hosted_responses_history:
                session.state.pop(_HOSTED_RESPONSES_HISTORY_SOURCE_ID, None)
            try:
                await session_storage.set(session_save_id, session)
            except Exception as save_error:
                save_failure = save_error
                if request_interrupted:
                    message = "Failed to persist the Agent Framework session while unwinding an interrupted request"
                elif request_failure is not None:
                    message = "Failed to persist the Agent Framework session after an agent failure"
                else:
                    message = "Failed to persist the Agent Framework session after a successful request"
                logger.error(message, exc_info=(type(save_error), save_error, save_error.__traceback__))

        if request_failure is not None and save_failure is not None:
            failure = RuntimeError(
                f"Agent request failed: {str(request_failure) or type(request_failure).__name__}; "
                f"session persistence also failed: {str(save_failure) or type(save_failure).__name__}"
            )
            for event in self._emit_failure(response_event_stream, tracker, failure):
                yield event
        elif request_failure is not None:
            for event in self._emit_failure(response_event_stream, tracker, request_failure):
                yield event
        elif save_failure is not None:
            for event in self._emit_failure(response_event_stream, tracker, save_failure):
                yield event
        else:
            yield response_event_stream.emit_completed()

    async def _handle_inner_workflow(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response for a workflow agent."""
        response_event_stream = ResponseEventStream(response_id=context.response_id)
        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        # Track the current active output item builder for streaming;
        # lazily created on matching content, closed when a different type arrives.
        tracker: _OutputItemTracker | None = None

        try:
            request_context = get_request_context()
            approval_storage = self._function_approval_storage_provider.get_store(
                config=self.config, platform_context=request_context
            )
            input_items = await context.get_input_items()
            input_messages = await _items_to_messages(input_items, approval_storage=approval_storage)

            _, are_options_set = _to_chat_options(request)
            if are_options_set:
                logger.warning("Workflow agent doesn't support runtime options. They will be ignored.")

            if not isinstance(self._agent, WorkflowAgent):
                raise RuntimeError("Agent is not a workflow agent.")

            # Workflow agents are not async context managers in any built-in path,
            # but call _ensure_agent_ready for symmetry with the regular path so
            # any future async resources owned by the workflow are entered here.
            await self._ensure_agent_ready()

            checkpoint_save_id = context.conversation_id or context.response_id
            _validate_checkpoint_context_id(checkpoint_save_id)
            checkpoint_storage = self._checkpoint_storage_provider.get_store(
                config=self.config,
                context_id=checkpoint_save_id,
                platform_context=request_context,
            )

            # Determine the latest checkpoint (if any) so we can resume the
            # workflow's prior state for this turn. The directory is keyed by
            # the platform derived context_id. Multi-turn declarative workflows
            # need the workflow's internal state (e.g. Conversation.messages,
            # intermediate Local.* variables) to survive across user turns;
            # the only place that state lives is the workflow checkpoint, so
            # on every turn we restore the latest checkpoint and feed the new
            # input back into the start executor as a continuation rather than
            # a fresh run.
            if request.get("previous_response_id") is not None and context.conversation_id is not None:
                raise RuntimeError("Previous response ID cannot be used in conjunction with conversation ID.")
            previous_response_id = request.get("previous_response_id")
            checkpoint_load_id = context.conversation_id or previous_response_id
            latest_checkpoint = None
            restore_checkpoint_storage = checkpoint_storage
            if checkpoint_load_id is not None:
                _validate_checkpoint_context_id(checkpoint_load_id)
                if checkpoint_load_id != checkpoint_save_id:
                    restore_checkpoint_storage = self._checkpoint_storage_provider.get_store(
                        config=self.config,
                        context_id=checkpoint_load_id,
                        platform_context=request_context,
                    )
                latest_checkpoint = await restore_checkpoint_storage.get_latest(workflow_name=self._agent.workflow.name)
                if latest_checkpoint is None and previous_response_id is not None:
                    raise RuntimeError(
                        f"Cannot find an existing workflow checkpoint for previous_response_id={previous_response_id}."
                    )

            # Multi-turn pattern: when we have a prior checkpoint, restore it
            # first (drive the workflow back to idle with prior state intact),
            # then make a separate call that delivers the new user input. This
            # depends on Workflow.run preserving shared state across calls. The
            # restore-only call may yield events from any pending in-flight
            # work in the checkpoint; we consume those internally here so they
            # don't surface to the response stream as duplicates.
            #
            # If the restored checkpoint had pending request_info events, the
            # restore-only call replays them through
            # ``WorkflowAgent._convert_workflow_event_to_agent_response_updates``
            # and populates ``self._agent.pending_requests``. That is the correct
            # state: those requests are genuinely outstanding, and the next
            # ``run(input_messages, ...)`` call may contain ``function_call_output``
            # items (carried as FunctionResult/FunctionApprovalResponse content)
            # that fulfill them via :meth:`WorkflowAgent._process_pending_requests`.
            if latest_checkpoint is not None:
                async for _ in self._agent.run(
                    stream=True,
                    checkpoint_id=latest_checkpoint.checkpoint_id,
                    checkpoint_storage=restore_checkpoint_storage,
                ):
                    pass

            tracker = _OutputItemTracker(response_event_stream)

            # Run the workflow agent in streaming mode with the new user input.
            async for update in self._agent.run(
                input_messages,
                stream=True,
                checkpoint_storage=checkpoint_storage,
            ):
                for content in update.contents:
                    for event in tracker.handle(content):
                        yield event
                    if tracker.needs_async:
                        async for item in _to_outputs(
                            response_event_stream, content, approval_storage=approval_storage
                        ):
                            yield item
                        tracker.needs_async = False

            # Close any remaining active builder
            for event in tracker.close():
                yield event
            yield response_event_stream.emit_completed()
        except Exception as ex:
            logger.exception("Failed to produce response for workflow agent")
            for event in self._emit_failure(response_event_stream, tracker, ex):
                yield event

    @staticmethod
    def _emit_failure(
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker | None,
        ex: BaseException,
    ) -> Generator[ResponseStreamEvent]:
        """Yield a terminal ``response.failed`` event for ``ex``.

        Drains any in-progress streaming output item first so the resulting
        SSE stream stays well-formed, then emits ``response.failed`` carrying
        the exception's message (falling back to the exception type name when
        ``str(ex)`` is empty). Any error raised while draining the tracker is
        logged and otherwise ignored so that the original failure is always
        what the client sees.
        """
        if tracker is not None:
            try:
                yield from tracker.close()
            except Exception:
                logger.exception("Error while closing streaming tracker after failure")
        message = str(ex) or type(ex).__name__
        yield response_event_stream.emit_failed(message=message)


# endregion ResponsesHostServer

# region Active Builder State


class _OutputItemTracker:
    """Tracks the current active output item builder during streaming.

    Handles lazy creation, delta emission, and closing of streaming builders
    for text messages, reasoning, function calls, and MCP calls.
    """

    _DELTA_TYPES = frozenset({"text", "text_reasoning", "function_call", "mcp_server_tool_call"})

    def __init__(self, stream: ResponseEventStream) -> None:
        self._stream = stream
        self._active_type: str | None = None
        self._active_id: str | None = None
        # Accumulated delta text for the current active builder
        self._accumulated: list[str] = []
        # Builder state — only one is active at a time
        self._message_item: OutputItemMessageBuilder | None = None
        self._text_content: TextContentBuilder | None = None
        self._reasoning_item: OutputItemBuilder | None = None
        self._summary_part: ReasoningSummaryPartBuilder | None = None
        self._reasoning_encrypted_content: str | None = None
        self._fc_builder: OutputItemFunctionCallBuilder | None = None
        self._mcp_builder: OutputItemMcpCallBuilder | None = None
        self._outstanding_function_calls: dict[str, str | None] = {}
        self.needs_async = False

    def handle(self, content: Content) -> Generator[ResponseStreamEvent]:
        """Process a content item, yielding sync events.

        Sets ``needs_async = True`` if the caller must also drain an
        async ``_to_outputs`` call for this content.
        """
        if content.type == "text" and content.text is not None:
            if self._active_type != "text":
                yield from self._close()
                yield from self._open_message()
            self._accumulated.append(content.text)
            if self._text_content is not None:
                yield self._text_content.emit_delta(content.text)

        elif content.type == "text_reasoning":
            if self._active_type != "text_reasoning" or (content.id is not None and content.id != self._active_id):
                yield from self._close()
                yield from self._open_reasoning(content)
            if encrypted_content := _reasoning_encrypted_content(content):
                self._reasoning_encrypted_content = encrypted_content
            if content.text:
                self._accumulated.append(content.text)
                if self._summary_part is not None:
                    yield self._summary_part.emit_text_delta(content.text)

        elif content.type == "function_call" and content.call_id is not None:
            # Declaration-only calls replay request metadata after the streamed call. Scope suppression to the
            # outstanding occurrence because a call_id may be reused after its terminal result.
            if (
                content.user_input_request
                and content.arguments is None
                and content.call_id in self._outstanding_function_calls
                and self._outstanding_function_calls[content.call_id] == content.name
            ):
                return
            if self._active_type != "function_call" or self._active_id != content.call_id:
                yield from self._close()
                yield from self._open_function_call(content)
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._fc_builder is not None:
                yield self._fc_builder.emit_arguments_delta(args_str)

        elif content.type == "function_result":
            yield from self._close()
            if content.call_id is not None:
                self._outstanding_function_calls.pop(content.call_id, None)
            self.needs_async = True

        elif content.type == "mcp_server_tool_call" and content.tool_name:
            key = content.call_id or f"{content.server_name or 'default'}::{content.tool_name}"
            if self._active_type != "mcp_server_tool_call" or self._active_id != key:
                yield from self._close()
                yield from self._open_mcp_call(content)
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._mcp_builder is not None:
                yield self._mcp_builder.emit_arguments_delta(args_str)

        elif (
            content.type == "mcp_server_tool_result"
            and self._active_type == "mcp_server_tool_call"
            and self._mcp_builder is not None
            and content.call_id is not None
            and content.call_id == self._mcp_builder.item_id
        ):
            accumulated = "".join(self._accumulated)
            yield self._mcp_builder.emit_arguments_done(accumulated)
            yield self._mcp_builder.emit_completed()
            yield self._mcp_builder.emit_done(output=_stringify_mcp_output(content.output))
            self._mcp_builder = None
            self._active_type = None
            self._active_id = None
            self._accumulated.clear()
            self.needs_async = False
            return

        else:
            yield from self._close()
            self.needs_async = True

    def close(self) -> Generator[ResponseStreamEvent]:
        """Close any remaining active builder."""
        yield from self._close()

    # -- Private open/close helpers --

    def _open_message(self) -> Generator[ResponseStreamEvent]:
        self._message_item = self._stream.add_output_item_message()
        self._text_content = self._message_item.add_text_content()
        self._active_type = "text"
        self._active_id = None
        yield self._message_item.emit_added()
        yield self._text_content.emit_added()

    def _open_reasoning(self, content: Content) -> Generator[ResponseStreamEvent]:
        item_id = content.id
        if not item_id or not IdGenerator.is_valid(item_id)[0]:
            item_id = IdGenerator.new_id("rs")
        self._reasoning_item = self._stream.add_output_item(item_id)
        self._summary_part = ReasoningSummaryPartBuilder(
            self._stream,
            self._reasoning_item.output_index,
            0,
            item_id,
        )
        self._reasoning_encrypted_content = _reasoning_encrypted_content(content)
        self._active_type = "text_reasoning"
        self._active_id = item_id
        yield self._reasoning_item.emit_added(
            _reasoning_output_item(
                item_id=item_id,
                summary_texts=[],
                encrypted_content=None,
                status="in_progress",
            )
        )
        yield self._summary_part.emit_added()

    def _open_function_call(self, content: Content) -> Generator[ResponseStreamEvent]:
        self._fc_builder = self._stream.add_output_item_function_call(
            name=content.name or "",
            call_id=content.call_id or "",
        )
        self._active_type = "function_call"
        self._active_id = content.call_id
        self._outstanding_function_calls[content.call_id or ""] = content.name
        yield self._fc_builder.emit_added()

    def _open_mcp_call(self, content: Content) -> Generator[ResponseStreamEvent]:
        self._mcp_builder = self._stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
            item_id=content.call_id,
        )
        self._active_type = "mcp_server_tool_call"
        self._active_id = content.call_id or f"{content.server_name or 'default'}::{content.tool_name}"
        yield self._mcp_builder.emit_added()

    def _close(self) -> Generator[ResponseStreamEvent]:
        accumulated = "".join(self._accumulated)

        if self._active_type == "text" and self._text_content and self._message_item:
            yield self._text_content.emit_text_done(accumulated)
            yield self._text_content.emit_done()
            yield self._message_item.emit_done()
            self._text_content = None
            self._message_item = None

        elif self._active_type == "text_reasoning" and self._summary_part and self._reasoning_item:
            yield self._summary_part.emit_text_done(accumulated)
            yield self._summary_part.emit_done()
            yield self._reasoning_item.emit_done(
                _reasoning_output_item(
                    item_id=self._reasoning_item.item_id,
                    summary_texts=[accumulated],
                    encrypted_content=self._reasoning_encrypted_content,
                    status="completed",
                )
            )
            self._summary_part = None
            self._reasoning_item = None
            self._reasoning_encrypted_content = None

        elif self._active_type == "function_call" and self._fc_builder:
            yield self._fc_builder.emit_arguments_done(accumulated)
            yield self._fc_builder.emit_done()
            self._fc_builder = None

        elif self._active_type == "mcp_server_tool_call" and self._mcp_builder:
            yield self._mcp_builder.emit_arguments_done(accumulated)
            yield self._mcp_builder.emit_completed()
            yield self._mcp_builder.emit_done()
            self._mcp_builder = None

        self._active_type = None
        self._active_id = None
        self._accumulated.clear()


# endregion


# region Option Conversion


def _to_chat_options(request: CreateResponse) -> tuple[ChatOptions, bool]:
    """Converts a CreateResponse request to ChatOptions.

    Args:
        request (CreateResponse): The request to convert.

    Returns:
        ChatOptions: The converted ChatOptions.
        bool: Whether any options were set.

    """
    chat_options = ChatOptions()
    are_options_set = False

    if (temperature := request.get("temperature")) is not None:
        chat_options["temperature"] = temperature
        are_options_set = True
    if (top_p := request.get("top_p")) is not None:
        chat_options["top_p"] = top_p
        are_options_set = True
    if (max_output_tokens := request.get("max_output_tokens")) is not None:
        chat_options["max_tokens"] = max_output_tokens
        are_options_set = True
    if (parallel_tool_calls := request.get("parallel_tool_calls")) is not None:
        chat_options["allow_multiple_tool_calls"] = parallel_tool_calls
        are_options_set = True

    return chat_options, are_options_set


# endregion


# region Input Message Conversion


async def _items_to_messages(
    input_items: Sequence[Item], *, approval_storage: FunctionApprovalStore | None = None
) -> list[Message]:
    """Converts a sequence of input items to a list of Messages, one per item.

    Args:
        input_items: The input items to convert.
        approval_storage: An optional ApprovalStorage instance used to look up
            approval requests when converting MCP approval response items.

    Returns:
        A list of Messages, one per supported input item.
    """
    messages: list[Message] = []
    for item in input_items:
        messages.append(await _item_to_message(item, approval_storage=approval_storage))
    return messages


def _reasoning_item_to_contents(reasoning: ItemReasoningItem | OutputItemReasoningItem) -> list[Content]:
    """Convert a hosted reasoning item without losing its stateless replay metadata."""
    encrypted_content = reasoning.get("encrypted_content")
    if summary_parts := reasoning.get("summary"):
        return [
            Content.from_text_reasoning(
                id=reasoning["id"],
                text=summary["text"],
                protected_data=encrypted_content if index == 0 else None,
            )
            for index, summary in enumerate(summary_parts)
        ]
    return [Content.from_text_reasoning(id=reasoning["id"], protected_data=encrypted_content)]


async def _item_to_message(item: Item, *, approval_storage: FunctionApprovalStore | None = None) -> Message:
    """Converts an Item to a Message.

    Args:
        item: The Item to convert.
        approval_storage: An optional ApprovalStorage instance used to look up
            approval requests when converting MCP approval response items.

    Returns:
        The converted Message.

    Raises:
        ValueError: If the Item type is not supported.
    """
    if item["type"] == "message":
        if isinstance(item["content"], str):
            return Message(role=item["role"], contents=[Content.from_text(item["content"])])
        return Message(role=item["role"], contents=[_convert_message_content(part) for part in item["content"]])

    if item["type"] == "output_message":
        return Message(role=item["role"], contents=[_convert_output_message_content(part) for part in item["content"]])

    if item["type"] == "function_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    item["name"],
                    arguments=item["arguments"],
                )
            ],
        )

    if item["type"] == "function_call_output":
        output = item["output"] if isinstance(item["output"], str) else str(item["output"])
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=output)],
        )

    if item["type"] == "reasoning":
        return Message(role="assistant", contents=_reasoning_item_to_contents(item))

    if item["type"] == "mcp_call":
        contents = [
            Content.from_mcp_server_tool_call(
                item["id"],
                item["name"],
                server_name=item["server_label"],
                arguments=item["arguments"],
            )
        ]
        if (output := item.get("output")) is not None:
            contents.append(Content.from_mcp_server_tool_result(call_id=item["id"], output=output))
        return Message(
            role="assistant",
            contents=contents,
        )

    if item["type"] == "mcp_approval_request":
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(item["id"])
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")
        return Message(
            role="assistant",
            contents=[function_approval_request_content],
        )

    if item["type"] == "mcp_approval_response":
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(
                item["approval_request_id"]
            )
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")
        return Message(
            role="user",
            contents=[function_approval_request_content.to_function_approval_response(item["approve"])],
        )

    if item["type"] == "code_interpreter_call":
        return Message(
            role="assistant",
            contents=[Content.from_code_interpreter_tool_call(call_id=item["id"])],
        )

    if item["type"] == "image_generation_call":
        return Message(
            role="assistant",
            contents=[Content.from_image_generation_tool_call(image_id=item["id"])],
        )

    if item["type"] == "shell_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=item["call_id"],
                    commands=item["action"]["commands"],
                    status=str(item.get("status")),
                )
            ],
        )

    if item["type"] == "shell_call_output":
        outputs = [
            Content.from_shell_command_output(
                stdout=out["stdout"] or "",
                stderr=out["stderr"] or "",
                exit_code=out["outcome"].get("exit_code"),
            )
            for out in (item["output"] or [])
        ]
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=item["call_id"],
                    outputs=outputs,
                    max_output_length=item.get("max_output_length"),
                )
            ],
        )

    if item["type"] == "local_shell_call":
        commands = item["action"].get("command") or []
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=item["call_id"],
                    commands=commands,
                    status=str(item["status"]),
                )
            ],
        )

    if item["type"] == "local_shell_call_output":
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=item["id"],
                    outputs=[Content.from_shell_command_output(stdout=item["output"])],
                )
            ],
        )

    if item["type"] == "file_search_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["id"],
                    "file_search",
                    arguments=json.dumps({"queries": item["queries"]}),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "web_search_call":
        return Message(
            role="assistant",
            contents=[Content.from_function_call(item["id"], "web_search", informational_only=True)],
        )

    if item["type"] == "computer_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    "computer_use",
                    arguments=str(item.get("action")),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "computer_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=str(item["output"]))],
        )

    if item["type"] == "custom_tool_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    item["name"],
                    arguments=item["input"],
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "custom_tool_call_output":
        output = item["output"] if isinstance(item["output"], str) else str(item["output"])
        # Hosted-MCP results land here because the host writes them via
        # `aoutput_item_custom_tool_call_output` (see `_to_outputs` for
        # `mcp_server_tool_result`). The persisted `call_id` keeps its
        # `mcp_*` prefix; on read, route those back to a hosted-MCP result
        # Content so the chat-client serialize layer can coalesce them
        # onto a single `mcp_call` input item with `output` populated.
        # Issue #5546.
        if item["call_id"] and item["call_id"].startswith("mcp_"):
            return Message(
                role="tool",
                contents=[Content.from_mcp_server_tool_result(call_id=item["call_id"], output=output)],
            )
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=output)],
        )

    if item["type"] == "apply_patch_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    "apply_patch",
                    arguments=str(item["operation"]),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "apply_patch_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=item.get("output") or "")],
        )

    raise ValueError(f"Unsupported Item type: {item['type']}")


async def _output_items_to_messages(
    history: Sequence[OutputItem],
    *,
    approval_storage: FunctionApprovalStore | None = None,
) -> list[Message]:
    """Converts a sequence of OutputItem objects to a list of Message objects.

    Args:
        history (Sequence[OutputItem]): The sequence of OutputItem objects to convert.
        approval_storage (ApprovalStorage | None, optional): The approval storage to use for
            resolving MCP approval requests. Defaults to None.

    Returns:
        list[Message]: The list of Message objects.
    """
    messages: list[Message] = []
    for item in history:
        messages.append(await _output_item_to_message(item, approval_storage=approval_storage))
    return messages


async def _output_item_to_message(
    item: OutputItem, *, approval_storage: FunctionApprovalStore | None = None
) -> Message:
    """Converts an OutputItem to a Message.

    Args:
        item (OutputItem): The OutputItem to convert.
        approval_storage (ApprovalStorage | None, optional): The approval storage to use for
            resolving MCP approval requests. Defaults to None.

    Returns:
        Message: The converted Message.

    Raises:
        ValueError: If the OutputItem type is not supported.
    """
    if item["type"] == "output_message":
        return Message(role=item["role"], contents=[_convert_output_message_content(part) for part in item["content"]])

    if item["type"] == "message":
        return Message(role=item["role"], contents=[_convert_message_content(part) for part in item["content"]])

    if item["type"] == "function_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    item["name"],
                    arguments=item["arguments"],
                )
            ],
        )

    if item["type"] == "function_call_output":
        output = item["output"] if isinstance(item["output"], str) else str(item["output"])
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=output)],
        )

    if item["type"] == "reasoning":
        return Message(role="assistant", contents=_reasoning_item_to_contents(item))

    if item["type"] == "mcp_call":
        contents = [
            Content.from_mcp_server_tool_call(
                item["id"],
                item["name"],
                server_name=item["server_label"],
                arguments=item["arguments"],
            )
        ]
        if (output := item.get("output")) is not None:
            contents.append(Content.from_mcp_server_tool_result(call_id=item["id"], output=output))
        return Message(
            role="assistant",
            contents=contents,
        )

    if item["type"] == "mcp_approval_request":
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(item["id"])
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")
        return Message(
            role="assistant",
            contents=[function_approval_request_content],
        )

    if item["type"] == "mcp_approval_response":
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(
                item["approval_request_id"]
            )
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")

        return Message(
            role="user",
            contents=[function_approval_request_content.to_function_approval_response(item["approve"])],
        )

    if item["type"] == "code_interpreter_call":
        return Message(
            role="assistant",
            contents=[Content.from_code_interpreter_tool_call(call_id=item["id"])],
        )

    if item["type"] == "image_generation_call":
        return Message(
            role="assistant",
            contents=[Content.from_image_generation_tool_call(image_id=item["id"])],
        )

    if item["type"] == "shell_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=item["call_id"],
                    commands=item["action"]["commands"],
                    status=str(item.get("status")),
                )
            ],
        )

    if item["type"] == "shell_call_output":
        outputs = [
            Content.from_shell_command_output(
                stdout=out["stdout"] or "",
                stderr=out["stderr"] or "",
                exit_code=out["outcome"].get("exit_code"),
            )
            for out in (item.get("output") or [])
        ]
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=item["call_id"],
                    outputs=outputs,
                    max_output_length=item.get("max_output_length"),
                )
            ],
        )

    if item["type"] == "local_shell_call":
        commands = item["action"].get("command") or []
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=item["call_id"],
                    commands=commands,
                    status=str(item["status"]),
                )
            ],
        )

    if item["type"] == "local_shell_call_output":
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=item["id"],
                    outputs=[Content.from_shell_command_output(stdout=item["output"])],
                )
            ],
        )

    if item["type"] == "file_search_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["id"],
                    "file_search",
                    arguments=json.dumps({"queries": item["queries"]}),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "web_search_call":
        return Message(
            role="assistant",
            contents=[Content.from_function_call(item["id"], "web_search", informational_only=True)],
        )

    if item["type"] == "computer_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    "computer_use",
                    arguments=str(item.get("action")),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "computer_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=str(item["output"]))],
        )

    if item["type"] == "custom_tool_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    item["name"],
                    arguments=item["input"],
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "custom_tool_call_output":
        output = item["output"] if isinstance(item["output"], str) else str(item["output"])
        # Hosted-MCP results land here because the host writes them via
        # `aoutput_item_custom_tool_call_output`. Route `mcp_*` call_ids
        # back to a hosted-MCP result Content so the chat-client serialize
        # layer can coalesce onto the matching `mcp_call` input item.
        # Issue #5546.
        if item["call_id"] and item["call_id"].startswith("mcp_"):
            return Message(
                role="tool",
                contents=[Content.from_mcp_server_tool_result(call_id=item["call_id"], output=output)],
            )
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=output)],
        )

    if item["type"] == "apply_patch_call":
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    "apply_patch",
                    arguments=str(item["operation"]),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "apply_patch_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=item.get("output") or "")],
        )

    if item["type"] == "oauth_consent_request":
        return Message(
            role="assistant",
            contents=[Content.from_oauth_consent_request(item["consent_link"])],
        )

    if item["type"] == "structured_outputs":
        text = json.dumps(item["output"]) if not isinstance(item["output"], str) else item["output"]
        return Message(role="assistant", contents=[Content.from_text(text)])

    raise ValueError(f"Unsupported OutputItem type: {item['type']}")


def _convert_output_message_content(content: OutputMessageContent) -> Content:
    """Converts an OutputMessageContent to a Content object.

    Args:
        content (OutputMessageContent): The OutputMessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the OutputMessageContent type is not supported.
    """
    if content["type"] == "output_text":
        return Content.from_text(content["text"])
    if content["type"] == "refusal":
        return Content.from_text(content["refusal"])

    # Defensive: `OutputMessageContent` currently only supports `output_text` and `refusal`,
    # but if new types are added in the future, this will catch them.
    raise ValueError(f"Unsupported OutputMessageContent type: {content['type']}")


def _convert_file_data(data_uri: str, filename: str | None = None) -> Content:
    """Convert a file_data data URI to a Content object.

    For text/* MIME types, decodes the base64 content and returns it as text.
    For other types, returns a URI-based Content with the filename preserved.
    """
    # Parse data URI: data:<media_type>;base64,<data>
    if data_uri.startswith("data:") and ";base64," in data_uri:
        header, encoded = data_uri.split(";base64,", 1)
        media_type = header[len("data:") :]
        if media_type.startswith("text/"):
            try:
                decoded_text = base64.b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                logger.warning(
                    "Failed to decode text/* file_data as UTF-8, falling through to URI passthrough.",
                    exc_info=True,
                )
            else:
                prefix = f"[File: {filename}]\n" if filename else ""
                return Content.from_text(f"{prefix}{decoded_text}")
    additional_properties = {"filename": filename} if filename else None
    return Content.from_uri(data_uri, additional_properties=additional_properties)


def _convert_message_content(content: MessageContent) -> Content:
    """Converts a MessageContent to a Content object.

    Args:
        content (MessageContent): The MessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the MessageContent type is not supported.
    """
    if content["type"] == "input_text":
        return Content.from_text(content["text"])
    if content["type"] == "output_text":
        return Content.from_text(content["text"])
    if content["type"] == "text":
        return Content.from_text(content["text"])
    if content["type"] == "summary_text":
        return Content.from_text(content["text"])
    if content["type"] == "refusal":
        return Content.from_text(content["refusal"])
    if content["type"] == "reasoning_text":
        return Content.from_text_reasoning(text=content["text"])
    if content["type"] == "input_image":
        if image_url := content.get("image_url"):
            if image_url.startswith("data:"):
                return Content.from_uri(image_url)
            return Content.from_uri(image_url, media_type="image/*")
        if file_id := content.get("file_id"):
            return Content.from_hosted_file(file_id)
    if content["type"] == "input_file":
        if file_url := content.get("file_url"):
            return Content.from_uri(file_url)
        if file_id := content.get("file_id"):
            return Content.from_hosted_file(file_id, name=content.get("filename"))
        if file_data := content.get("file_data"):
            return _convert_file_data(file_data, content.get("filename"))
    if content["type"] == "computer_screenshot":
        if image_url := content.get("image_url"):
            return Content.from_uri(image_url)
        if file_id := content.get("file_id"):
            return Content.from_hosted_file(file_id, name=content.get("filename"))

    raise ValueError(f"Unsupported MessageContent type: {content['type']}")


# endregion

# region Output Item Conversion


def _argument_json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _arguments_to_str(arguments: Any | None) -> str:
    """Convert arguments to a JSON string.

    Args:
        arguments: The arguments to convert, can be a string, JSON-like object, or None.

    Returns:
        The arguments as a JSON string.
    """
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments, default=_argument_json_default)


def _reasoning_encrypted_content(content: Content) -> str | None:
    """Return the opaque reasoning payload used for stateless replay."""
    encrypted_content = content.protected_data or content.additional_properties.get("encrypted_content")
    return encrypted_content if isinstance(encrypted_content, str) else None


def _reasoning_output_item(
    *,
    item_id: str,
    summary_texts: Sequence[str],
    encrypted_content: str | None,
    status: Literal["in_progress", "completed"],
) -> OutputItemReasoningItem:
    """Build a hosted reasoning item while retaining provider replay metadata."""
    return OutputItemReasoningItem({
        "type": "reasoning",
        "id": item_id,
        "summary": [{"type": "summary_text", "text": text} for text in summary_texts],
        "encrypted_content": encrypted_content,
        "status": status,
    })


def _emit_reasoning_output(
    stream: ResponseEventStream,
    contents: Sequence[Content],
) -> Generator[ResponseStreamEvent]:
    """Emit one reasoning output item for contents sharing a provider reasoning ID."""
    first = contents[0]
    item_id = first.id
    if not item_id or not IdGenerator.is_valid(item_id)[0]:
        item_id = IdGenerator.new_id("rs")
    summary_texts = [content.text or "" for content in contents]
    encrypted_content = next(
        (value for content in contents if (value := _reasoning_encrypted_content(content))),
        None,
    )
    builder = stream.add_output_item(item_id)
    yield builder.emit_added(
        _reasoning_output_item(
            item_id=item_id,
            summary_texts=[],
            encrypted_content=None,
            status="in_progress",
        )
    )
    for summary_index, summary_text in enumerate(summary_texts):
        summary_part = ReasoningSummaryPartBuilder(stream, builder.output_index, summary_index, item_id)
        yield summary_part.emit_added()
        yield summary_part.emit_text_delta(summary_text)
        yield summary_part.emit_text_done(summary_text)
        yield summary_part.emit_done()
    yield builder.emit_done(
        _reasoning_output_item(
            item_id=item_id,
            summary_texts=summary_texts,
            encrypted_content=encrypted_content,
            status="completed",
        )
    )


async def _to_outputs(
    stream: ResponseEventStream,
    content: Content,
    *,
    approval_storage: FunctionApprovalStore | None = None,
) -> AsyncIterator[ResponseStreamEvent]:
    """Converts a Content object to an async sequence of ResponseStreamEvent objects.

    Args:
        stream: The ResponseEventStream to use for building events.
        content: The Content to convert.
        approval_storage: An optional ApprovalStorage instance to use for saving and loading function approval requests.

    Yields:
        ResponseStreamEvent: The converted event objects.

    Raises:
        ValueError: If the Content type is not supported.
    """
    if content.type == "text" and content.text is not None:
        async for event in stream.output_item_message(content.text):
            yield event
    elif content.type == "text_reasoning":
        for event in _emit_reasoning_output(stream, [content]):
            yield event
    elif content.type == "function_call":
        async for event in stream.output_item_function_call(
            content.name,  # type: ignore[arg-type]
            content.call_id,  # type: ignore[arg-type]
            _arguments_to_str(content.arguments),
        ):
            yield event
    elif content.type == "function_result":
        async for event in stream.output_item_function_call_output(
            content.call_id,  # type: ignore[arg-type]
            str(content.result or ""),
        ):
            yield event
    elif content.type == "image_generation_tool_result" and content.outputs is not None:
        async for event in stream.output_item_image_gen_call(str(content.outputs)):
            yield event
    elif content.type == "mcp_server_tool_call":
        mcp_call = stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
            item_id=content.call_id,
        )
        yield mcp_call.emit_added()
        async for event in mcp_call.arguments(_arguments_to_str(content.arguments)):
            yield event
        yield mcp_call.emit_completed()
        yield mcp_call.emit_done()
    elif content.type == "mcp_server_tool_result":
        output = (
            content.output
            if isinstance(content.output, str)
            else str(content.output)
            if content.output is not None
            else ""
        )
        async for event in stream.output_item_custom_tool_call_output(content.call_id or "", output):
            yield event
    elif content.type == "shell_tool_call":
        action = FunctionShellAction(commands=content.commands or [], timeout_ms=0, max_output_length=0)
        async for event in stream.output_item_function_shell_call(
            content.call_id or "",
            action,
            LocalEnvironmentResource(type="local"),
            status=content.status or "completed",
        ):
            yield event
    elif content.type == "shell_tool_result":
        output_items: list[FunctionShellCallOutputContent] = []
        if content.outputs:
            for out in content.outputs:
                exit_code = getattr(out, "exit_code", None)
                output_items.append(
                    FunctionShellCallOutputContent(
                        stdout=getattr(out, "stdout", "") or "",
                        stderr=getattr(out, "stderr", "") or "",
                        outcome=FunctionShellCallOutputExitOutcome(
                            type="exit",
                            exit_code=exit_code if exit_code is not None else 0,
                        ),
                    )
                )
        async for event in stream.output_item_function_shell_call_output(
            content.call_id or "",
            output_items,
            status=content.status or "completed",
            max_output_length=content.max_output_length,
        ):
            yield event
    elif content.type == "function_approval_request":
        function_call: Content = content.function_call  # type: ignore
        server_label = function_call.additional_properties.get("server_label", "agent_framework")
        request_saved = False
        async for event in stream.output_item_mcp_approval_request(
            server_label,
            function_call.name,  # type: ignore
            _arguments_to_str(function_call.arguments),
        ):
            if approval_storage is not None and not request_saved:
                # Extract the approval request ID generated by the infrastructure
                # when the approval request item is added to the stream. Save the
                # approval request to the approval storage so it can be retrieved later
                # for round trips where the original approval request needs to be looked up.
                item = event.get("item") if isinstance(event, Mapping) else getattr(event, "item", None)
                approval_request_id = (
                    cast(Mapping[str, Any], item).get("id") if isinstance(item, Mapping) else getattr(item, "id", None)
                )
                if isinstance(approval_request_id, str):
                    await approval_storage.save_approval_request(approval_request_id, content)
                    request_saved = True
            yield event
        if approval_storage is not None and not request_saved:
            logger.warning(
                "Approval request was not saved to approval storage because the approval request ID "
                "could not be extracted from the stream event."
            )
    else:
        # Log a warning for unsupported content types instead of raising an error to avoid breaking the response stream.
        logger.warning(f"Content type '{content.type}' is not supported yet. This is usually safe to ignore.")


def _stringify_mcp_output(output: Any) -> str:
    """Convert hosted MCP output payloads into the string shape expected by mcp_call.output."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        text = cast(Any, output).get("text")
        if isinstance(text, str):
            return text
        return json.dumps(output, default=str)
    if isinstance(output, Sequence) and not isinstance(output, (str, bytes, bytearray)):
        parts: list[str] = []
        entries = cast(Sequence[object], output)
        for entry in entries:
            if isinstance(entry, Content) and entry.type == "text":
                parts.append(entry.text or "")
                continue
            parts.append(_stringify_mcp_output(entry))
        return "".join(parts)
    return str(output)


# endregion
