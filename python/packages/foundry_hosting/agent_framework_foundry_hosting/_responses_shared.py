# Copyright (c) Microsoft. All rights reserved.

"""Share Responses wire conversion, streaming, and validation between agent and workflow hosts."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import re
import uuid
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Mapping,
    Sequence,
)
from contextlib import suppress
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Generic, Literal, TypeGuard, TypeVar, cast
from urllib.parse import urlparse

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    ComputerSafetyCheck,
    Content,
    FinishReason,
    Message,
    ResponseStream,
    SessionStore,
    UsageDetails,
    add_usage_details,
    get_namespaced_value,
)
from agent_framework import (
    Annotation as FrameworkAnnotation,
)
from agent_framework._mcp import _MCP_TOOL_RESULT_HOST_PAYLOAD_KEY  # pyright: ignore[reportPrivateUsage]
from agent_framework._tools import (
    _bind_approval_response_to_pending_request,  # pyright: ignore[reportPrivateUsage]
    _load_pending_approval_requests,  # pyright: ignore[reportPrivateUsage]
)
from agent_framework._types import _get_annotation_text_span_regions  # pyright: ignore[reportPrivateUsage]
from agent_framework.observability import OBSERVABILITY_SETTINGS
from azure.ai.agentserver.responses import (
    ResponseContext,
)
from azure.ai.agentserver.responses._id_generator import IdGenerator
from azure.ai.agentserver.responses.aio import ResponseEventStream
from azure.ai.agentserver.responses.models import (
    Annotation as ResponsesAnnotation,
)
from azure.ai.agentserver.responses.models import (
    ComputerAction,
    ComputerCallSafetyCheckParam,
    ComputerScreenshotImage,
    ContainerFileCitationBody,
    CreateResponse,
    FileCitationBody,
    FilePath,
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
    OutputItemMcpApprovalRequest,
    OutputItemReasoningItem,
    OutputMessageContent,
    ResponseIncompleteReason,
    ResponseStreamEvent,
    ResponseUsage,
    ResponseUsageInputTokensDetails,
    ResponseUsageOutputTokensDetails,
    UrlCitationBody,
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
from mcp import MCPError

logger = logging.getLogger(__name__)

_MODEL_OUTPUT_KIND_KEY = "model_output_kind"
_MODEL_OUTPUT_REFUSAL = "refusal"
_NATIVE_APPROVAL_ID_KEY = "agent_framework_approval_id"
_NATIVE_APPROVAL_SESSION_KEY = "agent_framework_approval_session_id"
_HOSTED_PROVIDER_STATE_KEY = "_foundry_provider_background"
_HOSTED_SOURCE_CONVERSATION_KEY = "_foundry_source_conversation"
_HOSTED_SERVICE_CHILD_KEY = "_foundry_service_child"
_HOSTED_CONVERSATION_CLAIM_KEY = "_foundry_conversation_claim"
_HOSTED_CONVERSATION_COMMITTED_KEY = "_foundry_conversation_committed"
_HOSTED_PROVIDER_OUTPUT_COUNT_KEY = "_foundry_provider_output_count"
_HOSTED_PROVIDER_USAGE_KEY = "_foundry_provider_usage"
_PENDING_CONTAINER_FILE_CITATIONS_KEY = "_foundry_pending_container_file_citations"
_CONTAINER_FILE_CITATIONS_KEY = "container_file_citations"
_PUBLIC_STREAM_FAILURE_MESSAGE = "An internal server error occurred."


class _PublicResponseFailure(Exception):
    """Mark a vetted failure message as safe for client-visible serialization."""

    def __init__(self, error: Exception, public_message: str | None = None) -> None:
        super().__init__(public_message or str(error) or type(error).__name__)
        self.error = error
        self.public_message = public_message or str(error) or type(error).__name__


async def _set_agent_session(  # pyright: ignore[reportUnusedFunction]
    store: SessionStore, session_id: str, session: AgentSession
) -> None:
    """Persist a session while preserving the established public conflict contract."""
    try:
        await store.set(session_id, session)
    except RuntimeError as exc:
        if str(exc) == "Another request advanced this agent session; reload before writing.":
            raise _PublicResponseFailure(exc) from None
        raise


def _log_response_failure(  # pyright: ignore[reportUnusedFunction]
    phase: str, response_id: str, exc: BaseException
) -> None:
    """Log a correlated hosted response failure under the sensitive-data policy."""
    diagnostic_exception = exc.error if isinstance(exc, _PublicResponseFailure) else exc
    if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:
        logger.error(
            "Hosted Responses failure (phase=%s, response_id=%s, error_type=%s).",
            phase,
            response_id,
            type(diagnostic_exception).__name__,
            exc_info=(
                type(diagnostic_exception),
                diagnostic_exception,
                diagnostic_exception.__traceback__,
            ),
        )
    else:
        logger.error(
            "Hosted Responses failure (phase=%s, response_id=%s, error_type=%s).",
            phase,
            response_id,
            type(diagnostic_exception).__name__,
        )


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


def _annotations_to_output_text(
    annotations: Sequence[FrameworkAnnotation] | None,
) -> list[ResponsesAnnotation]:
    """Convert framework citations into Responses output-text annotations.

    Source-coordinate regions describe the cited source, not generated content, and
    are not emitted as output-text spans.
    """
    if not annotations or not isinstance(annotations, Sequence) or isinstance(annotations, (str, bytes)):
        return []

    output_annotations: list[ResponsesAnnotation] = []
    for annotation in annotations:
        if not isinstance(annotation, Mapping):
            continue
        annotation_mapping = cast("Mapping[str, Any]", annotation)
        if annotation_mapping.get("type") != "citation":
            continue

        raw_properties = annotation_mapping.get("additional_properties")
        properties: Mapping[str, Any] = (
            cast("Mapping[str, Any]", raw_properties) if isinstance(raw_properties, Mapping) else {}
        )
        regions = _get_annotation_text_span_regions(annotation_mapping)
        file_id = annotation_mapping.get("file_id")
        url = annotation_mapping.get("url")
        title = annotation_mapping.get("title")
        container_id = properties.get("container_id")
        index = properties.get("index")

        if isinstance(container_id, str) and container_id and isinstance(file_id, str) and file_id:
            for region in regions:
                output_annotations.append(
                    ContainerFileCitationBody(
                        type="container_file_citation",
                        container_id=container_id,
                        file_id=file_id,
                        filename=url if isinstance(url, str) else "",
                        start_index=region["start_index"],
                        end_index=region["end_index"],
                    )
                )
        elif isinstance(url, str) and url and not file_id:
            for region in regions:
                output_annotations.append(
                    UrlCitationBody(
                        type="url_citation",
                        url=url,
                        title=title if isinstance(title, str) else "",
                        start_index=region["start_index"],
                        end_index=region["end_index"],
                    )
                )
        elif (
            isinstance(file_id, str) and file_id and isinstance(url, str) and url and type(index) is int and index >= 0
        ):
            output_annotations.append(
                FileCitationBody(
                    type="file_citation",
                    file_id=file_id,
                    filename=url,
                    index=index,
                )
            )
        elif isinstance(file_id, str) and file_id and type(index) is int and index >= 0:
            output_annotations.append(
                FilePath(
                    type="file_path",
                    file_id=file_id,
                    index=index,
                )
            )

    return output_annotations


def _is_refusal_text_content(content: Content) -> bool:
    return (
        content.type == "text"
        and get_namespaced_value(
            content.additional_properties,
            "core",
            _MODEL_OUTPUT_KIND_KEY,
            content.additional_properties.get(_MODEL_OUTPUT_KIND_KEY),
        )
        == _MODEL_OUTPUT_REFUSAL
    )


def _refusal_additional_properties() -> dict[str, Any]:
    return {
        "core": {_MODEL_OUTPUT_KIND_KEY: _MODEL_OUTPUT_REFUSAL},
        _MODEL_OUTPUT_KIND_KEY: _MODEL_OUTPUT_REFUSAL,
    }


def _openai_value(content: Content, key: str, *legacy_keys: str, default: Any = None) -> Any:
    value = get_namespaced_value(content.additional_properties, "openai", key, None)
    if value is not None:
        return value
    for legacy_key in legacy_keys:
        if legacy_key in content.additional_properties:
            return content.additional_properties[legacy_key]
    return default


def _reject_busy_conversation(session: AgentSession) -> None:  # pyright: ignore[reportUnusedFunction]
    if session.state.get(_HOSTED_CONVERSATION_CLAIM_KEY) is not None:
        raise _PublicResponseFailure(
            RuntimeError(
                "A service-backed conversation already has an in-flight turn. Wait for it to finish; "
                "if it failed or was cancelled after dispatch, start a new conversation rather than "
                "reusing a possibly changed provider thread."
            )
        )


def _request_without_reserved_metadata(request: CreateResponse) -> CreateResponse:
    """Copy a create request with any client-supplied reserved metadata bag removed.

    ``ResponseEventStream`` seeds the response from the request, and host recovery later trusts
    that bag for incomplete status, provider cursors, usage, and citations. Only a persisted
    response is a trusted source. The caller's request mapping is left unchanged.
    """
    raw_metadata = request.get("metadata")
    if not isinstance(raw_metadata, Mapping):
        return request
    # Metadata is a TypedDict of known public keys. Cast so a client-supplied reserved key is visible.
    metadata = cast(Mapping[str, Any], raw_metadata)
    if _RESERVED_RESPONSE_METADATA_KEY not in metadata:
        return request
    public_metadata: dict[str, Any] = {
        key: value for key, value in metadata.items() if key != _RESERVED_RESPONSE_METADATA_KEY
    }
    seeded: dict[str, Any] = dict(request)
    if public_metadata:
        seeded["metadata"] = public_metadata
    else:
        seeded.pop("metadata", None)
    return cast(CreateResponse, seeded)


def _create_response_event_stream(  # pyright: ignore[reportUnusedFunction]
    context: ResponseContext, request: CreateResponse
) -> ResponseEventStream:
    """Create a response stream from recovery state or the originating request."""
    if context.is_recovery:
        persisted_response = context.persisted_response
        if persisted_response is not None:
            return ResponseEventStream(response=persisted_response, response_id=context.response_id)
    return ResponseEventStream(
        request=_request_without_reserved_metadata(request),
        response_id=context.response_id,
    )


def _hosted_internal_metadata(stream: ResponseEventStream) -> dict[str, Any]:
    """Keep private state in the durable envelope, outside the public metadata quota.

    The SDK strips its reserved ``internal_metadata`` key at every wire boundary. Older
    checkpoints used its quota-limited response metadata bag; copy that trusted state only
    when the envelope has no private bag of its own.
    """
    metadata = stream.response.get("internal_metadata")
    if metadata is None:
        metadata = dict(stream.internal_metadata)
        stream.response["internal_metadata"] = metadata
    if not isinstance(metadata, dict):
        raise RuntimeError("The persisted host metadata is invalid.")
    return cast(dict[str, Any], metadata)


def _read_persisted_incomplete_reason(stream: ResponseEventStream) -> str | None:
    """Return a truncating finish reason restored from a trusted response snapshot."""
    persisted = _hosted_internal_metadata(stream).get(_INCOMPLETE_REASON_KEY)
    if isinstance(persisted, str):
        return persisted
    details = stream.response.get("incomplete_details")
    if isinstance(details, Mapping):
        reason = cast(Mapping[str, Any], details).get("reason")
        if isinstance(reason, str):
            return reason
    return None


def _agent_response_updates(  # pyright: ignore[reportUnusedFunction]
    response: AgentResponse[Any], response_id: str
) -> list[AgentResponseUpdate]:
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


async def _await_before_signal(  # pyright: ignore[reportUnusedFunction]
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
# SDK-reserved response metadata entry. It round-trips server-owned recovery state (this reason,
# provider cursors, usage, and citations). Clients may send the same key; it is never trusted on a
# fresh request. Foundry counts it toward the 16-entry public metadata limit.
_RESERVED_RESPONSE_METADATA_KEY = "_internal_metadata"


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


def _normalize_allowed_oauth_consent_origins(  # pyright: ignore[reportUnusedFunction]
    allowed_origins: Sequence[str] | None,
) -> frozenset[str] | None:
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
    inner_exception = next((arg for arg in exc.args if isinstance(arg, MCPError)), None)
    if inner_exception is not None and inner_exception.code == CONSENT_ERROR_CODE:
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


# region Active Builder State


class _OutputItemTracker:  # pyright: ignore[reportUnusedClass]
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
        persisted_usage = _hosted_internal_metadata(stream).get(_HOSTED_PROVIDER_USAGE_KEY)
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
        self._text_annotations: list[ResponsesAnnotation] = []
        self._message_text_annotations: dict[int, list[ResponsesAnnotation]] = {}
        # Set when an agent update reports the model stopped early (content filter, token
        # limit); the response then ends as ``incomplete`` instead of ``completed`` so callers
        # can tell a cut-short turn from a successful one. Mirrored onto the response so it
        # survives a resilient checkpoint/recovery cycle, which rebuilds this tracker from the
        # persisted response.
        self._incomplete_reason: ResponseIncompleteReason | None = None
        persisted_reason = _read_persisted_incomplete_reason(stream)
        if persisted_reason is not None:
            with suppress(ValueError):
                self._incomplete_reason = ResponseIncompleteReason(persisted_reason)
        persisted_citations = _hosted_internal_metadata(stream).get(_PENDING_CONTAINER_FILE_CITATIONS_KEY)
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
        more actionable signal for the caller. The reason is recorded even when the caller's
        metadata already fills the public map, and that map is left intact.
        """
        if finish_reason == "content_filter":
            self._incomplete_reason = ResponseIncompleteReason.CONTENT_FILTER
        elif finish_reason == "length" and self._incomplete_reason is None:
            self._incomplete_reason = ResponseIncompleteReason.MAX_OUTPUT_TOKENS
        else:
            return
        _hosted_internal_metadata(self._stream)[_INCOMPLETE_REASON_KEY] = self._incomplete_reason.value

    def _consume_text_update(self, text: str, merge_mode: Literal["append", "replace"] | None) -> str:
        """Update the authoritative text buffer and return the wire delta still needed."""
        if merge_mode != "replace":
            self._accumulated.append(text)
            return text

        previous = "".join(self._accumulated)
        if text.startswith(previous):
            self._accumulated[:] = [text]
            return text[len(previous) :]
        if not previous:
            self._accumulated[:] = [text]
            return text
        raise _PublicResponseFailure(
            RuntimeError("Cannot project a divergent replacement text snapshot onto an append-only Responses stream.")
        )

    async def handle_update(
        self,
        update: AgentResponseUpdate,
        *,
        complete_message: bool = False,
        approval_session_id: str | None = None,
    ) -> AsyncGenerator[ResponseStreamEvent]:
        """Process one agent update: note its finish reason, then handle each of its contents.

        This is the single entry point for both the plain-agent and the workflow loops, so the
        finish reason cannot be forgotten on one of them. Set ``complete_message`` when the
        update contains a completed message's independent content parts rather than streaming
        deltas; text and refusal parts then retain their original boundaries and citation offsets.
        """
        self.record_finish_reason(update.finish_reason)
        for content in update.contents:
            async for event in self.handle(
                content,
                message_id=update.message_id,
                start_new_content_part=complete_message,
                approval_session_id=approval_session_id,
            ):
                yield event

    async def handle(
        self,
        content: Content,
        message_id: str | None = None,
        *,
        start_new_content_part: bool = False,
        approval_session_id: str | None = None,
    ) -> AsyncGenerator[ResponseStreamEvent]:
        """Process a content item, yielding its events.

        Args:
            content: The content item to process.
            message_id: The ``message_id`` of the update ``content`` came from, if any. A
                change in ``message_id`` across otherwise same-typed text content marks a new
                logical message and forces the previous output item closed, rather than being
                merged into it.
            start_new_content_part: Whether text and refusal content start a new independent
                content part instead of continuing the current streaming occurrence.
            approval_session_id: Native session identity used only to scope stored wire correlation.
        """
        if _is_refusal_text_content(content) and content.text is not None:
            for event in self._ensure_message_content("refusal", message_id, start_new_part=start_new_content_part):
                yield event
            self._active_message_id = message_id
            delta = self._consume_text_update(content.text, content.merge_mode)
            if delta and self._refusal_content is not None:
                yield self._refusal_content.emit_delta(delta)

        elif content.type == "text" and content.text is not None:
            for event in self._ensure_message_content("text", message_id, start_new_part=start_new_content_part):
                yield event
            self._active_message_id = message_id
            delta = self._consume_text_update(content.text, content.merge_mode)
            for annotation in _annotations_to_output_text(content.annotations):
                if annotation not in self._text_annotations:
                    self._text_annotations.append(annotation)
            if delta and self._text_content is not None:
                yield self._text_content.emit_delta(delta)

        elif content.type == "text_reasoning":
            if self._active_type != "text_reasoning" or (content.id is not None and content.id != self._active_id):
                for event in self._close():
                    yield event
                for event in self._open_reasoning(content):
                    yield event
            if encrypted_content := _reasoning_encrypted_content(content):
                self._reasoning_encrypted_content = encrypted_content
            if content.text:
                delta = self._consume_text_update(content.text, content.merge_mode)
                if delta and self._summary_part is not None:
                    yield self._summary_part.emit_text_delta(delta)

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
            delta = self._consume_text_update(args_str, content.merge_mode)
            if delta and self._fc_builder is not None:
                yield self._fc_builder.emit_arguments_delta(delta)

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
            delta = self._consume_text_update(args_str, content.merge_mode)
            if delta and self._mcp_builder is not None:
                yield self._mcp_builder.emit_arguments_delta(delta)

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
            result = _image_generation_result(content.outputs)
            if result is None:
                logger.warning("Image generation result has no base64 image; emitting it with an empty result.")
            async for event in self._stream.output_item_image_gen_call(result or ""):
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
            if _openai_value(content, "computer_action_format", "computer_action_format") == "single":
                if len(content.actions) != 1:
                    raise ValueError("A preview computer call requires exactly one action.")
                item.pop("actions")
                item["action"] = cast(ComputerAction, content.actions[0])
            yield builder.emit_added(item)
            yield builder.emit_done(item)
            self._outstanding_computer_calls.add(content.call_id)

        elif content.type == "computer_tool_result":
            if not content.call_id or content.screenshot is None:
                raise _PublicResponseFailure(ValueError("A computer result requires a call_id and screenshot."))
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
            function_call = content.function_call
            if not content.id or function_call is None or not function_call.name:
                raise ValueError("An approval request requires a native request ID and a named function call.")
            server_label = function_call.server_name or "agent_framework"
            wire_id = IdGenerator.new_mcp_approval_request_item_id(str(self._stream.response["id"]))
            item = OutputItemMcpApprovalRequest(
                type="mcp_approval_request",
                id=wire_id,
                server_label=server_label,
                name=function_call.name,
                arguments=_json_safe_to_str(function_call.arguments),
            )
            builder = self._stream.add_output_item(wire_id)
            builder.internal_metadata[_NATIVE_APPROVAL_ID_KEY] = content.id
            if approval_session_id is not None:
                builder.internal_metadata[_NATIVE_APPROVAL_SESSION_KEY] = approval_session_id
            yield builder.emit_added(item)
            yield builder.emit_done(item)

        elif content.type == "oauth_consent_request":
            for event in self._close():
                yield event

            consent_link = content.consent_link
            if not _is_allowed_oauth_consent_link(consent_link, self._allowed_oauth_consent_origins):
                raise ValueError("OAuth consent request content must include an allowed safe HTTPS consent link.")

            server_label = get_namespaced_value(
                content.additional_properties,
                "openai",
                "server_label",
                content.additional_properties.get("server_label"),
            )
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
        *,
        start_new_part: bool = False,
    ) -> Generator[ResponseStreamEvent]:
        message_changed = (
            message_id is not None and self._active_message_id is not None and message_id != self._active_message_id
        )
        if self._active_type == content_type and not message_changed and not start_new_part:
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
            self._text_annotations.clear()
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
            annotations = list(self._text_annotations)
            for annotation in self._container_file_annotations_for_text(accumulated):
                if annotation not in annotations:
                    annotations.append(annotation)
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
            self._text_annotations.clear()
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
            _hosted_internal_metadata(self._stream).pop(_PENDING_CONTAINER_FILE_CITATIONS_KEY, None)
            return
        _hosted_internal_metadata(self._stream)[_PENDING_CONTAINER_FILE_CITATIONS_KEY] = [
            {
                "container_id": citation.container_id,
                "file_id": citation.file_id,
                "filename": citation.filename,
            }
            for citation in self._pending_container_file_citations.values()
        ]


# endregion


# region Input Message Conversion


async def _items_to_messages(  # pyright: ignore[reportUnusedFunction]
    input_items: Sequence[Item],
    *,
    session: AgentSession | None = None,
    approval_ids: Mapping[str, str] | None = None,
) -> list[Message]:
    """Convert input items and restore native context for current approval decisions.

    Args:
        input_items: The input items to convert.
        session: Native session holding the agent's authoritative pending requests.
        approval_ids: Transport-only mapping from stored wire IDs to native request IDs.

    Returns:
        Native request context followed by the supported input messages.
    """
    messages: list[Message] = []
    if any(item["type"] == "mcp_approval_response" for item in input_items):
        requests = [
            request
            for request in _load_pending_approval_requests(session).values()
            if request.function_call is not None and not request.function_call.hosted
        ]
        if requests:
            # Capped wire history may omit calls. Core normalizes its own pending snapshots
            # into call/result pairs, including previously staged decisions in the same batch.
            messages.append(Message(role="assistant", contents=requests))
    for item in input_items:
        messages.append(await _item_to_message(item, session=session, approval_ids=approval_ids))
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
    openai_properties: dict[str, Any] = {}
    legacy_properties: dict[str, Any] = {}
    if detail := output.get("detail"):
        openai_properties["image_detail"] = detail
        legacy_properties["detail"] = detail
    additional_properties = {
        "openai": openai_properties,
        **legacy_properties,
    }
    if isinstance(image_url, str) and image_url:
        return Content.from_uri(
            image_url,
            file_id=file_id if isinstance(file_id, str) else None,
            additional_properties={
                **additional_properties,
                **({"file_id": file_id} if isinstance(file_id, str) else {}),
            },
        )
    if isinstance(file_id, str) and file_id:
        return Content.from_hosted_file(file_id, additional_properties=additional_properties)
    raise ValueError("Computer screenshot is missing its image URL or file ID.")


def _computer_screenshot_to_output(screenshot: Content) -> dict[str, Any]:
    output: dict[str, Any] = {"type": "computer_screenshot"}
    if screenshot.type in ("data", "uri") and screenshot.uri:
        output["image_url"] = screenshot.uri
        if file_id := screenshot.file_id or screenshot.additional_properties.get("file_id"):
            output["file_id"] = file_id
    elif screenshot.type == "hosted_file" and screenshot.file_id:
        output["file_id"] = screenshot.file_id
    else:
        raise ValueError("A computer screenshot requires image data, a URI, or a hosted file.")
    if detail := _openai_value(screenshot, "image_detail", "detail"):
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


async def _item_to_message(  # ruff: ignore[unused-async] -- Keep the shared async conversion contract.
    item: Item,
    *,
    session: AgentSession | None = None,
    approval_ids: Mapping[str, str] | None = None,
    _item_type_name: Literal["Item", "OutputItem"] = "Item",
) -> Message:
    """Converts an Item to a Message.

    Args:
        item: The Item to convert.
        session: Native session holding the agent's authoritative pending requests.
        approval_ids: Transport-only mapping from stored wire IDs to native request IDs.
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
        item_data = cast("Mapping[str, Any]", item)
        item_id = item_data.get("id")
        status = item_data.get("status")
        additional_properties: dict[str, Any] = {}
        if isinstance(item_id, str):
            additional_properties.update({"openai": {"item_id": item_id}, "fc_id": item_id})
        if status is not None:
            additional_properties["status"] = status
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    item["call_id"],
                    item["name"],
                    arguments=item["arguments"],
                    status=status if isinstance(status, str) else None,
                    additional_properties=additional_properties,
                )
            ],
        )

    if item["type"] == "function_call_output":
        call_id = item.get("call_id")
        if call_id is None:
            raise ValueError("Function call output item is missing a call_id.")
        item_id = item.get("id")
        result_additional_properties = (
            {
                "openai": {"item_id": item_id},
                "item_id": item_id,
            }
            if isinstance(item_id, str) and item_id
            else None
        )
        return Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id,
                    result=_json_safe_to_str(item["output"]),
                    status=item.get("status"),
                    additional_properties=result_additional_properties,
                )
            ],
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
        pending = _load_pending_approval_requests(session)
        request_id = approval_ids.get(item["id"]) if approval_ids is not None else item["id"]
        function_approval_request_content = pending.get(request_id) if request_id is not None else None
        if function_approval_request_content is None:
            raise _PublicResponseFailure(ValueError(f"No native pending approval matches {item['id']!r}."))
        return Message(
            role="assistant",
            contents=[function_approval_request_content],
        )

    if item["type"] == "mcp_approval_response":
        request_id = (
            approval_ids.get(item["approval_request_id"]) if approval_ids is not None else item["approval_request_id"]
        )
        response = Content(
            "function_approval_response",
            id=request_id,
            approved=item["approve"] is True,
        )
        bound = (
            _bind_approval_response_to_pending_request(response, session, consume=False)
            if session is not None and request_id is not None
            else None
        )
        if bound is None:
            raise _PublicResponseFailure(
                ValueError(f"No native pending approval matches {item['approval_request_id']!r}.")
            )
        response.function_call = bound.function_call
        return Message(
            role="user",
            contents=[response],
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
                    hosted=True,
                )
            ],
        )

    if item["type"] == "web_search_call":
        return Message(
            role="assistant",
            contents=[Content.from_function_call(item["id"], "web_search", informational_only=True, hosted=True)],
        )

    if item["type"] == "computer_call":
        plural_actions = item.get("actions")
        singular_action = item.get("action")
        actions = plural_actions or ([singular_action] if singular_action is not None else [])
        if not actions:
            raise ValueError("Computer call is missing its ordered actions.")
        props = (
            {
                "openai": {"computer_action_format": "single"},
                "computer_action_format": "single",
            }
            if not plural_actions and singular_action is not None
            else None
        )
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
                    hosted=True,
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
                    hosted=True,
                )
            ],
        )

    if item["type"] == "apply_patch_call_output":
        return Message(
            role="tool",
            contents=[Content.from_function_result(item["call_id"], result=_json_safe_to_str(item.get("output")))],
        )

    raise ValueError(f"Unsupported {_item_type_name} type: {item['type']}")


async def _output_items_to_messages(  # pyright: ignore[reportUnusedFunction]
    history: Sequence[OutputItem],
) -> list[Message]:
    """Converts a sequence of OutputItem objects to a list of Message objects.

    Historical approval controls are not replayed. Native session state owns
    pending requests; only current input carries new approval decisions.

    Args:
        history (Sequence[OutputItem]): The sequence of OutputItem objects to convert.

    Returns:
        list[Message]: The list of Message objects.
    """
    messages: list[Message] = []
    for item in history:
        if item["type"] in ("mcp_approval_request", "mcp_approval_response"):
            continue
        messages.append(await _output_item_to_message(item))
    return messages


def _native_approval_id(  # pyright: ignore[reportUnusedFunction]
    item: Mapping[str, Any], *, session_id: str | None = None
) -> str:
    """Read transport correlation, never executable authority, from a stored output item."""
    raw_metadata = item.get("internal_metadata")
    metadata: Mapping[str, Any] = cast(Mapping[str, Any], raw_metadata) if isinstance(raw_metadata, Mapping) else {}
    request_id = metadata.get(_NATIVE_APPROVAL_ID_KEY)
    if not isinstance(request_id, str) or not request_id:
        raise _PublicResponseFailure(
            ValueError("The approval uses an unsupported stored format; start a new conversation.")
        )
    if session_id is not None and metadata.get(_NATIVE_APPROVAL_SESSION_KEY) != session_id:
        raise _PublicResponseFailure(ValueError("The approval does not belong to this native session."))
    return request_id


async def _output_item_to_message(item: OutputItem, *, session: AgentSession | None = None) -> Message:
    """Converts an OutputItem to a Message.

    Args:
        item (OutputItem): The OutputItem to convert.
        session: Native session holding the agent's authoritative pending requests.

    Returns:
        Message: The converted Message.

    Raises:
        ValueError: If the OutputItem type is not supported.
    """
    if item["type"] == "oauth_consent_request":
        item_data = cast("Mapping[str, Any]", item)
        server_label = item_data.get("server_label")
        additional_properties = (
            {
                "openai": {"server_label": server_label},
                "server_label": server_label,
            }
            if isinstance(server_label, str) and server_label
            else None
        )
        return Message(
            role="assistant",
            contents=[
                Content.from_oauth_consent_request(
                    item["consent_link"],
                    additional_properties=additional_properties,
                )
            ],
        )

    if item["type"] == "structured_outputs":
        return Message(role="assistant", contents=[Content.from_text(_json_safe_to_str(item["output"]))])

    return await _item_to_message(
        cast(Item, item),
        session=session,
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
            additional_properties=_refusal_additional_properties(),
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
    additional_properties = (
        {
            "openai": {"content_type": "input_file"},
            "openai_content_type": "input_file",
            "filename": filename,
        }
        if filename
        else {
            "openai": {"content_type": "input_file"},
            "openai_content_type": "input_file",
        }
    )
    return Content.from_uri(data_uri, name=filename, additional_properties=additional_properties)


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
            additional_properties=_refusal_additional_properties(),
        )
    if content["type"] == "reasoning_text":
        return Content.from_text_reasoning(text=content["text"])
    if content["type"] == "input_image":
        detail = content.get("detail")
        additional_properties = {
            "openai": {
                "content_type": "input_image",
                **({"image_detail": detail} if isinstance(detail, str) else {}),
            },
            "openai_content_type": "input_image",
            **({"detail": detail} if isinstance(detail, str) else {}),
        }
        if image_url := content.get("image_url"):
            if image_url.startswith("data:"):
                return Content.from_uri(image_url, additional_properties=additional_properties)
            return Content.from_uri(image_url, media_type="image/*", additional_properties=additional_properties)
        if file_id := content.get("file_id"):
            return Content.from_hosted_file(file_id, additional_properties=additional_properties)
    if content["type"] == "input_file":
        filename = content.get("filename")
        additional_properties = {
            "openai": {"content_type": "input_file"},
            "openai_content_type": "input_file",
            **({"filename": filename} if isinstance(filename, str) else {}),
        }
        if file_url := content.get("file_url"):
            return Content.from_uri(
                file_url,
                name=filename if isinstance(filename, str) else None,
                additional_properties=additional_properties,
            )
        if file_id := content.get("file_id"):
            return Content.from_hosted_file(
                file_id,
                name=filename if isinstance(filename, str) else None,
                additional_properties=additional_properties,
            )
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


def _image_generation_result(outputs: Any) -> str | None:
    """Return the base64 image of an image generation tool result, as the Responses API expects.

    Only a non-empty, valid base64 string or the valid base64 payload of a base64 data URI qualifies. Other URIs
    (https, file, blob), data URIs without the base64 marker and malformed payloads are not base64, so they give
    None.
    """
    if isinstance(outputs, str):
        return outputs if _is_base64(outputs) else None
    items: Sequence[Any] = [outputs]
    if isinstance(outputs, Sequence) and not isinstance(outputs, (bytes, bytearray)):
        items = cast(Sequence[Any], outputs)
    for item in items:
        if isinstance(item, Content) and item.uri and item.uri.startswith("data:"):
            # RFC 2397: only the metadata before the first comma can carry the marker, as its last parameter.
            metadata, _, payload = item.uri.partition(",")
            if metadata.endswith(";base64") and _is_base64(payload):
                return payload
    return None


def _is_base64(value: str) -> bool:
    """Check whether a string is non-empty, valid base64."""
    if not value:
        return False
    try:
        base64.b64decode(value, validate=True)
    except ValueError:
        return False
    return True


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
