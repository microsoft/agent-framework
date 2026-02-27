# Copyright (c) Microsoft. All rights reserved.

"""Simplified AG-UI orchestration - single linear flow."""

from __future__ import annotations  # noqa: I001

import json
import logging
import uuid
from collections.abc import AsyncIterable, Awaitable
from typing import TYPE_CHECKING, Any, cast

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    MessagesSnapshotEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
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
    _collect_approval_responses,  # type: ignore
    _replace_approval_contents_with_results,  # type: ignore
    _try_execute_function_calls,  # type: ignore
    normalize_function_invocation_configuration,
)
from agent_framework._types import ResponseStream
from agent_framework.exceptions import AgentInvalidResponseException

from ._message_adapters import normalize_agui_input_messages
from ._orchestration._predictive_state import PredictiveStateHandler
from ._orchestration._tooling import collect_server_tools, merge_tools, register_additional_client_tools
from ._run_common import (
    FlowState,
    _build_run_finished_event,  # type: ignore
    _emit_content,  # type: ignore
    _extract_resume_payload,  # type: ignore
    _has_only_tool_calls,  # type: ignore
    _normalize_resume_interrupts,  # type: ignore
)
from ._utils import (
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
AG_UI_INTERNAL_METADATA_KEYS = {"ag_ui_thread_id", "ag_ui_run_id", "current_state"}


def _build_safe_metadata(thread_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Build metadata dict with truncated string values for Azure compatibility.

    Azure has a 512 character limit per metadata value.

    Args:
        thread_metadata: Raw metadata dict

    Returns:
        Metadata with string values truncated to 512 chars
    """
    if not thread_metadata:
        return {}
    safe_metadata: dict[str, Any] = {}
    for key, value in thread_metadata.items():
        value_str = value if isinstance(value, str) else json.dumps(value)
        if len(value_str) > 512:
            value_str = value_str[:512]
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


def _resume_to_tool_messages(resume_payload: Any) -> list[dict[str, Any]]:
    """Convert a resume payload into AG-UI tool messages for approval continuation."""
    result: list[dict[str, Any]] = []
    for interrupt in _normalize_resume_interrupts(resume_payload):
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


async def _resolve_approval_responses(
    messages: list[Any],
    tools: list[Any],
    agent: SupportsAgentRun,
    run_kwargs: dict[str, Any],
) -> None:
    """Execute approved function calls and replace approval content with results.

    This modifies the messages list in place, replacing function_approval_response
    content with function_result content containing the actual tool execution result.

    Args:
        messages: List of messages (will be modified in place)
        tools: List of available tools
        agent: The agent instance (to get client and config)
        run_kwargs: Kwargs for tool execution
    """
    fcc_todo = _collect_approval_responses(messages)
    if not fcc_todo:
        return

    approved_responses = [resp for resp in fcc_todo.values() if resp.approved]
    rejected_responses = [resp for resp in fcc_todo.values() if not resp.approved]
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

    # Build normalized results for approved responses
    normalized_results: list[Content] = []
    for idx, approval in enumerate(approved_responses):
        if (
            idx < len(approved_function_results)
            and getattr(approved_function_results[idx], "type", None) == "function_result"
        ):
            normalized_results.append(approved_function_results[idx])
            continue
        # Get call_id from function_call if present, otherwise use approval.id
        func_call = approval.function_call
        call_id = (func_call.call_id if func_call else None) or approval.id or ""
        normalized_results.append(
            Content.from_function_result(call_id=call_id, result="Error: Tool call invocation failed.")
        )

    # Build rejection results
    for rejection in rejected_responses:
        func_call = rejection.function_call
        call_id = (func_call.call_id if func_call else None) or rejection.id or ""
        normalized_results.append(
            Content.from_function_result(call_id=call_id, result="Error: Tool call invocation was rejected by user.")
        )

    _replace_approval_contents_with_results(messages, fcc_todo, normalized_results)  # type: ignore

    # Post-process: Convert user messages with function_result content to proper tool messages.
    # After _replace_approval_contents_with_results, approved tool calls have their results
    # placed in user messages. OpenAI requires tool results to be in role="tool" messages.
    # This transformation ensures the message history is valid for the LLM provider.
    _convert_approval_results_to_tool_messages(messages)


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

    return MessagesSnapshotEvent(messages=all_messages)  # type: ignore[arg-type]


async def run_agent_stream(
    input_data: dict[str, Any],
    agent: SupportsAgentRun,
    config: AgentConfig,
) -> AsyncGenerator[BaseEvent]:
    """Run agent and yield AG-UI events.

    This is the single entry point for all AG-UI agent runs. It follows a simple
    linear flow: RunStarted -> content events -> RunFinished.

    Args:
        input_data: AG-UI request data with messages, state, tools, etc.
        agent: The Agent Framework agent to run
        config: Agent configuration

    Yields:
        AG-UI events
    """
    # Parse IDs
    thread_id = input_data.get("thread_id") or input_data.get("threadId") or str(uuid.uuid4())
    run_id = input_data.get("run_id") or input_data.get("runId") or str(uuid.uuid4())

    # Initialize flow state with schema defaults
    flow = FlowState()
    if input_data.get("state"):
        flow.current_state = dict(input_data["state"])

    state_schema = cast(dict[str, Any], getattr(config, "state_schema", {}) or {})
    predict_state_config = cast(dict[str, dict[str, str]], getattr(config, "predict_state_config", {}) or {})

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

    # Normalize messages
    available_interrupts = input_data.get("available_interrupts") or input_data.get("availableInterrupts")
    raw_messages = list(cast(list[dict[str, Any]], input_data.get("messages", []) or []))
    resume_messages = _resume_to_tool_messages(_extract_resume_payload(input_data))
    if available_interrupts:
        logger.debug("Received available interrupts metadata: %s", available_interrupts)
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
        session = AgentSession(service_session_id=supplied_thread_id)
    else:
        session = AgentSession()

    # Inject metadata for AG-UI orchestration (Feature #2: Azure-safe truncation)
    base_metadata: dict[str, Any] = {
        "ag_ui_thread_id": thread_id,
        "ag_ui_run_id": run_id,
    }
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
    await _resolve_approval_responses(messages, tools_for_execution, agent, run_kwargs)

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
        for event in _handle_step_based_approval(messages):
            yield event
        yield _build_run_finished_event(run_id=run_id, thread_id=thread_id)
        return

    # Inject state context message so the model knows current application state
    # This is critical for shared state scenarios where the UI state needs to be visible
    if state_schema and flow.current_state:
        messages = _inject_state_context(messages, flow.current_state, state_schema)

    # Stream from agent - emit RunStarted after first update to get service IDs
    run_started_emitted = False
    all_updates: list[Any] = []  # Collect for structured output processing
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
                yield StateSnapshotEvent(snapshot=flow.current_state)
            run_started_emitted = True

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
            for event in _emit_content(
                content,
                flow,
                predictive_handler,
                skip_text,
                config.require_confirmation,
            ):
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

    # Process structured output if response_format is set
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
                        flow.interrupts = [
                            {
                                "id": str(confirm_id),
                                "value": {
                                    "type": "function_approval_request",
                                    "function_call": {
                                        "call_id": tool_call_id,
                                        "name": tool_name,
                                        "arguments": function_arguments,
                                    },
                                },
                            }
                        ]

    # Close any open message
    if flow.message_id:
        logger.debug(f"End of run: closing text message message_id={flow.message_id}")
        yield TextMessageEndEvent(message_id=flow.message_id)

    # Emit MessagesSnapshotEvent if we have tool calls or results
    # Feature #5: Suppress intermediate snapshots for predictive tools without confirmation
    should_emit_snapshot = flow.pending_tool_calls or flow.tool_results or flow.accumulated_text
    if should_emit_snapshot:
        # Check if we should suppress for predictive tool
        last_tool_name = None
        if flow.tool_results:
            last_result = flow.tool_results[-1]
            last_call_id = last_result.get("toolCallId")
            last_tool_name = flow.get_tool_name(last_call_id)
        if not _should_suppress_intermediate_snapshot(
            last_tool_name, predict_state_config, config.require_confirmation
        ):
            yield _build_messages_snapshot(flow, snapshot_messages)

    # Always emit RunFinished - confirm_changes tool call is complete (Start -> Args -> End)
    # The UI will show confirmation dialog and send a new request when user responds
    yield _build_run_finished_event(run_id=run_id, thread_id=thread_id, interrupts=flow.interrupts)
