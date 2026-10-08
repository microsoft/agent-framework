# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import os
import re
import uuid
import warnings
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Mapping,
    Sequence,
)
from contextlib import AbstractAsyncContextManager, AsyncExitStack, aclosing, suppress
from copy import copy
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypeGuard, TypeVar, cast
from urllib.parse import urlparse

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    ChatOptions,
    CheckpointStorage,
    ComputerSafetyCheck,
    Content,
    ContextProvider,
    FinishReason,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    RawAgent,
    ResponseStream,
    SessionStore,
    SupportsAgentRun,
    UsageDetails,
    Workflow,
    WorkflowAgent,
    add_usage_details,
)
from agent_framework._mcp import _MCP_TOOL_RESULT_HOST_PAYLOAD_KEY  # pyright: ignore[reportPrivateUsage]
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
    ComputerAction,
    ComputerCallSafetyCheckParam,
    ComputerScreenshotImage,
    ContainerFileCitationBody,
    CreateResponse,
    FunctionShellAction,
    FunctionShellCallOutputContent,
    FunctionShellCallOutputExitOutcome,
    FunctionShellCallOutputTimeoutOutcome,
    Item,
    ItemReasoningItem,
    LocalEnvironmentResource,
    MessageContent,
    OAuthConsentRequestOutputItem,
    OutputItem,
    OutputItemComputerToolCall,
    OutputItemComputerToolCallOutput,
    OutputItemReasoningItem,
    OutputMessageContent,
    ResponseIncompleteReason,
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

from ._agent_source import is_agent, resolve_agent, validate_agent_source
from ._feature_usage import FeatureIndex
from ._request import (
    HostedResponseRequest,
    OptionsHook,
    UnsupportedOptions,
    WorkflowTurn,
    prepare_response_options,
    response_run_options,
    validate_default_transport_options,
    validate_request_options,
    validate_unsupported_options,
)
from ._scope import FoundryRequestScope
from ._state_store import (
    AgentSessionStoreProvider,
    CheckpointStoreProvider,
    ContextScopedStoreProvider,
    FunctionApprovalStore,
    FunctionApprovalStoreProvider,
    StoreProvider,
)
from ._workflow_source import WorkflowSource, validate_workflow_source

if TYPE_CHECKING:
    from ._workflow_responses import NativeResponsesWorkflow

logger = logging.getLogger(__name__)

_MODEL_OUTPUT_KIND_KEY = "model_output_kind"
_MODEL_OUTPUT_REFUSAL = "refusal"
_HOSTED_RESPONSES_HISTORY_SOURCE_ID = "_foundry_responses_history"
_HOSTED_PROVIDER_STATE_KEY = "_foundry_provider_background"
_HOSTED_SOURCE_CONVERSATION_KEY = "_foundry_source_conversation"
_HOSTED_SERVICE_CHILD_KEY = "_foundry_service_child"
_HOSTED_CONVERSATION_CLAIM_KEY = "_foundry_conversation_claim"
_HOSTED_CONVERSATION_COMMITTED_KEY = "_foundry_conversation_committed"
_HOSTED_PROVIDER_OUTPUT_COUNT_KEY = "_foundry_provider_output_count"
_HOSTED_PROVIDER_USAGE_KEY = "_foundry_provider_usage"
_PENDING_CONTAINER_FILE_CITATIONS_KEY = "_foundry_pending_container_file_citations"
_CONTAINER_FILE_CITATIONS_KEY = "container_file_citations"

_HistorySource = Literal["agent_server", "agent", "service"]
_AGENT_SOURCE_UNSET = object()


@dataclass(frozen=True)
class _ContainerFileCitation:
    container_id: str
    file_id: str
    filename: str


def _has_container_filename_boundaries(text: str, start_index: int, end_index: int) -> bool:
    """Return whether a filename match is not embedded in another filename-like token."""
    before = text[start_index - 1] if start_index > 0 else None
    after = text[end_index] if end_index < len(text) else None
    return (before is None or not (before.isalnum() or before in "._-")) and (
        after is None or not (after.isalnum() or after in "._-")
    )


def _container_file_citations_from_function_result(content: Content) -> list[_ContainerFileCitation]:
    """Extract validated container file citations from a core-preserved MCP Host payload."""
    raw_payload = content.additional_properties.get(_MCP_TOOL_RESULT_HOST_PAYLOAD_KEY)
    if not isinstance(raw_payload, Mapping):
        return []
    payload = cast(Mapping[str, Any], raw_payload)

    metadata_blocks: list[Mapping[str, Any]] = []
    raw_result_meta = payload.get("_meta")
    if isinstance(raw_result_meta, Mapping):
        metadata_blocks.append(cast(Mapping[str, Any], raw_result_meta))

    raw_content = payload.get("content")
    if isinstance(raw_content, Sequence) and not isinstance(raw_content, (str, bytes, bytearray)):
        for raw_item in cast(Sequence[Any], raw_content):
            if not isinstance(raw_item, Mapping):
                continue
            item = cast(Mapping[str, Any], raw_item)
            raw_item_meta = item.get("_meta")
            if isinstance(raw_item_meta, Mapping):
                metadata_blocks.append(cast(Mapping[str, Any], raw_item_meta))

    citations: list[_ContainerFileCitation] = []
    for metadata in metadata_blocks:
        raw_citations = metadata.get(_CONTAINER_FILE_CITATIONS_KEY)
        if isinstance(raw_citations, str):
            try:
                raw_citations = json.loads(raw_citations)
            except (json.JSONDecodeError, RecursionError):
                continue

        citation_values: list[Any]
        if isinstance(raw_citations, Mapping):
            citation_values = [cast(Mapping[str, Any], raw_citations)]
        elif isinstance(raw_citations, Sequence) and not isinstance(raw_citations, (str, bytes, bytearray)):
            citation_values = list(cast(Sequence[Any], raw_citations))
        else:
            continue

        fallback_container_id = metadata.get("container_id")
        for raw_citation in citation_values:
            if not isinstance(raw_citation, Mapping):
                continue
            citation = cast(Mapping[str, Any], raw_citation)
            container_id = citation.get("container_id") or fallback_container_id
            file_id = citation.get("file_id")
            filename = citation.get("filename")
            if not isinstance(container_id, str) or not container_id:
                continue
            if not isinstance(file_id, str) or not file_id:
                continue
            if not isinstance(filename, str) or not filename:
                continue
            citations.append(
                _ContainerFileCitation(
                    container_id=container_id,
                    file_id=file_id,
                    filename=filename,
                )
            )

    return citations


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


def _reject_busy_conversation(session: AgentSession) -> None:
    if session.state.get(_HOSTED_CONVERSATION_CLAIM_KEY) is not None:
        raise RuntimeError(
            "A service-backed conversation already has an in-flight turn. Wait for it to finish; "
            "if it failed or was cancelled after dispatch, start a new conversation rather than "
            "reusing a possibly changed provider thread."
        )


def _create_response_event_stream(context: ResponseContext) -> ResponseEventStream:
    """Create a response stream seeded from recovery state when available."""
    if context.is_recovery:
        persisted_response = context.persisted_response
        if persisted_response is not None:
            return ResponseEventStream(response=persisted_response, response_id=context.response_id)
    return ResponseEventStream(response_id=context.response_id)


def _agent_response_updates(response: AgentResponse[Any], response_id: str) -> list[AgentResponseUpdate]:
    """Project a completed inner response without exposing its private provider token or ID."""
    updates = [
        AgentResponseUpdate(
            contents=list(message.contents),
            role=message.role,
            author_name=message.author_name,
            response_id=response_id,
            message_id=message.message_id or uuid.uuid4().hex,
        )
        for message in response.messages
    ]
    if response.usage_details is not None:
        updates.append(AgentResponseUpdate(contents=[Content.from_usage(response.usage_details)]))
    if response.finish_reason is not None:
        if not updates:
            updates.append(AgentResponseUpdate())
        updates[-1].finish_reason = FinishReason(response.finish_reason)
    return updates


_T = TypeVar("_T")


async def _await_before_signal(
    operation: Callable[[], Awaitable[_T]], *signals: asyncio.Event
) -> tuple[bool, _T | None]:
    """Race a provider await against lifecycle signals without discarding a completed continuation token."""
    if any(signal.is_set() for signal in signals):
        return False, None
    task = asyncio.ensure_future(operation())
    waiters = [asyncio.ensure_future(signal.wait()) for signal in signals]
    try:
        finished, _ = await asyncio.wait([task, *waiters], return_when=asyncio.FIRST_COMPLETED)
        if task in finished:
            return True, await task
        return False, None
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


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
    is discarded. Cancelling the background task while it's mid-call interrupts a suspended model or
    tool call, then the driver closes the underlying stream in ``finally``.

    Callers MUST drive this through ``contextlib.aclosing`` (or an equivalent try/finally calling
    ``aclose()``): ``__anext__`` only cancels the driver task on its own signalled/exhausted paths, so
    if the consumer of ``async for`` raises instead (e.g. while processing a yielded item), the driver
    task -- and the real agent/workflow run it's pumping -- would otherwise be silently abandoned.
    """

    def __init__(
        self,
        iterator: AsyncIterator[_T],
        *events: asyncio.Event,
        stamp: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        """Wrap an async iterator, stopping early if any of ``events`` fires.

        Args:
            iterator: The async iterator to wrap.
            events: One or more asyncio.Event objects to watch for. If any of them is set, iteration stops early.
            stamp: Optional coroutine function the driver awaits right after the wrapped iterator produces an
                item and before it is advanced again. Its result is exposed as :attr:`stamp` while that item
                is the current one, which lets a consumer observe state (e.g. the latest persisted workflow
                checkpoint) as it was when the item was produced rather than when it is consumed: the driver
                runs one item ahead, so by consumption time the wrapped iterator may already have moved on.
        """
        self._iterator = iterator
        self._events = events
        self._stamp_fn = stamp
        self._stamp: Any = None
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

    @property
    def stamp(self) -> Any:
        """The ``stamp`` result taken when the current item was produced (``None`` without a ``stamp``)."""
        return self._stamp

    def __aiter__(self) -> _SignalledIterator[_T]:
        return self

    async def _drive(self) -> None:
        """Pull items from the wrapped iterator into ``self._queue`` for the object's lifetime."""
        try:
            while True:
                try:
                    item: Any = await self._iterator.__anext__()
                    stamp = await self._stamp_fn() if self._stamp_fn is not None else None
                except StopAsyncIteration:
                    await self._queue.put(_STOP_SENTINEL)
                    return
                except Exception as exc:
                    await self._queue.put(exc)
                    return
                await self._queue.put((item, stamp))
        finally:
            iterator: AsyncIterator[_T] = self._iterator
            if isinstance(iterator, ResponseStream):
                await cast(ResponseStream[_T, Any], iterator).close()
            else:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()

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
        item, self._stamp = item
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
# ``internal_metadata`` key carrying a truncating finish reason across resilient checkpoints, so a
# turn cut short before a crash still ends ``incomplete`` after recovery.
_INCOMPLETE_REASON_KEY = "_incomplete_reason"


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


def _normalize_oauth_consent_origin(value: str, *, require_origin_only: bool) -> str:
    """Normalize an HTTPS consent URL or configured origin for exact matching."""
    if not _is_safe_oauth_consent_link(value):
        raise ValueError("OAuth consent origins must be absolute HTTPS URLs without user information.")

    parsed = urlparse(value)
    if require_origin_only and (parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment):
        raise ValueError("OAuth consent origin entries must not include a path, query, parameters, or fragment.")

    hostname = parsed.hostname
    if hostname is None:  # pragma: no cover - _is_safe_oauth_consent_link already proved this.
        raise ValueError("OAuth consent origin must include a hostname.")
    normalized_host = f"[{hostname.lower()}]" if ":" in hostname else hostname.lower()
    port = parsed.port
    return f"https://{normalized_host}" if port in (None, 443) else f"https://{normalized_host}:{port}"


def _normalize_allowed_oauth_consent_origins(allowed_origins: Sequence[str] | None) -> frozenset[str] | None:
    """Normalize the host-configured consent origin allowlist, or return ``None`` when none is configured."""
    if allowed_origins is None:
        return None
    return frozenset(_normalize_oauth_consent_origin(origin, require_origin_only=True) for origin in allowed_origins)


def _is_allowed_oauth_consent_link(consent_link: object, allowed_origins: frozenset[str] | None) -> TypeGuard[str]:
    """Return whether the link is safe and, when an allowlist is configured, has an allowed origin.

    ``allowed_origins`` must come from ``_normalize_allowed_oauth_consent_origins``. ``None`` keeps the
    safe-HTTPS check without restricting the origin; an empty set rejects every link.
    """
    if not _is_safe_oauth_consent_link(consent_link):
        return False
    if allowed_origins is None:
        return True
    return _normalize_oauth_consent_origin(consent_link, require_origin_only=False) in allowed_origins


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


@dataclass(frozen=True)
class _AgentConfiguration:
    workflow: bool
    agent_server_history: bool
    client_stores_by_default: bool
    hosted_history: bool


def _validate_agent_configuration(
    agent: SupportsAgentRun,
    history_source: _HistorySource,
    options: ResponsesServerOptions | None,
    *,
    background_source: Literal["agent_server", "provider"] = "agent_server",
) -> _AgentConfiguration:
    is_workflow_agent = isinstance(agent, WorkflowAgent)
    if is_workflow_agent and agent.workflow._runner_context.has_checkpointing():  # pyright: ignore[reportPrivateUsage]
        raise RuntimeError(
            "There should not be a checkpoint storage already present in the workflow agent. "
            "The hosting infrastructure will manage checkpoints instead."
        )

    resilient_background = bool(options and options.resilient_background)
    if resilient_background and not is_workflow_agent and background_source != "provider":
        raise RuntimeError(
            "resilient_background=True is only supported for workflow agents. "
            "Crash recovery cannot be provided for non-workflow agents."
        )
    if background_source == "provider" and (
        not isinstance(agent, RawAgent) or getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None) is not True
    ):
        raise RuntimeError("Provider background requires a RawAgent with a storing, resumable Responses client.")
    if options and options.steerable_conversations and is_workflow_agent:
        raise RuntimeError(
            "steerable_conversations=True is only supported for non-workflow agents. "
            "Steering cannot be provided reliably for workflow agents."
        )

    if is_workflow_agent and history_source == "service":
        raise ValueError("history_source='service' is only supported for regular agents.")

    if not is_workflow_agent and isinstance(agent, RawAgent):
        identity_defaults = ("session_id", "agent_session_id", "user_id", "call_id", "service_session_id")
        if conflicting := [name for name in identity_defaults if agent.default_options.get(name) is not None]:
            raise RuntimeError(f"Model defaults cannot supply Foundry platform identity: {', '.join(conflicting)}.")

    uses_agent_server_history = history_source == "agent_server"
    client_stores_by_default = False
    if not is_workflow_agent and history_source != "agent":
        if not isinstance(agent, RawAgent):
            raise RuntimeError(
                "history_source='agent_server' and 'service' require a RawAgent so hosting can enforce downstream "
                "storage. Use history_source='agent' for a custom SupportsAgentRun implementation on stored requests."
            )

        stores_by_default = getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None)
        if not isinstance(stores_by_default, bool):
            raise RuntimeError(
                "history_source='agent_server' or 'service' requires the chat client to declare STORES_BY_DEFAULT "
                "so hosting can enforce downstream storage behavior."
            )
        client_stores_by_default = stores_by_default

        if history_source == "service" and not stores_by_default:
            raise RuntimeError(
                "history_source='service' requires a storing client that declares STORES_BY_DEFAULT=True."
            )

        service_continuation_options = [
            name
            for name in ("conversation_id", "previous_response_id", "conversation", "continuation_token", "response_id")
            if agent.default_options.get(name) is not None
        ]
        if service_continuation_options:
            raise RuntimeError(
                f"history_source='agent_server' or 'service' cannot use developer defaults for downstream "
                f"continuation: {', '.join(service_continuation_options)}. "
                "Use history_source='agent' to retain developer-controlled continuation."
            )

        if history_source in ("agent_server", "service"):
            for provider in agent.context_providers:
                if isinstance(provider, HistoryProvider) and provider.load_messages:
                    if history_source == "agent_server" and _is_hosted_responses_history_sentinel(provider):
                        continue
                    raise RuntimeError(
                        "The selected history_source conflicts with a load-enabled HistoryProvider. "
                        "Remove that provider or select history_source='agent'."
                    )
        if history_source == "agent_server" and not stores_by_default and agent.default_options.get("store") is True:
            raise RuntimeError(
                "The chat client does not store by default, but the agent sets a downstream store option. "
                "Remove that developer-owned default rather than letting hosting change it."
            )

    return _AgentConfiguration(
        workflow=is_workflow_agent,
        agent_server_history=uses_agent_server_history,
        client_stores_by_default=client_stores_by_default,
        hosted_history=uses_agent_server_history and not is_workflow_agent,
    )


def _initialize_agent_history(agent: SupportsAgentRun, configuration: _AgentConfiguration) -> None:
    if not configuration.hosted_history or not isinstance(agent, RawAgent):
        return
    if not any(
        _is_hosted_responses_history_sentinel(provider)
        for provider in cast(Sequence[ContextProvider], agent.context_providers)
    ):
        agent.context_providers.append(InMemoryHistoryProvider(source_id=_HOSTED_RESPONSES_HISTORY_SOURCE_ID))


# region ResponsesHostServer
class ResponsesHostServer(ResponsesAgentServerHost):
    """A Responses server host for an agent or a native, typed workflow."""

    def __init__(
        self,
        agent: SupportsAgentRun
        | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]]
        | object = _AGENT_SOURCE_UNSET,
        *,
        workflow: WorkflowSource[HostedResponseRequest] | None = None,
        parse_response: Callable[[HostedResponseRequest], WorkflowTurn[Any] | Awaitable[WorkflowTurn[Any]]]
        | None = None,
        prefix: str = "",
        options: ResponsesServerOptions | None = None,
        store: ResponseProviderProtocol | None = None,
        response_store: ResponseProviderProtocol | None = None,
        agent_session_store_provider: StoreProvider[SessionStore] | None = None,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage] | None = None,
        function_approval_store_provider: StoreProvider[FunctionApprovalStore] | None = None,
        allowed_oauth_consent_origins: Sequence[str] | None = None,
        history_source: Literal["agent_server", "agent", "service"] = "agent_server",
        background_source: Literal["agent_server", "provider"] = "agent_server",
        prepare_options: OptionsHook | None = None,
        unsupported_options: UnsupportedOptions = "warn",
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for, or a zero-argument sync or async callable that creates one for
                each request. Use a callable for agents that keep mutable state outside `AgentSession`.
                Hosting a `WorkflowAgent` here is deprecated and should be avoided: it is stateful, so one instance
                must never serve requests from different users or conversations. Use `workflow=` instead.
            workflow: A built, unrun native workflow for one-shot execution, or a request-aware
                sync/async factory returning fresh built graphs, executors, agents, clients, tools,
                and providers with stable graph/executor IDs. Cannot be combined with ``agent``.
                Use a factory for continuation, pauses, or background recovery.
            parse_response: Required for ``workflow``. Maps this turn's ``HostedResponseRequest``
                to a typed ``WorkflowTurn(input=...)`` or validated pending ``responses``.
                Native workflows use checkpoints, not the agent's history-source policy.
            prefix: The URL prefix for the server.
            options: Optional server options.
            store: Deprecated alias for `response_store`.
            response_store: Optional response store for caller-facing persistence and history.
            agent_session_store_provider: Optional provider for MAF agent session storage.
                If not provided, a default `AgentSessionStoreProvider` will be used.
            checkpoint_store_provider: Optional provider for workflow checkpoint storage.
                If not provided, a default `CheckpointStoreProvider` will be used.
            function_approval_store_provider: Optional provider for function approval storage.
                If not provided, a default `FunctionApprovalStoreProvider` will be used.
            allowed_oauth_consent_origins: Optional exact HTTPS origins allowed for OAuth consent links.
                When omitted, hosting retains its existing safe-HTTPS validation without restricting the
                destination origin. When provided, every link must match an entry; an empty sequence rejects
                every link. Entries must be origins such as `"https://auth.example.com"` and must not include
                a path, query, or fragment.
            history_source: Who supplies prior messages to the *model*, independently of the caller's
                Responses `store` flag. Defaults to `"agent_server"`:

                - `"agent_server"`: Send the prior outer Responses transcript followed by this request's input.
                  For a storing chat client, force its per-run `store=False` and clear any restored
                  `service_session_id` to avoid replaying that transcript twice. A load-enabled
                  `HistoryProvider` or fixed downstream continuation default conflicts with this mode.
                - `"service"`: Send only this request's input. On caller `store=True`, run the inner
                  client with `store=True` and save its issued `service_session_id` in the host's
                  private MAF session store. The next stored request resumes that provider thread;
                  it must not branch an already-used provider conversation.
                - `"agent"`: Send only this request's input and preserve the agent's developer-owned
                  storage choice on stored requests. With an `InMemoryHistoryProvider` and
                  `default_options={"store": False}`, the provider loads prior messages from
                  the host-persisted MAF `AgentSession`. With `default_options={"store": True}`,
                  the downstream service retains history instead (the previous meaning of `"agent"`).

                For example, after a stored response to "My name is Ada", a stored follow-up
                "What is my name?" sends both turns to the model with `"agent_server"`, but
                sends only the follow-up with `"service"` (plus a private service continuation).
                With `"agent"`, the developer chooses either of those agent-owned history sources.
            background_source: `"agent_server"` (default) runs background work in the Responses host
                without invoking provider-native background APIs; `"provider"` opts a storing, resumable
                client into provider background polling and requires `history_source="service"`.
                Each poll retains the caller's run options and `background=True`; local tools must be
                idempotent because a crash before the next private token is saved can replay them.
            prepare_options: Developer hook to remove or replace caller model options for an agent.
            unsupported_options: `"warn"` (default), `"error"`, or `"ignore"` when a custom agent
                cannot accept runtime model options.
            **kwargs: Additional keyword arguments.

        Note:
            The *caller* controls outer persistence with `POST /responses` `store=True/False`.
            `store=False` writes no host-managed session or approval state and forces supported
            inner clients not to store, regardless of `history_source`. The constructor's
            deprecated `store=` argument instead selects the outer response-store backend
            (use `response_store=`). Outer `response.id` is the polling/continuation handle;
            any inner `service_session_id` is private and never replaces it.

            1. With `history_source="agent_server"`,
               the agent must not have a load-enabled history provider: the host supplies the transcript.
            2. Context providers must not keep required state only on their Python instances,
               because the hosting environment may get deactivated between requests. Provider
               state carried by `AgentSession`, including `InMemoryHistoryProvider` messages in
               `history_source="agent"` mode, is persisted by the configured session store.
            3. The server owns the supplied agent instance and may add hosting-specific providers.
               Do not reuse the same agent with another host or invoke it directly after construction.
               An agent returned by a callable belongs to that request.
            4. `resilient_background=True` supports legacy workflows and regular agents configured with
               `history_source="service", background_source="provider"`. For provider background, only
               a saved private continuation token can be polled after a crash; a crash before the token
               is saved cannot be replayed safely. Other regular-agent runs are not crash-recoverable.
               Legacy workflow background responses retain their checkpoint-based recovery behavior.
            5. Steering is temporarily unavailable for all agents. `steerable_conversations=True` fails
               at construction, before starting a host or enabling the process-wide TaskManager. The current
               AgentServer SDK retains futures for rejected turns after the steering queue fills.
            6. A stored, named `"service"` or `"agent"` conversation is claimed in the scoped session store
               before the agent runs. Conditional writes prevent a concurrent turn from mutating the same
               provider thread. If the turn fails or is cancelled, start a new conversation instead of
               reusing a potentially changed downstream thread.

        Raises:
            ValueError: If the history, background, or unsupported-options policy is invalid.
            RuntimeError: If the agent configuration conflicts with the selected history source,
                `resilient_background=True` is requested for a regular agent without provider background, or
                `steerable_conversations=True` is requested while steering is unavailable.
        """
        if options and options.steerable_conversations:
            # TODO(foundry-hosting): Remove this guard after Azure/azure-sdk-for-python#49233 ships in an official
            # azure-ai-agentserver-core wheel, the minimum and uv.lock are updated, and a concurrent
            # queue-overflow regression proves rejected turns leave no pending futures.
            raise RuntimeError(
                "steerable_conversations=True is temporarily unavailable: the current AgentServer SDK "
                "retains futures for rejected steering turns. Wait for the official fix in "
                "Azure/azure-sdk-for-python#49233, then update the dependency and verify queue overflow."
            )
        if history_source not in ("agent_server", "agent", "service"):
            raise ValueError("history_source must be 'agent_server', 'agent', or 'service'.")
        if background_source not in ("agent_server", "provider"):
            raise ValueError("background_source must be 'agent_server' or 'provider'.")
        if store is not None and response_store is not None:
            raise ValueError("Pass response_store instead of store; they cannot be combined.")

        if background_source == "provider" and history_source != "service":
            raise ValueError("Provider background requires history_source='service'.")
        if background_source == "provider" and options and options.steerable_conversations:
            raise ValueError("Provider background and steerable_conversations cannot be combined.")
        agent_supplied = agent is not _AGENT_SOURCE_UNSET
        if not agent_supplied and workflow is None:
            raise ValueError("Pass exactly one of agent or workflow.")
        if agent_supplied and workflow is not None:
            raise ValueError("Pass exactly one of agent or workflow.")
        if workflow is not None:
            validate_workflow_source(workflow)
            if parse_response is None or not callable(parse_response):
                raise TypeError("parse_response is required for native workflow hosting.")
            if history_source != "agent_server" or background_source != "agent_server":
                raise ValueError(
                    "Native workflows use checkpoint history and AgentServer background, not agent policies."
                )
            if isinstance(workflow, Workflow) and options and options.resilient_background:
                raise ValueError("Native workflow background recovery requires a request-aware factory.")
        else:
            if parse_response is not None:
                raise ValueError("parse_response is only supported with workflow.")
            validate_agent_source(agent)

        resolved_agent = agent if is_agent(agent) else None
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
            store=response_store if response_store is not None else store,
            **kwargs,
        )
        if options and options.steerable_conversations:
            from azure.ai.agentserver.core.tasks import set_resilient_tasks_enabled

            set_resilient_tasks_enabled(True)

        self._agent_source = cast(
            SupportsAgentRun | Callable[[], SupportsAgentRun | Awaitable[SupportsAgentRun]] | None,
            None if not agent_supplied else agent,
        )
        self._agent = resolved_agent
        self._configuration = configuration
        self._history_source: _HistorySource = history_source
        self._background_source: Literal["agent_server", "provider"] = background_source
        self._prepare_options = prepare_options
        self._unsupported_options = validate_unsupported_options(unsupported_options)
        self._host_options = options
        self._uses_agent_server_history = (
            configuration.agent_server_history if configuration is not None else history_source == "agent_server"
        )
        self._resilient_background = bool(options and options.resilient_background)
        self._warned_workflow_agent = False
        if resolved_agent is not None and configuration is not None:
            _initialize_agent_history(resolved_agent, configuration)

        if store is not None:
            warnings.warn("store= is deprecated; use response_store=.", DeprecationWarning, stacklevel=2)

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
        self._native_workflow: NativeResponsesWorkflow | None = None
        if workflow is not None and parse_response is not None:
            from ._workflow_responses import NativeResponsesWorkflow

            self._native_workflow = NativeResponsesWorkflow(
                workflow,
                parse_response,
                config=self.config,
                checkpoint_store_provider=self._checkpoint_storage_provider,
                prepare_options=prepare_options,
                resilient_background=self._resilient_background,
                allowed_oauth_consent_origins=self._allowed_oauth_consent_origins,
            )
            self._native_workflow.bind_streaming_route(
                self.router,
                prefix=prefix,
                keep_alive=bool(
                    (options and options.sse_keep_alive_interval_seconds) or self.config.sse_keepalive_interval
                ),
            )
        if isinstance(resolved_agent, WorkflowAgent):
            self._warn_legacy_workflow()

        # Lazy agent lifecycle: the agent (and any MCP tools it owns) is entered on
        # the first request rather than at server startup, so that authentication
        # failures during MCP connect can be surfaced to the client as an
        # `oauth_consent_request` stream event instead of crashing the server.
        self._agent_stack: AsyncExitStack | None = None
        self._agent_init_lock = asyncio.Lock()

        self.shutdown_handler(self._cleanup_agent)
        self.response_handler(self._handle_response)

        mark_feature_used(FeatureIndex.FOUNDRY_HOSTING)

    def _warn_legacy_workflow(self) -> None:
        if not self._warned_workflow_agent:
            self._warned_workflow_agent = True
            message = (
                "Hosting WorkflowAgent through agent= is deprecated for this beta release and should be avoided. "
                "A WorkflowAgent is stateful and keeps workflow state in memory between runs, so one instance must "
                "never serve requests from different users or conversations. "
                "Use workflow=a_request_aware_factory with an explicit parse_response. "
                "Until you migrate, pass a factory that builds a new WorkflowAgent for every request. "
                "Wrapper history, context providers, approvals, and event semantics are not automatically unwrapped."
            )
            warnings.warn(message, DeprecationWarning, stacklevel=3)
            # Request-time calls cannot be attributed to application code, so Python's default filter hides the
            # warning there; log it as well.
            logger.warning("DEPRECATION: %s", message)

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
        if self._native_workflow is not None:
            async with aclosing(self._native_workflow.response_events(request, context, cancellation_signal)) as events:
                async for event in events:
                    yield event
            return
        response_event_stream = _create_response_event_stream(context)
        if context.is_steered_turn:
            logger.debug("Serving steered turn (pending_input_count=%d)", context.pending_input_count)
        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        terminal_event: ResponseStreamEvent | None = None
        try:
            scope = FoundryRequestScope.from_context(
                self.config, get_request_context(), local_session_id=context.response_id
            )
            if self._agent_source is None:
                raise RuntimeError("The hosted agent source is not configured.")
            agent = await resolve_agent(self._agent_source)
            configuration = self._configuration or _validate_agent_configuration(
                agent, self._history_source, self._host_options, background_source=self._background_source
            )
            if self._configuration is None:
                _initialize_agent_history(agent, configuration)
            if configuration.workflow:
                self._warn_legacy_workflow()
            hosted_request: HostedResponseRequest | None = None
            if configuration.workflow:
                if self._prepare_options is not None:
                    raise ValueError("prepare_options is only supported for regular agents.")
            else:
                hosted_request = HostedResponseRequest(request, context, scope, response_run_options(request))
                await prepare_response_options(hosted_request, self._prepare_options)
                validate_request_options(hosted_request.options)
        except Exception as exc:
            logger.error("Failed to prepare hosted Responses request", exc_info=(type(exc), exc, exc.__traceback__))
            for event in self._emit_failure(response_event_stream, None, exc):
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
        hosted_request: HostedResponseRequest | None,
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
                logger.error("Failed to prepare agent: %s", ex, exc_info=(type(ex), ex, ex.__traceback__))
                for event in self._emit_failure(response_event_stream, None, ex):
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
                logger.error("%s", validation_error)
                for event in self._emit_failure(response_event_stream, None, validation_error):
                    yield event
                return

            if request.get("store") is False:
                for event in self._emit_failure(
                    response_event_stream, None, ValueError("OAuth consent continuation requires store=true.")
                ):
                    yield event
                return

            if not configuration.workflow:
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
                        session = agent.create_session()
                    if context.conversation_id is not None:
                        _reject_busy_conversation(session)
                    if previous_response_id is not None and context.conversation_id is None:
                        if session.service_session_id is not None and session.state.get(
                            _HOSTED_SOURCE_CONVERSATION_KEY
                        ):
                            raise ValueError("A service-managed downstream conversation cannot be forked.")
                        session.state.pop(_HOSTED_SOURCE_CONVERSATION_KEY, None)
                    if context.conversation_id is not None:
                        session.state[_HOSTED_SOURCE_CONVERSATION_KEY] = context.conversation_id
                    await session_storage.set(context.response_id, session)
                    if context.conversation_id is not None:
                        await session_storage.set(context.conversation_id, session)
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

        tracker = _OutputItemTracker(response_event_stream, self._allowed_oauth_consent_origins)
        try:
            if configuration.workflow:
                inner = self._handle_inner_workflow(
                    request,
                    context,
                    response_event_stream,
                    tracker,
                    cancellation_signal,
                    cast(WorkflowAgent, agent),
                )
            else:
                if hosted_request is None:
                    raise RuntimeError("A regular agent requires a prepared Responses request.")
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
                # A cancelled run drains the inner generator without raising (both
                # ``_handle_inner_workflow`` and ``_handle_inner_agent`` stop their
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
            logger.error("Failed to produce response for agent", exc_info=(type(ex), ex, ex.__traceback__))
            for event in tracker.close():
                yield event

            for event in self._emit_failure(response_event_stream, tracker, ex):
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
        hosted_request: HostedResponseRequest,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Handle a regular (non-workflow) agent.

        The response stream, tracker, and opening lifecycle events are produced
        by :meth:`_handle_response`, which also converts any raised exception
        into a terminal ``response.failed`` event (draining the tracker so the
        SSE stream stays well-formed).
        """
        provider_background = self._background_source == "provider" and request.get("background") is True
        if context.is_recovery and not provider_background:
            raise RuntimeError("A non-resumable agent cannot be replayed after a process crash.")

        stored = request.get("store") is not False

        request_messages_task: asyncio.Task[list[Message]] | None = None
        conversation_already_committed = False
        try:
            if isinstance(agent, RawAgent):
                validate_default_transport_options(
                    agent.default_options,
                    allow_agent_store=self._history_source == "agent" and stored,
                )
            if not stored:
                if not isinstance(agent, RawAgent):
                    raise RuntimeError(
                        "store=false cannot guarantee that a custom agent will disable inner storage; "
                        "use a RawAgent or store=true."
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
                    raise RuntimeError(
                        "store=false cannot prevent an external HistoryProvider from persisting responses. "
                        "Use an InMemoryHistoryProvider or store=true."
                    )
                if self._history_source == "agent":
                    stores_by_default = getattr(cast(Any, agent).client, "STORES_BY_DEFAULT", None)
                    if not isinstance(stores_by_default, bool):
                        raise RuntimeError(
                            "store=false with history_source='agent' requires a client declaring STORES_BY_DEFAULT; "
                            "select history_source='agent_server' or 'service', or use store=true."
                        )
                    if not stores_by_default and agent.default_options.get("store") is True:
                        raise RuntimeError(
                            "store=false with history_source='agent' cannot safely override a storing "
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
            if not stored and session_load_id is not None and self._history_source == "service":
                raise ValueError(
                    "store=false cannot resume service-managed history; start a new one-shot request "
                    "or use history_source='agent_server' or 'agent'."
                )
            session_storage = (
                self._session_storage_provider.get_store(config=self.config, platform_context=request_context)
                if stored or (session_load_id is not None and self._history_source == "agent")
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
                    raise RuntimeError("Provider background was interrupted before its continuation token was stored.")
                if stored and previous_response_id is not None and context.conversation_id is None:
                    raise RuntimeError(
                        f"Cannot find an existing agent session for previous_response_id={previous_response_id}."
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
                        raise RuntimeError(
                            "Cannot recover provider background: the service-backed conversation claim "
                            "is no longer held by this response."
                        )
                else:
                    _reject_busy_conversation(session)
            if not stored and self._history_source == "agent" and session.service_session_id is not None:
                raise ValueError(
                    "store=false cannot continue agent-managed downstream service history; "
                    "start a new one-shot request or use store=true."
                )
            if (
                not context.is_recovery
                and provider_state is not None
                and (
                    not isinstance(provider_state, Mapping)
                    or cast(Mapping[str, Any], provider_state).get("completed") is not True
                )
            ):
                raise ValueError("A provider background response must complete before the next turn.")
            if previous_response_id is not None and context.conversation_id is None and not context.is_recovery:
                if session.service_session_id is not None and session.state.get(_HOSTED_SOURCE_CONVERSATION_KEY):
                    raise ValueError("A service-managed downstream conversation cannot be forked.")
                if (
                    stored
                    and self._history_source in ("service", "agent")
                    and session.service_session_id is not None
                    and session.state.get(_HOSTED_SERVICE_CHILD_KEY)
                ):
                    raise ValueError("A service-managed downstream response cannot be forked.")
        except BaseException as ex:
            # Session preparation failed (or the request was cancelled / the stream closed —
            # neither of which is an Exception). Cancel and drain the in-flight message-loading
            # task so it is not orphaned, and log only ordinary failures.
            if request_messages_task is not None:
                request_messages_task.cancel()
                with suppress(BaseException):
                    await request_messages_task
            if isinstance(ex, Exception):
                logger.error("Failed to prepare state storage: %s", ex, exc_info=(type(ex), ex, ex.__traceback__))
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
            chat_options = cast(ChatOptions[Any], dict(hosted_request.options))
            are_options_set = bool(chat_options)
            if configuration.agent_server_history:
                if configuration.client_stores_by_default:
                    # The response provider already owns the transcript used for this run. Keep a
                    # storing downstream service stateless so it cannot become a second history source.
                    chat_options["store"] = False
                else:
                    # Do not pass a storage option to clients that do not advertise support for it.
                    chat_options.pop("store", None)
            elif self._history_source == "service":
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
                    raise TypeError("The hosted agent does not accept caller runtime options.")
                if self._unsupported_options == "warn":
                    logger.warning("Agent doesn't support runtime options. They will be ignored.")

            if previous_response_id is not None and context.conversation_id is None and not context.is_recovery:
                if stored and self._history_source in ("service", "agent") and session.service_session_id is not None:
                    if session_storage is None:
                        raise RuntimeError("Service history requires agent session storage.")
                    session.state[_HOSTED_SERVICE_CHILD_KEY] = context.response_id
                    try:
                        await session_storage.set(previous_response_id, session)
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
                    await session_storage.set(context.conversation_id, session)
                finally:
                    session.state.pop(_HOSTED_CONVERSATION_CLAIM_KEY, None)

            inner_stream: ResponseStream[AgentResponseUpdate, AgentResponse[Any]] | None = None
            updates: _SignalledIterator[AgentResponseUpdate] | None = None
            if provider_background:
                if session_storage is None or not isinstance(agent, RawAgent):
                    raise RuntimeError("Provider background requires a stored MAF agent session.")
                output_count = response_event_stream.internal_metadata.get(_HOSTED_PROVIDER_OUTPUT_COUNT_KEY, 0)
                if type(output_count) is not int or output_count < 0:
                    raise RuntimeError("The persisted provider output cursor is invalid.")
                responses = self._provider_background_responses(
                    agent=cast(RawAgent[ChatOptions[Any]], agent),
                    messages=messages,
                    session=session,
                    session_storage=session_storage,
                    options=chat_options,
                    context=context,
                    cancellation_signal=cancellation_signal,
                    emitted_output_count=output_count,
                )
                async with aclosing(responses):
                    async for response, output_count in responses:
                        for update in _agent_response_updates(response, context.response_id):
                            if context.shutdown.is_set() or cancellation_signal.is_set():
                                break
                            async for event in tracker.handle_update(update, approval_storage=approval_storage):
                                yield event
                        if context.shutdown.is_set() or cancellation_signal.is_set():
                            continue
                        for event in tracker.close():
                            yield event
                        response_event_stream.internal_metadata[_HOSTED_PROVIDER_OUTPUT_COUNT_KEY] = output_count
                        response_event_stream.internal_metadata[_HOSTED_PROVIDER_USAGE_KEY] = tracker.usage_details
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
                        "configure background_source='provider' with history_source='service' to resume it."
                    )
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
            if configuration.hosted_history:
                session.state.pop(_HOSTED_RESPONSES_HISTORY_SOURCE_ID, None)
            if not provider_background and not context.is_recovery:
                session.state.pop(_HOSTED_PROVIDER_STATE_KEY, None)

            # Never persist a session that could resume an inner response contrary to the
            # history mode or the caller's explicit storage decision.
            stored_output_violation = (
                self._history_source == "agent_server" or not stored
            ) and session.service_session_id is not None
            if stored_output_violation:
                misconfigured = RuntimeError(
                    "The agent's chat client stored this turn server-side despite store=False for the inner model. "
                    "Configure the client to honor store=False, or use history_source='service' with store=true."
                )
                logger.error("%s", misconfigured)
                if request_failure is None and not request_interrupted:
                    request_failure = misconfigured
            if (
                self._history_source == "service"
                and stored
                and _HOSTED_PROVIDER_STATE_KEY not in session.state
                and session.service_session_id is None
                and request_failure is None
                and not request_interrupted
                and not (cancellation_signal.is_set() and context.client_cancelled)
            ):
                request_failure = RuntimeError(
                    "history_source='service' requires the chat client to return a service continuation ID."
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
                    await session_storage.set(context.response_id, session)
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
                        await session_storage.set(context.conversation_id, session)
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
                raise RuntimeError(
                    "Provider background submission stopped before its token was saved; cannot safely retry it."
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
                raise RuntimeError("Cannot recover a provider background job without its stored continuation token.")
            saved_payload = cast(Mapping[str, Any], saved)
            if saved_payload.get("outer_response_id") != context.response_id:
                raise RuntimeError("Cannot recover a provider background job without its stored continuation token.")
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

    async def _handle_inner_workflow(
        self,
        request: CreateResponse,
        context: ResponseContext,
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker,
        cancellation_signal: asyncio.Event,
        agent: WorkflowAgent,
    ) -> AsyncGenerator[ResponseStreamEvent | ResponseCheckpointEvent]:
        """Handle the creation of a response for a workflow agent."""
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
                        checkpoint_id, checkpoint_storage, context.response_id, agent
                    )
                else:
                    latest_checkpoint = await checkpoint_storage.get_latest(workflow_name=agent.workflow.name)
                    if latest_checkpoint is not None:
                        logger.debug(
                            "Found a workflow checkpoint %s but no prior response snapshot was durably persisted; "
                            "resuming from the latest checkpoint",
                            latest_checkpoint.checkpoint_id,
                        )
                        run_stream = self._resume_workflow_from_checkpoint(
                            latest_checkpoint.checkpoint_id,
                            checkpoint_storage,
                            context.response_id,
                            agent,
                        )
                    else:
                        # No checkpoint was ever paired with a persisted response snapshot (e.g. the crash
                        # happened before the very first response checkpoint() call); replay the original
                        # input as a fresh entry, per the recovered-input parity guarantee
                        # (context.get_input_items() is unchanged from fresh entry).
                        logger.debug(
                            "Serving recovery request with no prior workflow checkpoint; replaying original input"
                        )
                        run_stream = agent.run(
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
                latest_checkpoint = await restore_checkpoint_storage.get_latest(workflow_name=agent.workflow.name)

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
                    # and populates ``agent.pending_requests``. That is the correct
                    # state: those requests are genuinely outstanding, and the next
                    # ``run(input_messages, ...)`` call may contain ``function_call_output``
                    # items (carried as FunctionResult/FunctionApprovalResponse content)
                    # that fulfill them via :meth:`WorkflowAgent._process_pending_requests`.
                    restore_iter = _SignalledIterator(
                        agent.run(
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

                run_stream = agent.run(
                    input_messages,
                    stream=True,
                    checkpoint_storage=checkpoint_storage,
                )

            workflow_name = agent.workflow.name

            async def latest_checkpoint_id() -> str | None:
                latest = await checkpoint_storage.get_latest(workflow_name=workflow_name)
                return latest.checkpoint_id if latest is not None else None

            def snapshot_response(
                checkpoint_id: str | None,
            ) -> Generator[ResponseStreamEvent | ResponseCheckpointEvent]:
                # Pair the response output emitted so far with the workflow checkpoint it corresponds
                # to, so recovery from that checkpoint replays exactly the updates that came after it.
                if checkpoint_id is None or checkpoint_id == response_event_stream.internal_metadata.get(
                    _LATEST_CHECKPOINT_ID_KEY
                ):
                    return
                yield from tracker.close()
                response_event_stream.internal_metadata[_LATEST_CHECKPOINT_ID_KEY] = checkpoint_id
                yield response_event_stream.checkpoint()

            main_iter = _SignalledIterator(
                run_stream,
                context.shutdown,
                cancellation_signal,
                # The runner creates a checkpoint at the end of each superstep, inside the generator
                # that produces the updates (see RunnerImpl.run_until_convergence). Stamping each
                # update with the latest checkpoint as it was produced tells which checkpoint the
                # update follows; the driver runs one update ahead, so by the time an update is
                # consumed the workflow may already have checkpointed past it.
                stamp=latest_checkpoint_id if self._resilient_background else None,
            )
            async with aclosing(main_iter):
                async for update in main_iter:
                    if self._resilient_background:
                        # Every update before this one belongs to the stamped checkpoint (or an
                        # earlier one), so the output so far can be snapshotted against it. If the
                        # workflow crashes before any update is produced, no snapshot is taken and
                        # recovery still resumes from the latest workflow checkpoint.
                        for event in snapshot_response(main_iter.stamp):
                            yield event

                    async for event in tracker.handle_update(update, approval_storage=approval_storage):
                        yield event
            # Cancellation needs no extra action here (the loop above already stopped); shutdown
            # does, but only if it's what actually stopped the loop, not a natural completion.
            if main_iter.signalled and context.shutdown.is_set():
                await context.exit_for_recovery()
            elif self._resilient_background and not main_iter.signalled:
                # The workflow ran to completion: pair its final checkpoint with the full output, so
                # recovery after this point does not replay the last superstep.
                for event in snapshot_response(await latest_checkpoint_id()):
                    yield event
        except Exception:
            logger.exception("Failed to produce response for workflow agent")
            raise

    async def _resume_workflow_from_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_storage: CheckpointStorage,
        response_id: str,
        agent: WorkflowAgent,
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
            tracker.discard_pending_container_file_citations()
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

    def __init__(
        self,
        stream: ResponseEventStream,
        allowed_oauth_consent_origins: frozenset[str] | None = None,
    ) -> None:
        self._stream = stream
        self._allowed_oauth_consent_origins = allowed_oauth_consent_origins
        self._usage_details: UsageDetails | None = None
        persisted_usage = stream.internal_metadata.get(_HOSTED_PROVIDER_USAGE_KEY)
        if persisted_usage is not None:
            if not isinstance(persisted_usage, Mapping) or any(
                not isinstance(key, str) or (value is not None and type(value) is not int)
                for key, value in cast(Mapping[object, object], persisted_usage).items()
            ):
                raise RuntimeError("The persisted provider usage is invalid.")
            self._usage_details = cast(UsageDetails, dict(cast(Mapping[str, int | None], persisted_usage)))
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
        self._outstanding_computer_calls: set[str] = set()
        self._oauth_consent_requests: set[tuple[str, str]] = set()
        self._pending_container_file_citations: dict[str, _ContainerFileCitation] = {}
        self._message_text_annotations: dict[int, list[ContainerFileCitationBody]] = {}
        # Set when an agent update reports the model stopped early (content filter, token
        # limit); the response then ends as ``incomplete`` instead of ``completed`` so callers
        # can tell a cut-short turn from a successful one. Mirrored into the stream's
        # ``internal_metadata`` so it survives a resilient checkpoint/recovery cycle, which
        # rebuilds this tracker from the persisted response.
        self._incomplete_reason: ResponseIncompleteReason | None = None
        persisted_reason = stream.internal_metadata.get(_INCOMPLETE_REASON_KEY)
        if isinstance(persisted_reason, str):
            with suppress(ValueError):
                self._incomplete_reason = ResponseIncompleteReason(persisted_reason)
        persisted_citations = stream.internal_metadata.get(_PENDING_CONTAINER_FILE_CITATIONS_KEY)
        if persisted_citations is not None:
            if not isinstance(persisted_citations, Sequence) or isinstance(
                persisted_citations, (str, bytes, bytearray)
            ):
                raise RuntimeError("The persisted container file citations are invalid.")
            for raw_citation in cast(Sequence[Any], persisted_citations):
                if not isinstance(raw_citation, Mapping):
                    raise RuntimeError("The persisted container file citations are invalid.")
                citation = cast(Mapping[str, Any], raw_citation)
                container_id = citation.get("container_id")
                file_id = citation.get("file_id")
                filename = citation.get("filename")
                if (
                    not isinstance(container_id, str)
                    or not container_id
                    or not isinstance(file_id, str)
                    or not file_id
                    or not isinstance(filename, str)
                    or not filename
                ):
                    raise RuntimeError("The persisted container file citations are invalid.")
                self._pending_container_file_citations[filename] = _ContainerFileCitation(
                    container_id=container_id,
                    file_id=file_id,
                    filename=filename,
                )
        for item in stream.response.get("output", []):
            if not isinstance(item, Mapping):
                continue
            persisted_item = cast(Mapping[str, Any], item)
            if persisted_item.get("type") == "computer_call":
                call_id = persisted_item.get("call_id")
                if isinstance(call_id, str):
                    self._outstanding_computer_calls.add(call_id)
            elif persisted_item.get("type") == "computer_call_output":
                if isinstance(call_id := persisted_item.get("call_id"), str):
                    self._outstanding_computer_calls.discard(call_id)
            if persisted_item.get("type") != "oauth_consent_request":
                continue
            consent_link = persisted_item.get("consent_link")
            server_label = persisted_item.get("server_label")
            if isinstance(consent_link, str) and isinstance(server_label, str):
                self._oauth_consent_requests.add((consent_link, server_label))

    @property
    def usage_details(self) -> UsageDetails | None:
        """Return usage retained with the provider output checkpoint."""
        return self._usage_details

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

    @property
    def incomplete_reason(self) -> ResponseIncompleteReason | None:
        """Return why the turn was cut short, if any update reported a truncating finish reason."""
        return self._incomplete_reason

    def record_finish_reason(self, finish_reason: str | None) -> None:
        """Note the finish reason of an agent update.

        Only finish reasons that mean the model stopped early are retained, mapped onto the
        Responses ``incomplete_details.reason`` vocabulary. A content filter is kept in
        preference to a token limit if both are seen during a multi-step turn, since it is the
        more actionable signal for the caller.
        """
        if finish_reason == "content_filter":
            self._incomplete_reason = ResponseIncompleteReason.CONTENT_FILTER
        elif finish_reason == "length" and self._incomplete_reason is None:
            self._incomplete_reason = ResponseIncompleteReason.MAX_OUTPUT_TOKENS
        else:
            return
        self._stream.internal_metadata[_INCOMPLETE_REASON_KEY] = self._incomplete_reason.value

    async def handle_update(
        self,
        update: AgentResponseUpdate,
        *,
        approval_storage: FunctionApprovalStore | None = None,
    ) -> AsyncGenerator[ResponseStreamEvent]:
        """Process one agent update: note its finish reason, then handle each of its contents.

        This is the single entry point for both the plain-agent and the workflow loops, so the
        finish reason cannot be forgotten on one of them.
        """
        self.record_finish_reason(update.finish_reason)
        for content in update.contents:
            async for event in self.handle(content, message_id=update.message_id, approval_storage=approval_storage):
                yield event

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
            citations = _container_file_citations_from_function_result(content)
            if citations:
                for citation in citations:
                    self._pending_container_file_citations[citation.filename] = citation
                self._persist_pending_container_file_citations()
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
                    outcome = (
                        FunctionShellCallOutputTimeoutOutcome(type="timeout")
                        if getattr(out, "timed_out", False)
                        else FunctionShellCallOutputExitOutcome(
                            type="exit",
                            exit_code=exit_code if exit_code is not None else 0,
                        )
                    )
                    output_items.append(
                        FunctionShellCallOutputContent(
                            stdout=getattr(out, "stdout", "") or "",
                            stderr=getattr(out, "stderr", "") or "",
                            outcome=outcome,
                        )
                    )
            async for event in self._stream.output_item_function_shell_call_output(
                content.call_id or "",
                output_items,
                status=content.status or "completed",
                max_output_length=content.max_output_length,
            ):
                yield event

        elif content.type == "computer_tool_call":
            if not content.id or not content.call_id or not content.actions:
                raise ValueError("A computer call requires an item id, call_id, and actions.")
            if content.call_id in self._outstanding_computer_calls:
                return
            for event in self._close():
                yield event
            if IdGenerator.is_valid(content.id)[0]:
                builder = self._stream.add_output_item(content.id)
            else:
                logger.warning("Remapping computer call item id %r to an AgentServer id.", content.id)
                builder = self._stream.add_output_item_computer_call()
            status = content.status if content.status is not None else "completed"
            if status not in ("in_progress", "completed", "incomplete"):
                raise ValueError(f"Unsupported computer call status: {status!r}")
            item = OutputItemComputerToolCall(
                type="computer_call",
                id=builder.item_id,
                call_id=content.call_id,
                actions=cast(list[ComputerAction], content.actions),
                pending_safety_checks=cast(list[ComputerCallSafetyCheckParam], content.pending_safety_checks or []),
                status=status,
            )
            if content.additional_properties.get("computer_action_format") == "single":
                if len(content.actions) != 1:
                    raise ValueError("A preview computer call requires exactly one action.")
                item.pop("actions")
                item["action"] = cast(ComputerAction, content.actions[0])
            yield builder.emit_added(item)
            yield builder.emit_done(item)
            self._outstanding_computer_calls.add(content.call_id)

        elif content.type == "computer_tool_result":
            if not content.call_id or content.screenshot is None:
                raise ValueError("A computer result requires a call_id and screenshot.")
            for event in self._close():
                yield event
            if content.id and IdGenerator.is_valid(content.id)[0]:
                builder = self._stream.add_output_item(content.id)
            else:
                if content.id:
                    logger.warning("Remapping computer output item id %r to an AgentServer id.", content.id)
                builder = self._stream.add_output_item_computer_call_output()
            item = OutputItemComputerToolCallOutput(
                type="computer_call_output",
                id=builder.item_id,
                call_id=content.call_id,
                output=cast(ComputerScreenshotImage, _computer_screenshot_to_output(content.screenshot)),
            )
            if content.status is not None:
                if content.status not in ("in_progress", "completed", "incomplete"):
                    raise ValueError(f"Unsupported computer output status: {content.status!r}")
                item["status"] = content.status
            if content.acknowledged_safety_checks is not None:
                item["acknowledged_safety_checks"] = cast(
                    list[ComputerCallSafetyCheckParam], content.acknowledged_safety_checks
                )
            yield builder.emit_added(item)
            yield builder.emit_done(item)
            self._outstanding_computer_calls.discard(content.call_id)

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
            if not _is_allowed_oauth_consent_link(consent_link, self._allowed_oauth_consent_origins):
                raise ValueError("OAuth consent request content must include an allowed safe HTTPS consent link.")

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
        """Flush any remaining active builder without discarding recoverable state."""
        yield from self._close()

    def discard_pending_container_file_citations(self) -> None:
        """Discard unmatched citations immediately before a terminal response event."""
        self._pending_container_file_citations.clear()
        self._persist_pending_container_file_citations()

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
        self._message_text_annotations.clear()
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
                message_done = self._message_item.emit_done()
                if self._message_text_annotations:
                    message_done_dict = cast(dict[str, Any], message_done)
                    item = cast(dict[str, Any], message_done_dict["item"])
                    content_parts = cast(list[dict[str, Any]], item["content"])
                    for content_index, annotations in self._message_text_annotations.items():
                        if content_index >= len(content_parts):
                            raise RuntimeError("Container file citation content index is out of range.")
                        content_parts[content_index]["annotations"] = annotations

                    response_output = self._stream.response.get("output")
                    output_index = self._message_item.output_index
                    if not isinstance(response_output, list):
                        raise RuntimeError("Container file citation output index is out of range.")
                    response_output_items = cast(list[Any], response_output)
                    if output_index >= len(response_output_items):
                        raise RuntimeError("Container file citation output index is out of range.")
                    response_output_items[output_index] = item
                yield message_done
            self._message_item = None
            self._message_text_annotations.clear()

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
            annotations = self._container_file_annotations_for_text(accumulated)
            yield self._text_content.emit_text_done(accumulated)
            for annotation in annotations:
                yield self._text_content.emit_annotation_added(annotation)
            content_done = self._text_content.emit_done()
            if annotations:
                content_done_dict = cast(dict[str, Any], content_done)
                part = cast(dict[str, Any], content_done_dict["part"])
                part["annotations"] = annotations
                self._message_text_annotations[self._text_content.content_index] = annotations
            yield content_done
            self._text_content = None
        elif self._active_type == "refusal" and self._refusal_content is not None:
            yield self._refusal_content.emit_refusal_done(accumulated)
            yield self._refusal_content.emit_done()
            self._refusal_content = None
        self._active_type = None
        self._active_id = None
        self._accumulated.clear()

    def _container_file_annotations_for_text(self, text: str) -> list[ContainerFileCitationBody]:
        candidates: list[tuple[int, int, str, _ContainerFileCitation]] = []
        for filename, citation in self._pending_container_file_citations.items():
            search_index = 0
            while True:
                start_index = text.find(filename, search_index)
                if start_index < 0:
                    break
                end_index = start_index + len(filename)
                if _has_container_filename_boundaries(text, start_index, end_index):
                    candidates.append((start_index, end_index, filename, citation))
                search_index = start_index + 1

        candidates.sort(key=lambda match: (-(match[1] - match[0]), match[0], match[2]))
        selected: list[tuple[int, int, str, _ContainerFileCitation]] = []
        selected_filenames: set[str] = set()
        for candidate in candidates:
            start_index, end_index, filename, _ = candidate
            if filename in selected_filenames:
                continue
            if any(
                start_index < selected_end and selected_start < end_index
                for selected_start, selected_end, _, _ in selected
            ):
                continue
            selected.append(candidate)
            selected_filenames.add(filename)

        annotations: list[ContainerFileCitationBody] = []
        for start_index, end_index, filename, citation in sorted(selected, key=lambda match: match[0]):
            annotations.append(
                ContainerFileCitationBody(
                    type="container_file_citation",
                    container_id=citation.container_id,
                    file_id=citation.file_id,
                    filename=citation.filename,
                    start_index=start_index,
                    end_index=end_index,
                )
            )
            del self._pending_container_file_citations[filename]
        if annotations:
            self._persist_pending_container_file_citations()
        return annotations

    def _persist_pending_container_file_citations(self) -> None:
        if not self._pending_container_file_citations:
            self._stream.internal_metadata.pop(_PENDING_CONTAINER_FILE_CITATIONS_KEY, None)
            return
        self._stream.internal_metadata[_PENDING_CONTAINER_FILE_CITATIONS_KEY] = [
            {
                "container_id": citation.container_id,
                "file_id": citation.file_id,
                "filename": citation.filename,
            }
            for citation in self._pending_container_file_citations.values()
        ]


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


def _computer_safety_checks(checks: Sequence[Mapping[str, Any]] | None) -> list[ComputerSafetyCheck] | None:
    if checks is None:
        return None
    parsed: list[ComputerSafetyCheck] = []
    for check in checks:
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id:
            raise ValueError("Computer safety checks require an id.")
        entry = ComputerSafetyCheck(id=check_id)
        for key in ("code", "message"):
            value = check.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"Computer safety check {key} must be a string.")
                entry[key] = value
        parsed.append(entry)
    return parsed


def _computer_screenshot_from_output(output: Mapping[str, Any]) -> Content:
    if output.get("type") != "computer_screenshot":
        raise ValueError("Computer call output must contain a computer screenshot.")
    image_url = output.get("image_url")
    file_id = output.get("file_id")
    additional_properties: dict[str, Any] = {}
    if detail := output.get("detail"):
        additional_properties["detail"] = detail
    if isinstance(image_url, str) and image_url:
        if file_id is not None:
            additional_properties["file_id"] = file_id
        return Content.from_uri(image_url, additional_properties=additional_properties)
    if isinstance(file_id, str) and file_id:
        return Content.from_hosted_file(file_id, additional_properties=additional_properties)
    raise ValueError("Computer screenshot is missing its image URL or file ID.")


def _computer_screenshot_to_output(screenshot: Content) -> dict[str, Any]:
    output: dict[str, Any] = {"type": "computer_screenshot"}
    if screenshot.type in ("data", "uri") and screenshot.uri:
        output["image_url"] = screenshot.uri
        if file_id := screenshot.additional_properties.get("file_id"):
            output["file_id"] = file_id
    elif screenshot.type == "hosted_file" and screenshot.file_id:
        output["file_id"] = screenshot.file_id
    else:
        raise ValueError("A computer screenshot requires image data, a URI, or a hosted file.")
    if detail := screenshot.additional_properties.get("detail"):
        output["detail"] = detail
    return output


def _shell_command_output_to_content(output: Mapping[str, Any]) -> Content:
    outcome = output["outcome"]
    outcome_type = outcome.get("type")
    return Content.from_shell_command_output(
        stdout=output.get("stdout") or "",
        stderr=output.get("stderr") or "",
        exit_code=outcome.get("exit_code") if outcome_type == "exit" else None,
        timed_out=True if outcome_type == "timeout" else False if outcome_type == "exit" else None,
    )


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
        outputs = [_shell_command_output_to_content(out) for out in (item["output"] or [])]
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
        plural_actions = item.get("actions")
        singular_action = item.get("action")
        actions = plural_actions or ([singular_action] if singular_action is not None else [])
        if not actions:
            raise ValueError("Computer call is missing its ordered actions.")
        props = {"computer_action_format": "single"} if not plural_actions and singular_action is not None else None
        return Message(
            role="assistant",
            contents=[
                Content.from_computer_tool_call(
                    id=item["id"],
                    call_id=item["call_id"],
                    actions=actions,
                    status=item.get("status"),
                    pending_safety_checks=_computer_safety_checks(item.get("pending_safety_checks")),
                    additional_properties=props,
                )
            ],
        )

    if item["type"] == "computer_call_output":
        return Message(
            role="tool",
            contents=[
                Content.from_computer_tool_result(
                    id=item.get("id"),
                    call_id=item["call_id"],
                    screenshot=_computer_screenshot_from_output(item["output"]),
                    status=item.get("status"),
                    acknowledged_safety_checks=_computer_safety_checks(item.get("acknowledged_safety_checks")),
                )
            ],
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
        return _computer_screenshot_from_output(content)

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
