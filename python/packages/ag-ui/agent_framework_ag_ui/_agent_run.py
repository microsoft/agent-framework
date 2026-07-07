# Copyright (c) Microsoft. All rights reserved.

"""Simplified AG-UI orchestration - single linear flow."""

from __future__ import annotations  # noqa: I001

import copy
import json
import logging
import uuid
from collections.abc import AsyncIterable, Awaitable, Mapping
from typing import TYPE_CHECKING, Any, TypedDict, cast

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
    Message,
    SupportsAgentRun,
)
from agent_framework._middleware import FunctionMiddlewarePipeline
from agent_framework._tools import (
    _ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY,  # type: ignore
    _collect_approval_responses,  # type: ignore
    _replace_approval_contents_with_results,  # type: ignore
    _TOOL_APPROVAL_STATE_KEY,  # type: ignore
    _try_execute_function_calls,  # type: ignore
    normalize_function_invocation_configuration,
)
from agent_framework._types import ResponseStream
from agent_framework.exceptions import AgentInvalidResponseException

from ._approval_state import _APPROVAL_SCOPE_INPUT_KEY, approval_state_thread_id
from ._message_adapters import normalize_agui_input_messages
from ._orchestration._predictive_state import PredictiveStateHandler
from ._orchestration._tooling import collect_server_tools, merge_tools, register_additional_client_tools
from ._run_common import (
    FlowState,
    _approval_interrupt_for_function_call,  # type: ignore
    _approval_steps_response_schema,  # type: ignore
    _build_run_finished_event,  # type: ignore
    _close_reasoning_block,  # type: ignore
    _emit_content,  # type: ignore
    _extract_resume_payload,  # type: ignore
    _extract_tool_result_display,  # type: ignore
    _has_only_tool_calls,  # type: ignore
    _normalize_resume_interrupts,  # type: ignore
    _reconstruct_messages_from_thread_snapshot,  # type: ignore
    _resume_contract_error,  # type: ignore
    _resolve_ui_payload,  # type: ignore
    _stringify_tool_result,  # type: ignore
)
from ._snapshots import (
    _DEFAULT_STATE_INPUT_KEY,
    _SNAPSHOT_SCOPE_INPUT_KEY,
    AGUIThreadSnapshot,
    _clear_thread_snapshot_interrupt,
)
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
            accepted = bool(result.get("accepted", False))
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


class _PendingApproval(TypedDict):
    """Pending approval details for a requested function call."""

    name: str
    arguments: str | None
    request_id: str | None
    interrupt_id: str | None


class _PendingApprovalWithSiblings(_PendingApproval, total=False):
    """Pending approval details including hidden already-approved sibling calls."""

    already_approved_requests: list[dict[str, Any]]


PendingApprovalEntry = _PendingApprovalWithSiblings | str
PendingApprovalKey = tuple[str, str]


def _pending_approval_key(thread_id: str, interrupt_id: str) -> PendingApprovalKey:
    """Build a structured pending-approval key scoped by thread and interrupt id."""
    return (thread_id, interrupt_id)


def _make_pending_approval_entry(
    name: str,
    arguments: str | None,
    *,
    request_id: str | None = None,
    interrupt_id: str | None = None,
    already_approved_requests: list[dict[str, Any]] | None = None,
) -> _PendingApprovalWithSiblings:
    entry: _PendingApprovalWithSiblings = {
        "name": name,
        "arguments": arguments,
        "request_id": request_id,
        "interrupt_id": interrupt_id,
    }
    if already_approved_requests:
        entry["already_approved_requests"] = already_approved_requests
    return entry


def _register_pending_approval_entry(
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry],
    thread_id: str,
    entry: PendingApprovalEntry,
    *ids: str | None,
) -> None:
    """Register all server-owned aliases for one pending approval entry."""
    for alias_key in _pending_approval_alias_keys(thread_id, entry, *ids):
        pending_approvals[alias_key] = entry


def _pending_approval_name(entry: PendingApprovalEntry) -> str | None:
    if isinstance(entry, str):
        return entry
    return entry["name"]


def _pending_approval_arguments(entry: PendingApprovalEntry) -> str | None:
    if isinstance(entry, str):
        return None
    return entry["arguments"]


def _pending_approval_already_approved_requests(entry: PendingApprovalEntry) -> list[dict[str, Any]]:
    if isinstance(entry, str):
        return []
    return list(entry.get("already_approved_requests", []))


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


def _thread_has_pending_approvals(
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] | None,
    thread_id: str,
) -> bool:
    if not pending_approvals:
        return False
    return any(key[0] == thread_id for key in pending_approvals)


def _pending_approval_interrupt_ids(
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] | None,
    thread_id: str,
) -> set[str]:
    if not pending_approvals:
        return set()
    interrupt_ids: set[str] = set()
    for key, entry in pending_approvals.items():
        if key[0] != thread_id:
            continue
        if isinstance(entry, str):
            interrupt_ids.add(key[1])
            continue
        interrupt_id = entry.get("interrupt_id") or entry.get("request_id") or key[1]
        interrupt_ids.add(str(interrupt_id))
    return interrupt_ids


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


def _find_pending_approval_entry(
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] | None,
    thread_id: str,
    interrupt_id: str,
) -> PendingApprovalEntry | None:
    if pending_approvals is None:
        return None
    return pending_approvals.get(_pending_approval_key(thread_id, interrupt_id))


def _pending_approval_alias_keys(
    thread_id: str,
    entry: PendingApprovalEntry,
    *ids: str | None,
) -> set[PendingApprovalKey]:
    aliases = {item for item in ids if item}
    if not isinstance(entry, str):
        request_id = entry.get("request_id")
        interrupt_id = entry.get("interrupt_id")
        if request_id:
            aliases.add(request_id)
        if interrupt_id:
            aliases.add(interrupt_id)
    return {_pending_approval_key(thread_id, alias) for alias in aliases}


def _consume_pending_approval_entry(
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry],
    thread_id: str,
    entry: PendingApprovalEntry,
    *ids: str | None,
) -> None:
    for alias_key in _pending_approval_alias_keys(thread_id, entry, *ids):
        pending_approvals.pop(alias_key, None)


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


def _canonical_approval_resume_messages(
    resume_payload: Any,
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] | None,
    thread_id: str,
    expected_interrupt_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str], set[str], RunErrorEvent | None]:
    """Translate canonical ResumeEntry approvals into existing approval response messages."""
    expected_ids = set(expected_interrupt_ids or set())
    if pending_approvals is None:
        if not expected_ids:
            return [], set(), set(), None
        entries, contract_error, contract_code = _resume_contract_error(
            resume_payload,
            expected_ids,
            required_code="APPROVAL_RESUME_REQUIRED",
            invalid_code="APPROVAL_RESUME_INVALID",
            unknown_code="APPROVAL_RESUME_NOT_FOUND",
            missing_code="APPROVAL_RESUME_MISSING_INTERRUPT",
        )
        if contract_error is not None and contract_code is not None:
            return [], set(), set(), RunErrorEvent(message=contract_error, code=contract_code)
        cancelled_expected_ids = {str(entry["interrupt_id"]) for entry in entries if entry.get("status") == "cancelled"}
        if cancelled_expected_ids:
            interrupt_id = next(str(entry["interrupt_id"]) for entry in entries if entry.get("status") == "cancelled")
            return (
                [],
                cancelled_expected_ids,
                cancelled_expected_ids,
                RunErrorEvent(
                    message=f"Approval resume for interruptId '{interrupt_id}' was cancelled.",
                    code="APPROVAL_RESUME_CANCELLED",
                ),
            )
        interrupt_id = entries[0]["interrupt_id"] if entries else sorted(expected_ids)[0]
        return (
            [],
            set(),
            set(),
            RunErrorEvent(
                message=f"No pending approval interrupt found for resume interruptId '{interrupt_id}'.",
                code="APPROVAL_RESUME_NOT_FOUND",
            ),
        )

    messages: list[dict[str, Any]] = []
    handled_ids: set[str] = set()
    cancelled_ids: set[str] = set()
    pending_interrupt_ids = _pending_approval_interrupt_ids(pending_approvals, thread_id)
    contract_interrupt_ids = expected_ids | pending_interrupt_ids
    if not contract_interrupt_ids:
        if _resume_payload_has_approval_decision(resume_payload):
            normalized_interrupts = _normalize_resume_interrupts(resume_payload)
            interrupt_id = normalized_interrupts[0]["id"] if normalized_interrupts else "unknown"
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

    has_pending_for_thread = _thread_has_pending_approvals(pending_approvals, thread_id)
    entries_by_interrupt_id: dict[str, PendingApprovalEntry | None] = {}
    for entry in entries:
        interrupt_id = cast(str, entry["interrupt_id"])
        status = entry["status"]
        pending_entry = _find_pending_approval_entry(pending_approvals, thread_id, interrupt_id)
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

    if cancelled_ids:
        for interrupt_id in cancelled_ids:
            pending_entry = entries_by_interrupt_id.get(interrupt_id)
            if pending_entry is not None:
                _consume_pending_approval_entry(pending_approvals, thread_id, pending_entry, interrupt_id)
        interrupt_id = next(str(entry["interrupt_id"]) for entry in entries if entry.get("status") == "cancelled")
        return (
            [],
            handled_ids,
            cancelled_ids,
            RunErrorEvent(
                message=f"Approval resume for interruptId '{interrupt_id}' was cancelled.",
                code="APPROVAL_RESUME_CANCELLED",
            ),
        )

    argument_updates: list[tuple[_PendingApprovalWithSiblings, str]] = []
    restored_sibling_response_ids: set[str] = set()
    for entry in entries:
        interrupt_id = cast(str, entry["interrupt_id"])
        pending_entry = entries_by_interrupt_id.get(interrupt_id)
        if pending_entry is None:
            continue

        payload = _parse_json_object(entry.get("payload"))
        if payload is None:
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(
                    message=f"Approval resume for interruptId '{interrupt_id}' must include an object payload.",
                    code="APPROVAL_RESUME_INVALID",
                ),
            )
        accepted = payload.get("accepted", payload.get("approved"))
        if not isinstance(accepted, bool):
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(
                    message=f"Approval resume for interruptId '{interrupt_id}' must include a boolean accepted value.",
                    code="APPROVAL_RESUME_INVALID",
                ),
            )

        pending_arguments = _pending_approval_arguments(pending_entry)
        original_arguments = _parse_json_object(pending_arguments) or {}
        edited_arguments = {key: value for key, value in payload.items() if key not in {"accepted", "approved"}}
        if not set(edited_arguments).issubset(set(original_arguments)):
            return (
                [],
                handled_ids,
                cancelled_ids,
                RunErrorEvent(
                    message=f"Approval resume for interruptId '{interrupt_id}' includes unsupported edited arguments.",
                    code="APPROVAL_RESUME_INVALID",
                ),
            )
        for name, edited_value in edited_arguments.items():
            original_value = original_arguments[name]
            if not _json_schema_value_matches(original_value, edited_value):
                return (
                    [],
                    handled_ids,
                    cancelled_ids,
                    RunErrorEvent(
                        message=(
                            f"Approval resume for interruptId '{interrupt_id}' has invalid type for edited "
                            f"argument '{name}'."
                        ),
                        code="APPROVAL_RESUME_INVALID_RESPONSE",
                    ),
                )

        merged_arguments = {**original_arguments, **edited_arguments}
        if not isinstance(pending_entry, str):
            argument_updates.append(
                (pending_entry, json.dumps(make_json_safe(merged_arguments), sort_keys=True, separators=(",", ":")))
            )
        function_approvals = [
            {
                "id": interrupt_id,
                "call_id": interrupt_id,
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
            sibling_entry = _make_pending_approval_entry(
                function_call.name,
                canonical_function_arguments(function_call),
                request_id=str(response.id) if response.id else None,
                interrupt_id=str(function_call.call_id) if function_call.call_id else None,
            )
            _register_pending_approval_entry(
                pending_approvals,
                thread_id,
                sibling_entry,
                str(response_id),
                str(function_call.call_id) if function_call.call_id else None,
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
        messages.append({"role": "user", "function_approvals": function_approvals})

    for pending_entry, arguments_json in argument_updates:
        pending_entry["arguments"] = arguments_json

    return messages, handled_ids, cancelled_ids, None


def _evict_oldest_approvals(registry: dict[PendingApprovalKey, PendingApprovalEntry], max_size: int = 10_000) -> None:
    """Evict the oldest entries from the pending-approvals registry (LRU).

    Only effective when *registry* is an ``OrderedDict``;  plain dicts are
    left untouched because insertion-order eviction is unreliable for them.
    """
    if len(registry) <= max_size:
        return
    try:
        while len(registry) > max_size:
            registry.popitem(last=False)  # type: ignore[call-arg]
    except (TypeError, KeyError):
        pass


async def _resolve_approval_responses(
    messages: list[Any],
    tools: list[Any],
    agent: SupportsAgentRun,
    run_kwargs: dict[str, Any],
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] | None = None,
    thread_id: str = "",
) -> list[Content]:
    """Execute approved function calls and replace approval content with results.

    This modifies the messages list in place, replacing function_approval_response
    content with function_result content containing the actual tool execution result.

    Args:
        messages: List of messages (will be modified in place)
        tools: List of available tools
        agent: The agent instance (to get client and config)
        run_kwargs: Kwargs for tool execution
        pending_approvals: Server-side registry of pending approval requests.
            Keys are ``(thread_id, request_id)``, values are function names.
            When provided, every approval response is validated against this
            registry to prevent bypass, function name spoofing, and replay.
        thread_id: The conversation thread ID used to scope registry keys.

    Returns:
        List of approved function_result Content objects only (empty if no
        approvals).  Rejection results are written into the message history
        but are *not* included in the return value because they should not
        be emitted as TOOL_CALL_RESULT events.
    """
    fcc_todo = _collect_approval_responses(messages)
    if not fcc_todo:
        return []

    approved_responses = [resp for resp in fcc_todo.values() if resp.approved]
    rejected_responses = [resp for resp in fcc_todo.values() if not resp.approved]

    # Validate every approval response (approved AND rejected) against the
    # pending approvals registry.  Invalid responses are stripped from messages
    # entirely — not converted to rejection results, which would inject
    # attacker-controlled content into the LLM conversation.
    if pending_approvals is not None and (approved_responses or rejected_responses):
        validated: list[Any] = []
        validated_rejected: list[Any] = []
        invalid_ids: set[str] = set()
        for resp in approved_responses + rejected_responses:
            resp_id = resp.id or ""
            resp_name = resp.function_call.name if resp.function_call else None
            registry_key = _pending_approval_key(thread_id, resp_id)

            if registry_key not in pending_approvals:
                logger.warning(
                    "Rejected approval response id=%s: no matching pending approval request",
                    resp_id,
                )
                invalid_ids.add(resp_id)
                continue

            pending_entry = pending_approvals[registry_key]
            pending_name = _pending_approval_name(pending_entry)
            if resp_name != pending_name:
                logger.warning(
                    "Rejected approval response id=%s: function name mismatch (response=%s, pending=%s)",
                    resp_id,
                    resp_name,
                    pending_name,
                )
                invalid_ids.add(resp_id)
                continue

            pending_arguments = _pending_approval_arguments(pending_entry)
            response_arguments = canonical_function_arguments(resp.function_call)
            if not _approval_arguments_match_pending(pending_arguments, response_arguments):
                logger.warning(
                    "Rejected approval response id=%s: function arguments mismatch",
                    resp_id,
                )
                invalid_ids.add(resp_id)
                continue

            # Valid — consume entry to prevent replay
            _consume_pending_approval_entry(
                pending_approvals,
                thread_id,
                pending_entry,
                resp_id,
                resp.function_call.call_id if resp.function_call else None,
            )
            if resp.approved:
                validated.append(resp)
            else:
                validated_rejected.append(resp)

        # Strip invalid approval responses from messages and fcc_todo so
        # _replace_approval_contents_with_results never sees them.
        if invalid_ids:
            for inv_id in invalid_ids:
                fcc_todo.pop(inv_id, None)
            for msg in messages:
                msg.contents = [
                    c for c in msg.contents if not (c.type == "function_approval_response" and c.id in invalid_ids)
                ]

        approved_responses = validated
        rejected_responses = validated_rejected

    approved_function_results: list[Any] = []

    # Execute approved tool calls
    if approved_responses and tools:
        client = getattr(agent, "client", None)
        config = normalize_function_invocation_configuration(getattr(client, "function_invocation_configuration", None))
        middleware_pipeline = FunctionMiddlewarePipeline(
            *getattr(client, "function_middleware", ()),
            *run_kwargs.get("middleware", ()),
        )
        # Filter out AG-UI-specific kwargs that should not be passed to tool execution
        tool_kwargs = {k: v for k, v in run_kwargs.items() if k != "options"}
        try:
            results, _ = await _try_execute_function_calls(
                custom_args=tool_kwargs,
                attempt_idx=0,
                function_calls=approved_responses,
                tools=tools,
                middleware_pipeline=middleware_pipeline,
                config=config,
            )
            approved_function_results = list(results)
        except Exception as e:
            logger.exception("Failed to execute approved tool calls; injecting error results: %s", e)
            approved_function_results = []

    # Build results for approved responses (used for TOOL_CALL_RESULT event emission)
    approved_results: list[Content] = []
    for idx, approval in enumerate(approved_responses):
        if (
            idx < len(approved_function_results)
            and getattr(approved_function_results[idx], "type", None) == "function_result"
        ):
            approved_results.append(approved_function_results[idx])
            continue
        # Get call_id from function_call if present, otherwise use approval.id
        func_call = approval.function_call
        call_id = (func_call.call_id if func_call else None) or approval.id or ""
        approved_results.append(
            Content.from_function_result(call_id=call_id, result="Error: Tool call invocation failed.")
        )

    _replace_approval_contents_with_results(messages, fcc_todo, approved_results)

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

    if not result_by_call_id:
        return

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
        if replacement is not None:
            snap_msg["content"] = replacement
            logger.info(
                "Replaced approval payload in snapshot for tool_call_id=%s with actual result",
                tool_call_id,
            )


def _build_messages_snapshot(
    flow: FlowState,
    snapshot_messages: list[dict[str, Any]],
) -> MessagesSnapshotEvent:
    """Build MessagesSnapshotEvent from current flow state."""
    all_messages = list(snapshot_messages)

    # Add assistant message with tool calls only (no content)
    if flow.pending_tool_calls:
        tool_call_message = {
            "id": flow.message_id or generate_event_id(),
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
        # Use a new ID for the content message if we had tool calls (separate message)
        content_message_id = (
            generate_event_id() if flow.pending_tool_calls else (flow.message_id or generate_event_id())
        )
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


def _event_messages_to_snapshot_dicts(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert AG-UI message event models back to plain snapshot dictionaries."""
    safe_messages = make_json_safe(messages)
    if not isinstance(safe_messages, list):
        return []
    return [cast(dict[str, Any], message) for message in safe_messages if isinstance(message, dict)]


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


async def _hydrate_thread_snapshot(
    *,
    config: AgentConfig,
    scope: str,
    thread_id: str,
    run_id: str,
) -> AsyncGenerator[BaseEvent]:
    """Replay the latest stored AG-UI Thread Snapshot without invoking the agent."""
    yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
    if config.snapshot_store is None:
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    snapshot = await config.snapshot_store.get(scope=scope, thread_id=thread_id)
    if snapshot is None:
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    if snapshot.state is not None:
        yield StateSnapshotEvent(snapshot=snapshot.state)
    if snapshot.messages:
        yield MessagesSnapshotEvent(messages=snapshot.messages)  # type: ignore[arg-type]
    yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=snapshot.interrupt)


async def _save_thread_snapshot(
    *,
    config: AgentConfig,
    scope: str | None,
    thread_id: str,
    messages: list[dict[str, Any]],
    state: dict[str, Any] | None,
    interrupt: list[dict[str, Any]] | None,
) -> None:
    """Save the latest replayable AG-UI Thread Snapshot when persistence is configured."""
    if config.snapshot_store is None or scope is None:
        return

    try:
        await config.snapshot_store.save(
            scope=scope,
            thread_id=thread_id,
            snapshot=AGUIThreadSnapshot(messages=messages, state=state, interrupt=interrupt),
        )
    except Exception:
        # The run itself already streamed successfully; a transient store failure
        # must not surface as RUN_ERROR for a completed run. The previous snapshot
        # stays available for hydration.
        logger.exception(
            "Failed to save AG-UI Thread Snapshot for scope=%s thread_id=%s; keeping previous snapshot.",
            scope,
            thread_id,
        )


async def run_agent_stream(
    input_data: dict[str, Any],
    agent: SupportsAgentRun,
    config: AgentConfig,
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] | None = None,
) -> AsyncGenerator[BaseEvent]:
    """Run agent and yield AG-UI events.

    This is the single entry point for all AG-UI agent runs. It follows a simple
    linear flow: RunStarted -> content events -> RunFinished.

    Args:
        input_data: AG-UI request data with messages, state, tools, etc.
        agent: The Agent Framework agent to run
        config: Agent configuration
        pending_approvals: Optional server-side registry of pending approval
            requests.  Keys are ``(thread_id, request_id)``, values are
            function names.  When provided, approval responses are validated
            against this registry to prevent bypass, spoofing, and replay.

    Yields:
        AG-UI events
    """
    # Parse IDs
    thread_id = input_data.get("thread_id") or input_data.get("threadId") or str(uuid.uuid4())
    run_id = input_data.get("run_id") or input_data.get("runId") or str(uuid.uuid4())
    snapshot_scope = cast(str | None, input_data.get(_SNAPSHOT_SCOPE_INPUT_KEY))
    approval_scope = cast(str | None, input_data.get(_APPROVAL_SCOPE_INPUT_KEY))
    approval_thread_id = approval_state_thread_id(scope=approval_scope, thread_id=thread_id)

    state_schema = cast(dict[str, Any], getattr(config, "state_schema", {}) or {})
    predict_state_config = cast(dict[str, dict[str, str]], getattr(config, "predict_state_config", {}) or {})

    # Normalize messages
    available_interrupts = input_data.get("available_interrupts") or input_data.get("availableInterrupts")
    raw_messages: list[dict[str, Any]] = input_data.get("messages", []) or []
    resume_payload = _extract_resume_payload(input_data)
    if config.snapshot_store is not None and snapshot_scope is not None and not raw_messages and resume_payload is None:
        async for event in _hydrate_thread_snapshot(
            config=config,
            scope=snapshot_scope,
            thread_id=thread_id,
            run_id=run_id,
        ):
            yield event
        return

    stored_snapshot: AGUIThreadSnapshot | None = None
    stored_pending_approval_interrupt_ids: set[str] = set()
    seeded_resume_from_snapshot = False
    if config.snapshot_store is not None and snapshot_scope is not None:
        stored_snapshot = await config.snapshot_store.get(scope=snapshot_scope, thread_id=thread_id)
        if stored_snapshot is not None:
            stored_pending_approval_interrupt_ids = _stored_pending_approval_interrupt_ids(stored_snapshot.interrupt)
        if stored_snapshot is not None and resume_payload is not None and stored_pending_approval_interrupt_ids:
            raw_messages = [copy.deepcopy(message) for message in stored_snapshot.messages] + raw_messages
            seeded_resume_from_snapshot = True
        elif stored_snapshot is not None:
            raw_messages = _reconstruct_messages_from_thread_snapshot(
                stored_messages=stored_snapshot.messages,
                incoming_messages=raw_messages,
                stored_interrupt=stored_snapshot.interrupt,
            )

    # Initialize flow state with stored state plus request-provided overrides.
    flow = FlowState()
    request_state = input_data.get("state")
    if stored_snapshot is not None and stored_snapshot.state is not None:
        flow.current_state = dict(stored_snapshot.state)
        if isinstance(request_state, dict):
            flow.current_state.update(request_state)
    elif isinstance(request_state, dict):
        flow.current_state = dict(request_state)

    # Apply endpoint-deferred defaults only for keys missing from both the stored
    # snapshot state and the request state, so defaults never reset persisted state.
    deferred_default_state = cast(dict[str, Any] | None, input_data.get(_DEFAULT_STATE_INPUT_KEY))
    if deferred_default_state:
        for key, value in deferred_default_state.items():
            if key not in flow.current_state:
                flow.current_state[key] = copy.deepcopy(value)

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

    approval_resume_messages, handled_resume_ids, cancelled_resume_ids, resume_error = (
        _canonical_approval_resume_messages(
            resume_payload,
            pending_approvals,
            approval_thread_id,
            expected_interrupt_ids=stored_pending_approval_interrupt_ids or None,
        )
    )
    if resume_error is not None:
        yield RunStartedEvent(run_id=run_id, thread_id=thread_id)
        if (
            getattr(resume_error, "code", None) == "APPROVAL_RESUME_CANCELLED"
            and config.snapshot_store is not None
            and snapshot_scope is not None
        ):
            await _clear_thread_snapshot_interrupt(
                snapshot_store=config.snapshot_store,
                scope=snapshot_scope,
                thread_id=thread_id,
                interrupt_ids=cancelled_resume_ids or None,
            )
        yield resume_error
        return
    resume_messages = _resume_to_tool_messages(resume_payload, exclude_interrupt_ids=handled_resume_ids)
    if available_interrupts:
        logger.debug("Received available interrupts metadata: %s", available_interrupts)
    if approval_resume_messages:
        logger.info(f"Appending {len(approval_resume_messages)} synthesized approval resume message(s).")
        raw_messages.extend(approval_resume_messages)
    if resume_messages:
        logger.info(f"Appending {len(resume_messages)} synthesized resume message(s) to AG-UI input.")
        raw_messages.extend(resume_messages)
    messages, snapshot_messages = normalize_agui_input_messages(raw_messages)

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

    # Prepare tools
    client_tools = convert_agui_tools_to_agent_framework(input_data.get("tools"))
    server_tools = collect_server_tools(agent)
    register_additional_client_tools(agent, client_tools)
    tools = merge_tools(server_tools, client_tools)

    # Create session (with service session support)
    if config.use_service_session:
        supplied_thread_id = input_data.get("thread_id") or input_data.get("threadId")
        session = AgentSession(session_id=thread_id, service_session_id=supplied_thread_id)
    else:
        session = AgentSession(session_id=thread_id)

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
    # Filter out AG-UI internal metadata keys before passing to chat client
    # These are used internally for orchestration and should not be sent to the LLM provider
    session_metadata = cast(dict[str, Any], getattr(session, "metadata", None) or {})
    client_metadata: dict[str, Any] = {
        k: v for k, v in session_metadata.items() if k not in AG_UI_INTERNAL_METADATA_KEYS
    }
    safe_metadata = _build_safe_metadata(client_metadata) if client_metadata else {}
    if safe_metadata:
        run_kwargs["options"] = {"metadata": safe_metadata, "store": True}

    # Resolve approval responses (execute approved tools, replace approvals with results)
    # This must happen before running the agent so it sees the tool results
    tools_for_execution = tools if tools is not None else server_tools
    resolved_approval_results = await _resolve_approval_responses(
        messages, tools_for_execution, agent, run_kwargs, pending_approvals, approval_thread_id
    )

    # Defense-in-depth: replace approval payloads in snapshot with actual tool results
    # so CopilotKit does not re-send stale approval content on subsequent turns.
    _clean_resolved_approvals_from_snapshot(snapshot_messages, messages)

    # Feature #3: Emit StateSnapshotEvent for approved state-changing tools before agent runs
    approved_state_updates = _extract_approved_state_updates(messages, predictive_handler)
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
        if resume_payload is not None and stored_snapshot is not None and not seeded_resume_from_snapshot:
            # Generic resume requests carry only the synthesized response, so prepend
            # stored history unless this run already seeded raw messages from it.
            persisted_messages = [copy.deepcopy(message) for message in stored_snapshot.messages] + persisted_messages
        await _save_thread_snapshot(
            config=config,
            scope=snapshot_scope,
            thread_id=thread_id,
            messages=persisted_messages,
            state=cast(dict[str, Any], make_json_safe(flow.current_state)) if flow.current_state else None,
            interrupt=None,
        )
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    # Inject state context message so the model knows current application state
    # This is critical for shared state scenarios where the UI state needs to be visible
    if state_schema and flow.current_state:
        messages = _inject_state_context(messages, flow.current_state, state_schema)

    # Stream from agent - emit RunStarted after first update to get service IDs
    run_started_emitted = False
    all_updates: list[Any] = []  # Collect for structured output processing
    latest_state_snapshot: dict[str, Any] | None = (
        cast(dict[str, Any], make_json_safe(flow.current_state)) if flow.current_state else None
    )
    response_stream = agent.run(messages, stream=True, **run_kwargs)
    stream = await _normalize_response_stream(response_stream)
    async for update in stream:
        # Collect updates for structured output processing
        if response_format is not None:
            all_updates.append(update)

        # Update IDs from service response on first update and emit RunStarted
        if not run_started_emitted:
            conv_id = get_conversation_id_from_update(update)
            if conv_id:
                thread_id = conv_id
            if update.response_id:
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

            # Register pending approval requests so we can validate responses later
            if content_type == "function_approval_request" and pending_approvals is not None:
                if content.id and content.function_call and content.function_call.name:
                    canonical_interrupt_id = content.function_call.call_id or content.id
                    pending_entry = _make_pending_approval_entry(
                        content.function_call.name,
                        canonical_function_arguments(content.function_call),
                        request_id=str(content.id),
                        interrupt_id=str(canonical_interrupt_id),
                        already_approved_requests=_stored_already_approved_requests_for_visible_approval(
                            session,
                            str(content.id),
                            str(canonical_interrupt_id) if canonical_interrupt_id else None,
                        ),
                    )
                    _register_pending_approval_entry(
                        pending_approvals,
                        approval_thread_id,
                        pending_entry,
                        str(content.id),
                        str(canonical_interrupt_id) if canonical_interrupt_id else None,
                    )
                    # Evict oldest entries if the registry exceeds a safe bound (LRU)
                    _evict_oldest_approvals(pending_approvals, max_size=10_000)
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
                        yield ToolCallStartEvent(
                            tool_call_id=confirm_id,
                            tool_call_name="confirm_changes",
                            parent_message_id=flow.message_id,
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
        if not _should_suppress_intermediate_snapshot(
            last_tool_name, predict_state_config, config.require_confirmation
        ):
            yield snapshot_event

    # Always emit RunFinished - confirm_changes tool call is complete (Start -> Args -> End)
    # The UI will show confirmation dialog and send a new request when user responds
    persisted_messages = latest_messages_snapshot
    if resume_payload is not None and stored_snapshot is not None and not seeded_resume_from_snapshot:
        # Generic resume requests carry only the synthesized response, so prepend
        # stored history unless this run already seeded raw messages from it.
        persisted_messages = [copy.deepcopy(message) for message in stored_snapshot.messages] + persisted_messages
    await _save_thread_snapshot(
        config=config,
        scope=snapshot_scope,
        thread_id=thread_id,
        messages=persisted_messages,
        state=latest_state_snapshot,
        interrupt=flow.interrupts or None,
    )
    yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=flow.interrupts)
