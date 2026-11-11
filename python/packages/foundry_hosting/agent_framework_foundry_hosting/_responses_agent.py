# Copyright (c) Microsoft. All rights reserved.

"""Host session-owned agents through the Responses protocol."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    Generator,
    Mapping,
    Sequence,
)
from contextlib import AbstractAsyncContextManager, AsyncExitStack, aclosing, suppress
from copy import copy
from dataclasses import dataclass
from typing import Any, Literal, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    ChatOptions,
    ContextProvider,
    FinishReason,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    ResponseStream,
    SessionStore,
    SupportsAgentRun,
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
    OAuthConsentRequestOutputItem,
    ResponseStreamEvent,
)
from azure.ai.agentserver.responses.streaming._checkpoint import ResponseCheckpointEvent

from ._feature_usage import FeatureIndex
from ._responses_shared import (
    _HOSTED_CONVERSATION_CLAIM_KEY,  # pyright: ignore[reportPrivateUsage]
    _HOSTED_CONVERSATION_COMMITTED_KEY,  # pyright: ignore[reportPrivateUsage]
    _HOSTED_PROVIDER_OUTPUT_COUNT_KEY,  # pyright: ignore[reportPrivateUsage]
    _HOSTED_PROVIDER_STATE_KEY,  # pyright: ignore[reportPrivateUsage]
    _HOSTED_PROVIDER_USAGE_KEY,  # pyright: ignore[reportPrivateUsage]
    _HOSTED_SERVICE_CHILD_KEY,  # pyright: ignore[reportPrivateUsage]
    _HOSTED_SOURCE_CONVERSATION_KEY,  # pyright: ignore[reportPrivateUsage]
    _PUBLIC_STREAM_FAILURE_MESSAGE,  # pyright: ignore[reportPrivateUsage]
    _agent_response_updates,  # pyright: ignore[reportPrivateUsage]
    _await_before_signal,  # pyright: ignore[reportPrivateUsage]
    _create_response_event_stream,  # pyright: ignore[reportPrivateUsage]
    _hosted_internal_metadata,  # pyright: ignore[reportPrivateUsage]
    _is_allowed_oauth_consent_link,  # pyright: ignore[reportPrivateUsage]
    _items_to_messages,  # pyright: ignore[reportPrivateUsage]
    _log_response_failure,  # pyright: ignore[reportPrivateUsage]
    _normalize_allowed_oauth_consent_origins,  # pyright: ignore[reportPrivateUsage]
    _output_items_to_messages,  # pyright: ignore[reportPrivateUsage]
    _OutputItemTracker,  # pyright: ignore[reportPrivateUsage]
    _PublicResponseFailure,  # pyright: ignore[reportPrivateUsage]
    _reject_busy_conversation,  # pyright: ignore[reportPrivateUsage]
    _set_agent_session,  # pyright: ignore[reportPrivateUsage]
    _SignalledIterator,  # pyright: ignore[reportPrivateUsage]
    consent_url_from_error,
)
from ._scope import FoundryRequestScope
from ._shared import (
    AgentSource,
    OptionsHook,
    ResponsesRequest,
    UnsupportedOptions,
    build_response_server_options,
    is_agent,
    prepare_response_options,
    reject_removed_host_settings,
    resolve_agent,
    response_run_options,
    validate_agent_background_options,
    validate_agent_source,
    validate_default_transport_options,
    validate_request_options,
    validate_unsupported_options,
)
from ._state_store import (
    AgentSessionStoreProvider,
    FunctionApprovalStore,
    FunctionApprovalStoreProvider,
    StoreProvider,
)

logger = logging.getLogger(__name__)


_HOSTED_RESPONSES_HISTORY_SOURCE_ID = "_foundry_responses_history"

_HistorySource = Literal["host_managed", "agent_managed", "inference_service"]


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


@dataclass(frozen=True)
class _AgentConfiguration:
    agent_server_history: bool
    client_stores_by_default: bool
    hosted_history: bool


def _validate_agent_defaults(
    agent: SupportsAgentRun, *, provider_background: bool, allow_agent_store: bool
) -> None:
    validate_agent_background_options(agent, provider_background=provider_background)
    if isinstance(agent, RawAgent):
        validate_default_transport_options(agent.default_options, allow_agent_store=allow_agent_store)


def _validate_agent_configuration(
    agent: SupportsAgentRun,
    history_source: _HistorySource,
    options: ResponsesServerOptions | None,
    *,
    background_source: Literal["host_managed", "inference_service"] = "host_managed",
) -> _AgentConfiguration:
    resilient_background = bool(options and options.resilient_background)
    if resilient_background and background_source != "inference_service":
        raise RuntimeError(
            "resilient_background=True requires background_source='inference_service' for regular agents. "
            "Use ResponsesWorkflowHostServer for checkpoint-based workflow recovery."
        )
    if background_source == "inference_service" and (
        not isinstance(agent, RawAgent) or getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None) is not True
    ):
        raise RuntimeError("Provider background requires a RawAgent with a storing, resumable Responses client.")
    if isinstance(agent, RawAgent):
        identity_defaults = ("session_id", "agent_session_id", "user_id", "call_id", "service_session_id")
        if conflicting := [name for name in identity_defaults if agent.default_options.get(name) is not None]:
            raise RuntimeError(f"Model defaults cannot supply Foundry platform identity: {', '.join(conflicting)}.")

    uses_agent_server_history = history_source == "host_managed"
    client_stores_by_default = False
    if history_source != "agent_managed":
        if not isinstance(agent, RawAgent):
            raise RuntimeError(
                "history_source='host_managed' and 'inference_service' require a RawAgent so hosting can enforce "
                "downstream storage. Use history_source='agent_managed' for a custom SupportsAgentRun implementation "
                "on stored requests."
            )

        stores_by_default = getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None)
        if not isinstance(stores_by_default, bool):
            raise RuntimeError(
                "history_source='host_managed' or 'inference_service' requires the chat client to declare "
                "STORES_BY_DEFAULT so hosting can enforce downstream storage behavior."
            )
        client_stores_by_default = stores_by_default

        if history_source == "inference_service" and not stores_by_default:
            raise RuntimeError(
                "history_source='inference_service' requires a storing client that declares STORES_BY_DEFAULT=True."
            )

        service_continuation_options = [
            name
            for name in ("conversation_id", "previous_response_id", "conversation", "continuation_token", "response_id")
            if agent.default_options.get(name) is not None
        ]
        if service_continuation_options:
            raise RuntimeError(
                f"history_source='host_managed' or 'inference_service' cannot use developer defaults for downstream "
                f"continuation: {', '.join(service_continuation_options)}. "
                "Use history_source='agent_managed' to retain developer-controlled continuation."
            )

        if history_source in ("host_managed", "inference_service"):
            for provider in agent.context_providers:
                if isinstance(provider, HistoryProvider) and provider.load_messages:
                    if history_source == "host_managed" and _is_hosted_responses_history_sentinel(provider):
                        continue
                    raise RuntimeError(
                        "The selected history_source conflicts with a load-enabled HistoryProvider. "
                        "Remove that provider or select history_source='agent_managed'."
                    )
        if history_source == "host_managed" and not stores_by_default and agent.default_options.get("store") is True:
            raise RuntimeError(
                "The chat client does not store by default, but the agent sets a downstream store option. "
                "Remove that developer-owned default rather than letting hosting change it."
            )

    return _AgentConfiguration(
        agent_server_history=uses_agent_server_history,
        client_stores_by_default=client_stores_by_default,
        hosted_history=uses_agent_server_history,
    )


def _initialize_agent_history(agent: SupportsAgentRun, configuration: _AgentConfiguration) -> None:
    if not configuration.hosted_history or not isinstance(agent, RawAgent):
        return
    if not any(
        _is_hosted_responses_history_sentinel(provider)
        for provider in cast(Sequence[ContextProvider], agent.context_providers)
    ):
        agent.context_providers.append(InMemoryHistoryProvider(source_id=_HOSTED_RESPONSES_HISTORY_SOURCE_ID))


class ResponsesHostServer(ResponsesAgentServerHost):
    """Host an agent through the Responses protocol."""

    def __init__(
        self,
        agent: AgentSource[ResponsesRequest],
        *,
        prefix: str = "",
        response_store: ResponseProviderProtocol | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        function_approval_store_provider: StoreProvider[FunctionApprovalStore] | None = None,
        allowed_oauth_consent_origins: Sequence[str] | None = None,
        history_source: Literal["host_managed", "agent_managed", "inference_service"] = "host_managed",
        background_source: Literal["host_managed", "inference_service"] = "host_managed",
        max_history_items: int | None = None,
        sse_keep_alive_interval_seconds: int | None = None,
        shutdown_grace_period_seconds: int = 10,
        enable_background_recovery: bool = False,
        prepare_options: OptionsHook | None = None,
        unsupported_options: UnsupportedOptions = "warn",
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for, or a sync/async callable that creates one for each request.
                Factories must declare a required parameter named `request`, accepting a `ResponsesRequest`
                passed by keyword. Extra parameters must have defaults. The factory may ignore the request.
                Factories run before `prepare_options`; the request exposes trusted scope,
                this turn's input, and translated caller options before that hook. Use a callable for agents
                that keep mutable state outside `AgentSession`.
                `WorkflowAgent` instances and factory results are rejected. Use `ResponsesWorkflowHostServer`
                with a native workflow factory instead.
            prefix: The URL prefix for the server.
            response_store: Optional response store for caller-facing persistence and history.
            agent_session_store_provider: Optional provider for MAF agent session storage.
                If not provided, a default `AgentSessionStoreProvider` will be used.
            function_approval_store_provider: Optional provider for function approval storage.
                If not provided, a default `FunctionApprovalStoreProvider` will be used.
            allowed_oauth_consent_origins: Optional exact HTTPS origins allowed for OAuth consent links.
                When omitted, hosting retains its existing safe-HTTPS validation without restricting the
                destination origin. When provided, every link must match an entry; an empty sequence rejects
                every link. Entries must be origins such as `"https://auth.example.com"` and must not include
                a path, query, or fragment.
            history_source: Who supplies prior messages to the *model*, independently of the caller's
                Responses `store` flag. Defaults to `"host_managed"`:

                - `"host_managed"`: Send the prior outer Responses transcript followed by this request's input.
                  For a storing chat client, force its per-run `store=False` and clear any restored
                  `service_session_id` to avoid replaying that transcript twice. A load-enabled
                  `HistoryProvider` or fixed downstream continuation default conflicts with this mode.
                - `"inference_service"`: Send only this request's input. On caller `store=True`, run the inner
                  client with `store=True` and save its issued `service_session_id` in the host's
                  private MAF session store. The next stored request resumes that provider thread;
                  it must not branch an already-used provider conversation.
                - `"agent_managed"`: Send only this request's input and preserve the agent's developer-owned
                  storage choice on stored requests. With an `InMemoryHistoryProvider` and
                  `default_options={"store": False}`, the provider loads prior messages from
                  the host-persisted MAF `AgentSession`. With `default_options={"store": True}`,
                  the downstream service retains history instead.

                For example, after a stored response to "My name is Ada", a stored follow-up
                "What is my name?" sends both turns to the model with `"host_managed"`, but
                sends only the follow-up with `"inference_service"` (plus a private service continuation).
                With `"agent_managed"`, the developer chooses either of those agent-owned history sources.
            background_source: `"host_managed"` (default) runs background work in the Responses host
                without invoking provider-native background APIs; `"inference_service"` opts a storing, resumable
                client into provider background polling and requires `history_source="inference_service"`.
                Each poll retains the caller's run options and `background=True`; local tools must be
                idempotent because a crash before the next private token is saved can replay them.
            max_history_items: Positive outer history limit for host-managed history. `None` leaves the
                installed SDK default unchanged; it does not mean unlimited.
            sse_keep_alive_interval_seconds: Positive streaming heartbeat interval. If omitted, the SDK
                uses a positive `SSE_KEEPALIVE_INTERVAL` environment value, or disables heartbeats.
            shutdown_grace_period_seconds: Positive shutdown wait. The SDK also uses this duration when
                DELETE waits for response persistence. Defaults to 10 seconds.
            enable_background_recovery: Allow eligible provider-background work to recover after shutdown.
                Defaults to `False`; it does not enable background execution or guarantee exactly-once effects.
            prepare_options: Developer hook to remove or replace caller model options for an agent.
            unsupported_options: `"warn"` (default), `"error"`, or `"ignore"` when a custom agent
                cannot accept runtime model options.
            **kwargs: Additional keyword arguments.

        Note:
            The *caller* controls outer persistence with `POST /responses` `store=True/False`.
            `store=False` writes no host-managed session or approval state and forces supported
            inner clients not to store, regardless of `history_source`. The constructor's
            `response_store=` argument selects the outer response-store backend.
            The former constructor `store=` alias is rejected. Outer `response.id` is the polling/continuation handle;
            any inner `service_session_id` is private and never replaces it.

            1. With `history_source="host_managed"`,
               the agent must not have a load-enabled history provider: the host supplies the transcript.
            2. Context providers must not keep required state only on their Python instances,
               because the hosting environment may get deactivated between requests. Provider
               state carried by `AgentSession`, including `InMemoryHistoryProvider` messages in
               `history_source="agent_managed"` mode, is persisted by the configured session store.
            3. The server owns the supplied agent instance and may add hosting-specific providers.
               Do not reuse the same agent with another host or invoke it directly after construction.
               An agent returned by a callable belongs to that request.
            4. `enable_background_recovery=True` supports regular agents configured with
               `history_source="inference_service", background_source="inference_service"`.
               For provider background, only a saved private continuation token can be polled after a crash;
               a crash before the token is saved cannot be replayed safely.
               Other regular-agent runs are not crash-recoverable.
            5. Steering is unavailable. The upstream `options` bag and steering settings are not host parameters.
            6. A stored, named `"inference_service"` or `"agent_managed"` conversation is claimed in the scoped
               session store before the agent runs. Conditional writes prevent a concurrent turn from mutating the same
               provider thread. If the turn fails or is cancelled, start a new conversation instead of
               reusing a potentially changed downstream thread.

        Raises:
            TypeError: If the agent is a `WorkflowAgent`, or native workflow settings are supplied.
            ValueError: If the history, background, or unsupported-options policy is invalid.
            RuntimeError: If the agent configuration conflicts with the selected history or background source.
        """
        reject_removed_host_settings(kwargs)
        if "store" in kwargs:
            raise TypeError("The constructor store= alias was removed; use response_store= instead.")
        if {"workflow", "parse_input", "parse_response", "checkpoint_store_provider"}.intersection(kwargs):
            raise TypeError("Use ResponsesWorkflowHostServer for native workflows and checkpoint storage.")
        validate_agent_source(agent)
        if prepare_options is not None and not callable(prepare_options):
            raise TypeError("prepare_options must be a callable.")
        unsupported_options = validate_unsupported_options(unsupported_options)
        options = build_response_server_options(
            is_workflow=False,
            history_source=history_source,
            background_source=background_source,
            max_history_items=max_history_items,
            sse_keep_alive_interval_seconds=sse_keep_alive_interval_seconds,
            shutdown_grace_period_seconds=shutdown_grace_period_seconds,
            enable_background_recovery=enable_background_recovery,
        )

        resolved_agent = agent if is_agent(agent) else None
        if resolved_agent is not None:
            _validate_agent_defaults(
                resolved_agent,
                provider_background=background_source == "inference_service",
                allow_agent_store=history_source == "agent_managed",
            )
        configuration = (
            _validate_agent_configuration(resolved_agent, history_source, options, background_source=background_source)
            if resolved_agent is not None
            else None
        )

        # No caller-owned agent state is mutated until all validation and base-host construction succeed.
        self._allowed_oauth_consent_origins = _normalize_allowed_oauth_consent_origins(allowed_oauth_consent_origins)
        super().__init__(
            prefix=prefix,
            options=options,
            store=response_store,
            **kwargs,
        )
        self._agent_source = agent
        self._agent = resolved_agent
        self._configuration = configuration
        self._history_source: _HistorySource = history_source
        self._background_source: Literal["host_managed", "inference_service"] = background_source
        self._prepare_options = prepare_options
        self._unsupported_options = unsupported_options
        self._host_options = options
        self._uses_agent_server_history = (
            configuration.agent_server_history if configuration is not None else history_source == "host_managed"
        )
        self._resilient_background = enable_background_recovery
        if resolved_agent is not None and configuration is not None:
            _initialize_agent_history(resolved_agent, configuration)

        # Storage providers
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
            agent = self._agent
            if agent is None:
                raise RuntimeError("A request-scoped agent cannot use the server-lifetime initialization path.")
            stack = AsyncExitStack()
            try:
                if isinstance(agent, AbstractAsyncContextManager):
                    await stack.enter_async_context(cast(AbstractAsyncContextManager[Any], agent))
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
        response_event_stream = _create_response_event_stream(context, request)
        if context.is_steered_turn:
            logger.debug("Serving steered turn (pending_input_count=%d)", context.pending_input_count)
        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        terminal_event: ResponseStreamEvent | None = None
        try:
            try:
                scope = FoundryRequestScope.from_context(
                    self.config, get_request_context(), local_session_id=context.response_id
                )
            except (TypeError, ValueError, RuntimeError) as exc:
                raise _PublicResponseFailure(exc) from None
            try:
                hosted_request = ResponsesRequest(request, context, scope, response_run_options(request))
            except (TypeError, ValueError) as exc:
                raise _PublicResponseFailure(exc) from None
            agent = await resolve_agent(self._agent_source, hosted_request)
            try:
                provider_background = (
                    self._background_source == "inference_service" and request.get("background") is True
                )
                _validate_agent_defaults(
                    agent,
                    provider_background=provider_background,
                    allow_agent_store=self._history_source == "agent_managed" and request.get("store") is not False,
                )
                configuration = self._configuration or _validate_agent_configuration(
                    agent, self._history_source, self._host_options, background_source=self._background_source
                )
            except (TypeError, ValueError, RuntimeError) as exc:
                raise _PublicResponseFailure(exc) from None
            if self._configuration is None:
                _initialize_agent_history(agent, configuration)
            await prepare_response_options(hosted_request, self._prepare_options)
            try:
                validate_request_options(hosted_request.options)
                _validate_agent_defaults(
                    agent,
                    provider_background=provider_background,
                    allow_agent_store=self._history_source == "agent_managed" and request.get("store") is not False,
                )
            except (TypeError, ValueError) as exc:
                raise _PublicResponseFailure(exc) from None
        except Exception as exc:
            for event in self._emit_failure(
                context.response_id,
                "request preparation",
                response_event_stream,
                None,
                exc,
            ):
                yield event
            return

        async with AsyncExitStack() as resources:
            inner = self._handle_prepared_response(
                request,
                context,
                cancellation_signal,
                response_event_stream,
                agent,
                configuration,
                resources,
                hosted_request,
            )
            try:
                async for event in inner:
                    if isinstance(event, Mapping) and event.get("type") in (
                        "response.completed",
                        "response.incomplete",
                        "response.failed",
                    ):
                        terminal_event = event
                    else:
                        yield event
            finally:
                await inner.aclose()
        if terminal_event is not None:
            yield terminal_event

    async def _handle_prepared_response(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
        response_event_stream: ResponseEventStream,
        agent: SupportsAgentRun,
        configuration: _AgentConfiguration,
        resources: AsyncExitStack,
        hosted_request: ResponsesRequest,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        # Lazy-enter the agent (and any MCP tools it owns). The MCP client wraps gateway
        # consent failures (and other connection-time errors) in AgentFrameworkException; if
        # one of those is a consent error we surface the consent link to the client through
        # the already-opened response stream instead of failing the request. Other exception
        # types fall through to the outer handler below and become ``response.failed``.
        try:
            if self._configuration is not None:
                await self._ensure_agent_ready()
            elif isinstance(agent, AbstractAsyncContextManager):
                await resources.enter_async_context(agent)
        except AgentFrameworkException as ex:
            consent_errors_to_emit = consent_url_from_error(ex)
            if consent_errors_to_emit is None or len(consent_errors_to_emit) == 0:
                for event in self._emit_failure(
                    context.response_id,
                    "agent initialization",
                    response_event_stream,
                    None,
                    ex,
                ):
                    yield event
                return

            invalid_consent = next(
                (
                    consent_error
                    for consent_error in consent_errors_to_emit
                    if not _is_allowed_oauth_consent_link(
                        consent_error.consent_url, self._allowed_oauth_consent_origins
                    )
                ),
                None,
            )
            if invalid_consent is not None:
                validation_error = ValueError(
                    f"OAuth consent request for tool '{invalid_consent.name}' must include an allowed safe HTTPS "
                    "consent link."
                )
                for event in self._emit_failure(
                    context.response_id,
                    "OAuth consent validation",
                    response_event_stream,
                    None,
                    _PublicResponseFailure(validation_error),
                ):
                    yield event
                return

            if request.get("store") is False:
                validation_error = ValueError("OAuth consent continuation requires store=true.")
                for event in self._emit_failure(
                    context.response_id,
                    "OAuth consent validation",
                    response_event_stream,
                    None,
                    _PublicResponseFailure(validation_error),
                ):
                    yield event
                return

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
                        raise _PublicResponseFailure(
                            RuntimeError(
                                "Cannot find an existing agent session for "
                                f"previous_response_id={previous_response_id}."
                            )
                        )
                    session = agent.create_session()
                if context.conversation_id is not None:
                    _reject_busy_conversation(session)
                if previous_response_id is not None and context.conversation_id is None:
                    if session.service_session_id is not None and session.state.get(_HOSTED_SOURCE_CONVERSATION_KEY):
                        raise _PublicResponseFailure(
                            ValueError("A service-managed downstream conversation cannot be forked.")
                        )
                    session.state.pop(_HOSTED_SOURCE_CONVERSATION_KEY, None)
                if context.conversation_id is not None:
                    session.state[_HOSTED_SOURCE_CONVERSATION_KEY] = context.conversation_id
                await _set_agent_session(session_storage, context.response_id, session)
                if context.conversation_id is not None:
                    await _set_agent_session(session_storage, context.conversation_id, session)
            except Exception as save_error:
                for event in self._emit_failure(
                    context.response_id,
                    "OAuth consent session persistence",
                    response_event_stream,
                    None,
                    save_error,
                ):
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

        tracker = _OutputItemTracker(response_event_stream, self._allowed_oauth_consent_origins)
        try:
            inner = self._handle_inner_agent(
                request,
                context,
                response_event_stream,
                tracker,
                cancellation_signal,
                agent,
                configuration,
                hosted_request,
            )

            try:
                async for event in inner:
                    yield event
            except BaseException:
                await inner.aclose()
                raise

            if cancellation_signal.is_set() and context.client_cancelled:
                # A cancelled run drains the inner generator without raising
                # (``_handle_inner_agent`` stops its
                # ``_SignalledIterator`` loop and return normally once the signal fires).
                # Emit nothing here so a caller cannot mistake this for a normal
                # completion; the host server's cancel-aware layer synthesizes the
                # cancelled terminal when the handler returns without one. Gated on
                # ``client_cancelled`` (not just the signal) because steering pressure
                # also sets ``cancellation_signal`` without that cause flag; a steered
                # turn must still drain ``tracker.close()`` and emit its normal terminal
                # below so its partial output is not misreported as a failure.
                return

            for event in tracker.close():
                yield event

            if cancellation_signal.is_set() and context.client_cancelled:
                # Draining ``tracker.close()`` yields events one at a time, and each
                # ``yield`` above suspends this handler until the caller resumes it.
                # A cancellation can arrive during that window, after the earlier check
                # already passed, so it must be rechecked here, immediately before
                # selecting the terminal event. Same ``client_cancelled`` gate as above.
                return

            tracker.discard_pending_container_file_citations()
            incomplete_reason = tracker.incomplete_reason
            if tracker.oauth_consent_requested or incomplete_reason is not None:
                yield response_event_stream.emit_incomplete(reason=incomplete_reason, usage=tracker.usage)
            else:
                yield response_event_stream.emit_completed(usage=tracker.usage)
        except Exception as ex:
            for event in tracker.close():
                yield event

            for event in self._emit_failure(
                context.response_id,
                "response production",
                response_event_stream,
                tracker,
                ex,
            ):
                yield event

    async def _load_request_messages(
        self,
        context: ResponseContext,
        *,
        approval_storage: FunctionApprovalStore | None,
        configuration: _AgentConfiguration | None = None,
    ) -> list[Message]:
        """Load the request's input and prior history concurrently, assembled for the run.

        The caller's input items and the conversation history are independent
        storage round-trips with no data dependency, so they are fetched in
        parallel to remove serial latency from the request critical path. The
        history read is only issued when AgentServer is the history source; in
        stateless single-turn requests it short-circuits without a round-trip.

        Returns the messages already ordered as model input (history precedes
        input), so the message-ordering rule lives only here and callers do not
        need to know the storage-result ordering. If either read fails, the
        sibling task is cancelled and drained so no storage read is orphaned.
        """
        uses_agent_server_history = (
            configuration.agent_server_history if configuration is not None else self._uses_agent_server_history
        )

        async def _load_input() -> list[Message]:
            input_items = await context.get_input_items()
            return await _items_to_messages(input_items, approval_storage=approval_storage)

        async def _load_history() -> list[Message]:
            if not uses_agent_server_history:
                return []
            history = await context.get_history()
            return await _output_items_to_messages(history, approval_storage=approval_storage)

        input_task = asyncio.ensure_future(_load_input())
        history_task = asyncio.ensure_future(_load_history())
        try:
            input_messages, history_messages = await asyncio.gather(input_task, history_task)
        except BaseException:
            # gather surfaces the first failure without cancelling the sibling, and a
            # cancellation of this coroutine must not leave either read running. Cancel
            # both and await them so no storage operation is orphaned after we unwind.
            input_task.cancel()
            history_task.cancel()
            await asyncio.gather(input_task, history_task, return_exceptions=True)
            raise
        return [*history_messages, *input_messages]

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker,
        cancellation_signal: asyncio.Event,
        agent: SupportsAgentRun,
        configuration: _AgentConfiguration,
        hosted_request: ResponsesRequest,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Handle a regular (non-workflow) agent.

        The response stream, tracker, and opening lifecycle events are produced
        by :meth:`_handle_response`, which also converts any raised exception
        into a terminal ``response.failed`` event (draining the tracker so the
        SSE stream stays well-formed).
        """
        provider_background = self._background_source == "inference_service" and request.get("background") is True
        if context.is_recovery and not provider_background:
            raise RuntimeError("A non-resumable agent cannot be replayed after a process crash.")

        stored = request.get("store") is not False

        request_messages_task: asyncio.Task[list[Message]] | None = None
        conversation_already_committed = False
        try:
            if isinstance(agent, RawAgent):
                try:
                    validate_default_transport_options(
                        agent.default_options,
                        allow_agent_store=self._history_source == "agent_managed" and stored,
                    )
                except (TypeError, ValueError) as exc:
                    raise _PublicResponseFailure(exc) from None
            if not stored:
                if not isinstance(agent, RawAgent):
                    raise _PublicResponseFailure(
                        RuntimeError(
                            "store=false cannot guarantee that a custom agent will disable inner storage; "
                            "use a RawAgent or store=true."
                        )
                    )
                continuation_defaults = [
                    name
                    for name in (
                        "conversation_id",
                        "previous_response_id",
                        "conversation",
                        "continuation_token",
                        "response_id",
                    )
                    if agent.default_options.get(name) is not None
                ]
                if continuation_defaults:
                    raise RuntimeError(
                        "store=false cannot use developer defaults for downstream service continuation: "
                        + ", ".join(continuation_defaults)
                    )
                if any(
                    isinstance(provider, HistoryProvider)
                    and not isinstance(provider, InMemoryHistoryProvider)
                    and (provider.store_inputs or provider.store_context_messages or provider.store_outputs)
                    for provider in agent.context_providers
                ):
                    raise _PublicResponseFailure(
                        RuntimeError(
                            "store=false cannot prevent an external HistoryProvider from persisting responses. "
                            "Use an InMemoryHistoryProvider or store=true."
                        )
                    )
                if self._history_source == "agent_managed":
                    stores_by_default = getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None)
                    if not isinstance(stores_by_default, bool):
                        raise RuntimeError(
                            "store=false with history_source='agent_managed' requires a client declaring "
                            "STORES_BY_DEFAULT; "
                            "select history_source='host_managed' or 'inference_service', or use store=true."
                        )
                    if not stores_by_default and agent.default_options.get("store") is True:
                        raise RuntimeError(
                            "store=false with history_source='agent_managed' cannot safely override a storing "
                            "default on a client that does not declare storage support."
                        )

            request_context = get_request_context()
            approval_storage = (
                self._function_approval_storage_provider.get_store(config=self.config, platform_context=request_context)
                if stored
                else None
            )
            previous_response_id = request.get("previous_response_id")
            session_load_id = (
                context.response_id
                if context.is_recovery and provider_background
                else context.conversation_id or previous_response_id
            )
            if not stored and session_load_id is not None and self._history_source == "inference_service":
                raise ValueError(
                    "store=false cannot resume service-managed history; start a new one-shot request "
                    "or use history_source='host_managed' or 'agent_managed'."
                )
            session_storage = (
                self._session_storage_provider.get_store(config=self.config, platform_context=request_context)
                if stored or (session_load_id is not None and self._history_source == "agent_managed")
                else None
            )

            # Load the caller's input items and prior conversation history concurrently with the
            # session load below. These are independent storage round-trips with no data dependency
            # between them, so overlapping them removes serial latency from the request critical path.
            request_messages_task = asyncio.ensure_future(
                self._load_request_messages(
                    context,
                    approval_storage=approval_storage,
                    configuration=configuration,
                )
            )

            session = (
                await session_storage.get(session_load_id)
                if session_storage is not None and session_load_id is not None
                else None
            )
            if session is None:
                if context.is_recovery and provider_background:
                    raise _PublicResponseFailure(
                        RuntimeError("Provider background was interrupted before its continuation token was stored.")
                    )
                if stored and previous_response_id is not None and context.conversation_id is None:
                    raise _PublicResponseFailure(
                        RuntimeError(
                            f"Cannot find an existing agent session for previous_response_id={previous_response_id}."
                        )
                    )
                session = agent.create_session()
            provider_state = session.state.get(_HOSTED_PROVIDER_STATE_KEY)
            if context.conversation_id is not None:
                if context.is_recovery and provider_background:
                    if session_storage is None:
                        raise RuntimeError("Provider background recovery requires agent session storage.")
                    head = await session_storage.get(context.conversation_id)
                    conversation_already_committed = (
                        head is not None
                        and head.state.get(_HOSTED_CONVERSATION_CLAIM_KEY) is None
                        and head.state.get(_HOSTED_CONVERSATION_COMMITTED_KEY) == context.response_id
                        and isinstance(provider_state, Mapping)
                        and cast(Mapping[str, Any], provider_state).get("completed") is True
                    )
                    if not conversation_already_committed and (
                        head is None or head.state.get(_HOSTED_CONVERSATION_CLAIM_KEY) != context.response_id
                    ):
                        raise _PublicResponseFailure(
                            RuntimeError(
                                "Cannot recover provider background: the service-backed conversation claim "
                                "is no longer held by this response."
                            )
                        )
                else:
                    _reject_busy_conversation(session)
            if not stored and self._history_source == "agent_managed" and session.service_session_id is not None:
                raise _PublicResponseFailure(
                    ValueError(
                        "store=false cannot continue agent-managed downstream service history; "
                        "start a new one-shot request or use store=true."
                    )
                )
            if (
                not context.is_recovery
                and provider_state is not None
                and (
                    not isinstance(provider_state, Mapping)
                    or cast(Mapping[str, Any], provider_state).get("completed") is not True
                )
            ):
                raise _PublicResponseFailure(
                    ValueError("A provider background response must complete before the next turn.")
                )
            if previous_response_id is not None and context.conversation_id is None and not context.is_recovery:
                if session.service_session_id is not None and session.state.get(_HOSTED_SOURCE_CONVERSATION_KEY):
                    raise _PublicResponseFailure(
                        ValueError("A service-managed downstream conversation cannot be forked.")
                    )
                if (
                    stored
                    and self._history_source in ("inference_service", "agent_managed")
                    and session.service_session_id is not None
                    and session.state.get(_HOSTED_SERVICE_CHILD_KEY)
                ):
                    raise _PublicResponseFailure(ValueError("A service-managed downstream response cannot be forked."))
        except BaseException as ex:
            # Session preparation failed (or the request was cancelled / the stream closed —
            # neither of which is an Exception). Cancel and drain the in-flight message-loading
            # task so it is not orphaned, and log only ordinary failures.
            if request_messages_task is not None:
                request_messages_task.cancel()
                with suppress(BaseException):
                    await request_messages_task
            if isinstance(ex, Exception):
                _log_response_failure("state storage preparation", context.response_id, ex)
            raise

        request_failure: Exception | None = None
        save_failure: Exception | None = None
        request_interrupted = False

        try:
            if configuration.agent_server_history:
                session.state.pop(_HOSTED_RESPONSES_HISTORY_SOURCE_ID, None)
                # A restored service ID belongs to the downstream model service. Replaying the
                # AgentServer transcript while resuming that service history would duplicate every
                # prior turn, so AgentServer-history mode always starts the model call statelessly.
                session.service_session_id = None

            messages = await request_messages_task
            run_kwargs: dict[str, Any] = {
                "messages": messages,
                "session": session,
            }
            chat_options = dict(hosted_request.options)
            are_options_set = bool(chat_options)
            if self._background_source == "inference_service":
                chat_options["background"] = provider_background
            if configuration.agent_server_history:
                if configuration.client_stores_by_default:
                    # The response provider already owns the transcript used for this run. Keep a
                    # storing downstream service stateless so it cannot become a second history source.
                    chat_options["store"] = False
                else:
                    # Do not pass a storage option to clients that do not advertise support for it.
                    chat_options.pop("store", None)
            elif self._history_source == "inference_service":
                chat_options["store"] = stored
                if not stored:
                    session.service_session_id = None
            elif (
                not stored
                and isinstance(agent, RawAgent)
                and (
                    getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", False)
                    or agent.default_options.get("store") is not None
                )
            ):
                chat_options["store"] = False

            if isinstance(agent, RawAgent):
                run_kwargs["options"] = chat_options
            elif are_options_set:
                if self._unsupported_options == "error":
                    raise _PublicResponseFailure(TypeError("The hosted agent does not accept caller runtime options."))
                if self._unsupported_options == "warn":
                    logger.warning("Agent doesn't support runtime options. They will be ignored.")

            if previous_response_id is not None and context.conversation_id is None and not context.is_recovery:
                if (
                    stored
                    and self._history_source in ("inference_service", "agent_managed")
                    and session.service_session_id is not None
                ):
                    if session_storage is None:
                        raise RuntimeError("Service history requires agent session storage.")
                    session.state[_HOSTED_SERVICE_CHILD_KEY] = context.response_id
                    try:
                        await _set_agent_session(session_storage, previous_response_id, session)
                    finally:
                        session.state.pop(_HOSTED_SERVICE_CHILD_KEY, None)
                session.state.pop(_HOSTED_SOURCE_CONVERSATION_KEY, None)

            if not context.is_recovery:
                session.state.pop(_HOSTED_PROVIDER_STATE_KEY, None)
                session.state.pop(_HOSTED_CONVERSATION_COMMITTED_KEY, None)

            if (
                stored
                and context.conversation_id is not None
                and not configuration.agent_server_history
                and not conversation_already_committed
            ):
                if session_storage is None:
                    raise RuntimeError("Service history requires agent session storage.")
                # The scoped store's conditional write must succeed before the provider can
                # mutate its linear thread; a losing turn never reaches agent.run().
                session.state[_HOSTED_CONVERSATION_CLAIM_KEY] = context.response_id
                try:
                    await _set_agent_session(session_storage, context.conversation_id, session)
                finally:
                    session.state.pop(_HOSTED_CONVERSATION_CLAIM_KEY, None)

            inner_stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]] | None = None
            updates: _SignalledIterator[AgentResponseUpdate] | None = None
            if provider_background:
                if session_storage is None or not isinstance(agent, RawAgent):
                    raise RuntimeError("Provider background requires a stored MAF agent session.")
                output_count = _hosted_internal_metadata(response_event_stream).get(
                    _HOSTED_PROVIDER_OUTPUT_COUNT_KEY, 0
                )
                if type(output_count) is not int or output_count < 0:
                    raise RuntimeError("The persisted provider output cursor is invalid.")
                responses = self._provider_background_responses(
                    agent=cast(RawAgent[ChatOptions[Any]], agent),
                    messages=messages,
                    session=session,
                    session_storage=session_storage,
                    options=cast(ChatOptions[Any], chat_options),
                    context=context,
                    cancellation_signal=cancellation_signal,
                    emitted_output_count=output_count,
                )
                async with aclosing(responses):
                    async for response, output_count in responses:
                        for update in _agent_response_updates(response, context.response_id):
                            if context.shutdown.is_set() or cancellation_signal.is_set():
                                break
                            async for event in tracker.handle_update(
                                update, approval_storage=approval_storage, complete_message=True
                            ):
                                yield event
                        if context.shutdown.is_set() or cancellation_signal.is_set():
                            continue
                        for event in tracker.close():
                            yield event
                        private_metadata = _hosted_internal_metadata(response_event_stream)
                        private_metadata[_HOSTED_PROVIDER_OUTPUT_COUNT_KEY] = output_count
                        private_metadata[_HOSTED_PROVIDER_USAGE_KEY] = tracker.usage_details
                        if self._resilient_background:
                            yield response_event_stream.checkpoint()
            else:
                inner_stream = agent.run(stream=True, **run_kwargs)  # type: ignore[reportUnknownMemberType]
                updates = _SignalledIterator(inner_stream, context.shutdown, cancellation_signal)
                async with aclosing(updates):
                    async for update in updates:
                        if not stored and any(
                            content.type in ("function_approval_request", "oauth_consent_request")
                            or content.user_input_request
                            for content in update.contents
                        ):
                            raise ValueError("Approval and user-input continuation requires store=true.")
                        async for event in tracker.handle_update(update, approval_storage=approval_storage):
                            yield event
            if inner_stream is not None and isinstance(updates, _SignalledIterator) and not updates.signalled:
                final = await inner_stream.get_final_response()
                if final.continuation_token is not None and final.finish_reason is None:
                    raise RuntimeError(
                        "The inner agent returned an unfinished provider response; "
                        "configure background_source='inference_service' with history_source='inference_service' "
                        "to resume it."
                    )
        except (asyncio.CancelledError, GeneratorExit):
            request_interrupted = True
            raise
        except Exception as ex:
            request_failure = ex
            _log_response_failure("agent execution", context.response_id, ex)
        finally:
            if configuration.hosted_history:
                session.state.pop(_HOSTED_RESPONSES_HISTORY_SOURCE_ID, None)
            if not provider_background and not context.is_recovery:
                session.state.pop(_HOSTED_PROVIDER_STATE_KEY, None)

            # Never persist a session that could resume an inner response contrary to the
            # history mode or the caller's explicit storage decision.
            stored_output_violation = (
                self._history_source == "host_managed" or not stored
            ) and session.service_session_id is not None
            if stored_output_violation:
                misconfigured = RuntimeError(
                    "The agent's chat client stored this turn server-side despite store=False for the inner model. "
                    "Configure the client to honor store=False, or use history_source='inference_service' "
                    "with store=true."
                )
                _log_response_failure("stored output validation", context.response_id, misconfigured)
                if request_failure is None and not request_interrupted:
                    request_failure = _PublicResponseFailure(misconfigured)
            if (
                self._history_source == "inference_service"
                and stored
                and _HOSTED_PROVIDER_STATE_KEY not in session.state
                and session.service_session_id is None
                and request_failure is None
                and not request_interrupted
                and not (cancellation_signal.is_set() and context.client_cancelled)
            ):
                request_failure = RuntimeError(
                    "history_source='inference_service' requires the chat client to return a service continuation ID."
                )
            try:
                provider_state = session.state.get(_HOSTED_PROVIDER_STATE_KEY)
                final_provider_state = not provider_background or (
                    request_failure is None
                    and not request_interrupted
                    and not (cancellation_signal.is_set() and context.client_cancelled)
                    and (
                        provider_state is None
                        or (
                            isinstance(provider_state, Mapping)
                            and cast(Mapping[str, Any], provider_state).get("completed") is True
                        )
                    )
                )
                superseded_by_steering = bool(self._host_options and self._host_options.steerable_conversations) and (
                    cancellation_signal.is_set() and not context.client_cancelled and not context.shutdown.is_set()
                )
                if stored and session_storage is not None and not stored_output_violation and final_provider_state:
                    if context.conversation_id is not None:
                        session.state[_HOSTED_SOURCE_CONVERSATION_KEY] = context.conversation_id
                    await _set_agent_session(session_storage, context.response_id, session)
                    if (
                        context.conversation_id is not None
                        and not conversation_already_committed
                        and not superseded_by_steering
                        and not request_interrupted
                        and request_failure is None
                        and (
                            configuration.agent_server_history
                            or (not cancellation_signal.is_set() and not context.shutdown.is_set())
                        )
                    ):
                        if provider_background:
                            session.state.pop(_HOSTED_PROVIDER_STATE_KEY, None)
                        session.state[_HOSTED_CONVERSATION_COMMITTED_KEY] = context.response_id
                        await _set_agent_session(session_storage, context.conversation_id, session)
            except Exception as save_error:
                save_failure = save_error
                if request_interrupted:
                    message = "Failed to persist the Agent Framework session while unwinding an interrupted request"
                elif request_failure is not None:
                    message = "Failed to persist the Agent Framework session after an agent failure"
                else:
                    message = "Failed to persist the Agent Framework session after a successful request"
                _log_response_failure(message, context.response_id, save_error)

        if request_failure is not None and save_failure is not None:
            raise RuntimeError(
                f"Agent request failed: {str(request_failure) or type(request_failure).__name__}; "
                f"session persistence also failed: {str(save_failure) or type(save_failure).__name__}"
            )
        elif request_failure is not None:
            raise request_failure
        elif save_failure is not None:
            raise save_failure

    async def _provider_background_responses(
        self,
        *,
        agent: RawAgent[ChatOptions[Any]],
        messages: list[Message],
        session: AgentSession,
        session_storage: SessionStore,
        options: ChatOptions[Any],
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
        emitted_output_count: int,
    ) -> AsyncGenerator[tuple[AgentResponse[Any], int]]:
        """Persist polling output with its private token and replay uncheckpointed output on recovery."""
        outputs: list[dict[str, Any]] = []

        async def proceed(*, has_token: bool) -> bool:
            if cancellation_signal.is_set() and context.client_cancelled:
                if not has_token:
                    logger.warning(
                        "Provider background submission was cancelled before a token was saved; "
                        "remote work may continue."
                    )
                return False
            if context.shutdown.is_set():
                if has_token and self._resilient_background:
                    await context.exit_for_recovery()
                if has_token:
                    raise RuntimeError("Provider background recovery requires resilient_background=True.")
                raise _PublicResponseFailure(
                    RuntimeError(
                        "Provider background submission stopped before its token was saved; cannot safely retry it."
                    )
                )
            if cancellation_signal.is_set():
                raise RuntimeError("Provider background was interrupted without a client cancellation.")
            return True

        async def run_provider(
            options: ChatOptions[Any], *, input_messages: list[Message] | None, phase: Literal["submit", "poll"]
        ) -> AgentResponse[Any]:
            try:
                return await agent.run(input_messages, session=session, options=options)
            except Exception as exc:
                logger.warning("Inner provider background %s failed (%s).", phase, type(exc).__name__)
            raise RuntimeError(f"Inner provider background {phase} failed; inspect the host logs.")

        async def save_private_state() -> None:
            try:
                await session_storage.set(context.response_id, session)
            except Exception as exc:
                logger.warning("Private provider background state save failed (%s).", type(exc).__name__)
            else:
                return
            raise RuntimeError("Could not save private provider background state; inspect the host logs.")

        def record_output(response: AgentResponse[Any]) -> None:
            messages = response.messages
            if response.continuation_token is not None:
                # A tool loop prefixes completed calls/results to the unfinished model
                # response. Retain that prefix, not partial output that polling will repeat.
                for index in range(len(messages) - 1, -1, -1):
                    message = messages[index]
                    last_result = next(
                        (
                            offset
                            for offset in range(len(message.contents) - 1, -1, -1)
                            if message.contents[offset].type == "function_result"
                        ),
                        None,
                    )
                    if last_result is not None:
                        completed_message = copy(message)
                        completed_message.contents = message.contents[: last_result + 1]
                        messages = [*messages[:index], completed_message]
                        break
                else:
                    return
            outputs.append(
                AgentResponse(
                    messages=messages,
                    usage_details=response.usage_details,
                    finish_reason=FinishReason(response.finish_reason) if response.finish_reason is not None else None,
                ).to_dict()
            )

        async def pending_outputs() -> AsyncGenerator[tuple[AgentResponse[Any], int]]:
            nonlocal emitted_output_count
            while emitted_output_count < len(outputs):
                if not await proceed(has_token=True):
                    return
                yield AgentResponse.from_dict(outputs[emitted_output_count]), emitted_output_count + 1
                if not await proceed(has_token=True):
                    return
                emitted_output_count += 1

        if context.is_recovery:
            saved = session.state.get(_HOSTED_PROVIDER_STATE_KEY)
            if not isinstance(saved, Mapping):
                raise _PublicResponseFailure(
                    RuntimeError("Cannot recover a provider background job without its stored continuation token.")
                )
            saved_payload = cast(Mapping[str, Any], saved)
            if saved_payload.get("outer_response_id") != context.response_id:
                raise _PublicResponseFailure(
                    RuntimeError("Cannot recover a provider background job without its stored continuation token.")
                )
            token = saved_payload.get("continuation_token")
            if not isinstance(token, Mapping):
                raise RuntimeError("The stored provider continuation token is invalid.")
            continuation_token: Mapping[str, Any] = cast(Mapping[str, Any], token)
            saved_outputs = saved_payload.get("outputs", [])
            if not isinstance(saved_outputs, list) or any(
                not isinstance(output, dict) for output in cast(list[object], saved_outputs)
            ):
                raise RuntimeError("The stored provider output is invalid.")
            outputs = cast(list[dict[str, Any]], saved_outputs)
            if emitted_output_count > len(outputs):
                raise RuntimeError("The persisted provider output cursor exceeds its private snapshot.")
            async for output in pending_outputs():
                yield output
            if saved_payload.get("completed") is True and outputs:
                await proceed(has_token=True)
                return
        else:
            if not await proceed(has_token=False):
                return
            completed, first = await _await_before_signal(
                lambda: run_provider(
                    cast(ChatOptions[Any], {**options, "background": True}),
                    input_messages=messages,
                    phase="submit",
                ),
                context.shutdown,
                cancellation_signal,
            )
            if not completed:
                if not await proceed(has_token=False):
                    return
                raise RuntimeError("Provider background submission was interrupted before its token was saved.")
            if first is None:
                raise RuntimeError("The provider did not return a background response.")
            if first.continuation_token is None:
                if not await proceed(has_token=False):
                    return
                yield first, 1
                return
            if not isinstance(first.continuation_token, Mapping):
                raise RuntimeError("The provider returned a continuation token that cannot be persisted.")
            continuation_token = cast(Mapping[str, Any], first.continuation_token)
            if any(message.contents for message in first.messages) or first.usage_details:
                record_output(first)
            session.state[_HOSTED_PROVIDER_STATE_KEY] = {
                "outer_response_id": context.response_id,
                "continuation_token": dict(continuation_token),
                "outputs": outputs,
            }
            await save_private_state()
            async for output in pending_outputs():
                yield output

        while True:
            if not await proceed(has_token=True):
                return
            slept, _ = await _await_before_signal(lambda: asyncio.sleep(2), context.shutdown, cancellation_signal)
            if not slept:
                if not await proceed(has_token=True):
                    return
                raise RuntimeError("Provider background polling was interrupted.")
            if not await proceed(has_token=True):
                return
            completed, current = await _await_before_signal(
                lambda token=continuation_token: run_provider(
                    cast(
                        ChatOptions[Any],
                        {**options, "background": True, "store": True, "continuation_token": token},
                    ),
                    input_messages=None,
                    phase="poll",
                ),
                context.shutdown,
                cancellation_signal,
            )
            if not completed:
                if not await proceed(has_token=True):
                    return
                raise RuntimeError("Provider background polling was interrupted.")
            if current is None:
                raise RuntimeError("The provider did not return a background response.")
            if current.continuation_token is None:
                # Save the completed output with its token before publishing it; recovery
                # replays the uncheckpointed output without invoking the agent again.
                record_output(current)
                session.state[_HOSTED_PROVIDER_STATE_KEY] = {
                    "outer_response_id": context.response_id,
                    "continuation_token": dict(continuation_token),
                    "completed": True,
                    "outputs": outputs,
                }
                await save_private_state()
                async for output in pending_outputs():
                    yield output
                return
            if not isinstance(current.continuation_token, Mapping):
                raise RuntimeError("The provider returned a continuation token that cannot be persisted.")
            if current.continuation_token == continuation_token:
                continue
            if any(message.contents for message in current.messages) or current.usage_details:
                record_output(current)
            continuation_token = cast(Mapping[str, Any], current.continuation_token)
            session.state[_HOSTED_PROVIDER_STATE_KEY] = {
                "outer_response_id": context.response_id,
                "continuation_token": dict(continuation_token),
                "outputs": outputs,
            }
            await save_private_state()
            async for output in pending_outputs():
                yield output

    @staticmethod
    def _emit_failure(
        response_id: str,
        phase: str,
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker | None,
        ex: BaseException,
        *,
        public_message: str | None = None,
    ) -> Generator[ResponseStreamEvent]:
        """Log ``ex`` and yield a terminal ``response.failed`` event.

        Drains any in-progress streaming output item first so the resulting
        SSE stream stays well-formed, then emits ``response.failed`` carrying a
        stable public message unless the caller explicitly supplies a safe
        validation message. Any error raised while draining the tracker is
        logged and otherwise ignored so that the original failure remains the
        terminal failure.
        """
        _log_response_failure(phase, response_id, ex)
        if tracker is not None:
            try:
                yield from tracker.close()
            except Exception as close_error:
                _log_response_failure("failed tracker cleanup", response_id, close_error)
            tracker.discard_pending_container_file_citations()
        if public_message is not None:
            message = public_message
        elif isinstance(ex, _PublicResponseFailure):
            message = ex.public_message
        else:
            message = _PUBLIC_STREAM_FAILURE_MESSAGE
        yield response_event_stream.emit_failed(message=message, usage=tracker.usage if tracker is not None else None)
