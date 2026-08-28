# Copyright (c) Microsoft. All rights reserved.

"""Simplified AG-UI orchestration - single linear flow."""

from __future__ import annotations  # noqa: I001

import copy
import json
import logging
import uuid
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, cast

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import (
    AgentSession,
    Content,
    HistoryProvider,
    InMemoryHistoryProvider,
    MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY,
    Message,
    SupportsAgentRun,
)
from agent_framework._middleware import FunctionMiddlewarePipeline
from agent_framework._tools import (
    _ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY,  # type: ignore
    _collect_approval_responses,  # type: ignore
    _get_tool_map,  # type: ignore
    _is_hosted_tool_approval,  # type: ignore
    _replace_approval_contents_with_results,  # type: ignore
    _TOOL_APPROVAL_STATE_KEY,  # type: ignore
    _try_execute_function_call_groups,  # type: ignore
    normalize_function_invocation_configuration,
)
from agent_framework._types import ResponseStream
from agent_framework.exceptions import AgentInvalidResponseException
from agent_framework.observability import (
    _use_telemetry_conversation_id,  # pyright: ignore[reportPrivateUsage]
)

from ._a2ui._state import build_ag_ui_context_slice, read_inject_a2ui_flag
from ._approval_lifecycle import (
    ApprovalExecutionOwner,
    ApprovalLifecycle,
    ApprovalOccurrence,
    ApprovalOccurrenceIdentity,
    ApprovalSnapshotReconciliation,
    ApprovalStatus,
    AuthorizedExecution,
    ClaimRecoveryPolicy,
    DeferredPendingToolTransitionOwner,
    ForwardedPendingToolTransitionOwner,
    HostedPendingToolTransitionOwner,
    LocalPendingToolTransitionOwner,
    ResumeDecision,
)
from ._approval_state import _APPROVAL_SCOPE_INPUT_KEY, InMemoryAGUIApprovalStateStore, approval_state_thread_id
from ._message_adapters import normalize_agui_input_messages
from ._predictive_state import PredictiveStateHandler
from ._tooling import collect_server_tools, merge_tools
from ._run_common import (
    FlowState,
    _approval_interrupt_for_function_call,  # type: ignore
    _approval_steps_response_schema,  # type: ignore
    _build_run_finished_event,  # type: ignore
    _cancelled_resume_interrupt_ids,  # type: ignore
    _close_reasoning_block,  # type: ignore
    _emit_content,  # type: ignore
    _extract_resume_payload,  # type: ignore
    _extract_tool_result_display,  # type: ignore
    _has_only_tool_calls,  # type: ignore
    _iterate_with_context,  # type: ignore
    _normalize_resume_interrupts,  # type: ignore
    _new_tool_call_segment_id,  # type: ignore
    _reconstruct_messages_from_thread_snapshot,  # type: ignore
    _resume_contract_error,  # type: ignore
    _resolve_ui_payload,  # type: ignore
    _stringify_tool_result,  # type: ignore
    _track_tool_call_segment,  # type: ignore
)
from ._snapshots import (
    _DEFAULT_STATE_INPUT_KEY,
    _SNAPSHOT_SCOPE_INPUT_KEY,
    AGUIThreadSnapshot,
)
from ._snapshot_session import ThreadSnapshotSession, _event_messages_to_snapshot_dicts
from ._utils import (
    canonical_function_arguments,
    convert_agui_tools_to_agent_framework,
    generate_event_id,
    get_conversation_id_from_update,
    get_role_value,
    make_json_safe,
    normalize_agui_role,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from ._agent import AgentConfig

logger = logging.getLogger(__name__)

# Keys that are internal to AG-UI orchestration and should not be passed to chat clients
AG_UI_INTERNAL_METADATA_KEYS = {"ag_ui_thread_id", "ag_ui_run_id", "current_state", "forwarded_props"}
_COLLECTED_APPROVAL_RESPONSES_KEY = "collected_approval_responses"
_PROVIDER_SERVICE_SESSION_ID_STATE_KEY = "__ag_ui_provider_service_session_id"


@dataclass
class _LocalApprovalOccurrence:
    """One local function-call occurrence tracked across AG-UI replay."""

    call_id: str
    name: str | None
    arguments: str | None
    approval_ids: set[str] = field(default_factory=set)
    terminal_result_content_ids: set[int] = field(default_factory=set)
    closed: bool = False


def _local_approval_content_ids_to_remove(
    messages: Sequence[Message],
    *,
    pending_response_content_ids: set[int] | None = None,
) -> tuple[set[int], set[int]]:
    """Find local approval controls and untrusted terminal results to remove.

    A terminal result in a client request is not evidence that the occurrence
    currently awaiting a server-side approval already executed. When the
    response belongs to a registered pending approval, the result is removed
    and the response remains available for static execution. Results in the
    default path retain the historical replay behavior.
    """
    occurrences_by_call_id: dict[str, list[_LocalApprovalOccurrence]] = {}
    occurrences_by_approval_id: dict[str, list[_LocalApprovalOccurrence]] = {}
    response_occurrence_by_approval_id: dict[str, _LocalApprovalOccurrence] = {}
    response_content_id_by_approval_id: dict[str, int] = {}
    response_occurrences: dict[int, _LocalApprovalOccurrence] = {}
    duplicate_response_content_ids: set[int] = set()
    untrusted_result_content_ids: set[int] = set()

    def add_occurrence(function_call: Content, *, closed: bool = False) -> _LocalApprovalOccurrence | None:
        if function_call.call_id is None:
            return None
        occurrence = _LocalApprovalOccurrence(
            call_id=function_call.call_id,
            name=function_call.name,
            arguments=canonical_function_arguments(function_call),
            closed=closed,
        )
        occurrences_by_call_id.setdefault(function_call.call_id, []).append(occurrence)
        return occurrence

    def matching_occurrence(
        candidates: Sequence[_LocalApprovalOccurrence],
        function_call: Content,
        *,
        require_open: bool = False,
        require_unbound: bool = False,
        newest_first: bool = True,
        prefer_open: bool = False,
    ) -> _LocalApprovalOccurrence | None:
        ordered = reversed(candidates) if newest_first else iter(candidates)
        eligible = [
            occurrence
            for occurrence in ordered
            if (not require_open or not occurrence.closed) and (not require_unbound or not occurrence.approval_ids)
        ]
        arguments = canonical_function_arguments(function_call)
        if prefer_open:
            exact_open = next(
                (
                    occurrence
                    for occurrence in eligible
                    if not occurrence.closed
                    and occurrence.name == function_call.name
                    and occurrence.arguments == arguments
                ),
                None,
            )
            if exact_open is not None:
                return exact_open
            if open_occurrence := next((occurrence for occurrence in eligible if not occurrence.closed), None):
                return open_occurrence
        exact = next(
            (
                occurrence
                for occurrence in eligible
                if occurrence.name == function_call.name and occurrence.arguments == arguments
            ),
            None,
        )
        return exact or next(iter(eligible), None)

    for message in messages:
        for content in message.contents:
            if content.type == "function_call":
                add_occurrence(content)
                continue

            if content.type == "function_approval_request":
                function_call = content.function_call
                if function_call is None or function_call.call_id is None or content.id is None:
                    continue
                candidates = occurrences_by_call_id.get(function_call.call_id, [])
                occurrence = matching_occurrence(
                    candidates,
                    function_call,
                    require_open=True,
                    require_unbound=True,
                    newest_first=False,
                ) or add_occurrence(function_call)
                if occurrence is not None:
                    occurrence.approval_ids.add(content.id)
                    occurrences_by_approval_id.setdefault(content.id, []).append(occurrence)
                continue

            if content.type == "function_approval_response":
                if _is_hosted_tool_approval(content):
                    continue
                function_call = content.function_call
                if function_call is None or function_call.call_id is None:
                    continue
                previous_occurrence = response_occurrence_by_approval_id.get(content.id or "")
                request_occurrences = occurrences_by_approval_id.get(content.id or "", [])
                is_pending_response = (
                    pending_response_content_ids is not None and id(content) in pending_response_content_ids
                )
                request_occurrence = matching_occurrence(
                    request_occurrences,
                    function_call,
                    prefer_open=not is_pending_response,
                )
                call_occurrence = matching_occurrence(
                    occurrences_by_call_id.get(function_call.call_id, []),
                    function_call,
                    prefer_open=not is_pending_response,
                )
                occurrence = (
                    call_occurrence
                    if call_occurrence is not None
                    and not call_occurrence.closed
                    and (request_occurrence is None or request_occurrence.closed)
                    else request_occurrence or call_occurrence
                )
                if occurrence is None:
                    occurrence = add_occurrence(function_call)
                if previous_occurrence is not None and occurrence is previous_occurrence:
                    previous_content_id = response_content_id_by_approval_id.get(content.id or "")
                    if previous_content_id is not None:
                        duplicate_response_content_ids.add(previous_content_id)
                if content.id is not None and occurrence is not None:
                    occurrence.approval_ids.add(content.id)
                    response_occurrence_by_approval_id[content.id] = occurrence
                    response_content_id_by_approval_id[content.id] = id(content)
                if occurrence is not None:
                    response_occurrences[id(content)] = occurrence
                continue

            if content.call_id is None:
                continue
            is_terminal_result = content.type == "function_result" and not (
                isinstance(content.result, str) and "[APPROVAL_PENDING]" in content.result
            )
            is_follow_up_request = content.user_input_request and content.type not in {
                "function_approval_request",
                "function_approval_response",
            }
            if not (is_terminal_result or is_follow_up_request):
                continue
            occurrence = next(
                (candidate for candidate in occurrences_by_call_id.get(content.call_id, []) if not candidate.closed),
                None,
            )
            if occurrence is None:
                occurrence = _LocalApprovalOccurrence(
                    call_id=content.call_id,
                    name=None,
                    arguments=None,
                )
                occurrences_by_call_id.setdefault(content.call_id, []).append(occurrence)
            occurrence.terminal_result_content_ids.add(id(content))
            occurrence.closed = True

    if pending_response_content_ids:
        for response_content_id, occurrence in response_occurrences.items():
            if response_content_id not in pending_response_content_ids:
                continue
            # A client-supplied result cannot close the server-owned pending
            # occurrence. Remove it before static execution so it cannot be
            # mistaken for the result produced by the approved local tool.
            untrusted_result_content_ids.update(occurrence.terminal_result_content_ids)
            occurrence.closed = False

    return (
        duplicate_response_content_ids
        | {content_id for content_id, occurrence in response_occurrences.items() if occurrence.closed},
        untrusted_result_content_ids,
    )


def _local_approval_response_content_ids_to_remove(messages: Sequence[Message]) -> set[int]:
    """Find completed and duplicate local approval responses by call occurrence."""
    response_content_ids, _ = _local_approval_content_ids_to_remove(messages)
    return response_content_ids


def _filter_local_approval_responses_for_provider(
    messages: Sequence[Message],
    *,
    pending_response_content_ids: set[int] | None = None,
) -> list[Message]:
    """Remove completed local approval controls from AG-UI provider input.

    A matching terminal result only closes a local response when it is not part
    of a server-registered pending approval occurrence. Client-authored results
    for a still-pending occurrence are removed before execution, while hosted-
    service responses remain provider protocol data.
    """
    response_content_ids_to_remove, untrusted_result_content_ids = _local_approval_content_ids_to_remove(
        messages,
        pending_response_content_ids=pending_response_content_ids,
    )
    response_content_ids_to_remove.update(untrusted_result_content_ids)

    filtered_messages: list[Message] = []
    for message in messages:
        filtered_contents = [
            content for content in message.contents if id(content) not in response_content_ids_to_remove
        ]
        if len(filtered_contents) == len(message.contents):
            filtered_messages.append(message)
            continue
        if not filtered_contents:
            continue
        filtered_message = copy.copy(message)
        filtered_message.contents = filtered_contents
        filtered_messages.append(filtered_message)
    return filtered_messages


def _build_safe_metadata(thread_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Build metadata dict with string values for Azure compatibility.

    Azure has a 512 character limit per metadata value.  String values that
    already fit are kept as-is.  Non-string values are JSON-serialized.  If the
    resulting string exceeds 512 characters the key is **dropped** (with a
    warning) instead of truncated, because truncation can produce invalid JSON
    that downstream consumers cannot decode.

    Args:
        thread_metadata: Raw metadata dict

    Returns:
        Metadata with safe string values (each <= 512 chars)
    """
    if not thread_metadata:
        return {}
    safe_metadata: dict[str, Any] = {}
    for key, value in thread_metadata.items():
        value_str = value if isinstance(value, str) else json.dumps(value)
        if len(value_str) > 512:
            logger.warning(
                "Dropping metadata key %r: serialized value is %d chars (limit 512)",
                key,
                len(value_str),
            )
            continue
        safe_metadata[key] = value_str
    return safe_metadata


def _should_suppress_intermediate_snapshot(
    tool_name: str | None,
    predict_state_config: dict[str, dict[str, str]] | None,
    require_confirmation: bool,
) -> bool:
    """Check if intermediate MessagesSnapshotEvent should be suppressed for this tool.

    For predictive tools without confirmation, we delay the snapshot until the end.

    Args:
        tool_name: Name of the tool that just completed
        predict_state_config: Predictive state configuration
        require_confirmation: Whether confirmation is required

    Returns:
        True if snapshot should be suppressed
    """
    if not tool_name or not predict_state_config:
        return False
    # Only suppress when confirmation is disabled
    if require_confirmation:
        return False
    # Check if this tool is a predictive tool
    for config in predict_state_config.values():
        if config["tool"] == tool_name:
            logger.info(f"Suppressing intermediate MessagesSnapshotEvent for predictive tool '{tool_name}'")
            return True
    return False


def _extract_approved_state_updates(
    messages: list[Any],
    predictive_handler: PredictiveStateHandler | None,
) -> dict[str, Any]:
    """Extract state updates from function_approval_response content.

    This emits StateSnapshotEvent for approved state-changing tools before running agent.

    Args:
        messages: List of messages to scan
        predictive_handler: Predictive state handler

    Returns:
        Dict of state updates to apply
    """
    if not predictive_handler:
        return {}

    updates: dict[str, Any] = {}
    for msg in messages:
        for content in msg.contents:
            if getattr(content, "type", None) != "function_approval_response":
                continue
            if not getattr(content, "approved", False) or not getattr(content, "function_call", None):
                continue
            parsed_args = content.function_call.parse_arguments()
            result = predictive_handler.extract_state_value(content.function_call.name, parsed_args)
            if result:
                state_key, state_value = result
                updates[state_key] = state_value
                logger.info(f"Found approved state update for key '{state_key}'")
    return updates


def _resume_to_tool_messages(
    resume_payload: Any,
    *,
    exclude_interrupt_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert a resume payload into AG-UI tool messages for approval continuation."""
    result: list[dict[str, Any]] = []
    for interrupt in _normalize_resume_interrupts(resume_payload):
        if interrupt.get("status") not in {None, "resolved"}:
            continue
        if exclude_interrupt_ids and interrupt["id"] in exclude_interrupt_ids:
            continue
        value = interrupt.get("value")
        content: str
        if isinstance(value, str):
            content = value
        else:
            content = json.dumps(make_json_safe(value))
        result.append(
            {
                "role": "tool",
                "toolCallId": interrupt["id"],
                "content": content,
            }
        )
    return result


async def _normalize_response_stream(response_stream: Any) -> AsyncIterable[Any]:
    """Normalize agent streaming return types to an async iterable.

    Supports:
      - ResponseStream (standard agent stream type)
      - AsyncIterable[AgentResponseUpdate] (workflow-style stream)
      - Awaitable that resolves to either of the above
    """
    if isinstance(response_stream, Awaitable):
        resolved_stream = await cast(Awaitable[Any], response_stream)
        if isinstance(resolved_stream, ResponseStream):
            # AG-UI consumes update iteration only; ResponseStream finalizers are not used here.
            return cast(AsyncIterable[Any], resolved_stream)
        if isinstance(resolved_stream, AsyncIterable):
            return cast(AsyncIterable[Any], resolved_stream)
        resolved_type = f"{type(resolved_stream).__module__}.{type(resolved_stream).__name__}"
        raise AgentInvalidResponseException(
            "Agent did not return a streaming AsyncIterable response. "
            f"Awaitable resolved to unsupported type: {resolved_type}."
        )

    if isinstance(response_stream, ResponseStream):
        # AG-UI consumes update iteration only; ResponseStream finalizers are not used here.
        return cast(AsyncIterable[Any], response_stream)

    if isinstance(response_stream, AsyncIterable):
        return cast(AsyncIterable[Any], response_stream)

    stream_type = f"{type(response_stream).__module__}.{type(response_stream).__name__}"
    raise AgentInvalidResponseException(
        f"Agent did not return a streaming AsyncIterable response. Received unsupported type: {stream_type}."
    )


def _create_state_context_message(
    current_state: dict[str, Any],
    state_schema: dict[str, Any],
) -> Message | None:
    """Create a system message with current state context.

    This injects the current state into the conversation so the model
    knows what state exists and can make informed updates.

    Args:
        current_state: The current state to inject
        state_schema: The state schema (used to determine if injection is needed)

    Returns:
        Message with state context, or None if not needed
    """
    if not current_state or not state_schema:
        return None

    state_json = json.dumps(current_state, indent=2)
    return Message(
        role="system",
        contents=[
            Content.from_text(
                text=(
                    "Current state of the application:\n"
                    f"{state_json}\n\n"
                    "When modifying state, you MUST include ALL existing data plus your changes.\n"
                    "For example, if adding one new item to a list, include ALL existing items PLUS the new item.\n"
                    "Never replace existing data - always preserve and append or merge."
                )
            )
        ],
    )


def _inject_state_context(
    messages: list[Message],
    current_state: dict[str, Any],
    state_schema: dict[str, Any],
) -> list[Message]:
    """Inject state context message into messages if appropriate.

    The state context is injected before the last user message to give
    the model visibility into the current application state.

    Args:
        messages: The messages to potentially inject into
        current_state: The current state
        state_schema: The state schema

    Returns:
        Messages with state context injected if appropriate
    """
    state_msg = _create_state_context_message(current_state, state_schema)
    if not state_msg:
        return messages

    # Check if the last message is from a user (new user turn)
    if not messages:
        return messages

    from ._utils import get_role_value

    last_role = get_role_value(messages[-1])
    if last_role != "user":
        return messages

    # Always inject state context if state is provided
    # This ensures UI state changes are visible to the model

    # Insert state context before the last user message
    result = list(messages[:-1])
    result.append(state_msg)
    result.append(messages[-1])
    return result


def _is_confirm_changes_response(messages: list[Any]) -> bool:
    """Check if the last message is a confirm_changes tool result (state confirmation flow).

    This returns True for confirm_changes flows where we emit a confirmation message
    and stop. The key indicator is the presence of a 'steps' key in the tool result
    (even if empty), combined with 'accepted' boolean.
    """
    if not messages:
        return False
    last = messages[-1]
    additional_properties = cast(dict[str, Any], getattr(last, "additional_properties", {}) or {})
    if not additional_properties.get("is_tool_result", False):
        return False

    # Parse the content to check if it has the confirm_changes structure
    for content in last.contents:
        if getattr(content, "type", None) == "text" and content.text:
            try:
                result = json.loads(content.text)
                if not isinstance(result, dict):
                    continue
                # confirm_changes results have 'accepted' and 'steps' keys
                if "accepted" in result and "steps" in result:
                    return True
            except json.JSONDecodeError:
                # Content is not valid JSON; continue checking other content items
                logger.debug("Failed to parse confirm_changes tool result as JSON; treating as non-confirmation.")
    return False


def _handle_step_based_approval(messages: list[Any]) -> list[BaseEvent]:
    """Handle step-based approval response and emit confirmation message."""
    events: list[BaseEvent] = []
    last = messages[-1]

    # Parse the approval content
    approval_text = ""
    for content in last.contents:
        if getattr(content, "type", None) == "text" and content.text:
            approval_text = content.text
            break

    if not approval_text:
        message = "Acknowledged."
    else:
        try:
            parsed_result = json.loads(approval_text)
            result: dict[str, Any] = cast(dict[str, Any], parsed_result) if isinstance(parsed_result, dict) else {}
            accepted = result.get("accepted") is True
            steps_raw = result.get("steps", [])
            steps: list[dict[str, Any]] = []
            if isinstance(steps_raw, list):
                for step_raw in cast(list[Any], steps_raw):
                    if isinstance(step_raw, dict):
                        steps.append(cast(dict[str, Any], step_raw))

            if accepted:
                # Generate acceptance message with step descriptions
                enabled_steps: list[dict[str, Any]] = [step for step in steps if step.get("status") == "enabled"]
                if enabled_steps:
                    message_parts = [f"Executing {len(enabled_steps)} approved steps:\n\n"]
                    for i, step in enumerate(enabled_steps, 1):
                        message_parts.append(f"{i}. {step.get('description', 'Step')}\n")
                    message_parts.append("\nAll steps completed successfully!")
                    message = "".join(message_parts)
                else:
                    message = "Changes confirmed and applied successfully!"
            else:
                # Rejection message
                message = "No problem! What would you like me to change about the plan?"
        except json.JSONDecodeError:
            message = "Acknowledged."

    message_id = generate_event_id()
    events.append(TextMessageStartEvent(message_id=message_id, role="assistant"))
    events.append(TextMessageContentEvent(message_id=message_id, delta=message))
    events.append(TextMessageEndEvent(message_id=message_id))

    return events


def _make_approval_tool_result_events(resolved_approval_results: list[Content]) -> list[ToolCallResultEvent]:
    """Build TOOL_CALL_RESULT events for tools executed during approval resolution.

    Honors ``TOOL_RESULT_DISPLAY_KEY`` so tools returning
    ``state_update(..., tool_result=...)`` route the display payload to the UI
    event even when gated by HITL approval.
    """
    events: list[ToolCallResultEvent] = []
    for resolved in resolved_approval_results:
        if resolved.call_id:
            raw = resolved.result if resolved.result is not None else ""
            llm_str = _stringify_tool_result(raw)
            ui_str = _resolve_ui_payload(llm_str, _extract_tool_result_display(resolved))
            events.append(
                ToolCallResultEvent(
                    message_id=generate_event_id(),
                    tool_call_id=resolved.call_id,
                    content=ui_str,
                    role="tool",
                )
            )
    return events


def _pending_approval_name(entry: ApprovalOccurrence) -> str:
    return entry.name


def _pending_approval_arguments(entry: ApprovalOccurrence) -> str:
    return entry.arguments


def _pending_approval_already_approved_requests(
    entry: ApprovalOccurrence,
) -> list[dict[str, Any]]:
    return list(entry.already_approved_requests)


def _pending_approval_server_label(entry: ApprovalOccurrence) -> str | None:
    return entry.server_label


def _function_call_server_label(function_call: Content | None) -> str | None:
    if function_call is None:
        return None
    server_label = function_call.additional_properties.get("server_label")
    return server_label if isinstance(server_label, str) and server_label else None


def _function_call_execution_owner(
    function_call: Content,
    tools: list[Any] | None,
    *,
    has_deferred_owner: bool = False,
) -> ApprovalExecutionOwner:
    """Resolve execution ownership only after the call and available tools exist."""
    if _function_call_server_label(function_call):
        return ApprovalExecutionOwner.HOSTED
    tool = _get_tool_map(tools).get(function_call.name) if tools and function_call.name else None
    if tool is not None and not getattr(tool, "declaration_only", False):
        return ApprovalExecutionOwner.LOCAL
    if has_deferred_owner:
        return ApprovalExecutionOwner.DEFERRED
    return ApprovalExecutionOwner.UNAVAILABLE


def _stored_already_approved_requests_for_visible_approval(
    session: AgentSession,
    *approval_ids: str | None,
) -> list[dict[str, Any]]:
    """Return hidden already-approved sibling requests recorded by the core invocation loop."""
    requested_ids = {str(approval_id) for approval_id in approval_ids if approval_id}
    if not requested_ids:
        return []

    tool_approval_state = session.state.get(_TOOL_APPROVAL_STATE_KEY)
    if not isinstance(tool_approval_state, Mapping):
        return []

    raw_groups = tool_approval_state.get(_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY)
    if not isinstance(raw_groups, list):
        return []

    stored_requests: list[dict[str, Any]] = []
    seen_request_ids: set[str] = set()
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping):
            continue
        raw_ids = raw_group.get("approval_request_ids")
        group_ids = {str(item) for item in raw_ids if item is not None} if isinstance(raw_ids, list) else set()
        if group_ids.isdisjoint(requested_ids):
            continue

        raw_requests = raw_group.get("approval_requests")
        if not isinstance(raw_requests, list):
            continue
        for raw_request in raw_requests:
            if not isinstance(raw_request, Mapping):
                continue
            request = dict(cast(Mapping[str, Any], raw_request))
            request_id = request.get("id")
            function_call = request.get("function_call") or request.get("functionCall")
            if request_id is None and isinstance(function_call, Mapping):
                request_id = function_call.get("call_id") or function_call.get("callId")
            dedupe_key = (
                str(request_id) if request_id is not None else json.dumps(make_json_safe(request), sort_keys=True)
            )
            if dedupe_key in seen_request_ids:
                continue
            seen_request_ids.add(dedupe_key)
            stored_requests.append(request)
    return stored_requests


def _content_from_approval_state(value: Any) -> Content | None:
    """Restore approval-specific Content values from server-owned Approval State."""
    if isinstance(value, Content):
        return value
    if isinstance(value, Mapping):
        return Content.from_dict(cast(Mapping[str, Any], value))
    return None


def _serialized_tool_approval_state(value: Any) -> dict[str, Any] | None:
    """Return a JSON-safe copy of the core tool-approval state bag."""
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(cast(Mapping[str, Any], value)))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        raw_state = to_dict(exclude={"type"})
        if isinstance(raw_state, Mapping):
            return copy.deepcopy(dict(cast(Mapping[str, Any], raw_state)))
    logger.warning("Ignoring unsupported tool approval state type: %s", type(value).__name__)
    return None


def _restore_tool_approval_state(
    session: AgentSession,
    approval_state_store: InMemoryAGUIApprovalStateStore | None,
    thread_id: str,
) -> None:
    """Restore only core tool-approval state into the per-run AgentSession."""
    session.state.pop(_TOOL_APPROVAL_STATE_KEY, None)
    if approval_state_store is None:
        return
    stored_state = approval_state_store.get_tool_approval_state(thread_id)
    if stored_state is None:
        return
    session.state[_TOOL_APPROVAL_STATE_KEY] = stored_state


def _save_tool_approval_state(
    session: AgentSession,
    approval_state_store: InMemoryAGUIApprovalStateStore | None,
    thread_id: str,
) -> None:
    """Persist only approval-specific ToolApprovalMiddleware state server-side."""
    if approval_state_store is None:
        return
    raw_state = session.state.get(_TOOL_APPROVAL_STATE_KEY)
    if raw_state is None:
        approval_state_store.delete_tool_approval_state(thread_id)
        return
    serialized_state = _serialized_tool_approval_state(raw_state)
    if serialized_state is None:
        return
    approval_state_store.set_tool_approval_state(thread_id, serialized_state)


def _clear_tool_approval_state(
    approval_state_store: InMemoryAGUIApprovalStateStore | None,
    thread_id: str,
) -> None:
    """Discard queued ToolApprovalMiddleware state for a cancelled approval flow."""
    if approval_state_store is None:
        return
    approval_state_store.delete_tool_approval_state(thread_id)


def _register_server_generated_approval_response(
    response: Content,
    thread_id: str,
    tools: list[Any] | None,
    *,
    lifecycle: ApprovalLifecycle,
    has_deferred_owner: bool,
    approval_scope: str | None = None,
) -> AuthorizedExecution | None:
    """Register a server-owned approval response so normal validation can consume it."""
    if response.function_call is None or not response.function_call.name:
        return None
    response_id = response.id or response.function_call.call_id
    if not response_id:
        return None
    execution_owner = _function_call_execution_owner(
        response.function_call,
        tools,
        has_deferred_owner=has_deferred_owner,
    )
    arguments = canonical_function_arguments(response.function_call) or "{}"
    lifecycle.register(
        owner=execution_owner,
        scope=approval_scope,
        thread_ids=[thread_id],
        interrupt_id=str(response_id),
        call_id=str(response.function_call.call_id or response_id),
        name=response.function_call.name,
        arguments=arguments,
        aliases=[str(response.function_call.call_id)] if response.function_call.call_id else None,
        server_label=_function_call_server_label(response.function_call),
    )
    if response.approved is not True:
        lifecycle.claim_batch(
            thread_id=thread_id,
            decisions=[
                ResumeDecision(
                    interrupt_id=str(response_id),
                    accepted=False,
                    arguments=arguments,
                    name=response.function_call.name,
                )
            ],
        )
        return None
    if execution_owner is ApprovalExecutionOwner.UNAVAILABLE:
        return None
    return lifecycle.claim(
        thread_id=thread_id,
        decision=ResumeDecision(
            interrupt_id=str(response_id),
            accepted=True,
            arguments=arguments,
            name=response.function_call.name,
        ),
    )


def _pop_collected_tool_approval_response_messages(
    session: AgentSession,
    thread_id: str,
    tools: list[Any] | None,
    *,
    lifecycle: ApprovalLifecycle,
    authorized_executions: dict[ApprovalOccurrenceIdentity, AuthorizedExecution] | None = None,
    approval_scope: str | None = None,
) -> list[Message]:
    """Pop server-collected auto-approved responses into provider-visible messages."""
    raw_state = session.state.get(_TOOL_APPROVAL_STATE_KEY)
    if not isinstance(raw_state, Mapping):
        return []

    state = dict(cast(Mapping[str, Any], raw_state))
    raw_responses = state.get(_COLLECTED_APPROVAL_RESPONSES_KEY)
    if not isinstance(raw_responses, list):
        return []

    responses: list[Content] = []
    for raw_response in raw_responses:
        response = _content_from_approval_state(raw_response)
        if response is None or response.type != "function_approval_response":
            continue
        intent = _register_server_generated_approval_response(
            response,
            thread_id,
            tools,
            lifecycle=lifecycle,
            has_deferred_owner=True,
            approval_scope=approval_scope,
        )
        if intent is not None and authorized_executions is not None:
            authorized_executions[intent.identity] = intent
        responses.append(response)

    state[_COLLECTED_APPROVAL_RESPONSES_KEY] = []
    session.state[_TOOL_APPROVAL_STATE_KEY] = state
    if not responses:
        return []
    return [Message(role="user", contents=responses)]


def _parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else None


def _content_tool_call_ids(value: Any) -> set[str]:
    """Collect tool call ids from serialized approval-specific state values."""
    call_ids: set[str] = set()
    if isinstance(value, Content):
        if value.call_id:
            call_ids.add(str(value.call_id))
        if value.function_call and value.function_call.call_id:
            call_ids.add(str(value.function_call.call_id))
        return call_ids
    if isinstance(value, Mapping):
        value_mapping = cast(Mapping[str, Any], value)
        value_type = value_mapping.get("type")
        if value_type in {"function_call", "function_approval_request", "function_approval_response"}:
            call_id = value_mapping.get("call_id") or value_mapping.get("callId")
            if call_id:
                call_ids.add(str(call_id))
        function_call = value_mapping.get("function_call") or value_mapping.get("functionCall")
        if isinstance(function_call, Mapping):
            function_call_id = function_call.get("call_id") or function_call.get("callId")
            if function_call_id:
                call_ids.add(str(function_call_id))
        for nested in value_mapping.values():
            call_ids.update(_content_tool_call_ids(nested))
        return call_ids
    if isinstance(value, list):
        for item in value:
            call_ids.update(_content_tool_call_ids(item))
    return call_ids


def _approval_state_tool_call_ids(
    approval_state_store: InMemoryAGUIApprovalStateStore,
    thread_id: str,
) -> set[str]:
    """Return server-owned approval call ids that are not abandoned."""
    call_ids: set[str] = set()
    for occurrence in approval_state_store.lifecycle.occurrences_for_thread(thread_id=thread_id):
        call_ids.add(occurrence.identity.call_id)
        call_ids.add(occurrence.identity.interrupt_id)
        call_ids.update(occurrence.aliases)
        call_ids.update(_content_tool_call_ids(list(occurrence.already_approved_requests)))
    stored_state = approval_state_store.get_tool_approval_state(thread_id)
    if stored_state is not None:
        call_ids.update(_content_tool_call_ids(stored_state))
    return call_ids


def _tool_approval_state_exists_for_cancelled_resume(
    resume_payload: Any,
    approval_state_store: InMemoryAGUIApprovalStateStore | None,
    thread_id: str,
) -> bool:
    """Return whether an unmatched cancelled resume should discard hidden queued approval state."""
    if approval_state_store is None:
        return False
    cancelled_ids = _cancelled_resume_interrupt_ids(resume_payload)
    if not cancelled_ids:
        return False
    return approval_state_store.has_tool_approval_state(thread_id)


def _stored_pending_approval_interrupt_ids(interrupts: list[dict[str, Any]] | None) -> set[str]:
    """Return stored interrupt ids that require server-side approval registry validation."""
    if not interrupts:
        return set()
    interrupt_ids: set[str] = set()
    for interrupt in interrupts:
        metadata = interrupt.get("metadata")
        if not isinstance(metadata, dict):
            continue
        agent_framework_metadata = metadata.get("agent_framework")
        if not isinstance(agent_framework_metadata, dict):
            continue
        if agent_framework_metadata.get("type") != "function_approval_request":
            continue
        if agent_framework_metadata.get("confirmation_tool_call_id"):
            continue
        interrupt_id = interrupt.get("id") or interrupt.get("interruptId")
        if interrupt_id:
            interrupt_ids.add(str(interrupt_id))
    return interrupt_ids


def _resume_payload_has_approval_decision(resume_payload: Any) -> bool:
    """Return whether a resume payload looks like an approval decision."""
    for interrupt in _normalize_resume_interrupts(resume_payload):
        if interrupt.get("status") == "cancelled":
            return True
        value = interrupt.get("value")
        if isinstance(value, dict) and any(key in value for key in ("accepted", "approved")):
            return True
    return False


def _approval_arguments_match_pending(pending_arguments: str | None, response_arguments: str | None) -> bool:
    return pending_arguments is None or response_arguments == pending_arguments


def _json_schema_value_matches(original_value: Any, edited_value: Any) -> bool:
    if isinstance(original_value, bool):
        return isinstance(edited_value, bool)
    if isinstance(original_value, int) and not isinstance(original_value, bool):
        return isinstance(edited_value, int) and not isinstance(edited_value, bool)
    if isinstance(original_value, float):
        return isinstance(edited_value, (int, float)) and not isinstance(edited_value, bool)
    if isinstance(original_value, str):
        return isinstance(edited_value, str)
    if isinstance(original_value, list):
        return isinstance(edited_value, list)
    if isinstance(original_value, dict):
        return isinstance(edited_value, dict)
    return True


def _canonical_approval_decision(
    payload_value: Any,
    *,
    interrupt_id: str,
    original_arguments_text: str,
    server_label: str | None,
) -> tuple[bool | None, str | None, dict[str, Any] | None, RunErrorEvent | None]:
    """Validate one approval payload and return its canonical full argument replacement."""
    payload = _parse_json_object(payload_value)
    if payload is None:
        return (
            None,
            None,
            None,
            RunErrorEvent(
                message=f"Approval resume for interruptId '{interrupt_id}' must include an object payload.",
                code="APPROVAL_RESUME_INVALID",
            ),
        )
    accepted = payload.get("approved", payload.get("accepted"))
    if not isinstance(accepted, bool):
        return (
            None,
            None,
            None,
            RunErrorEvent(
                message=f"Approval resume for interruptId '{interrupt_id}' must include a boolean accepted value.",
                code="APPROVAL_RESUME_INVALID",
            ),
        )

    original_arguments = _parse_json_object(original_arguments_text) or {}
    direct_edited_arguments = {
        key: value for key, value in payload.items() if key not in {"accepted", "approved", "editedArgs"}
    }
    standard_edited_arguments = payload.get("editedArgs")
    if standard_edited_arguments is not None:
        if not isinstance(standard_edited_arguments, dict) or direct_edited_arguments:
            return (
                None,
                None,
                None,
                RunErrorEvent(
                    message=(
                        f"Approval resume for interruptId '{interrupt_id}' must provide editedArgs as the "
                        "only edited-argument representation."
                    ),
                    code="APPROVAL_RESUME_INVALID_RESPONSE",
                ),
            )
        edited_arguments = cast(dict[str, Any], standard_edited_arguments)
        if set(edited_arguments) != set(original_arguments):
            return (
                None,
                None,
                None,
                RunErrorEvent(
                    message=(
                        f"Approval resume for interruptId '{interrupt_id}' must provide editedArgs as a full "
                        "replacement of the pending tool arguments."
                    ),
                    code="APPROVAL_RESUME_INVALID_RESPONSE",
                ),
            )
    else:
        edited_arguments = direct_edited_arguments
    if edited_arguments and server_label:
        return (
            None,
            None,
            None,
            RunErrorEvent(
                message=f"Hosted approval resume for interruptId '{interrupt_id}' does not support edited arguments.",
                code="APPROVAL_RESUME_INVALID_RESPONSE",
            ),
        )
    if not set(edited_arguments).issubset(set(original_arguments)):
        return (
            None,
            None,
            None,
            RunErrorEvent(
                message=f"Approval resume for interruptId '{interrupt_id}' includes unsupported edited arguments.",
                code="APPROVAL_RESUME_INVALID",
            ),
        )
    for name, edited_value in edited_arguments.items():
        if not _json_schema_value_matches(original_arguments[name], edited_value):
            return (
                None,
                None,
                None,
                RunErrorEvent(
                    message=(
                        f"Approval resume for interruptId '{interrupt_id}' has invalid type for edited argument "
                        f"'{name}'."
                    ),
                    code="APPROVAL_RESUME_INVALID_RESPONSE",
                ),
            )

    merged_arguments = (
        dict(edited_arguments) if standard_edited_arguments is not None else {**original_arguments, **edited_arguments}
    )
    canonical_arguments = json.dumps(make_json_safe(merged_arguments), sort_keys=True, separators=(",", ":"))
    return accepted, canonical_arguments, merged_arguments, None


def _canonical_approval_resume_messages(
    resume_payload: Any,
    thread_id: str,
    expected_interrupt_ids: set[str] | None = None,
    *,
    lifecycle: ApprovalLifecycle,
    tools: list[Any] | None = None,
    has_deferred_owner: bool = False,
    authorized_executions: dict[ApprovalOccurrenceIdentity, AuthorizedExecution] | None = None,
    retained_results: list[Content] | None = None,
    snapshot_reconciliations: list[ApprovalSnapshotReconciliation] | None = None,
    approval_scope: str | None = None,
) -> tuple[list[dict[str, Any]], set[str], set[str], RunErrorEvent | None]:
    """Translate canonical ResumeEntry approvals into existing approval response messages."""
    expected_ids = set(expected_interrupt_ids or set())
    messages: list[dict[str, Any]] = []
    handled_ids: set[str] = set()
    cancelled_ids: set[str] = set()
    pending_interrupt_ids = lifecycle.pending_interrupt_ids(thread_id=thread_id)
    contract_interrupt_ids = expected_ids | pending_interrupt_ids
    if not contract_interrupt_ids:
        if _resume_payload_has_approval_decision(resume_payload):
            normalized_interrupts = _normalize_resume_interrupts(resume_payload)
            interrupt_id = normalized_interrupts[0]["id"] if normalized_interrupts else "unknown"
            cancelled_retry_ids = [
                str(interrupt["id"]) for interrupt in normalized_interrupts if interrupt.get("status") == "cancelled"
            ]
            if len(cancelled_retry_ids) == len(normalized_interrupts) and cancelled_retry_ids:
                try:
                    reconciliations = lifecycle.cancel_batch(
                        thread_id=thread_id,
                        interrupt_ids=cancelled_retry_ids,
                    )
                except KeyError:
                    pass
                except ValueError as exc:
                    return (
                        [],
                        handled_ids,
                        cancelled_ids,
                        RunErrorEvent(message=str(exc), code="APPROVAL_RESUME_INVALID"),
                    )
                else:
                    if snapshot_reconciliations is not None:
                        snapshot_reconciliations.extend(reconciliations)
                    handled_ids.update(cancelled_retry_ids)
                    cancelled_ids.update(cancelled_retry_ids)
                    return [], handled_ids, cancelled_ids, None
            if retained_results is not None:
                decisions: list[ResumeDecision] = []
                for interrupt in normalized_interrupts:
                    if interrupt.get("status") != "resolved":
                        break
                    interrupt_id = str(interrupt["id"])
                    try:
                        name, retained_arguments = lifecycle.decision_context(
                            thread_id=thread_id,
                            interrupt_id=interrupt_id,
                        )
                    except KeyError:
                        break
                    occurrence = lifecycle.occurrence_for_alias(thread_id=thread_id, interrupt_id=interrupt_id)
                    original_arguments_text = (
                        occurrence.decision.original_arguments
                        if occurrence is not None
                        and occurrence.decision is not None
                        and occurrence.decision.original_arguments is not None
                        else retained_arguments
                    )
                    accepted, canonical_arguments, _, validation_error = _canonical_approval_decision(
                        interrupt.get("value"),
                        interrupt_id=interrupt_id,
                        original_arguments_text=original_arguments_text,
                        server_label=occurrence.server_label if occurrence is not None else None,
                    )
                    if validation_error is not None:
                        return [], handled_ids, cancelled_ids, validation_error
                    if accepted is None or canonical_arguments is None:
                        break
                    decisions.append(
                        ResumeDecision(
                            interrupt_id=interrupt_id,
                            accepted=accepted,
                            arguments=canonical_arguments,
                            name=name,
                            original_arguments=original_arguments_text,
                        )
                    )
                if len(decisions) == len(normalized_interrupts) and decisions:
                    try:
                        batch = lifecycle.claim_batch(thread_id=thread_id, decisions=decisions)
                    except KeyError:
                        pass
                    except ValueError as exc:
                        return (
                            [],
                            handled_ids,
                            cancelled_ids,
                            RunErrorEvent(message=str(exc), code="APPROVAL_RESUME_INVALID"),
                        )
                    else:
                        for outcome in batch.retained_outcomes:
                            if outcome.snapshot_reconciliation.status is ApprovalStatus.SETTLED:
                                retained_results.extend(result.content for result in outcome.replayable_results)
                        if snapshot_reconciliations is not None:
                            snapshot_reconciliations.extend(batch.snapshot_reconciliations)
                        handled_ids.update(decision.interrupt_id for decision in decisions)
                        return [], handled_ids, cancelled_ids, None
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(
                    message=f"No pending approval interrupt found for resume interruptId '{interrupt_id}'.",
                    code="APPROVAL_RESUME_NOT_FOUND",
                ),
            )
        return messages, handled_ids, cancelled_ids, None

    entries, contract_error, contract_code = _resume_contract_error(
        resume_payload,
        contract_interrupt_ids,
        required_code="APPROVAL_RESUME_REQUIRED",
        invalid_code="APPROVAL_RESUME_INVALID",
        unknown_code="APPROVAL_RESUME_NOT_FOUND",
        missing_code="APPROVAL_RESUME_MISSING_INTERRUPT",
    )
    if contract_error is not None and contract_code is not None:
        return [], handled_ids, cancelled_ids, RunErrorEvent(message=contract_error, code=contract_code)

    has_pending_for_thread = bool(pending_interrupt_ids)
    entries_by_interrupt_id: dict[str, ApprovalOccurrence | None] = {}
    for entry in entries:
        interrupt_id = cast(str, entry["interrupt_id"])
        status = entry["status"]
        pending_entry = lifecycle.pending_occurrence(thread_id=thread_id, interrupt_id=interrupt_id)
        if pending_entry is None:
            if status == "cancelled" and interrupt_id in expected_ids:
                handled_ids.add(interrupt_id)
                cancelled_ids.add(interrupt_id)
                entries_by_interrupt_id[interrupt_id] = None
                continue
            if has_pending_for_thread or interrupt_id in expected_ids:
                return (
                    [],
                    handled_ids,
                    cancelled_ids,
                    RunErrorEvent(
                        message=f"No pending approval interrupt found for resume interruptId '{interrupt_id}'.",
                        code="APPROVAL_RESUME_NOT_FOUND",
                    ),
                )
            continue

        handled_ids.add(interrupt_id)
        entries_by_interrupt_id[interrupt_id] = pending_entry
        if status == "cancelled":
            cancelled_ids.add(interrupt_id)
            continue
        if status != "resolved":
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(
                    message=f"Unsupported approval resume status '{status}' for interruptId '{interrupt_id}'.",
                    code="APPROVAL_RESUME_INVALID",
                ),
            )

    lifecycle_decisions: list[ResumeDecision] = []
    restored_sibling_response_ids: set[str] = set()
    for entry in entries:
        interrupt_id = cast(str, entry["interrupt_id"])
        pending_entry = entries_by_interrupt_id.get(interrupt_id)
        if pending_entry is None or entry["status"] == "cancelled":
            continue

        pending_arguments = _pending_approval_arguments(pending_entry)
        accepted, canonical_arguments, merged_arguments, validation_error = _canonical_approval_decision(
            entry.get("payload"),
            interrupt_id=interrupt_id,
            original_arguments_text=pending_arguments,
            server_label=_pending_approval_server_label(pending_entry),
        )
        if validation_error is not None:
            return [], handled_ids, cancelled_ids, validation_error
        if accepted is None or canonical_arguments is None or merged_arguments is None:
            raise RuntimeError("Validated approval decision is missing canonical values.")
        lifecycle_decisions.append(
            ResumeDecision(
                interrupt_id=interrupt_id,
                accepted=accepted,
                arguments=canonical_arguments,
                name=_pending_approval_name(pending_entry),
                original_arguments=pending_arguments,
            )
        )
        function_approvals = [
            {
                "id": interrupt_id,
                "call_id": pending_entry.identity.call_id,
                "name": _pending_approval_name(pending_entry) or "",
                "approved": accepted,
                "arguments": merged_arguments,
            }
        ]
        for raw_request in _pending_approval_already_approved_requests(pending_entry):
            request = Content.from_dict(raw_request)
            if request.type != "function_approval_request" or request.function_call is None:
                continue
            response = request.to_function_approval_response(approved=True)
            function_call = response.function_call
            if function_call is None:
                continue
            response_id = response.id or function_call.call_id
            if not response_id or not function_call.name:
                continue
            if str(response_id) in restored_sibling_response_ids:
                continue
            restored_sibling_response_ids.add(str(response_id))
            sibling_interrupt_id = str(response_id)
            sibling_call_id = str(function_call.call_id or response_id)
            sibling_arguments = canonical_function_arguments(function_call) or "{}"
            execution_owner = _function_call_execution_owner(
                function_call,
                tools,
                has_deferred_owner=has_deferred_owner,
            )
            lifecycle.register(
                owner=execution_owner,
                scope=approval_scope,
                thread_ids=[thread_id],
                interrupt_id=sibling_interrupt_id,
                call_id=sibling_call_id,
                name=function_call.name,
                arguments=sibling_arguments,
                aliases=[sibling_call_id],
                server_label=_function_call_server_label(function_call),
            )
            lifecycle_decisions.append(
                ResumeDecision(
                    interrupt_id=sibling_interrupt_id,
                    accepted=True,
                    arguments=sibling_arguments,
                    name=function_call.name,
                )
            )
            function_approvals.append(
                {
                    "id": str(response_id),
                    "call_id": str(function_call.call_id or response_id),
                    "name": function_call.name,
                    "approved": True,
                    "arguments": make_json_safe(function_call.parse_arguments() or {}),
                }
            )
        messages.append(
            {
                "id": f"approval-response-{interrupt_id}",
                "role": "user",
                "function_approvals": function_approvals,
            }
        )

    lifecycle_cancelled_ids = [
        interrupt_id for interrupt_id in cancelled_ids if entries_by_interrupt_id.get(interrupt_id) is not None
    ]
    if authorized_executions is not None:
        try:
            intents = lifecycle.resolve_batch(
                thread_id=thread_id,
                decisions=lifecycle_decisions,
                cancelled_interrupt_ids=lifecycle_cancelled_ids,
            )
            if snapshot_reconciliations is not None:
                snapshot_reconciliations.extend(intents.snapshot_reconciliations)
            for intent in intents:
                authorized_executions[intent.identity] = intent
        except (KeyError, ValueError) as exc:
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(message=str(exc), code="APPROVAL_RESUME_INVALID"),
            )
    elif lifecycle_cancelled_ids:
        try:
            reconciliations = lifecycle.cancel_batch(thread_id=thread_id, interrupt_ids=lifecycle_cancelled_ids)
            if snapshot_reconciliations is not None:
                snapshot_reconciliations.extend(reconciliations)
        except (KeyError, ValueError) as exc:
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(message=str(exc), code="APPROVAL_RESUME_INVALID"),
            )

    return messages, handled_ids, cancelled_ids, None


async def _resolve_approval_responses(
    messages: list[Any],
    tools: list[Any],
    agent: SupportsAgentRun,
    run_kwargs: dict[str, Any],
    thread_id: str = "",
    validated_approved_responses: list[Content] | None = None,
    *,
    lifecycle: ApprovalLifecycle,
    authorized_executions: dict[ApprovalOccurrenceIdentity, AuthorizedExecution] | None = None,
    forwarded_executions: (
        dict[str, list[tuple[ForwardedPendingToolTransitionOwner, AuthorizedExecution, Content]]] | None
    ) = None,
) -> list[Content]:
    """Execute approved function calls and replace approval content with results.

    This modifies the messages list in place, replacing function_approval_response
    content with function_result content containing the actual tool execution result.

    Args:
        messages: List of messages (will be modified in place)
        tools: List of available tools
        agent: The agent instance (to get client and config)
        run_kwargs: Kwargs for tool execution
        thread_id: The conversation thread ID used to scope registry keys.
        validated_approved_responses: Optional collector for validated local
            approval responses, including controls removed because the matching
            call occurrence already has a terminal result.

    Returns:
        List of approved function_result Content objects only (empty if no
        approvals).  Rejection results are written into the message history
        but are *not* included in the return value because they should not
        be emitted as TOOL_CALL_RESULT events.
    """
    approval_responses: list[Content] = []
    responses_by_id: dict[str, list[Content]] = {}
    for message in messages:
        for content in message.contents:
            if content.type == "function_approval_response" and content.id is not None:
                approval_responses.append(content)
                responses_by_id.setdefault(content.id, []).append(content)

    valid_response_content_ids: set[int] | None = None
    pending_local_response_content_ids: set[int] | None = None
    validated_forwarded_approvals: list[Content] = []
    response_content_ids_to_strip: set[int] = set()
    valid_response_content_ids = set()
    pending_local_response_content_ids = set()
    pending_response_groups: dict[object, tuple[ApprovalOccurrence, list[Content]]] = {}
    intents_by_response_content_id: dict[int, AuthorizedExecution] = {}
    for response in approval_responses:
        resp_id = response.id
        function_call_id = response.function_call.call_id if response.function_call else None
        pending_entry = None
        for alias in (resp_id, function_call_id):
            if alias is not None:
                pending_entry = lifecycle.occurrence_for_alias(thread_id=thread_id, interrupt_id=str(alias))
            if pending_entry is not None:
                break
        if pending_entry is None:
            if not _is_hosted_tool_approval(response):
                logger.warning("Rejected approval response id=%s: no matching approval occurrence", resp_id)
                response_content_ids_to_strip.add(id(response))
            continue
        group = pending_response_groups.get(pending_entry.identity)
        if group is None:
            pending_response_groups[pending_entry.identity] = (pending_entry, [response])
        else:
            group[1].append(response)

    for pending_entry, responses in pending_response_groups.values():
        pending_name = pending_entry.name
        # The canonical AG-UI approval id may be the provider call id, which can
        # be reused by a later call occurrence, while provider request ids may
        # alias that same pending entry. Only the latest response across every
        # trusted alias can answer the current entry; earlier responses are
        # stale replay controls and must not authorize a malformed fresh one.
        primary_response = responses[-1]
        response_content_ids_to_strip.update(id(response) for response in responses[:-1])
        if not isinstance(primary_response.approved, bool):
            logger.warning(
                "Treating approval response id=%s as rejected: approved must be a boolean",
                primary_response.id,
            )
            primary_response.approved = False
        resp_id = primary_response.id
        id_entry = (
            lifecycle.occurrence_for_alias(thread_id=thread_id, interrupt_id=str(resp_id))
            if resp_id is not None
            else None
        )
        if id_entry is not pending_entry:
            logger.warning(
                "Rejected approval response id=%s: no matching pending approval request",
                resp_id,
            )
            response_content_ids_to_strip.add(id(primary_response))
            continue
        function_call_id = primary_response.function_call.call_id if primary_response.function_call else None
        if function_call_id != pending_entry.identity.call_id:
            logger.warning(
                "Rejected approval response id=%s: function call id mismatch (response=%s)",
                resp_id,
                function_call_id,
            )
            response_content_ids_to_strip.add(id(primary_response))
            continue
        response_name = primary_response.function_call.name if primary_response.function_call else None
        if response_name != pending_name:
            logger.warning(
                "Rejected approval response id=%s: function name mismatch (response=%s, pending=%s)",
                resp_id,
                response_name,
                pending_name,
            )
            response_content_ids_to_strip.add(id(primary_response))
            continue
        pending_arguments = pending_entry.arguments
        response_arguments = canonical_function_arguments(primary_response.function_call)
        if not _approval_arguments_match_pending(pending_arguments, response_arguments):
            logger.warning("Rejected approval response id=%s: function arguments mismatch", resp_id)
            response_content_ids_to_strip.add(id(primary_response))
            continue

        server_label = pending_entry.server_label
        intent: AuthorizedExecution | None = None
        if primary_response.function_call is not None:
            if server_label:
                primary_response.function_call.additional_properties["server_label"] = server_label
            else:
                primary_response.function_call.additional_properties.pop("server_label", None)
        if (
            primary_response.approved is True
            and lifecycle is not None
            and authorized_executions is not None
            and primary_response.function_call is not None
        ):
            call_id = primary_response.function_call.call_id or primary_response.id or ""
            intent = authorized_executions.get(pending_entry.identity)
            if intent is None:
                logger.warning("Approval remains pending because no transition owner can act for call_id=%s.", call_id)
                response_content_ids_to_strip.add(id(primary_response))
                continue
            intents_by_response_content_id[id(primary_response)] = intent
        valid_response_content_ids.add(id(primary_response))
        if (
            primary_response.approved is True
            and intent is not None
            and intent.owner in {ApprovalExecutionOwner.HOSTED, ApprovalExecutionOwner.DEFERRED}
        ):
            validated_forwarded_approvals.append(primary_response)
        if not server_label:
            pending_local_response_content_ids.add(id(primary_response))
        if validated_approved_responses is not None and primary_response.approved is True and not server_label:
            validated_approved_responses.append(primary_response)

    if response_content_ids_to_strip:
        filtered_messages: list[Message] = []
        for message in messages:
            filtered_contents = [
                content for content in message.contents if id(content) not in response_content_ids_to_strip
            ]
            if len(filtered_contents) == len(message.contents):
                filtered_messages.append(message)
                continue
            if not filtered_contents:
                continue
            message.contents = filtered_contents
            filtered_messages.append(message)
        messages[:] = filtered_messages

    # A replayed terminal result can precede the synthesized approval response.
    # Remove completed controls before static execution, but do not let an
    # untrusted result in a still-pending server occurrence suppress execution.
    # Collapse duplicate responses for the same approval occurrence to one.
    messages[:] = _filter_local_approval_responses_for_provider(
        messages,
        pending_response_content_ids=pending_local_response_content_ids,
    )

    if (
        validated_forwarded_approvals
        and lifecycle is not None
        and authorized_executions is not None
        and forwarded_executions is not None
    ):
        for approval in validated_forwarded_approvals:
            function_call = approval.function_call
            call_id = (function_call.call_id if function_call else None) or approval.id or ""
            intent = intents_by_response_content_id.get(id(approval))
            if intent is None:
                logger.warning("Skipping hosted approval without lifecycle authority for call_id=%s.", call_id)
                continue

            async def forward_hosted_decision(approval: Content = approval) -> list[Content]:
                return [approval]

            if intent.owner is ApprovalExecutionOwner.HOSTED:
                forwarded_owner: ForwardedPendingToolTransitionOwner = HostedPendingToolTransitionOwner(
                    forward_hosted_decision
                )
            else:
                forwarded_owner = DeferredPendingToolTransitionOwner(forward_hosted_decision)
            forwarded = await forwarded_owner.forward(intent, lifecycle=lifecycle)
            if len(forwarded) != 1:
                raise RuntimeError("Hosted transition owner did not forward exactly one approval decision.")
            forwarded_executions.setdefault(call_id, []).append((forwarded_owner, intent, forwarded[0]))

    fcc_todo = _collect_approval_responses(messages)
    if valid_response_content_ids is not None:
        fcc_todo = {
            response_id: response
            for response_id, response in fcc_todo.items()
            if id(response) in valid_response_content_ids
        }
    if not fcc_todo:
        return []

    approved_responses = [resp for resp in fcc_todo.values() if resp.approved is True]

    approved_function_result_groups: list[list[Content]] = []

    # Partition approved responses into static (execute now) and deferred (execute during run)
    static_approved: list[Content] = []

    for approval in approved_responses:
        function_call = approval.function_call
        call_id = (function_call.call_id if function_call else None) or approval.id or ""
        intent = intents_by_response_content_id.get(id(approval))
        if intent is None or intent.owner is not ApprovalExecutionOwner.LOCAL:
            continue
        static_approved.append(approval)

    # Execute lifecycle-authorized local calls only through their transition owner.
    if static_approved and tools and lifecycle is not None and authorized_executions is not None:
        client = getattr(agent, "client", None)
        config = normalize_function_invocation_configuration(getattr(client, "function_invocation_configuration", None))
        middleware_pipeline = FunctionMiddlewarePipeline(
            *getattr(client, "function_middleware", ()),
            *run_kwargs.get("middleware", ()),
        )
        tool_kwargs = {k: v for k, v in run_kwargs.items() if k != "options"}
        for approval in static_approved:
            function_call = approval.function_call
            call_id = (function_call.call_id if function_call else None) or approval.id or ""
            intent = intents_by_response_content_id.get(id(approval))
            if intent is None:
                logger.warning("Skipping local approval without lifecycle authority for call_id=%s.", call_id)
                approved_function_result_groups.append([])
                continue

            async def execute_local_call(approval: Content = approval, call_id: str = call_id) -> list[Content]:
                try:
                    result_groups, _ = await _try_execute_function_call_groups(
                        custom_args=tool_kwargs,
                        function_calls=[approval],
                        tools=tools,
                        middleware_pipeline=middleware_pipeline,
                        config=config,
                    )
                except Exception as exc:
                    logger.exception("Failed to execute approved tool call; injecting error result: %s", exc)
                    return [Content.from_function_result(call_id=call_id, result="Error: Tool call invocation failed.")]
                if not result_groups or not result_groups[0]:
                    return [Content.from_function_result(call_id=call_id, result="Error: Tool call invocation failed.")]
                return result_groups[0]

            local_owner = LocalPendingToolTransitionOwner(execute_local_call)
            outcome = await local_owner.execute(intent, lifecycle=lifecycle)
            approved_function_result_groups.append(list(outcome.result_group))

    # Normalize one group per static approval and collect only terminal results for TOOL_CALL_RESULT events.
    # Deferred provider-injected approvals are left in messages for ToolApprovalMiddleware to process.
    replacement_groups: list[list[Content]] = []
    approved_results: list[Content] = []
    for idx, approval in enumerate(static_approved):
        result_group = approved_function_result_groups[idx] if idx < len(approved_function_result_groups) else []
        if not result_group:
            func_call = approval.function_call
            call_id = (func_call.call_id if func_call else None) or approval.id or ""
            result_group = [Content.from_function_result(call_id=call_id, result="Error: Tool call invocation failed.")]
        replacement_groups.append(result_group)
        approved_results.extend(content for content in result_group if content.type == "function_result")

    _replace_approval_contents_with_results(messages, fcc_todo, replacement_groups)

    # Post-process: Convert user messages with function_result content to proper tool messages.
    # After _replace_approval_contents_with_results, approved tool calls have their results
    # placed in user messages. OpenAI requires tool results to be in role="tool" messages.
    # This transformation ensures the message history is valid for the LLM provider.
    _convert_approval_results_to_tool_messages(messages)

    return approved_results


def _convert_approval_results_to_tool_messages(messages: list[Message]) -> None:
    """Convert function_result content in user messages to proper tool messages.

    After approval processing, tool results end up in user messages. OpenAI and other
    providers require tool results to be in role="tool" messages. This function
    extracts function_result content from user messages and creates proper tool messages.

    This modifies the messages list in place.

    Args:
        messages: List of Message objects to process
    """
    result: list[Message] = []

    for msg in messages:
        if get_role_value(msg) != "user":
            result.append(msg)
            continue

        msg_contents = msg.contents or []
        function_results: list[Content] = [content for content in msg_contents if content.type == "function_result"]
        other_contents: list[Content] = [content for content in msg_contents if content.type != "function_result"]

        if not function_results:
            result.append(msg)
            continue

        logger.info(
            f"Converting {len(function_results)} function_result content(s) from user message to tool message(s)"
        )

        # Tool messages first (right after the preceding assistant message per OpenAI requirements)
        for func_result in function_results:
            result.append(Message(role="tool", contents=[func_result]))

        # Then user message with remaining content (if any)
        if other_contents:
            result.append(Message(role="user", contents=other_contents))

    messages[:] = result


def _confirm_changes_target_call_id(
    snapshot_messages: list[dict[str, Any]],
    confirm_call_id: str,
    approval_payload: Mapping[str, Any],
) -> str | None:
    explicit_call_id = approval_payload.get("function_call_id")
    if explicit_call_id:
        return str(explicit_call_id)

    for snapshot_message in snapshot_messages:
        if normalize_agui_role(snapshot_message.get("role", "")) != "assistant":
            continue
        tool_calls = snapshot_message.get("tool_calls") or snapshot_message.get("toolCalls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, Mapping) or str(tool_call.get("id") or "") != confirm_call_id:
                continue
            function = tool_call.get("function")
            if not isinstance(function, Mapping) or function.get("name") != "confirm_changes":
                return None
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    return None
            if isinstance(arguments, Mapping) and arguments.get("function_call_id"):
                return str(arguments["function_call_id"])
            return None
    return None


def _clean_resolved_approvals_from_snapshot(
    snapshot_messages: list[dict[str, Any]],
    resolved_messages: list[Message],
) -> None:
    """Replace approval payloads in snapshot messages with actual tool results.

    After _resolve_approval_responses executes approved tools, the snapshot still
    contains the raw approval payload (e.g. ``{"accepted": true}``). When this
    snapshot is sent back to CopilotKit via ``MessagesSnapshotEvent``, the approval
    payload persists in the conversation history.  On the next turn CopilotKit
    re-sends the full history and the adapter re-detects the approval, causing the
    tool to be re-executed.

    This function replaces approval tool-message content in ``snapshot_messages``
    with the real tool result so the approval payload no longer appears in the
    history sent to the client.

    Args:
        snapshot_messages: Raw AG-UI snapshot messages (mutated in place).
        resolved_messages: Provider messages after approval resolution.
    """
    # Build call_id → result text from resolved tool messages
    result_by_call_id: dict[str, str] = {}
    for msg in resolved_messages:
        if get_role_value(msg) != "tool":
            continue
        for content in msg.contents or []:
            if content.type == "function_result" and content.call_id:
                result_text = (
                    content.result if isinstance(content.result, str) else json.dumps(make_json_safe(content.result))
                )
                result_by_call_id[str(content.call_id)] = result_text

    for snap_msg in snapshot_messages:
        if normalize_agui_role(snap_msg.get("role", "")) != "tool":
            continue
        raw_content = snap_msg.get("content")
        if not isinstance(raw_content, str):
            continue

        # Check if this is an approval payload
        try:
            parsed = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, dict) or "accepted" not in parsed:
            continue

        # Find matching tool result by toolCallId
        tool_call_id = snap_msg.get("toolCallId") or snap_msg.get("tool_call_id") or ""
        replacement = result_by_call_id.get(str(tool_call_id))
        if replacement is None:
            target_call_id = _confirm_changes_target_call_id(
                snapshot_messages,
                str(tool_call_id),
                parsed,
            )
            if target_call_id is None:
                continue
            if parsed.get("accepted") is True:
                replacement = result_by_call_id.get(target_call_id)
                if replacement is None:
                    continue
            else:
                replacement = "Changes declined."
        snap_msg["content"] = replacement
        logger.info(
            "Replaced approval payload in snapshot for tool_call_id=%s with resolved content",
            tool_call_id,
        )


def _snapshot_tool_call_ids(message: Mapping[str, Any]) -> list[str]:
    """Return assistant tool call ids from a snapshot message."""
    tool_calls = message.get("tool_calls") or message.get("toolCalls")
    if not isinstance(tool_calls, list):
        return []
    call_ids: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, Mapping):
            continue
        call_id = tool_call.get("id")
        if call_id:
            call_ids.append(str(call_id))
    return call_ids


def _resolved_tool_result_snapshot_messages(resolved_messages: list[Message]) -> dict[str, dict[str, Any]]:
    """Build replayable AG-UI tool messages from resolved approval results."""
    result_by_call_id: dict[str, dict[str, Any]] = {}
    for msg in resolved_messages:
        if get_role_value(msg) != "tool":
            continue
        function_results = [
            content for content in msg.contents or [] if content.type == "function_result" and content.call_id
        ]
        for content in function_results:
            call_id = str(content.call_id)
            result_by_call_id[call_id] = {
                "id": msg.message_id if msg.message_id and len(function_results) == 1 else generate_event_id(),
                "role": "tool",
                "toolCallId": call_id,
                "content": _stringify_tool_result(content.result if content.result is not None else ""),
            }
    return result_by_call_id


def _merge_resolved_approval_results_into_snapshot(
    snapshot_messages: list[dict[str, Any]],
    resolved_messages: list[Message],
) -> None:
    """Persist approval-resolved tool results under their original tool call ids."""
    result_by_call_id = _resolved_tool_result_snapshot_messages(resolved_messages)
    if not result_by_call_id:
        snapshot_messages[:] = [message for message in snapshot_messages if not message.get("function_approvals")]
        return

    merged_messages: list[dict[str, Any]] = []
    for message in snapshot_messages:
        if message.get("function_approvals"):
            continue
        role = normalize_agui_role(message.get("role", ""))
        if role == "tool":
            tool_call_id = message.get("toolCallId") or message.get("tool_call_id")
            if tool_call_id and str(tool_call_id) in result_by_call_id:
                continue
        merged_messages.append(message)
        if role != "assistant":
            continue
        for call_id in _snapshot_tool_call_ids(message):
            result_message = result_by_call_id.pop(call_id, None)
            if result_message is not None:
                merged_messages.append(result_message)

    merged_messages.extend(result_by_call_id.values())
    snapshot_messages[:] = merged_messages


def _append_segmented_snapshot_messages(flow: FlowState, all_messages: list[dict[str, Any]]) -> None:
    """Append this turn's messages in the order the model emitted them.

    Segments tracked during streaming record whether text came before or after
    tool calls (issue #7223); tool results still follow the tool-call message
    they answer. Anything not covered by segment tracking falls back to the
    legacy grouping so no content is dropped.
    """
    emitted_call_ids: set[str] = set()

    for segment in flow.snapshot_segments:
        kind = segment["kind"]
        if kind == "text":
            if segment["text"]:
                all_messages.append({"id": segment["id"], "role": "assistant", "content": segment["text"]})
        elif kind == "tool_calls":
            calls = [
                flow.tool_calls_by_id[call_id] for call_id in segment["call_ids"] if call_id in flow.tool_calls_by_id
            ]
            if not calls:
                continue
            message_id = str(segment.get("id") or _new_tool_call_segment_id(flow))
            segment["id"] = message_id
            all_messages.append({"id": message_id, "role": "assistant", "tool_calls": [call.copy() for call in calls]})
            # Only mark the calls we actually emitted; a stale segment id that
            # never made it into tool_calls_by_id must stay eligible for the
            # leftover path below rather than vanishing silently.
            emitted_ids = {call["id"] for call in calls}
            emitted_call_ids.update(emitted_ids)
            all_messages.extend(result for result in flow.tool_results if result.get("toolCallId") in emitted_ids)
        elif kind == "reasoning":
            all_messages.extend(entry for entry in flow.reasoning_messages if entry.get("id") == segment["id"])

    leftover_calls = [tc for tc in flow.pending_tool_calls if tc.get("id") not in emitted_call_ids]
    if leftover_calls:
        leftover_ids = {cid for call in leftover_calls if (cid := call.get("id")) is not None}
        all_messages.append(
            {
                "id": _new_tool_call_segment_id(flow),
                "role": "assistant",
                "tool_calls": [call.copy() for call in leftover_calls],
            }
        )
        # Their results ride along too; without this they would be marked
        # emitted above and then excluded from the final append below.
        all_messages.extend(result for result in flow.tool_results if result.get("toolCallId") in leftover_ids)
        emitted_call_ids.update(leftover_ids)
    all_messages.extend(result for result in flow.tool_results if result.get("toolCallId") not in emitted_call_ids)


def _build_messages_snapshot(
    flow: FlowState,
    snapshot_messages: list[dict[str, Any]],
) -> MessagesSnapshotEvent:
    """Build MessagesSnapshotEvent from current flow state."""
    all_messages = list(snapshot_messages)

    if flow.snapshot_segments:
        _append_segmented_snapshot_messages(flow, all_messages)
        return MessagesSnapshotEvent(messages=all_messages)  # type: ignore[arg-type]

    # Add assistant message with tool calls only (no content)
    if flow.pending_tool_calls:
        tool_call_message_id = (
            generate_event_id() if flow.accumulated_text else (flow.message_id or generate_event_id())
        )
        tool_call_message = {
            "id": tool_call_message_id,
            "role": "assistant",
            "tool_calls": flow.pending_tool_calls.copy(),
        }
        all_messages.append(tool_call_message)

    # Add tool results
    all_messages.extend(flow.tool_results)

    # Add text-only assistant message if there is accumulated text
    # This is a separate message from the tool calls message to maintain
    # the expected AG-UI protocol format (see issue #3619)
    if flow.accumulated_text:
        content_message_id = flow.message_id or generate_event_id()
        all_messages.append(
            {
                "id": content_message_id,
                "role": "assistant",
                "content": flow.accumulated_text,
            }
        )

    # Add reasoning messages so frontends that reconcile state from
    # MESSAGES_SNAPSHOT retain reasoning content after streaming ends.
    all_messages.extend(flow.reasoning_messages)

    return MessagesSnapshotEvent(messages=all_messages)  # type: ignore[arg-type]


def _text_events_to_snapshot_messages(events: list[BaseEvent]) -> list[dict[str, Any]]:
    """Convert streamed text-message events into snapshot message dictionaries."""
    messages: list[dict[str, Any]] = []
    messages_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        if isinstance(event, TextMessageStartEvent):
            message: dict[str, Any] = {"id": event.message_id, "role": event.role, "content": ""}
            messages.append(message)
            messages_by_id[event.message_id] = message
        elif isinstance(event, TextMessageContentEvent):
            open_message = messages_by_id.get(event.message_id)
            if open_message is not None:
                open_message["content"] = f"{open_message['content']}{event.delta}"
    return [message for message in messages if message.get("content")]


def _restore_session_continuation_state(session: AgentSession, snapshot: AGUIThreadSnapshot | None) -> None:
    """Restore typed private state from trusted snapshot storage."""
    if snapshot is None or snapshot.session_state is None:
        return
    serialized_state = copy.deepcopy(snapshot.session_state)
    service_session_id = serialized_state.pop(_PROVIDER_SERVICE_SESSION_ID_STATE_KEY, None)
    try:
        restored = AgentSession.from_dict(
            {
                "type": "session",
                "session_id": session.session_id,
                "service_session_id": service_session_id,
                "state": serialized_state,
            }
        )
    except Exception:
        logger.exception(
            "Failed to restore AG-UI Session Continuation State for session_id=%s; continuing without it.",
            session.session_id,
        )
        return
    if service_session_id is not None:
        session.service_session_id = restored.service_session_id
    session.state.update(restored.state)


def _is_a2ui_runner(agent: Any) -> bool:
    """True when ``agent`` is an A2UI runner (auto-injected or hand-wired).

    Thin wrapper over the A2UI module's ``is_a2ui_runner`` that lets the terminal-snapshot
    suppression recognize A2UI runs. Imported lazily so this module stays importable
    without the optional ag-ui-a2ui-toolkit.
    """
    try:
        from ._a2ui import is_a2ui_runner
    except ImportError:
        return False
    return is_a2ui_runner(agent)


def _a2ui_existing_tool_names(agent: SupportsAgentRun, tools: list[Any] | None) -> list[str]:
    """Tool names already visible for this run, for the A2UI no-double-injection check.

    Combines the merged runtime ``tools`` with the agent's own default tools
    (``agent.default_options["tools"]``). Without the latter, an agent constructed with
    its own ``generate_a2ui`` but called with no runtime tools would look empty, so
    auto-injection would add a second declaration and the core tool merge would raise
    ``Duplicate tool name`` before the provider call.
    """
    names: set[str] = {name for name in (getattr(t, "name", None) for t in (tools or [])) if name}
    default_options = getattr(agent, "default_options", None)
    if isinstance(default_options, dict):
        for tool in default_options.get("tools") or []:
            name = getattr(tool, "name", None)
            if name:
                names.add(name)
    return list(names)


def _request_state_protected_keys(agent: SupportsAgentRun) -> set[str]:
    """Return session-state namespaces that client Shared State cannot own."""
    context_providers = cast(list[Any], getattr(agent, "context_providers", []))
    return {
        _TOOL_APPROVAL_STATE_KEY,
        InMemoryHistoryProvider.DEFAULT_SOURCE_ID,
        MESSAGE_INJECTION_PENDING_MESSAGES_STATE_KEY,
        *(provider.source_id for provider in context_providers),
    }


def _serialize_session_continuation_state(
    session: AgentSession,
    agent: SupportsAgentRun,
    *,
    shared_state_keys: set[str],
) -> dict[str, Any] | None:
    """Serialize server-owned state while preserving each AG-UI State Authority."""
    context_providers = cast(list[Any], getattr(agent, "context_providers", []))
    excluded_keys = {
        *shared_state_keys,
        _TOOL_APPROVAL_STATE_KEY,
        _PROVIDER_SERVICE_SESSION_ID_STATE_KEY,
        *(provider.source_id for provider in context_providers if isinstance(provider, HistoryProvider)),
    }
    continuation_state = {key: value for key, value in session.state.items() if key not in excluded_keys}
    if not continuation_state and session.service_session_id is None:
        return None

    serialized_session = AgentSession(
        session_id=session.session_id,
        service_session_id=session.service_session_id,
    )
    serialized_session.state.update(continuation_state)
    serialized_payload = serialized_session.to_dict()
    serialized_state = cast(dict[str, Any], serialized_payload["state"])
    if serialized_service_session_id := serialized_payload.get("service_session_id"):
        serialized_state[_PROVIDER_SERVICE_SESSION_ID_STATE_KEY] = serialized_service_session_id
    return serialized_state


def _safe_serialize_session_continuation_state(
    session: AgentSession,
    agent: SupportsAgentRun,
    *,
    shared_state_keys: set[str],
) -> dict[str, Any] | None:
    """Return JSON-safe continuation state without failing a completed run."""
    try:
        serialized_state = _serialize_session_continuation_state(
            session,
            agent,
            shared_state_keys=shared_state_keys,
        )
        if serialized_state is None:
            return None
        safe_state = make_json_safe(serialized_state)
        if isinstance(safe_state, dict):
            return cast(dict[str, Any], safe_state)
        logger.warning(
            "Ignoring AG-UI Session Continuation State with unsupported serialized type: %s",
            type(safe_state).__name__,
        )
    except Exception:
        logger.exception(
            "Failed to serialize AG-UI Session Continuation State for session_id=%s; saving snapshot without it.",
            session.session_id,
        )
    return None


def _split_service_session_input(
    stored_snapshot_messages: list[dict[str, Any]],
    current_turn_messages: list[dict[str, Any]],
    stored_interrupt: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the validated new suffix and backend-authoritative snapshot history."""
    if not current_turn_messages:
        snapshot_messages = copy.deepcopy(stored_snapshot_messages)
    else:
        snapshot_messages = _reconstruct_messages_from_thread_snapshot(
            stored_messages=stored_snapshot_messages,
            incoming_messages=current_turn_messages,
            stored_interrupt=stored_interrupt,
        )
    return snapshot_messages[len(stored_snapshot_messages) :], snapshot_messages


async def run_agent_stream(
    input_data: dict[str, Any],
    agent: SupportsAgentRun,
    config: AgentConfig,
    approval_state_store: InMemoryAGUIApprovalStateStore | None = None,
) -> AsyncGenerator[BaseEvent]:
    """Run agent and yield AG-UI events.

    This is the single entry point for all AG-UI agent runs. It follows a simple
    linear flow: RunStarted -> content events -> RunFinished.

    Args:
        input_data: AG-UI request data with messages, state, tools, etc.
        agent: The Agent Framework agent to run
        config: Agent configuration
        approval_state_store: Optional server-side Approval State store used to
            preserve approval-only middleware state across AG-UI requests.

    Yields:
        AG-UI events
    """
    # Parse IDs
    supplied_thread_id = input_data.get("thread_id") or input_data.get("threadId")
    supplied_run_id = input_data.get("run_id") or input_data.get("runId")
    thread_id = supplied_thread_id or str(uuid.uuid4())
    run_id = supplied_run_id or str(uuid.uuid4())
    snapshot_scope = cast(str | None, input_data.get(_SNAPSHOT_SCOPE_INPUT_KEY))
    approval_scope = cast(str | None, input_data.get(_APPROVAL_SCOPE_INPUT_KEY))
    approval_thread_id = approval_state_thread_id(scope=approval_scope, thread_id=thread_id)
    if approval_state_store is None:
        approval_state_store = InMemoryAGUIApprovalStateStore()

    state_schema = cast(dict[str, Any], getattr(config, "state_schema", {}) or {})
    predict_state_config = cast(dict[str, dict[str, str]], getattr(config, "predict_state_config", {}) or {})

    # Normalize messages
    available_interrupts = input_data.get("available_interrupts") or input_data.get("availableInterrupts")
    raw_messages: list[dict[str, Any]] = input_data.get("messages", []) or []
    resume_payload = _extract_resume_payload(input_data)
    snapshot_session = await ThreadSnapshotSession.open(
        store=config.snapshot_store,
        scope=snapshot_scope,
        thread_id=thread_id,
    )

    stored_snapshot = snapshot_session.stored
    stored_pending_approval_interrupt_ids: set[str] = set()
    seeded_resume_from_snapshot = False
    if stored_snapshot is not None:
        stored_pending_approval_interrupt_ids = _stored_pending_approval_interrupt_ids(stored_snapshot.interrupt)
        if approval_state_store is not None and stored_pending_approval_interrupt_ids:
            reconciliations = approval_state_store.lifecycle.reconcile_snapshot(
                thread_id=approval_thread_id,
                interrupt_ids=list(stored_pending_approval_interrupt_ids),
            )
            retired_interrupt_ids = {
                reconciliation.identity.interrupt_id
                if reconciliation.identity is not None
                else reconciliation.interrupt_id
                for reconciliation in reconciliations
                if reconciliation.retire_interrupt
            }
            if retired_interrupt_ids:
                await snapshot_session.clear_interrupts(interrupt_ids=retired_interrupt_ids)
                stored_snapshot = snapshot_session.stored
                stored_pending_approval_interrupt_ids.difference_update(retired_interrupt_ids)
    if snapshot_session.enabled and not raw_messages and resume_payload is None:
        async for event in snapshot_session.hydrate_events(run_id=run_id):
            yield event
        return

    snapshot_seed_messages: list[dict[str, Any]] | None = None

    if stored_snapshot is not None:
        if resume_payload is not None and stored_pending_approval_interrupt_ids:
            seeded_resume_from_snapshot = True

            if not config.use_service_session:
                raw_messages = snapshot_session.resume_seeded_messages(raw_messages)
            else:
                provider_suffix, snapshot_seed_messages = _split_service_session_input(
                    stored_snapshot_messages=stored_snapshot.messages,
                    current_turn_messages=raw_messages,
                    stored_interrupt=stored_snapshot.interrupt,
                )
                raw_messages = provider_suffix
        elif not config.use_service_session:
            raw_messages = _reconstruct_messages_from_thread_snapshot(
                stored_messages=stored_snapshot.messages,
                incoming_messages=raw_messages,
                stored_interrupt=stored_snapshot.interrupt,
            )
        else:
            provider_suffix, snapshot_seed_messages = _split_service_session_input(
                stored_snapshot_messages=stored_snapshot.messages,
                current_turn_messages=raw_messages,
                stored_interrupt=stored_snapshot.interrupt,
            )
            raw_messages = provider_suffix

    # Initialize flow state with stored state plus request-provided overrides;
    # endpoint-deferred defaults apply only to keys missing from both.
    flow = FlowState()
    flow.current_state = snapshot_session.effective_state(
        request_state=input_data.get("state"),
        deferred_defaults=cast(dict[str, Any] | None, input_data.get(_DEFAULT_STATE_INPUT_KEY)),
    )

    # Apply schema defaults for missing state keys
    if state_schema:
        for key, schema in state_schema.items():
            if key in flow.current_state:
                continue
            if isinstance(schema, dict) and cast(dict[str, Any], schema).get("type") == "array":
                flow.current_state[key] = []
            else:
                flow.current_state[key] = {}

    # Initialize predictive state handler if configured
    predictive_handler: PredictiveStateHandler | None = None
    if predict_state_config:
        predictive_handler = PredictiveStateHandler(
            predict_state_config=predict_state_config,
            current_state=flow.current_state,
        )

    authorized_executions: dict[ApprovalOccurrenceIdentity, AuthorizedExecution] = {}
    forwarded_executions: dict[str, list[tuple[ForwardedPendingToolTransitionOwner, AuthorizedExecution, Content]]] = {}
    retained_approval_results: list[Content] = []
    approval_snapshot_reconciliations: list[ApprovalSnapshotReconciliation] = []
    client_tools = convert_agui_tools_to_agent_framework(input_data.get("tools"))
    server_tools = collect_server_tools(agent)
    tools = merge_tools(server_tools, client_tools)
    approval_resume_messages, handled_resume_ids, cancelled_resume_ids, resume_error = (
        _canonical_approval_resume_messages(
            resume_payload,
            approval_thread_id,
            expected_interrupt_ids=stored_pending_approval_interrupt_ids or None,
            lifecycle=approval_state_store.lifecycle,
            tools=tools,
            has_deferred_owner=approval_state_store.has_tool_approval_state(approval_thread_id),
            authorized_executions=authorized_executions,
            retained_results=retained_approval_results,
            snapshot_reconciliations=approval_snapshot_reconciliations,
            approval_scope=approval_scope,
        )
    )
    if resume_error is not None:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        resume_error_code = getattr(resume_error, "code", None)
        should_clear_tool_approval_state = resume_error_code == "APPROVAL_RESUME_CANCELLED" or (
            resume_error_code == "APPROVAL_RESUME_NOT_FOUND"
            and _tool_approval_state_exists_for_cancelled_resume(
                resume_payload, approval_state_store, approval_thread_id
            )
        )
        if should_clear_tool_approval_state:
            _clear_tool_approval_state(approval_state_store, approval_thread_id)
        if resume_error_code == "APPROVAL_RESUME_CANCELLED":
            retired_interrupt_ids = {
                reconciliation.identity.interrupt_id
                if reconciliation.identity is not None
                else reconciliation.interrupt_id
                for reconciliation in approval_snapshot_reconciliations
                if reconciliation.retire_interrupt
            }
            await snapshot_session.clear_interrupts(interrupt_ids=retired_interrupt_ids or cancelled_resume_ids or None)
        yield resume_error
        return
    if cancelled_resume_ids and handled_resume_ids == cancelled_resume_ids:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        _clear_tool_approval_state(approval_state_store, approval_thread_id)
        retired_interrupt_ids = {
            reconciliation.identity.interrupt_id if reconciliation.identity is not None else reconciliation.interrupt_id
            for reconciliation in approval_snapshot_reconciliations
            if reconciliation.retire_interrupt
        }
        await snapshot_session.clear_interrupts(interrupt_ids=retired_interrupt_ids or cancelled_resume_ids)
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return
    resume_messages = _resume_to_tool_messages(resume_payload, exclude_interrupt_ids=handled_resume_ids)
    if available_interrupts:
        logger.debug("Received available interrupts metadata: %s", available_interrupts)
    if approval_resume_messages:
        logger.info(f"Appending {len(approval_resume_messages)} synthesized approval resume message(s).")
        raw_messages.extend(approval_resume_messages)
        if snapshot_seed_messages is not None:
            snapshot_seed_messages.extend(copy.deepcopy(approval_resume_messages))
    if resume_messages:
        logger.info(f"Appending {len(resume_messages)} synthesized resume message(s) to AG-UI input.")
        raw_messages.extend(resume_messages)
        if snapshot_seed_messages is not None:
            snapshot_seed_messages.extend(copy.deepcopy(resume_messages))
    if retained_approval_results and not raw_messages:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        for event in _make_approval_tool_result_events(retained_approval_results):
            yield event
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return
    protected_tool_call_ids = _approval_state_tool_call_ids(approval_state_store, approval_thread_id)
    messages, snapshot_messages = normalize_agui_input_messages(
        raw_messages,
        sanitize_tool_history=not (config.use_service_session and stored_snapshot is not None),
        protected_tool_call_ids=protected_tool_call_ids,
    )

    if snapshot_seed_messages is not None:
        _, snapshot_messages = normalize_agui_input_messages(
            snapshot_seed_messages,
            protected_tool_call_ids=protected_tool_call_ids,
        )
    # Check for structured output mode (skip text content)
    skip_text = False
    response_format: type[Any] | None = None
    default_options = getattr(agent, "default_options", None)
    if isinstance(default_options, dict):
        typed_default_options = cast(dict[str, Any], default_options)
        response_format = cast(type[Any] | None, typed_default_options.get("response_format"))
        skip_text = response_format is not None

    # Handle empty messages (emit RunStarted immediately since no agent response)
    if not messages:
        logger.warning("No messages provided in AG-UI input")
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    # A2UI auto-injection: CopilotKit's runtime composes forwardedProps; the AG-UI
    # a2ui-middleware sets injectA2UITool there. When set (or a backend
    # config["inject_a2ui_tool"] opt-in is — nullish fallback, so an explicit runtime
    # false still wins), the run is driven through an A2UI runner that adds surface
    # generation and strips the middleware-injected render tool from the planner's list.
    #
    # The runner wraps the agent ONLY for the stream call below; ``agent`` itself is NOT
    # rebound, so protected-state-key computation, approval resolution, and continuation
    # serialization keep reading the real agent's context_providers and client. The
    # forwarded AG-UI context is handed to the runner directly (not stamped onto run
    # option additional_properties), so a non-A2UI run that supplies context is never
    # affected. plan_a2ui_injection is imported lazily so this hosting path stays
    # importable without the optional ag-ui-a2ui-toolkit.
    _forwarded = input_data.get("forwarded_props") or input_data.get("forwardedProps")
    _a2ui_config = getattr(config, "a2ui_config", None)
    _a2ui_flag = read_inject_a2ui_flag(_forwarded)
    if _a2ui_flag is None and _a2ui_config:
        _a2ui_flag = _a2ui_config.get("inject_a2ui_tool")
    a2ui_runner: Any | None = None
    if _a2ui_flag:
        try:
            from ._a2ui import plan_a2ui_injection
        except ImportError as exc:
            # A2UI was explicitly requested; failing loud beats limping on with the
            # render tool advertised but no executor (which strands an unanswered tool
            # call). Tell the caller exactly how to fix it.
            raise RuntimeError(
                "A2UI was requested (injectA2UITool / a2ui_config) but the A2UI support "
                "package is not installed. Install the optional extra: "
                "pip install 'agent-framework-ag-ui[a2ui]'."
            ) from exc
        a2ui_runner = plan_a2ui_injection(
            agent=agent,
            forwarded_props=_forwarded,
            existing_tool_names=_a2ui_existing_tool_names(agent, tools),
            config=_a2ui_config,
            context_slice=build_ag_ui_context_slice(input_data.get("context")),
        )
        if a2ui_runner is not None and tools:
            drop = set(a2ui_runner.drop_tool_names)
            tools = [t for t in tools if getattr(t, "name", None) not in drop]

    # A2UI drove this run when it auto-injected a runner OR the developer hand-wired one
    # via enable_a2ui(). Recognizing both keeps the terminal-snapshot suppression correct
    # for the manual path too. The A2UI module owns this check (is_a2ui_runner).
    a2ui_active = _is_a2ui_runner(a2ui_runner or agent)

    # Create session (with service session support)
    if config.use_service_session:
        if not config.service_session_id_from_thread_id and not snapshot_session.enabled:
            raise ValueError(
                "use_service_session=True requires snapshot persistence unless service_session_id_from_thread_id=True."
            )
        service_session_id = supplied_thread_id if config.service_session_id_from_thread_id else None
        session = AgentSession(session_id=thread_id, service_session_id=service_session_id)
        stored_service_session_id = (
            stored_snapshot.session_state.get(_PROVIDER_SERVICE_SESSION_ID_STATE_KEY)
            if stored_snapshot is not None and stored_snapshot.session_state is not None
            else None
        )
        create_conversation = getattr(agent, "create_conversation", None)
        if (
            not config.service_session_id_from_thread_id
            and stored_service_session_id is None
            and callable(create_conversation)
        ):
            created_session = create_conversation(session_id=thread_id)
            if isinstance(created_session, Awaitable):
                created_session = await created_session
            if not isinstance(created_session, AgentSession):
                raise TypeError("agent.create_conversation() must return AgentSession")
            session = created_session
    else:
        session = AgentSession(session_id=thread_id)
    _restore_session_continuation_state(session, stored_snapshot)
    protected_session_state_keys = _request_state_protected_keys(agent)
    session.state.update(
        {
            key: copy.deepcopy(value)
            for key, value in flow.current_state.items()
            if key not in protected_session_state_keys
        }
    )
    _restore_tool_approval_state(session, approval_state_store, approval_thread_id)

    # Inject metadata for AG-UI orchestration (Feature #2: Azure-safe truncation)
    base_metadata: dict[str, Any] = {
        "ag_ui_thread_id": thread_id,
        "ag_ui_run_id": run_id,
    }
    if "forwarded_props" in input_data:
        base_metadata["forwarded_props"] = input_data["forwarded_props"]
    elif "forwardedProps" in input_data:
        base_metadata["forwarded_props"] = input_data["forwardedProps"]
    if flow.current_state:
        base_metadata["current_state"] = flow.current_state
    session.metadata = _build_safe_metadata(base_metadata)  # type: ignore[attr-defined]

    # Build run kwargs (Feature #6: Azure store flag when metadata present)
    run_kwargs: dict[str, Any] = {"session": session}
    if tools:
        run_kwargs["tools"] = tools
    # Hand the forwarded AG-UI context to the A2UI runner PER REQUEST (not just at
    # construction), so a reused manually enable_a2ui()-wrapped runner never serves stale
    # catalog/guidelines. Only when A2UI actually drives the run — a plain agent's run()
    # would reject the unknown kwarg.
    if a2ui_active:
        run_kwargs["a2ui_context"] = build_ag_ui_context_slice(input_data.get("context"))
    # Filter out AG-UI internal metadata keys before passing to chat client
    # These are used internally for orchestration and should not be sent to the LLM provider
    session_metadata = cast(dict[str, Any], getattr(session, "metadata", None) or {})
    client_metadata: dict[str, Any] = {
        k: v for k, v in session_metadata.items() if k not in AG_UI_INTERNAL_METADATA_KEYS
    }
    safe_metadata = _build_safe_metadata(client_metadata) if client_metadata else {}
    if safe_metadata:
        run_kwargs["options"] = {"metadata": safe_metadata, "store": True}

    # NOTE: the forwarded AG-UI context (A2UI component catalog + guidelines) is no
    # longer stamped onto run-option additional_properties. It is handed to the A2UI
    # runner directly (see the gate above / _a2ui.plan_a2ui_injection). Stamping it here
    # leaked the slice to the provider SDK as an unknown request option on any run that
    # supplied AG-UI context, including non-A2UI runs where no wrapper stripped it back.

    # Resolve approval responses (execute approved tools, replace approvals with results)
    # This must happen before running the agent so it sees the tool results
    tools_for_execution = tools if tools is not None else server_tools
    messages.extend(
        _pop_collected_tool_approval_response_messages(
            session,
            approval_thread_id,
            tools_for_execution,
            lifecycle=approval_state_store.lifecycle,
            authorized_executions=authorized_executions,
            approval_scope=approval_scope,
        )
    )
    execution_tool_map = _get_tool_map(tools_for_execution) if tools_for_execution else {}
    local_intents = [
        intent for intent in authorized_executions.values() if intent.owner is ApprovalExecutionOwner.LOCAL
    ]
    unavailable_local_intents = [
        intent
        for intent in local_intents
        if (tool := execution_tool_map.get(intent.name)) is None or getattr(tool, "declaration_only", False)
    ]
    if unavailable_local_intents:
        for intent in authorized_executions.values():
            approval_state_store.lifecycle.release_claim(intent, policy=ClaimRecoveryPolicy.SAFE_TO_RETRY)
        unavailable_names = ", ".join(sorted({intent.name for intent in unavailable_local_intents}))
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        yield RunErrorEvent(
            message=f"Approved tool(s) {unavailable_names} are temporarily unavailable; retry the approval later.",
            code="APPROVAL_TOOL_UNAVAILABLE",
        )
        return
    validated_approved_responses: list[Content] = []
    newly_resolved_approval_results = await _resolve_approval_responses(
        messages,
        tools_for_execution,
        agent,
        run_kwargs,
        approval_thread_id,
        validated_approved_responses,
        lifecycle=approval_state_store.lifecycle,
        authorized_executions=authorized_executions,
        forwarded_executions=forwarded_executions,
    )
    resolved_approval_results = retained_approval_results + newly_resolved_approval_results

    # Defense-in-depth: replace approval payloads in snapshot with actual tool results
    # so CopilotKit does not re-send stale approval content on subsequent turns.
    _clean_resolved_approvals_from_snapshot(snapshot_messages, messages)
    if resolved_approval_results or any(message.get("function_approvals") for message in snapshot_messages):
        _merge_resolved_approval_results_into_snapshot(snapshot_messages, messages)

    # Feature #3: Emit StateSnapshotEvent for approved state-changing tools before agent runs
    approved_state_updates = _extract_approved_state_updates(
        [Message(role="user", contents=validated_approved_responses)],
        predictive_handler,
    )
    approved_state_snapshot_emitted = False
    if approved_state_updates:
        flow.current_state.update(approved_state_updates)
        approved_state_snapshot_emitted = True

    # Handle confirm_changes response (state confirmation flow - emit confirmation and stop)
    if _is_confirm_changes_response(messages):
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        # Emit approved state snapshot before confirmation message
        if approved_state_snapshot_emitted:
            yield StateSnapshotEvent(snapshot=flow.current_state)
        confirmation_events = _handle_step_based_approval(messages)
        for event in confirmation_events:
            yield event
        # Persist the completed confirmation turn with interrupt=None so hydration
        # does not replay the stale pending interrupt after the user responded.
        persisted_messages = snapshot_messages + _text_events_to_snapshot_messages(confirmation_events)
        if resume_payload is not None and not seeded_resume_from_snapshot and snapshot_seed_messages is None:
            # Generic resume requests carry only the synthesized response, so prepend
            # stored history unless this run already seeded raw messages from it.
            persisted_messages = snapshot_session.resume_seeded_messages(persisted_messages)
        await snapshot_session.save(
            messages=persisted_messages,
            state=cast(dict[str, Any], make_json_safe(flow.current_state)) if flow.current_state else None,
            interrupt=None,
            session_state=_safe_serialize_session_continuation_state(
                session,
                agent,
                shared_state_keys=set(flow.current_state).difference(protected_session_state_keys),
            ),
        )
        _save_tool_approval_state(session, approval_state_store, approval_thread_id)
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    # Inject state context message so the model knows current application state
    # This is critical for shared state scenarios where the UI state needs to be visible
    if state_schema and flow.current_state:
        messages = _inject_state_context(messages, flow.current_state, state_schema)

    # Stream from agent - emit RunStarted after first update to get service IDs
    run_started_emitted = False
    provider_thread_id: str | None = None
    all_updates: list[Any] = []  # Collect for structured output processing
    latest_state_snapshot: dict[str, Any] | None = (
        cast(dict[str, Any], make_json_safe(flow.current_state)) if flow.current_state else None
    )
    # Agent middleware can defer the inner run until streaming begins, so the
    # telemetry override must cover construction, stream resolution, and every pull.
    # Drive the A2UI runner when one is active (see the gate above); the original agent
    # stays bound for all other reads.
    telemetry_conversation_id = str(supplied_thread_id) if supplied_thread_id is not None else None
    telemetry_context = partial(_use_telemetry_conversation_id, telemetry_conversation_id)
    stream_completed = False
    try:
        with telemetry_context():
            response_stream = (a2ui_runner or agent).run(messages, stream=True, **run_kwargs)
            stream = await _normalize_response_stream(response_stream)

        async for update in _iterate_with_context(stream, telemetry_context):
            # Collect updates for structured output processing
            if response_format is not None:
                all_updates.append(update)

            # Use service-generated IDs only when the AG-UI request omitted them. Client-supplied
            # IDs remain authoritative for lifecycle correlation and thread-scoped persistence.
            if not run_started_emitted:
                conv_id = get_conversation_id_from_update(update)
                if conv_id:
                    provider_thread_id = conv_id
                if supplied_thread_id is None and conv_id:
                    thread_id = conv_id
                    snapshot_session.rebind_thread_id(thread_id)
                if supplied_run_id is None and update.response_id:
                    run_id = update.response_id
                # NOW emit RunStarted with proper IDs
                yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
                # Emit PredictState custom event if configured
                if predict_state_config:
                    predict_state_value = [
                        {
                            "state_key": state_key,
                            "tool": cfg["tool"],
                            "tool_argument": cfg["tool_argument"],
                        }
                        for state_key, cfg in predict_state_config.items()
                    ]
                    yield CustomEvent(name="PredictState", value=predict_state_value)
                # Emit initial state snapshot only if we have both state_schema and state
                if state_schema and flow.current_state:
                    latest_state_snapshot = cast(dict[str, Any], make_json_safe(flow.current_state))
                    yield StateSnapshotEvent(snapshot=flow.current_state)
                run_started_emitted = True

                for event in _make_approval_tool_result_events(resolved_approval_results):
                    yield event

            # Feature #4: Detect tool-only messages (no text content)
            # Emit TextMessageStartEvent to create message context for tool calls
            if not flow.message_id and _has_only_tool_calls(update.contents):
                flow.message_id = generate_event_id()
                logger.info(f"Tool-only response detected, creating message_id={flow.message_id}")
                yield TextMessageStartEvent(message_id=flow.message_id, role="assistant")

            # Emit events for each content item
            for content in update.contents:
                content_type = getattr(content, "type", None)
                logger.debug(f"Processing content type={content_type}, message_id={flow.message_id}")

                if (
                    content_type == "function_result"
                    and content.call_id
                    and (forwarded_queue := forwarded_executions.get(content.call_id))
                    and approval_state_store is not None
                ):
                    forwarded = forwarded_queue.pop(0)
                    if not forwarded_queue:
                        forwarded_executions.pop(content.call_id, None)
                    owner, intent, _ = forwarded
                    owner.record_outcome(intent, [content], lifecycle=approval_state_store.lifecycle)

                # Register pending approval requests so we can validate responses later
                if content_type == "function_approval_request":
                    if content.id and content.function_call and content.function_call.name:
                        canonical_interrupt_id = content.function_call.call_id or content.id
                        provider_approval_thread_id = approval_state_thread_id(
                            scope=approval_scope,
                            thread_id=provider_thread_id or thread_id,
                        )
                        server_label = _function_call_server_label(content.function_call)
                        already_approved_requests = _stored_already_approved_requests_for_visible_approval(
                            session,
                            str(content.id),
                            str(canonical_interrupt_id) if canonical_interrupt_id else None,
                        )
                        execution_owner = _function_call_execution_owner(
                            content.function_call,
                            tools,
                            has_deferred_owner=_TOOL_APPROVAL_STATE_KEY in session.state,
                        )
                        registration_kwargs = {
                            "thread_ids": [approval_thread_id, provider_approval_thread_id],
                            "name": content.function_call.name,
                            "arguments": canonical_function_arguments(content.function_call) or "{}",
                            "request_id": str(content.id),
                            "interrupt_id": str(canonical_interrupt_id),
                            "already_approved_requests": already_approved_requests,
                        }
                        approval_state_store.register(
                            owner=execution_owner,
                            scope=approval_scope,
                            server_label=server_label,
                            **registration_kwargs,
                        )
                    else:
                        logger.warning(
                            "Approval request not registered: missing id=%s, function_call=%s, or function name",
                            getattr(content, "id", None),
                            getattr(content, "function_call", None),
                        )

                for event in _emit_content(
                    content,
                    flow,
                    predictive_handler,
                    skip_text,
                    config.require_confirmation,
                ):
                    if isinstance(event, StateSnapshotEvent):
                        latest_state_snapshot = cast(dict[str, Any], make_json_safe(event.snapshot))
                    yield event

            # Stop if waiting for approval
            if flow.waiting_for_approval:
                break
        stream_completed = True
    finally:
        if approval_state_store is not None:
            for queued_executions in forwarded_executions.values():
                for owner, intent, forwarded_approval in queued_executions:
                    if stream_completed:
                        owner.record_outcome(intent, [forwarded_approval], lifecycle=approval_state_store.lifecycle)
                    else:
                        approval_state_store.lifecycle.recover_execution(intent, owner=intent.owner)
            forwarded_executions.clear()

    if flow.waiting_for_approval and isinstance(stream, ResponseStream):
        await stream.get_final_response()

    # If no updates at all, still emit RunStarted
    if not run_started_emitted:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        if predict_state_config:
            predict_state_value = [
                {
                    "state_key": state_key,
                    "tool": cfg["tool"],
                    "tool_argument": cfg["tool_argument"],
                }
                for state_key, cfg in predict_state_config.items()
            ]
            yield CustomEvent(name="PredictState", value=predict_state_value)
        if state_schema and flow.current_state:
            yield StateSnapshotEvent(snapshot=flow.current_state)

        for event in _make_approval_tool_result_events(resolved_approval_results):
            yield event
    if response_format is not None and all_updates:
        from agent_framework import AgentResponse
        from pydantic import BaseModel

        if not (isinstance(response_format, type) and issubclass(response_format, BaseModel)):
            logger.warning("Skipping structured output parsing: response_format is not a Pydantic model type.")
        else:
            logger.info(f"Processing structured output, update count: {len(all_updates)}")
            final_response = AgentResponse.from_updates(all_updates, output_format_type=response_format)

            if final_response.value and isinstance(final_response.value, BaseModel):
                response_dict = final_response.value.model_dump(mode="json", exclude_none=True)
                logger.info(f"Received structured output keys: {list(response_dict.keys())}")

                # Extract state updates - if no state_schema, all non-message fields are state
                state_keys = set(state_schema.keys()) if state_schema else set(response_dict.keys()) - {"message"}
                state_updates = {k: v for k, v in response_dict.items() if k in state_keys}

                if state_updates:
                    flow.current_state.update(state_updates)
                    latest_state_snapshot = cast(dict[str, Any], make_json_safe(flow.current_state))
                    yield StateSnapshotEvent(snapshot=flow.current_state)
                    logger.info(f"Emitted StateSnapshotEvent with updates: {list(state_updates.keys())}")

                # Emit message field as text if present
                message_text = response_dict.get("message")
                if isinstance(message_text, str) and message_text:
                    message_id = generate_event_id()
                    yield TextMessageStartEvent(message_id=message_id, role="assistant")
                    yield TextMessageContentEvent(message_id=message_id, delta=message_text)
                    yield TextMessageEndEvent(message_id=message_id)
                    logger.info(f"Emitted conversational message with length={len(message_text)}")

    # Feature #1: Emit ToolCallEndEvent for declaration-only tools (tools without results)
    pending_without_end = flow.get_pending_without_end()
    if pending_without_end:
        logger.info(f"Found {len(pending_without_end)} pending tool calls without end event")
        for tool_call in pending_without_end:
            tool_call_id = tool_call.get("id")
            tool_name = tool_call.get("function", {}).get("name")
            if tool_call_id:
                logger.info(f"Emitting ToolCallEndEvent for declaration-only tool '{tool_call_id}'")
                yield ToolCallEndEvent(tool_call_id=tool_call_id)

                # For predictive tools with require_confirmation, emit confirm_changes
                if config.require_confirmation and predict_state_config and tool_name:
                    is_predictive_tool = any(cfg["tool"] == tool_name for cfg in predict_state_config.values())
                    if is_predictive_tool:
                        logger.info(f"Emitting confirm_changes for predictive tool '{tool_name}'")
                        # Extract state value from tool arguments for StateSnapshot
                        if predictive_handler:
                            try:
                                args_str = tool_call.get("function", {}).get("arguments", "{}")
                                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                                result = predictive_handler.extract_state_value(tool_name, args)
                                if result:
                                    state_key, state_value = result
                                    flow.current_state[state_key] = state_value
                                    latest_state_snapshot = cast(dict[str, Any], make_json_safe(flow.current_state))
                                    yield StateSnapshotEvent(snapshot=flow.current_state)
                            except json.JSONDecodeError:
                                # Ignore malformed JSON in tool arguments for predictive state;
                                # predictive updates are best-effort and should not break the flow.
                                logger.warning(
                                    "Failed to decode JSON arguments for predictive tool '%s' (tool_call_id=%s).",
                                    tool_name,
                                    tool_call_id,
                                )

                        # Parse function arguments - skip confirm_changes if we can't parse
                        # (we can't ask user to confirm something we can't properly display)
                        try:
                            function_arguments = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to decode JSON arguments for confirm_changes tool '%s' "
                                "(tool_call_id=%s). Skipping confirmation flow - cannot display "
                                "malformed arguments to user for approval.",
                                tool_name,
                                tool_call_id,
                            )
                            continue  # Skip to next tool call without emitting confirm_changes

                        # Emit confirm_changes tool call
                        confirm_id = generate_event_id()
                        confirm_message_id = _track_tool_call_segment(flow, confirm_id)
                        yield ToolCallStartEvent(
                            tool_call_id=confirm_id,
                            tool_call_name="confirm_changes",
                            parent_message_id=confirm_message_id,
                        )
                        confirm_args = {
                            "function_name": tool_name,
                            "function_call_id": tool_call_id,
                            "function_arguments": function_arguments,
                            "steps": [{"description": f"Execute {tool_name}", "status": "enabled"}],
                        }
                        confirm_args_json = json.dumps(confirm_args)
                        yield ToolCallArgsEvent(tool_call_id=confirm_id, delta=confirm_args_json)
                        yield ToolCallEndEvent(tool_call_id=confirm_id)

                        # Track confirm_changes in pending_tool_calls for MessagesSnapshotEvent
                        # The frontend needs to see this in the snapshot to render the confirmation dialog
                        confirm_entry = {
                            "id": confirm_id,
                            "type": "function",
                            "function": {"name": "confirm_changes", "arguments": confirm_args_json},
                        }
                        flow.pending_tool_calls.append(confirm_entry)
                        flow.tool_calls_by_id[confirm_id] = confirm_entry
                        flow.tool_calls_ended.add(confirm_id)  # Mark as ended since we emit End event
                        flow.waiting_for_approval = True
                        flow.interrupts.append(
                            _approval_interrupt_for_function_call(
                                interrupt_id=str(confirm_id),
                                function_call=Content.from_function_call(
                                    call_id=tool_call_id,
                                    name=tool_name,
                                    arguments=function_arguments,
                                ),
                                message=f"Approve the proposed changes from {tool_name}?",
                                response_schema=_approval_steps_response_schema(),
                                metadata={"confirmation_tool_call_id": confirm_id},
                            )
                        )

    # Close any open reasoning block
    for event in _close_reasoning_block(flow):
        yield event

    # Close any open message
    if flow.message_id:
        logger.debug(f"End of run: closing text message message_id={flow.message_id}")
        yield TextMessageEndEvent(message_id=flow.message_id)

    # Emit MessagesSnapshotEvent if we have tool calls or results
    # Feature #5: Suppress intermediate snapshots for predictive tools without confirmation
    should_emit_snapshot = (
        flow.pending_tool_calls or flow.tool_results or flow.accumulated_text or flow.reasoning_messages
    )
    latest_messages_snapshot = snapshot_messages
    if should_emit_snapshot:
        # Always fold this turn's output into the persisted snapshot, even when the
        # outbound MESSAGES_SNAPSHOT event is suppressed for predictive tools.
        snapshot_event = _build_messages_snapshot(flow, snapshot_messages)
        latest_messages_snapshot = _event_messages_to_snapshot_dicts(list(snapshot_event.messages))
        # Check if we should suppress for predictive tool
        last_tool_name = None
        if flow.tool_results:
            last_result = flow.tool_results[-1]
            last_call_id = last_result.get("toolCallId")
            last_tool_name = flow.get_tool_name(last_call_id)
        # A2UI surfaces stream as activities in emission order (tool card -> surface ->
        # narration). A terminal MessagesSnapshotEvent makes the client re-render from
        # the reconciled message list, which drops that order — the injected
        # generate_a2ui tool card re-positions BELOW the surface and text. Other AG-UI
        # frameworks emit no terminal snapshot here, so skip it for A2UI runs; the next
        # turn's history is still reconstructable from the streamed events. Keyed off
        # whether A2UI actually drove this run (a2ui_active), NOT the literal tool names,
        # so an unrelated user tool named "generate_a2ui" keeps its snapshot.
        if a2ui_active:
            logger.info("Suppressing terminal MessagesSnapshotEvent for A2UI run to preserve streamed message order.")
        if not a2ui_active and not _should_suppress_intermediate_snapshot(
            last_tool_name, predict_state_config, config.require_confirmation
        ):
            yield snapshot_event

    persisted_messages = latest_messages_snapshot
    if resume_payload is not None and not seeded_resume_from_snapshot and snapshot_seed_messages is None:
        # Generic resume requests carry only the synthesized response, so prepend
        # stored history unless this run already seeded raw messages from it.
        persisted_messages = snapshot_session.resume_seeded_messages(persisted_messages)
    await snapshot_session.save(
        messages=persisted_messages,
        state=latest_state_snapshot,
        interrupt=flow.interrupts or None,
        session_state=_safe_serialize_session_continuation_state(
            session,
            agent,
            shared_state_keys=set(flow.current_state).difference(protected_session_state_keys),
        ),
    )
    _save_tool_approval_state(session, approval_state_store, approval_thread_id)
    yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=flow.interrupts)
