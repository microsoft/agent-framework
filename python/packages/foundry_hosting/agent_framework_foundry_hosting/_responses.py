# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import os
import re
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Generator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, aclosing, suppress
from dataclasses import asdict, dataclass, is_dataclass
from typing import Generic, Literal, TypeGuard, TypeVar, cast
from urllib.parse import urlparse

from agent_framework import (
    AgentResponseUpdate,
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
    UsageDetails,
    WorkflowAgent,
    add_usage_details,
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
    ResponseUsage,
    ResponseUsageInputTokensDetails,
    ResponseUsageOutputTokensDetails,
)
from azure.ai.agentserver.responses.streaming._builders import (
    OutputItemBuilder,
    OutputItemFunctionCallBuilder,
    OutputItemMcpCallBuilder,
    OutputItemMessageBuilder,
    ReasoningSummaryPartBuilder,
    RefusalContentBuilder,
    TextContentBuilder,
)
from azure.ai.agentserver.responses.streaming._checkpoint import ResponseCheckpointEvent
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

_MODEL_OUTPUT_KIND_KEY = "model_output_kind"
_MODEL_OUTPUT_REFUSAL = "refusal"
_HOSTED_RESPONSES_HISTORY_SOURCE_ID = "_foundry_responses_history"


def _is_refusal_text_content(content: Content) -> bool:
    return content.type == "text" and content.additional_properties.get(_MODEL_OUTPUT_KIND_KEY) == _MODEL_OUTPUT_REFUSAL


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


def _create_response_event_stream(context: ResponseContext) -> ResponseEventStream:
    """Create a response stream seeded from recovery state when available."""
    if context.is_recovery:
        persisted_response = context.persisted_response
        if persisted_response is not None:
            return ResponseEventStream(response=persisted_response, response_id=context.response_id)
    return ResponseEventStream(response_id=context.response_id)


_T = TypeVar("_T")

# Sentinel put on the internal queue by _SignalledIterator's driver task to signal that the
# wrapped iterator is exhausted (distinct from `None`, which is a valid item value).
_STOP_SENTINEL: Any = object()


class _SignalledIterator(Generic[_T]):
    """Wraps an async iterator, stopping early as soon as any of ``events`` fires.

    Plain ``async for update in agent.run(...): if event.is_set(): break`` only observes ``event``
    once ``run()`` actually yields an item -- if it's suspended on a single slow model or tool call
    with no intermediate item, the signal is invisible until that call resolves. This drives the
    wrapped iterator from a single persistent background task and races each produced item against
    ``events`` via ``asyncio.wait`` instead, so a signal is observed immediately.

    The background task (``_drive``) is required (rather than spawning a fresh task per step)
    because some cleanup run by the wrapped iterator (e.g. observability span teardown) resets a
    contextvar token set on an earlier call and requires every call against it to share the same
    async context.

    If an event and a new item becomes ready at the same time, the event takes priority and the item
    is discarded. Cancelling the background task while it's mid-call is also what actually interrupts
    a suspended model/tool call, since ``ResponseStream`` (what ``SupportsAgentRun.run(stream=True)``
    returns) has no ``aclose()`` of its own.

    Callers MUST drive this through ``contextlib.aclosing`` (or an equivalent try/finally calling
    ``aclose()``): ``__anext__`` only cancels the driver task on its own signalled/exhausted paths, so
    if the consumer of ``async for`` raises instead (e.g. while processing a yielded item), the driver
    task -- and the real agent/workflow run it's pumping -- would otherwise be silently abandoned.
    """

    def __init__(self, iterator: AsyncIterator[_T], *events: asyncio.Event) -> None:
        """Wrap an async iterator, stopping early if any of ``events`` fires.

        Args:
            iterator: The async iterator to wrap.
            events: One or more asyncio.Event objects to watch for. If any of them is set, iteration stops early.
        """
        self._iterator = iterator
        self._events = events
        self._signalled = False
        # The queue is used to communicate items from the background driver task to the main iteration loop.
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        # The background task that drives the wrapped iterator.
        self._driver: asyncio.Task[None] | None = None

    @property
    def signalled(self) -> bool:
        """Whether iteration stopped early due to an event being set.

        ``signalled`` is only set when iteration stopped early because of an event -- never on ordinary
        exhaustion -- so callers can tell "the agent/workflow finished" apart from "we gave up waiting".
        """
        return self._signalled

    def __aiter__(self) -> _SignalledIterator[_T]:
        return self

    async def _drive(self) -> None:
        """Pull items from the wrapped iterator into ``self._queue`` for the object's lifetime."""
        while True:
            try:
                item: Any = await self._iterator.__anext__()
            except StopAsyncIteration:
                await self._queue.put(_STOP_SENTINEL)
                return
            except Exception as exc:
                await self._queue.put(exc)
                return
            await self._queue.put(item)

    async def __anext__(self) -> _T:
        if self._driver is None:
            self._driver = asyncio.ensure_future(self._drive())

        # Create the background tasks for monitoring the events and the queue.
        waiters = [asyncio.ensure_future(event.wait()) for event in self._events]
        get_task = asyncio.ensure_future(self._queue.get())
        try:
            # Waits until at least one of the tasks is completed.
            await asyncio.wait([get_task, *waiters], return_when=asyncio.FIRST_COMPLETED)
            if any(waiter.done() for waiter in waiters):
                self._signalled = True
                self._driver.cancel()
                with suppress(BaseException):
                    await self._driver
                get_task.cancel()
                with suppress(BaseException):
                    await get_task
                raise StopAsyncIteration
            item = get_task.result()
        finally:
            for waiter in waiters:
                if not waiter.done():
                    waiter.cancel()
            for waiter in waiters:
                with suppress(BaseException):
                    await waiter
        if item is _STOP_SENTINEL:
            raise StopAsyncIteration
        if isinstance(item, Exception):
            raise item
        return cast(_T, item)

    async def aclose(self) -> None:
        """Cancel the background driver task, if any, and wait for it to finish.

        Safe to call unconditionally: a no-op if the driver was never started, and cancelling an
        already-finished task (normal exhaustion or a prior signalled stop) is also a no-op.
        """
        if self._driver is None:
            return
        self._driver.cancel()
        with suppress(BaseException):
            await self._driver


# Reserved response metadata key pinning the workflow checkpoint that was current at the moment of
# the last successfully persisted response-stream checkpoint. Recovery MUST resume from this specific
# checkpoint if it exists, not simply the latest one in checkpoint_storage: the workflow may have
# saved further checkpoints after it but before a crash, without their output ever being durably
# recorded in response.output. If this key is missing, the workflow will resume from the latest
# checkpoint in storage (if any), or replay the original input if none exists as no output was ever
# durably persisted.
_LATEST_CHECKPOINT_ID_KEY = "_last_checkpoint_id"


# Foundry Toolbox Auth integration
# Consent-URL error code returned by the Foundry MCP gateway when calling `/list`
CONSENT_ERROR_CODE = -32006

_OAUTH_HOST_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")


@dataclass
class ConsentError:
    name: str
    consent_url: str


def _is_safe_oauth_consent_link(consent_link: object) -> TypeGuard[str]:
    """Return whether a consent link is an absolute HTTPS URL safe to expose as an action."""
    if not isinstance(consent_link, str) or not consent_link:
        return False
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in consent_link):
        return False

    try:
        parsed = urlparse(consent_link)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False

    if parsed.scheme.lower() != "https" or not hostname or parsed.username is not None or parsed.password is not None:
        return False

    if "%" in hostname:
        return False
    authority = parsed.netloc
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        if closing_bracket == -1:
            return False
        ipv6_literal = authority[1:closing_bracket]
        suffix = authority[closing_bracket + 1 :]
        if suffix and (not suffix.startswith(":") or not suffix[1:].isdigit()):
            return False
        try:
            ipaddress.IPv6Address(ipv6_literal)
        except ValueError:
            return False
        return True
    if "[" in authority or "]" in authority or ":" in hostname:
        return False
    return _OAUTH_HOST_PATTERN.fullmatch(hostname) is not None


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
        #           "type" : "mcp" | "a2a_preview",
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
                    and error.get("type") in ("mcp", "a2a_preview")  # type: ignore
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
        history_source: Literal["agent_server", "agent"] = "agent_server",
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
            history_source: Source of conversation history supplied to the model for regular agents.
                `"agent_server"` (default) uses the transcript from the configured response store,
                requires a `RawAgent` whose client declares `STORES_BY_DEFAULT`, rejects load-enabled
                agent history providers, and disables downstream service storage.
                `"agent"` passes only the current request input and preserves the agent's normal
                history-provider or service-storage behavior. AgentServer still manages Responses
                API persistence through `store` in both modes.
            **kwargs: Additional keyword arguments.

        Note:
            1. When `history_source="agent_server"`, the agent must not have a history provider
               with `load_messages=True`, because history is managed by the hosting infrastructure.
            2. Context providers must not keep required state only on their Python instances,
               because the hosting environment may get deactivated between requests. Provider
               state carried by `AgentSession`, including `InMemoryHistoryProvider` messages in
               `history_source="agent"` mode, is persisted by the configured session store.
            3. The server owns the supplied agent instance and may add hosting-specific providers.
               Do not reuse the same agent with another host or invoke it directly after construction.
            4. Resiliency (resilient_background=True) is ONLY supported for workflows; constructing this
               server with a non-workflow agent and `resilient_background=True` raises `RuntimeError`.
               When resiliency is enabled, and the server crashes mid-response:
               - Background responses are automatically re-invoked on server restart (client won't see the crash).
               - Stream events are preserved for client reconnection.
               - State is maintained across crashes.
            5. Steering (steerable_conversations=True) is ONLY supported for non-workflow agents; constructing
               this server with a workflow agent and `steerable_conversations=True` raises `RuntimeError`.
               Steering a workflow is conceptually undefined -- a workflow's graph may have loops or parallel
               branches with no single well-defined "current point" to cancel and resume from, unlike an
               agent's strictly linear execution. It's also not currently practical to implement: a workflow
               instance cannot start a new run until its previous (steered-past) run has been garbage
               collected, and that isn't guaranteed to have happened in time.

        Raises:
            ValueError: If `history_source` is not supported.
            RuntimeError: If the agent configuration conflicts with the selected history source,
                `resilient_background=True` is requested for a non-workflow agent, or
                `steerable_conversations=True` is requested for a workflow agent.
        """
        if history_source not in ("agent_server", "agent"):
            raise ValueError("history_source must be either 'agent_server' or 'agent'.")

        is_workflow_agent = isinstance(agent, WorkflowAgent)
        if is_workflow_agent and agent.workflow._runner_context.has_checkpointing():  # pyright: ignore[reportPrivateUsage]
            raise RuntimeError(
                "There should not be a checkpoint storage already present in the workflow agent. "
                "The hosting infrastructure will manage checkpoints instead."
            )

        resilient_background = bool(options and options.resilient_background)
        if resilient_background and not is_workflow_agent:
            raise RuntimeError(
                "resilient_background=True is only supported for workflow agents. "
                "Crash recovery cannot be provided for non-workflow agents."
            )
        if options and options.steerable_conversations and is_workflow_agent:
            raise RuntimeError(
                "steerable_conversations=True is only supported for non-workflow agents. "
                "Steering cannot be provided reliably for workflow agents."
            )

        uses_agent_server_history = history_source == "agent_server"
        client_stores_by_default = False
        if uses_agent_server_history and not is_workflow_agent:
            if not isinstance(agent, RawAgent):
                raise RuntimeError(
                    "history_source='agent_server' requires a RawAgent so hosting can enforce downstream "
                    "storage options. Construct ResponsesHostServer with history_source='agent' for a custom "
                    "SupportsAgentRun implementation."
                )
            for provider in agent.context_providers:
                if isinstance(provider, HistoryProvider) and provider.load_messages:
                    if _is_hosted_responses_history_sentinel(provider):
                        continue
                    raise RuntimeError(
                        "AgentServer response history is enabled, but the agent has a HistoryProvider "
                        "with load_messages=True. Remove that provider or construct ResponsesHostServer "
                        "with history_source='agent' to use the agent's regular history setup."
                    )
            service_continuation_options = [
                name
                for name in ("conversation_id", "previous_response_id", "conversation")
                if agent.default_options.get(name) is not None
            ]
            if service_continuation_options:
                raise RuntimeError(
                    "AgentServer response history is enabled, but the agent has downstream service continuation "
                    f"option(s): {', '.join(service_continuation_options)}. Remove them or construct "
                    "ResponsesHostServer with history_source='agent' to resume the downstream service conversation."
                )
            stores_by_default = getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None)
            if not isinstance(stores_by_default, bool):
                raise RuntimeError(
                    "history_source='agent_server' requires the agent's chat client to declare "
                    "STORES_BY_DEFAULT so hosting can enforce downstream storage behavior."
                )
            client_stores_by_default = stores_by_default

        # No caller-owned agent state is mutated until all validation and base-host construction succeed.
        super().__init__(prefix=prefix, options=options, store=store, **kwargs)

        self._uses_agent_server_history = uses_agent_server_history
        self._client_stores_by_default = client_stores_by_default
        self._is_workflow_agent = is_workflow_agent
        self._resilient_background = resilient_background

        self._uses_hosted_responses_history = False
        if self._uses_agent_server_history and not self._is_workflow_agent and isinstance(agent, RawAgent):
            self._uses_hosted_responses_history = True
            if not self._client_stores_by_default:
                agent.default_options.pop("store", None)
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
    ) -> AsyncIterable[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Handle the creation of a response."""
        # Common per-request setup shared by the workflow and non-workflow paths:
        # create the response stream and the streaming output-item tracker, emit
        # the opening lifecycle events, and convert any exception raised while
        # producing the response into a terminal ``response.failed`` event (which
        # also drains the tracker so the SSE stream stays well-formed).
        response_event_stream = _create_response_event_stream(context)

        if context.is_steered_turn:
            logger.debug("Serving steered turn (pending_input_count=%d)", context.pending_input_count)

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

            invalid_consent = next(
                (
                    consent_error
                    for consent_error in consent_errors_to_emit
                    if not _is_safe_oauth_consent_link(consent_error.consent_url)
                ),
                None,
            )
            if invalid_consent is not None:
                validation_error = ValueError(
                    f"OAuth consent request for tool '{invalid_consent.name}' must include a safe HTTPS consent link."
                )
                logger.error("%s", validation_error)
                for event in self._emit_failure(response_event_stream, None, validation_error):
                    yield event
                return

            if not self._is_workflow_agent:
                try:
                    request_context = get_request_context()
                    session_storage = self._session_storage_provider.get_store(
                        config=self.config, platform_context=request_context
                    )
                    previous_response_id = request.get("previous_response_id")
                    session_load_id = context.conversation_id or previous_response_id
                    session = await session_storage.get(session_load_id) if session_load_id is not None else None
                    if session is None:
                        if previous_response_id is not None and context.conversation_id is None:
                            raise RuntimeError(
                                "Cannot find an existing agent session for "
                                f"previous_response_id={previous_response_id}."
                            )
                        session = self._agent.create_session()
                    await session_storage.set(context.conversation_id or context.response_id, session)
                except Exception as save_error:
                    logger.error(
                        "Failed to persist the Agent Framework session for OAuth consent",
                        exc_info=(type(save_error), save_error, save_error.__traceback__),
                    )
                    for event in self._emit_failure(response_event_stream, None, save_error):
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

            yield response_event_stream.emit_incomplete()
            return

        tracker = _OutputItemTracker(response_event_stream)
        try:
            if self._is_workflow_agent:
                inner = self._handle_inner_workflow(
                    request, context, response_event_stream, tracker, cancellation_signal
                )
            else:
                inner = self._handle_inner_agent(request, context, response_event_stream, tracker, cancellation_signal)

            try:
                async for event in inner:
                    yield event
            except BaseException:
                await inner.aclose()
                raise

            for event in tracker.close():
                yield event

            if tracker.oauth_consent_requested:
                yield response_event_stream.emit_incomplete(usage=tracker.usage)
            else:
                yield response_event_stream.emit_completed(usage=tracker.usage)
        except Exception as ex:
            logger.error("Failed to produce response for agent", exc_info=(type(ex), ex, ex.__traceback__))
            for event in tracker.close():
                yield event

            for event in self._emit_failure(response_event_stream, tracker, ex):
                yield event

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker,
        cancellation_signal: asyncio.Event,
    ) -> AsyncGenerator[ResponseStreamEvent]:
        """Handle a regular (non-workflow) agent.

        The response stream, tracker, and opening lifecycle events are produced
        by :meth:`_handle_response`, which also converts any raised exception
        into a terminal ``response.failed`` event (draining the tracker so the
        SSE stream stays well-formed).
        """
        if context.is_recovery:
            logger.warning(
                "Recovery mode is not supported for non-workflow agents. "
                "The agent will restart from the original input."
            )

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
            raise

        request_failure: Exception | None = None
        save_failure: Exception | None = None
        request_interrupted = False

        try:
            if self._uses_agent_server_history:
                session.state.pop(_HOSTED_RESPONSES_HISTORY_SOURCE_ID, None)
                # A restored service ID belongs to the downstream model service. Replaying the
                # AgentServer transcript while resuming that service history would duplicate every
                # prior turn, so AgentServer-history mode always starts the model call statelessly.
                session.service_session_id = None

            input_items = await context.get_input_items()
            input_messages = await _items_to_messages(input_items, approval_storage=approval_storage)

            history_messages: list[Message] = []
            if self._uses_agent_server_history:
                history = await context.get_history()
                history_messages = await _output_items_to_messages(history, approval_storage=approval_storage)
            run_kwargs: dict[str, Any] = {
                "messages": [*history_messages, *input_messages],
                "session": session,
            }
            chat_options, are_options_set = _to_chat_options(request)
            if self._uses_agent_server_history:
                if self._client_stores_by_default:
                    # The response provider already owns the transcript used for this run. Keep a
                    # storing downstream service stateless so it cannot become a second history source.
                    chat_options["store"] = False
                else:
                    # Do not pass a storage option to clients that do not advertise support for it.
                    chat_options.pop("store", None)

            if isinstance(self._agent, RawAgent):
                run_kwargs["options"] = chat_options
            elif are_options_set:
                logger.warning("Agent doesn't support runtime options. They will be ignored.")

            # Non-workflow agents can't be resilient, so there is no exit_for_recovery path here:
            # both shutdown and steering/cancel just wind the turn down once observed.
            agent_stream = _SignalledIterator(
                self._agent.run(stream=True, **run_kwargs),  # type: ignore[reportUnknownMemberType]
                context.shutdown,
                cancellation_signal,
            )
            async with aclosing(agent_stream):
                async for update in agent_stream:
                    for content in update.contents:
                        async for event in tracker.handle(
                            content, message_id=update.message_id, approval_storage=approval_storage
                        ):
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

            # A service ID here means the client stored the turn despite the forced `store=False`.
            # Do not persist a session that could resume that unreconciled history on a later turn.
            stored_output_violation = self._uses_agent_server_history and session.service_session_id is not None
            if stored_output_violation:
                misconfigured = RuntimeError(
                    "The agent's chat client stored this turn server-side while AgentServer response history "
                    "is supplying the conversation. Configure the client to honor store=False, or construct "
                    "ResponsesHostServer with history_source='agent' to use the agent's regular history setup."
                )
                logger.error("%s", misconfigured)
                if request_failure is None and not request_interrupted:
                    request_failure = misconfigured
            try:
                if not stored_output_violation:
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
            raise RuntimeError(
                f"Agent request failed: {str(request_failure) or type(request_failure).__name__}; "
                f"session persistence also failed: {str(save_failure) or type(save_failure).__name__}"
            )
        elif request_failure is not None:
            raise request_failure
        elif save_failure is not None:
            raise save_failure

    async def _handle_inner_workflow(
        self,
        request: CreateResponse,
        context: ResponseContext,
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker,
        cancellation_signal: asyncio.Event,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Handle the creation of a response for a workflow agent."""
        if not isinstance(self._agent, WorkflowAgent):
            raise RuntimeError("Agent is not a workflow agent.")

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

            # Determine the checkpoint storage for this request. The checkpoint
            # storage is keyed by the conversation ID (if present) or the response
            # ID (if no conversation ID is present). On a subsequent turn, the same
            # conversation ID or a `previous_response_id` can be used to resume the
            # workflow from the last checkpoint.
            checkpoint_save_id = context.conversation_id or context.response_id
            _validate_checkpoint_context_id(checkpoint_save_id)
            checkpoint_storage = self._checkpoint_storage_provider.get_store(
                config=self.config,
                context_id=checkpoint_save_id,
                platform_context=request_context,
            )

            if context.is_recovery:
                if not self._resilient_background:
                    raise RuntimeError("Recovery mode is only supported when resilient_background=True.")
                # Resume from the workflow checkpoint durably paired with the last persisted response
                # snapshot (recorded in that snapshot's own metadata) -- NOT simply the latest workflow
                # checkpoint in storage, which may be ahead of what response.output actually reflects if
                # the crash happened between two response-stream checkpoint() calls.
                checkpoint_id = response_event_stream.internal_metadata.get(_LATEST_CHECKPOINT_ID_KEY)
                if checkpoint_id is not None:
                    logger.debug("Serving recovery request from workflow checkpoint %s", checkpoint_id)
                    run_stream = self._resume_workflow_from_checkpoint(
                        checkpoint_id, checkpoint_storage, context.response_id
                    )
                else:
                    latest_checkpoint = await checkpoint_storage.get_latest(workflow_name=self._agent.workflow.name)
                    if latest_checkpoint is not None:
                        logger.debug(
                            "Found a workflow checkpoint %s but no prior response snapshot was durably persisted; "
                            "resuming from the latest checkpoint",
                            latest_checkpoint.checkpoint_id,
                        )
                        run_stream = self._resume_workflow_from_checkpoint(
                            latest_checkpoint.checkpoint_id, checkpoint_storage, context.response_id
                        )
                    else:
                        # No checkpoint was ever paired with a persisted response snapshot (e.g. the crash
                        # happened before the very first response checkpoint() call); replay the original
                        # input as a fresh entry, per the recovered-input parity guarantee
                        # (context.get_input_items() is unchanged from fresh entry).
                        logger.debug(
                            "Serving recovery request with no prior workflow checkpoint; replaying original input"
                        )
                        run_stream = self._agent.run(
                            input_messages,
                            stream=True,
                            checkpoint_storage=checkpoint_storage,
                        )
            else:
                # Determine the latest checkpoint (if any) so we can resume the
                # workflow's prior state for this turn. The directory is keyed by
                # the conversation id or the previous response id.
                previous_response_id = request.get("previous_response_id")
                if previous_response_id is not None and context.conversation_id is not None:
                    raise RuntimeError("Previous response ID cannot be used in conjunction with conversation ID.")
                checkpoint_load_id = context.conversation_id or previous_response_id
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
                    # A previous_response_id must have a prior workflow checkpoint to resume from
                    raise RuntimeError(
                        f"Cannot find an existing workflow checkpoint for previous_response_id={previous_response_id}."
                    )

                if latest_checkpoint is not None:
                    # If we have a prior checkpoint, restore it first (drive the workflow
                    # back to idle with prior state intact), then make a separate call that
                    # delivers the new user input. The restore-only call may yield events
                    # from any pending in-flight work in the checkpoint; we consume those
                    # internally here so they don't surface to the response stream as duplicates.
                    #
                    # If the restored checkpoint had pending request_info events, the
                    # restore-only call replays them through
                    # ``WorkflowAgent._convert_workflow_event_to_agent_response_updates``
                    # and populates ``self._agent.pending_requests``. That is the correct
                    # state: those requests are genuinely outstanding, and the next
                    # ``run(input_messages, ...)`` call may contain ``function_call_output``
                    # items (carried as FunctionResult/FunctionApprovalResponse content)
                    # that fulfill them via :meth:`WorkflowAgent._process_pending_requests`.
                    restore_iter = _SignalledIterator(
                        self._agent.run(
                            stream=True,
                            checkpoint_id=latest_checkpoint.checkpoint_id,
                            checkpoint_storage=restore_checkpoint_storage,
                        ),
                        context.shutdown,
                        cancellation_signal,
                    )
                    async with aclosing(restore_iter):
                        async for _ in restore_iter:
                            pass
                    if restore_iter.signalled:
                        if context.shutdown.is_set():
                            await context.exit_for_recovery()
                        if cancellation_signal.is_set():
                            return

                # A cancel signal that fired after the restore-only replay finished (or was never
                # entered) must still preempt starting a brand new workflow run below.
                if cancellation_signal.is_set():
                    return

                run_stream = self._agent.run(
                    input_messages,
                    stream=True,
                    checkpoint_storage=checkpoint_storage,
                )

            main_iter = _SignalledIterator(run_stream, context.shutdown, cancellation_signal)
            async with aclosing(main_iter):
                async for update in main_iter:
                    if self._resilient_background:
                        latest_checkpoint = await checkpoint_storage.get_latest(workflow_name=self._agent.workflow.name)
                        if (
                            latest_checkpoint is not None
                            and latest_checkpoint.checkpoint_id
                            != response_event_stream.internal_metadata.get(_LATEST_CHECKPOINT_ID_KEY)
                        ):
                            # A new checkpoint is created when we pull the next item from the stream
                            # (see RunnerImpl.run_until_convergence). We only take a snapshot of the
                            # response (response_event_stream.checkpoint()) once the checkpoint is
                            # durably persisted. This means all items from the previous superstep
                            # has been pulled thus we can safely close the tracker. The latest checkpoint
                            # now reflects the state of the workflow that matches the response output.
                            # Note that if a workflow crashes before any update is created, no response
                            # snapshot is taken. However, upon recovery the workflow will still be resumed
                            # from the latest checkpoint.
                            for event in tracker.close():
                                yield event
                            response_event_stream.internal_metadata[_LATEST_CHECKPOINT_ID_KEY] = (
                                latest_checkpoint.checkpoint_id
                            )
                            yield response_event_stream.checkpoint()

                    for content in update.contents:
                        async for event in tracker.handle(
                            content, message_id=update.message_id, approval_storage=approval_storage
                        ):
                            yield event
            # Cancellation needs no extra action here (the loop above already stopped); shutdown
            # does, but only if it's what actually stopped the loop, not a natural completion.
            if main_iter.signalled and context.shutdown.is_set():
                await context.exit_for_recovery()
        except Exception:
            logger.exception("Failed to produce response for workflow agent")
            raise

    async def _resume_workflow_from_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_storage: CheckpointStorage,
        response_id: str,
    ) -> AsyncGenerator[AgentResponseUpdate]:
        """Resume a crashed background workflow run, forwarding every event it produces.

        ``WorkflowAgent.run(checkpoint_id=..., messages=None)`` treats a message-less resume as
        "restore only": it drives the workflow with the checkpoint's own already-queued internal
        messages, but silently discards every event produced while doing so, on the assumption
        that the workflow merely settles back to idle awaiting the next turn's input. That
        assumption doesn't hold for crash recovery: the countdown (and any other self-driving
        workflow) genuinely continues -- and may run to completion -- from its own queued
        messages, and that output must not be lost. Drive the underlying ``Workflow`` directly so
        none of it is discarded, converting each event the same way ``WorkflowAgent.run`` does.

        TODO(@taochen): #7677
        """
        if not isinstance(self._agent, WorkflowAgent):
            raise RuntimeError("Agent is not a workflow agent.")
        agent = self._agent
        async for event in agent.workflow.run(
            stream=True,
            checkpoint_id=checkpoint_id,
            checkpoint_storage=checkpoint_storage,
        ):
            for update in agent._convert_workflow_event_to_agent_response_updates(  # pyright: ignore[reportPrivateUsage]
                response_id, event
            ):
                yield update

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
        yield response_event_stream.emit_failed(message=message, usage=tracker.usage if tracker is not None else None)


# endregion ResponsesHostServer

# region Active Builder State


class _OutputItemTracker:
    """Converts a stream of agent ``Content`` into ``ResponseStreamEvent``s for one response.

    For content types that arrive as a series of deltas (text, reasoning, function calls, MCP
    calls) it tracks the single currently-open output item builder, merging consecutive same-item
    deltas and closing the builder (emitting its `*_done` events) as soon as a different item
    starts. All other content types (function results, image generation, shell calls/results,
    approval requests, etc.) are emitted in one shot, closing any still-open streaming item first.
    """

    def __init__(self, stream: ResponseEventStream) -> None:
        self._stream = stream
        self._usage_details: UsageDetails | None = None
        self._active_type: str | None = None
        self._active_id: str | None = None
        # message_id of the update that opened the active text item, used to detect a new
        # logical message (e.g. a fresh workflow yield_output call) even when the content
        # type doesn't change, so it isn't silently merged into the still-open item.
        self._active_message_id: str | None = None
        # Accumulated delta text for the current active builder
        self._accumulated: list[str] = []
        # Builder state — only one is active at a time
        self._message_item: OutputItemMessageBuilder | None = None
        self._text_content: TextContentBuilder | None = None
        self._refusal_content: RefusalContentBuilder | None = None
        self._reasoning_item: OutputItemBuilder | None = None
        self._summary_part: ReasoningSummaryPartBuilder | None = None
        self._reasoning_encrypted_content: str | None = None
        self._fc_builder: OutputItemFunctionCallBuilder | None = None
        self._mcp_builder: OutputItemMcpCallBuilder | None = None
        self._outstanding_function_calls: dict[str, str | None] = {}
        self._oauth_consent_requests: set[tuple[str, str]] = set()
        for item in stream.response.get("output", []):
            if not isinstance(item, Mapping):
                continue
            persisted_item = cast(Mapping[str, Any], item)
            if persisted_item.get("type") != "oauth_consent_request":
                continue
            consent_link = persisted_item.get("consent_link")
            server_label = persisted_item.get("server_label")
            if isinstance(consent_link, str) and isinstance(server_label, str):
                self._oauth_consent_requests.add((consent_link, server_label))

    @property
    def usage(self) -> ResponseUsage | None:
        """Return accumulated usage in the Responses API schema."""
        if self._usage_details is None:
            return None

        input_tokens = int(self._usage_details.get("input_token_count") or 0)
        output_tokens = int(self._usage_details.get("output_token_count") or 0)
        total_tokens = self._usage_details.get("total_token_count")
        return ResponseUsage(
            input_tokens=input_tokens,
            input_tokens_details=ResponseUsageInputTokensDetails(
                cached_tokens=int(self._usage_details.get("cache_read_input_token_count") or 0),
                cache_write_tokens=int(self._usage_details.get("cache_creation_input_token_count") or 0),
            ),
            output_tokens=output_tokens,
            output_tokens_details=ResponseUsageOutputTokensDetails(
                reasoning_tokens=int(self._usage_details.get("reasoning_output_token_count") or 0)
            ),
            total_tokens=int(total_tokens) if total_tokens is not None else input_tokens + output_tokens,
        )

    @property
    def oauth_consent_requested(self) -> bool:
        """Return whether this response emitted an OAuth consent request."""
        return bool(self._oauth_consent_requests)

    async def handle(
        self,
        content: Content,
        message_id: str | None = None,
        *,
        approval_storage: FunctionApprovalStore | None = None,
    ) -> AsyncGenerator[ResponseStreamEvent]:
        """Process a content item, yielding its events.

        Args:
            content: The content item to process.
            message_id: The ``message_id`` of the update ``content`` came from, if any. A
                change in ``message_id`` across otherwise same-typed text content marks a new
                logical message and forces the previous output item closed, rather than being
                merged into it.
            approval_storage: Used for content types that fall back to one-shot emission
                (anything not recognized as a streaming delta type) to save/load approval requests.
        """
        if _is_refusal_text_content(content) and content.text is not None:
            for event in self._ensure_message_content("refusal", message_id):
                yield event
            self._active_message_id = message_id
            self._accumulated.append(content.text)
            if self._refusal_content is not None:
                yield self._refusal_content.emit_delta(content.text)

        elif content.type == "text" and content.text is not None:
            for event in self._ensure_message_content("text", message_id):
                yield event
            self._active_message_id = message_id
            self._accumulated.append(content.text)
            if self._text_content is not None:
                yield self._text_content.emit_delta(content.text)

        elif content.type == "text_reasoning":
            if self._active_type != "text_reasoning" or (content.id is not None and content.id != self._active_id):
                for event in self._close():
                    yield event
                for event in self._open_reasoning(content):
                    yield event
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
                for event in self._close():
                    yield event
                for event in self._open_function_call(content):
                    yield event
            args_str = _json_safe_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._fc_builder is not None:
                yield self._fc_builder.emit_arguments_delta(args_str)

        elif content.type == "function_result":
            for event in self._close():
                yield event
            async for event in self._stream.output_item_function_call_output(
                content.call_id,  # type: ignore[arg-type]
                _json_safe_to_str(content.result),
            ):
                yield event
            if content.call_id is not None:
                self._outstanding_function_calls.pop(content.call_id, None)

        elif content.type == "mcp_server_tool_call" and content.tool_name:
            key = content.call_id or f"{content.server_name or 'default'}::{content.tool_name}"
            if self._active_type != "mcp_server_tool_call" or self._active_id != key:
                for event in self._close():
                    yield event
                for event in self._open_mcp_call(content):
                    yield event
            args_str = _json_safe_to_str(content.arguments)
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
            return

        elif content.type == "image_generation_tool_result" and content.outputs is not None:
            for event in self._close():
                yield event
            async for event in self._stream.output_item_image_gen_call(str(content.outputs)):
                yield event

        elif content.type == "mcp_server_tool_call":
            # Reached only when `content.tool_name` is falsy (the streaming branch above didn't match).
            for event in self._close():
                yield event
            mcp_call = self._stream.add_output_item_mcp_call(
                server_label=content.server_name or "default",
                name=content.tool_name or "",
                item_id=content.call_id,
            )
            yield mcp_call.emit_added()
            async for event in mcp_call.arguments(_json_safe_to_str(content.arguments)):
                yield event
            yield mcp_call.emit_completed()
            yield mcp_call.emit_done()

        elif content.type == "mcp_server_tool_result":
            # Reached when there's no correlated in-progress mcp_server_tool_call to close against.
            for event in self._close():
                yield event
            output = _stringify_mcp_output(content.output)
            async for event in self._stream.output_item_custom_tool_call_output(content.call_id or "", output):
                yield event

        elif content.type == "shell_tool_call":
            for event in self._close():
                yield event
            action = FunctionShellAction(
                commands=content.commands or [],
                timeout_ms=content.timeout_ms,
                max_output_length=content.max_output_length,
            )
            async for event in self._stream.output_item_function_shell_call(
                content.call_id or "",
                action,
                LocalEnvironmentResource(type="local"),
                status=content.status or "completed",
            ):
                yield event

        elif content.type == "shell_tool_result":
            for event in self._close():
                yield event
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
            async for event in self._stream.output_item_function_shell_call_output(
                content.call_id or "",
                output_items,
                status=content.status or "completed",
                max_output_length=content.max_output_length,
            ):
                yield event

        elif content.type == "function_approval_request":
            for event in self._close():
                yield event
            function_call: Content = content.function_call  # type: ignore
            server_label = function_call.additional_properties.get("server_label", "agent_framework")
            request_saved = False
            async for event in self._stream.output_item_mcp_approval_request(
                server_label,
                function_call.name,  # type: ignore
                _json_safe_to_str(function_call.arguments),
            ):
                if approval_storage is not None and not request_saved:
                    # Extract the approval request ID generated by the infrastructure when the
                    # approval request item is added to the stream, and save it to approval
                    # storage so it can be retrieved later for round trips.
                    item = event.get("item") if isinstance(event, Mapping) else getattr(event, "item", None)
                    approval_request_id = (
                        cast(Mapping[str, Any], item).get("id")
                        if isinstance(item, Mapping)
                        else getattr(item, "id", None)
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

        elif content.type == "oauth_consent_request":
            for event in self._close():
                yield event

            consent_link = content.consent_link
            if not _is_safe_oauth_consent_link(consent_link):
                raise ValueError("OAuth consent request content must include a safe HTTPS consent link.")

            server_label = content.additional_properties.get("server_label")
            if not isinstance(server_label, str) or not server_label:
                server_label = getattr(content.raw_representation, "server_label", None)
            if not isinstance(server_label, str) or not server_label:
                server_label = "agent_framework"

            consent_key = (consent_link, server_label)
            if consent_key in self._oauth_consent_requests:
                return
            self._oauth_consent_requests.add(consent_key)

            oauth_item = OAuthConsentRequestOutputItem(
                id=IdGenerator.new_id("oacr"),
                response_id=str(self._stream.response["id"]),
                type="oauth_consent_request",
                consent_link=consent_link,
                server_label=server_label,
            )
            builder = self._stream.add_output_item(oauth_item["id"])
            yield builder.emit_added(oauth_item)
            yield builder.emit_done(oauth_item)

        elif content.type == "usage":
            self._usage_details = add_usage_details(self._usage_details, content.usage_details)

        else:
            for event in self._close():
                yield event
            # Defensive: covers content types not recognized above (e.g. "text"/"text_reasoning"/
            # "function_call" with missing required fields), logged instead of raised so the
            # response stream isn't broken by one unsupported content item.
            logger.warning(f"Content type '{content.type}' is not supported yet. This is usually safe to ignore.")

    def close(self) -> Generator[ResponseStreamEvent]:
        """Close any remaining active builder."""
        yield from self._close()

    # -- Private open/close helpers --

    def _ensure_message_content(
        self,
        content_type: Literal["text", "refusal"],
        message_id: str | None,
    ) -> Generator[ResponseStreamEvent]:
        message_changed = (
            message_id is not None and self._active_message_id is not None and message_id != self._active_message_id
        )
        if self._active_type == content_type and not message_changed:
            return
        if self._message_item is not None and self._active_type in {"text", "refusal"} and not message_changed:
            yield from self._close_message_content()
            yield from self._open_message_content(content_type)
            return
        yield from self._close()
        yield from self._open_message(content_type)

    def _open_message(self, content_type: Literal["text", "refusal"]) -> Generator[ResponseStreamEvent]:
        self._message_item = self._stream.add_output_item_message()
        yield self._message_item.emit_added()
        yield from self._open_message_content(content_type)

    def _open_message_content(
        self,
        content_type: Literal["text", "refusal"],
    ) -> Generator[ResponseStreamEvent]:
        if self._message_item is None:
            raise RuntimeError("Cannot open message content without an active message")
        self._active_type = content_type
        self._active_id = None
        if content_type == "refusal":
            self._refusal_content = self._message_item.add_refusal_content()
            yield self._refusal_content.emit_added()
        else:
            self._text_content = self._message_item.add_text_content()
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
        if self._active_type in {"text", "refusal"}:
            yield from self._close_message_content()
            if self._message_item is not None:
                yield self._message_item.emit_done()
            self._message_item = None

        elif self._active_type == "text_reasoning" and self._summary_part and self._reasoning_item:
            accumulated = "".join(self._accumulated)
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
            accumulated = "".join(self._accumulated)
            yield self._fc_builder.emit_arguments_done(accumulated)
            yield self._fc_builder.emit_done()
            self._fc_builder = None

        elif self._active_type == "mcp_server_tool_call" and self._mcp_builder:
            accumulated = "".join(self._accumulated)
            yield self._mcp_builder.emit_arguments_done(accumulated)
            yield self._mcp_builder.emit_completed()
            yield self._mcp_builder.emit_done()
            self._mcp_builder = None

        self._active_type = None
        self._active_id = None
        self._active_message_id = None
        self._accumulated.clear()

    def _close_message_content(self) -> Generator[ResponseStreamEvent]:
        accumulated = "".join(self._accumulated)
        if self._active_type == "text" and self._text_content is not None:
            yield self._text_content.emit_text_done(accumulated)
            yield self._text_content.emit_done()
            self._text_content = None
        elif self._active_type == "refusal" and self._refusal_content is not None:
            yield self._refusal_content.emit_refusal_done(accumulated)
            yield self._refusal_content.emit_done()
            self._refusal_content = None
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


async def _item_to_message(
    item: Item,
    *,
    approval_storage: FunctionApprovalStore | None = None,
    _item_type_name: Literal["Item", "OutputItem"] = "Item",
) -> Message:
    """Converts an Item to a Message.

    Args:
        item: The Item to convert.
        approval_storage: An optional ApprovalStorage instance used to look up
            approval requests when converting MCP approval response items.
        _item_type_name: The item type name to include in unsupported-type errors.

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
        call_id = item.get("call_id")
        if call_id is None:
            raise ValueError("Function call output item is missing a call_id.")
        return Message(
            role="tool",
            contents=[Content.from_function_result(call_id, result=_json_safe_to_str(item["output"]))],
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
                    timeout_ms=item["action"].get("timeout_ms"),
                    max_output_length=item["action"].get("max_output_length"),
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
                    timeout_ms=item["action"].get("timeout_ms"),
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
                    arguments=_json_safe_to_str({"queries": item["queries"]}),
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
                    arguments=_json_safe_to_str(item.get("action")),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "computer_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=_json_safe_to_str(item["output"]))],
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
        output = _json_safe_to_str(item["output"])
        # Hosted-MCP results land here because the host writes them via
        # `aoutput_item_custom_tool_call_output` (see `_OutputItemTracker.handle` for
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
                    arguments=_json_safe_to_str(item["operation"]),
                    informational_only=True,
                )
            ],
        )

    if item["type"] == "apply_patch_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=_json_safe_to_str(item.get("output")))],
        )

    raise ValueError(f"Unsupported {_item_type_name} type: {item['type']}")


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
    if item["type"] == "oauth_consent_request":
        return Message(
            role="assistant",
            contents=[Content.from_oauth_consent_request(item["consent_link"])],
        )

    if item["type"] == "structured_outputs":
        return Message(role="assistant", contents=[Content.from_text(_json_safe_to_str(item["output"]))])

    return await _item_to_message(
        cast(Item, item),
        approval_storage=approval_storage,
        _item_type_name="OutputItem",
    )


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
        return Content.from_text(
            content["refusal"],
            additional_properties={_MODEL_OUTPUT_KIND_KEY: _MODEL_OUTPUT_REFUSAL},
        )

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
        return Content.from_text(
            content["refusal"],
            additional_properties={_MODEL_OUTPUT_KIND_KEY: _MODEL_OUTPUT_REFUSAL},
        )
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


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return str(value)


def _json_safe_to_str(value: Any | None) -> str:
    """Convert an argument or result value to a JSON-safe string.

    Args:
        value: The value to convert, which can be a string, JSON-like object, or None.

    Returns:
        The value as a JSON string.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=_json_default)
    except (TypeError, ValueError):
        return json.dumps(str(value))


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


def _mcp_mapping_text(output: Mapping[Any, Any]) -> str | None:
    """Extract text only from a recognized MCP text-content mapping."""
    text = output.get("text")
    if not isinstance(text, str):
        return None
    if output.get("type") == "text" or set(output) == {"text"}:
        return text
    return None


def _stringify_mcp_output(output: Any) -> str:
    """Convert hosted MCP output payloads into the string shape expected by mcp_call.output."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        mapping = cast(Mapping[Any, Any], output)
        if (text := _mcp_mapping_text(mapping)) is not None:
            return text
        return _json_safe_to_str(mapping)
    if isinstance(output, Sequence) and not isinstance(output, (str, bytes, bytearray)):
        parts: list[str] = []
        entries = cast(Sequence[Any], output)
        for entry in entries:
            if isinstance(entry, str):
                parts.append(entry)
                continue
            if isinstance(entry, Content) and entry.type == "text":
                parts.append(entry.text or "")
                continue
            if isinstance(entry, Mapping) and (text := _mcp_mapping_text(cast(Mapping[Any, Any], entry))) is not None:
                parts.append(text)
                continue
            return _json_safe_to_str(entries)
        return "".join(parts)
    return _json_safe_to_str(output)


# endregion
