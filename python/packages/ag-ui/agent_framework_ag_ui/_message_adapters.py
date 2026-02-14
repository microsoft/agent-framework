# Copyright (c) Microsoft. All rights reserved.

"""Message format conversion between AG-UI and Agent Framework."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from typing import Any, cast

from agent_framework import (
    Content,
    Message,
)

from ._utils import (
    AGUI_TO_FRAMEWORK_ROLE,
    FRAMEWORK_TO_AGUI_ROLE,
    get_role_value,
    normalize_agui_role,
    safe_json_parse,
)

logger = logging.getLogger(__name__)


def _sanitize_tool_history(messages: list[Message]) -> list[Message]:
    """Normalize tool ordering and inject synthetic results for AG-UI edge cases."""
    sanitized: list[Message] = []
    pending_tool_call_ids: set[str] | None = None
    pending_confirm_changes_id: str | None = None

    for msg in messages:
        role_value = get_role_value(msg)

        if role_value == "assistant":
            tool_ids = {
                str(content.call_id)
                for content in msg.contents or []
                if content.type == "function_call" and content.call_id
            }
            confirm_changes_call = None
            for content in msg.contents or []:
                if content.type == "function_call" and content.name == "confirm_changes":
                    confirm_changes_call = content
                    break

            # Filter out confirm_changes from assistant messages before sending to LLM.
            # confirm_changes is a synthetic tool for the approval UI flow - the LLM shouldn't
            # see it because it may contain stale function_arguments that confuse the model
            # (e.g., showing 5 steps when only 2 were approved).
            # When we filter out confirm_changes, we also remove it from tool_ids and don't
            # set pending_confirm_changes_id, so no synthetic result is injected for it.
            # This is required because OpenAI validates that every tool result has a matching
            # tool call in the previous assistant message.
            if confirm_changes_call:
                filtered_contents = [
                    c for c in (msg.contents or []) if not (c.type == "function_call" and c.name == "confirm_changes")
                ]
                if filtered_contents:
                    # Create a new message without confirm_changes to avoid mutating the input
                    filtered_msg = Message(role=msg.role, contents=filtered_contents)
                    sanitized.append(filtered_msg)
                # If no contents left after filtering, don't append anything

                # Remove confirm_changes from tool_ids since we filtered it from the message
                if confirm_changes_call.call_id:
                    tool_ids.discard(str(confirm_changes_call.call_id))
                # Don't set pending_confirm_changes_id - we don't want a synthetic result
                confirm_changes_call = None
            else:
                sanitized.append(msg)

            pending_tool_call_ids = tool_ids if tool_ids else None
            pending_confirm_changes_id = (
                str(confirm_changes_call.call_id) if confirm_changes_call and confirm_changes_call.call_id else None
            )
            continue

        if role_value == "user":
            approval_call_ids: set[str] = set()
            approval_accepted: bool | None = None
            for content in msg.contents or []:
                if content.type == "function_approval_response":
                    if content.function_call and content.function_call.call_id:
                        approval_call_ids.add(str(content.function_call.call_id))
                    if approval_accepted is None:
                        approval_accepted = bool(content.approved)
                    else:
                        approval_accepted = approval_accepted and bool(content.approved)

            if approval_call_ids and pending_tool_call_ids:
                pending_tool_call_ids -= approval_call_ids
                logger.info(
                    f"function_approval_response content found for call_ids={sorted(approval_call_ids)} - "
                    "framework will handle execution"
                )

            if pending_confirm_changes_id and approval_accepted is not None:
                logger.info(f"Injecting synthetic tool result for confirm_changes call_id={pending_confirm_changes_id}")
                synthetic_result = Message(
                    role="tool",
                    contents=[
                        Content.from_function_result(
                            call_id=pending_confirm_changes_id,
                            result="Confirmed" if approval_accepted else "Rejected",
                        )
                    ],
                )
                sanitized.append(synthetic_result)
                if pending_tool_call_ids:
                    pending_tool_call_ids.discard(pending_confirm_changes_id)
                pending_confirm_changes_id = None

            if pending_confirm_changes_id:
                user_text = ""
                for content in msg.contents or []:
                    if content.type == "text":
                        user_text = content.text  # type: ignore[assignment]
                        break

                if not user_text:
                    continue
                try:
                    parsed = json.loads(user_text)  # type: ignore[arg-type]
                    if "accepted" in parsed:
                        logger.info(
                            f"Injecting synthetic tool result for confirm_changes call_id={pending_confirm_changes_id}"
                        )
                        synthetic_result = Message(
                            role="tool",
                            contents=[
                                Content.from_function_result(
                                    call_id=pending_confirm_changes_id,
                                    result="Confirmed" if parsed.get("accepted") else "Rejected",
                                )
                            ],
                        )
                        sanitized.append(synthetic_result)
                        if pending_tool_call_ids:
                            pending_tool_call_ids.discard(pending_confirm_changes_id)
                        pending_confirm_changes_id = None
                        continue
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.debug(f"Could not parse user message as confirm_changes response: {type(exc).__name__}")

            if pending_tool_call_ids:
                logger.info(
                    f"User message arrived with {len(pending_tool_call_ids)} pending tool calls - "
                    "injecting synthetic results"
                )
                for pending_call_id in pending_tool_call_ids:
                    logger.info(f"Injecting synthetic tool result for pending call_id={pending_call_id}")
                    synthetic_result = Message(
                        role="tool",
                        contents=[
                            Content.from_function_result(
                                call_id=pending_call_id,
                                result="Tool execution skipped - user provided follow-up message",
                            )
                        ],
                    )
                    sanitized.append(synthetic_result)
                pending_tool_call_ids = None
                pending_confirm_changes_id = None

            sanitized.append(msg)
            pending_confirm_changes_id = None
            continue

        if role_value == "tool":
            if not pending_tool_call_ids:
                continue
            keep = False
            for content in msg.contents or []:
                if content.type == "function_result" and content.call_id:
                    call_id = str(content.call_id)
                    if call_id in pending_tool_call_ids:
                        keep = True
                        # Remove the call_id from pending since we now have its result.
                        # This prevents duplicate synthetic "skipped" results from being
                        # injected when a user message arrives later.
                        pending_tool_call_ids.discard(call_id)
                        if call_id == pending_confirm_changes_id:
                            pending_confirm_changes_id = None
                        break
            if keep:
                sanitized.append(msg)
            continue

        sanitized.append(msg)
        pending_tool_call_ids = None
        pending_confirm_changes_id = None

    return sanitized


def _deduplicate_messages(messages: list[Message]) -> list[Message]:
    """Remove duplicate messages while preserving order."""
    seen_keys: dict[Any, int] = {}
    unique_messages: list[Message] = []

    for idx, msg in enumerate(messages):
        role_value = get_role_value(msg)

        if role_value == "tool" and msg.contents and msg.contents[0].type == "function_result":
            call_id = str(msg.contents[0].call_id)
            key: Any = (role_value, call_id)

            if key in seen_keys:
                existing_idx = seen_keys[key]
                existing_msg = unique_messages[existing_idx]

                existing_result = None
                if existing_msg.contents and existing_msg.contents[0].type == "function_result":
                    existing_result = existing_msg.contents[0].result
                new_result = msg.contents[0].result

                if (not existing_result or existing_result == "") and new_result:
                    logger.info(f"Replacing empty tool result at index {existing_idx} with data from index {idx}")
                    unique_messages[existing_idx] = msg
                else:
                    logger.info(f"Skipping duplicate tool result at index {idx}: call_id={call_id}")
                continue

            seen_keys[key] = len(unique_messages)
            unique_messages.append(msg)

        elif role_value == "assistant" and msg.contents and any(c.type == "function_call" for c in msg.contents):
            tool_call_ids = tuple(
                sorted(str(c.call_id) for c in msg.contents if c.type == "function_call" and c.call_id)
            )
            key = (role_value, tool_call_ids)

            if key in seen_keys:
                logger.info(f"Skipping duplicate assistant tool call at index {idx}")
                continue

            seen_keys[key] = len(unique_messages)
            unique_messages.append(msg)

        else:
            content_str = str([str(c) for c in msg.contents]) if msg.contents else ""
            key = (role_value, hash(content_str))

            if key in seen_keys:
                logger.info(f"Skipping duplicate message at index {idx}: role={role_value}")
                continue

            seen_keys[key] = len(unique_messages)
            unique_messages.append(msg)

    return unique_messages


def _parse_multimodal_media_part(part: dict[str, Any]) -> Content | None:
    """Convert a multimodal media part into Agent Framework content."""
    part_type = str(part.get("type", "")).lower()
    source = part.get("source")

    mime_type = cast(
        str | None,
        part.get("mimeType")
        or part.get("mime_type")
        or {
            "image": "image/*",
            "audio": "audio/*",
            "video": "video/*",
            "document": "application/octet-stream",
            "binary": "application/octet-stream",
        }.get(part_type, "application/octet-stream"),
    )
    url = cast(str | None, part.get("url") or part.get("uri"))
    data = cast(str | None, part.get("data"))
    binary_id = cast(str | None, part.get("id"))

    if isinstance(source, dict):
        source_dict = cast(dict[str, Any], source)
        source_type = str(source_dict.get("type", "")).lower()
        source_mime = source_dict.get("mimeType") or source_dict.get("mime_type")
        if isinstance(source_mime, str) and source_mime:
            mime_type = source_mime

        if source_type in {"url", "uri"}:
            url = cast(str | None, source_dict.get("url") or source_dict.get("uri"))
        elif source_type in {"base64", "data", "binary"}:
            data = cast(str | None, source_dict.get("data"))
        elif source_type in {"id", "file"}:
            binary_id = cast(str | None, source_dict.get("id"))
        else:
            url = cast(str | None, source_dict.get("url") or source_dict.get("uri") or url)
            data = cast(str | None, source_dict.get("data") or data)
            binary_id = cast(str | None, source_dict.get("id") or binary_id)

    if isinstance(url, str) and url:
        return Content.from_uri(uri=url, media_type=mime_type)

    if isinstance(data, str) and data:
        if data.startswith("data:"):
            return Content.from_uri(uri=data, media_type=mime_type)
        try:
            decoded = base64.b64decode(data, validate=True)
            return Content.from_data(data=decoded, media_type=mime_type or "application/octet-stream")
        except (binascii.Error, ValueError):
            logger.debug("Strict base64 decode failed for AG-UI media payload (mime_type=%s).", mime_type)
            try:
                decoded = base64.b64decode(data)
                return Content.from_data(data=decoded, media_type=mime_type or "application/octet-stream")
            except (binascii.Error, ValueError):
                logger.warning(
                    "Failed to decode AG-UI media payload as base64; falling back to data URI (mime_type=%s).",
                    mime_type,
                    exc_info=True,
                )
                # Best effort fallback for malformed payloads.
                return Content.from_uri(
                    uri=f"data:{mime_type or 'application/octet-stream'};base64,{data}",
                    media_type=mime_type,
                )

    if isinstance(binary_id, str) and binary_id:
        return Content.from_uri(uri=f"ag-ui://binary/{binary_id}", media_type=mime_type)

    return None


def _convert_agui_content_to_framework(content: Any) -> list[Content]:
    """Convert AG-UI content payloads to Agent Framework Content entries."""
    if isinstance(content, str):
        return [Content.from_text(text=content)]

    if isinstance(content, list):
        converted: list[Content] = []
        for item in content:
            if isinstance(item, str):
                converted.append(Content.from_text(text=item))
                continue
            if not isinstance(item, dict):
                converted.append(Content.from_text(text=str(item)))
                continue

            part = cast(dict[str, Any], item)
            part_type = str(part.get("type", "")).lower()

            if part_type in {"text", "input_text"}:
                converted.append(Content.from_text(text=str(part.get("text", ""))))
                continue

            if part_type in {"binary", "image", "audio", "video", "document"}:
                media_content = _parse_multimodal_media_part(part)
                if media_content is not None:
                    converted.append(media_content)
                continue

            text_value = part.get("text")
            if isinstance(text_value, str):
                converted.append(Content.from_text(text=text_value))
            else:
                converted.append(Content.from_text(text=str(part)))

        return converted

    if content is None:
        return []

    return [Content.from_text(text=str(content))]


def _normalize_snapshot_content(content: Any) -> Any:
    """Normalize AG-UI message content for snapshot payloads.

    Preserve multimodal fidelity whenever non-text parts are present.
    """
    if isinstance(content, list):
        has_non_text_parts = False
        normalized_parts: list[dict[str, Any]] = []
        text_parts: list[str] = []

        def _legacy_binary_part(part: dict[str, Any]) -> dict[str, Any]:
            """Convert draft/legacy multimodal parts to AG-UI snapshot binary shape."""
            normalized: dict[str, Any] = {"type": "binary"}

            mime_type = cast(str | None, part.get("mimeType") or part.get("mime_type"))
            url = cast(str | None, part.get("url") or part.get("uri"))
            data = cast(str | None, part.get("data"))
            binary_id = cast(str | None, part.get("id"))

            source = part.get("source")
            if isinstance(source, dict):
                source_part = cast(dict[str, Any], source)
                source_mime = source_part.get("mimeType") or source_part.get("mime_type")
                if isinstance(source_mime, str) and source_mime:
                    mime_type = source_mime

                source_type = str(source_part.get("type", "")).lower()
                if source_type in {"url", "uri"}:
                    url = cast(str | None, source_part.get("url") or source_part.get("uri"))
                elif source_type in {"base64", "data", "binary"}:
                    data = cast(str | None, source_part.get("data"))
                elif source_type in {"id", "file"}:
                    binary_id = cast(str | None, source_part.get("id"))
                else:
                    url = cast(str | None, source_part.get("url") or source_part.get("uri") or url)
                    data = cast(str | None, source_part.get("data") or data)
                    binary_id = cast(str | None, source_part.get("id") or binary_id)

            if isinstance(mime_type, str) and mime_type:
                normalized["mimeType"] = mime_type
            if isinstance(url, str) and url:
                normalized["url"] = url
            if isinstance(data, str) and data:
                normalized["data"] = data
            if isinstance(binary_id, str) and binary_id:
                normalized["id"] = binary_id

            return normalized

        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                normalized_parts.append({"type": "text", "text": item})
                continue
            if not isinstance(item, dict):
                item_text = str(item)
                text_parts.append(item_text)
                normalized_parts.append({"type": "text", "text": item_text})
                continue

            part = cast(dict[str, Any], item).copy()
            part_type = str(part.get("type", "")).lower()

            if part_type == "input_text":
                part["type"] = "text"
                part_type = "text"
            elif part_type == "input_image":
                part["type"] = "binary"
                part_type = "binary"

            if part_type == "text":
                text_parts.append(str(part.get("text", "")))
            else:
                has_non_text_parts = True
                if part_type in {"binary", "image", "audio", "video", "document"}:
                    normalized_parts.append(_legacy_binary_part(part))
                    continue

            if "mime_type" in part and "mimeType" not in part:
                part["mimeType"] = part.get("mime_type")

            source = part.get("source")
            if isinstance(source, dict):
                source_part = cast(dict[str, Any], source)
                if "mime_type" in source_part and "mimeType" not in source_part:
                    source_part["mimeType"] = source_part.get("mime_type")

            normalized_parts.append(part)

        if has_non_text_parts:
            return normalized_parts

        return "".join(text_parts)

    if content is None:
        return ""

    return content


def normalize_agui_input_messages(
    messages: list[dict[str, Any]],
    *,
    sanitize_tool_history: bool = True,
) -> tuple[list[Message], list[dict[str, Any]]]:
    """Normalize raw AG-UI messages into provider and snapshot formats.

    Args:
        messages: Raw AG-UI messages.
        sanitize_tool_history: Apply agent-run specific tool history repair logic.
            Keep enabled for standard agent runs; disable for native workflow runs
            where pending-request responses must come explicitly from interrupt resume.
    """
    provider_messages = agui_messages_to_agent_framework(messages)
    if sanitize_tool_history:
        provider_messages = _sanitize_tool_history(provider_messages)
    provider_messages = _deduplicate_messages(provider_messages)
    snapshot_messages = agui_messages_to_snapshot_format(messages)
    return provider_messages, snapshot_messages


def agui_messages_to_agent_framework(messages: list[dict[str, Any]]) -> list[Message]:
    """Convert AG-UI messages to Agent Framework format.

    Args:
        messages: List of AG-UI messages

    Returns:
        List of Agent Framework Message objects
    """

    def _update_tool_call_arguments(
        raw_messages: list[dict[str, Any]],
        tool_call_id: str,
        modified_args: dict[str, Any],
    ) -> None:
        for raw_msg in raw_messages:
            tool_calls = raw_msg.get("tool_calls") or raw_msg.get("toolCalls")
            if not isinstance(tool_calls, list):
                continue
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                if str(tool_call.get("id", "")) != tool_call_id:
                    continue
                function_payload = tool_call.get("function")
                if not isinstance(function_payload, dict):
                    return
                existing_args = function_payload.get("arguments")
                if isinstance(existing_args, str):
                    function_payload["arguments"] = json.dumps(modified_args)
                else:
                    function_payload["arguments"] = modified_args
                return

    def _find_matching_func_call(call_id: str) -> Content | None:
        for prev_msg in result:
            role_val = prev_msg.role if hasattr(prev_msg.role, "value") else str(prev_msg.role)
            if role_val != "assistant":
                continue
            for content in prev_msg.contents or []:
                if content.type == "function_call" and content.call_id == call_id and content.name != "confirm_changes":
                    return content
        return None

    def _parse_arguments(arguments: Any) -> dict[str, Any] | None:
        return safe_json_parse(arguments)

    def _resolve_approval_call_id(tool_call_id: str, parsed_payload: dict[str, Any] | None) -> str | None:
        if parsed_payload:
            explicit_call_id = parsed_payload.get("function_call_id")
            if explicit_call_id:
                return str(explicit_call_id)

        for prev_msg in result:
            role_val = prev_msg.role if hasattr(prev_msg.role, "value") else str(prev_msg.role)
            if role_val != "assistant":
                continue
            direct_call = None
            confirm_call = None
            sibling_calls: list[Content] = []
            for content in prev_msg.contents or []:
                if content.type != "function_call":
                    continue
                if content.call_id == tool_call_id:
                    direct_call = content
                if content.name == "confirm_changes" and content.call_id == tool_call_id:
                    confirm_call = content
                elif content.name != "confirm_changes":
                    sibling_calls.append(content)

            if direct_call:
                direct_args = direct_call.parse_arguments() or {}
                if isinstance(direct_args, dict):
                    explicit_call_id = direct_args.get("function_call_id")
                    if explicit_call_id:
                        return str(explicit_call_id)

            if not confirm_call:
                continue

            confirm_args = confirm_call.parse_arguments() or {}
            if isinstance(confirm_args, dict):
                explicit_call_id = confirm_args.get("function_call_id")
                if explicit_call_id:
                    return str(explicit_call_id)

            if len(sibling_calls) == 1 and sibling_calls[0].call_id:
                return str(sibling_calls[0].call_id)

        return None

    def _filter_modified_args(
        modified_args: dict[str, Any],
        original_args: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not modified_args:
            return {}
        if not isinstance(original_args, dict) or not original_args:
            return {}
        allowed_keys = set(original_args.keys())
        return {key: value for key, value in modified_args.items() if key in allowed_keys}

    result: list[Message] = []
    for msg in messages:
        # Handle standard tool result messages early (role="tool") to preserve provider invariants
        # This path maps AG‑UI tool messages to function_result content with the correct tool_call_id
        role_str = normalize_agui_role(msg.get("role", "user"))
        if role_str == "tool":
            # Prefer explicit tool_call_id fields; fall back to backend fields only if necessary
            tool_call_id = msg.get("tool_call_id") or msg.get("toolCallId")

            # If no explicit tool_call_id, treat as backend tool rendering payloads where
            # AG‑UI may send actionExecutionId/actionName. This must still map to the
            # assistant's tool call id to satisfy provider requirements.
            if not tool_call_id:
                tool_call_id = msg.get("actionExecutionId") or ""

            # Extract raw content text
            result_content = msg.get("content")
            if result_content is None:
                result_content = msg.get("result", "")

            # Distinguish approval payloads from actual tool results
            parsed: dict[str, Any] | None = None
            if isinstance(result_content, str) and result_content:
                try:
                    parsed_candidate = json.loads(result_content)
                except Exception:
                    parsed_candidate = None
                if isinstance(parsed_candidate, dict):
                    parsed = cast(dict[str, Any], parsed_candidate)
            elif isinstance(result_content, dict):
                parsed = cast(dict[str, Any], result_content)

            is_approval = parsed is not None and "accepted" in parsed

            if is_approval:
                # Look for the matching function call in previous messages to create
                # proper function_approval_response content. This enables the agent framework
                # to execute the approved tool (fix for GitHub issue #3034).
                accepted = parsed.get("accepted", False) if parsed is not None else False
                approval_payload_text = result_content if isinstance(result_content, str) else json.dumps(parsed)

                # Log the full approval payload to debug modified arguments
                logger.info(f"Approval payload received: {parsed}")

                approval_call_id = tool_call_id
                resolved_call_id = _resolve_approval_call_id(tool_call_id, parsed)
                if resolved_call_id:
                    approval_call_id = resolved_call_id
                matching_func_call = _find_matching_func_call(approval_call_id)

                if matching_func_call:
                    # Remove any existing tool result for this call_id since the framework
                    # will re-execute the tool after approval. Keeping old results causes
                    # OpenAI API errors ("tool message must follow assistant with tool_calls").
                    result = [
                        m
                        for m in result
                        if not (
                            (m.role if hasattr(m.role, "value") else str(m.role)) == "tool"
                            and any(
                                c.type == "function_result" and c.call_id == approval_call_id
                                for c in (m.contents or [])
                            )
                        )
                    ]

                    # Check if the approval payload contains modified arguments
                    # The UI sends back the modified state (e.g., deselected steps) in the approval payload
                    modified_args = {k: v for k, v in parsed.items() if k != "accepted"} if parsed else {}
                    original_args = matching_func_call.parse_arguments()
                    filtered_args = _filter_modified_args(modified_args, original_args)
                    state_args: dict[str, Any] | None = None
                    if filtered_args:
                        original_args = original_args or {}
                        merged_args: dict[str, Any]
                        if isinstance(original_args, dict) and original_args:
                            merged_args = {**original_args, **filtered_args}
                        else:
                            merged_args = dict(filtered_args)

                        if isinstance(filtered_args.get("steps"), list):
                            original_steps = original_args.get("steps") if isinstance(original_args, dict) else None
                            if isinstance(original_steps, list):
                                approved_steps_list = list(filtered_args.get("steps") or [])
                                approved_by_description: dict[str, dict[str, Any]] = {}
                                for step_item in approved_steps_list:
                                    if isinstance(step_item, dict):
                                        step_item_dict = cast(dict[str, Any], step_item)
                                        desc = step_item_dict.get("description")
                                        if desc:
                                            approved_by_description[str(desc)] = step_item_dict
                                merged_steps: list[Any] = []
                                for orig_step in original_steps:
                                    if not isinstance(orig_step, dict):
                                        merged_steps.append(orig_step)
                                        continue
                                    orig_step_dict = cast(dict[str, Any], orig_step)
                                    description = str(orig_step_dict.get("description", ""))
                                    approved_step = approved_by_description.get(description)
                                    status: str = (
                                        str(approved_step.get("status"))
                                        if approved_step is not None and approved_step.get("status")
                                        else "disabled"
                                    )
                                    updated_step: dict[str, Any] = orig_step_dict.copy()
                                    updated_step["status"] = status
                                    merged_steps.append(updated_step)
                                merged_args["steps"] = merged_steps
                        state_args = merged_args

                        # Update the Message tool call with only enabled steps (for LLM context).
                        # The LLM should only see the steps that were actually approved/executed.
                        updated_args_for_llm = (
                            json.dumps(filtered_args)
                            if isinstance(matching_func_call.arguments, str)
                            else filtered_args
                        )
                        matching_func_call.arguments = updated_args_for_llm

                        # Update raw messages with all steps + status (for MESSAGES_SNAPSHOT display).
                        # This allows the UI to show which steps were enabled/disabled.
                        _update_tool_call_arguments(messages, str(approval_call_id), merged_args)
                        # Create a new FunctionCallContent with the modified arguments
                        func_call_for_approval = Content.from_function_call(
                            call_id=matching_func_call.call_id,  # type: ignore[arg-type]
                            name=matching_func_call.name,  # type: ignore[arg-type]
                            arguments=json.dumps(filtered_args),
                        )
                        logger.info(f"Using modified arguments from approval: {filtered_args}")
                    else:
                        # No modified arguments - use the original function call
                        func_call_for_approval = matching_func_call

                    # Create function_approval_response content for the agent framework
                    approval_response = Content.from_function_approval_response(
                        approved=accepted,
                        id=str(approval_call_id),
                        function_call=func_call_for_approval,
                        additional_properties={"ag_ui_state_args": state_args} if state_args else None,
                    )
                    chat_msg = Message(
                        role="user",
                        contents=[approval_response],
                    )
                else:
                    # No matching function call found - this is likely a confirm_changes approval
                    # Keep the old behavior for backwards compatibility
                    chat_msg = Message(
                        role="user",
                        contents=[Content.from_text(text=approval_payload_text)],
                        additional_properties={"is_tool_result": True, "tool_call_id": str(tool_call_id or "")},
                    )
                if "id" in msg:
                    chat_msg.message_id = msg["id"]
                result.append(chat_msg)
                continue

            # Cast result_content to acceptable type for function_result content
            func_result: str | dict[str, Any] | list[Any]
            if isinstance(result_content, str):
                func_result = result_content
            elif isinstance(result_content, dict):
                func_result = result_content
            elif isinstance(result_content, list):
                func_result = result_content
            else:
                func_result = str(result_content)
            chat_msg = Message(
                role="tool",
                contents=[Content.from_function_result(call_id=str(tool_call_id), result=func_result)],
            )
            if "id" in msg:
                chat_msg.message_id = msg["id"]
            result.append(chat_msg)
            continue

        # Backend tool rendering payloads without an explicit role
        # Prefer standard tool mapping above; this block only covers legacy/minimal payloads
        if "actionExecutionId" in msg or "actionName" in msg:
            # Prefer toolCallId if present; otherwise fall back to actionExecutionId
            tool_call_id = msg.get("toolCallId") or msg.get("tool_call_id") or msg.get("actionExecutionId", "")
            result_content = msg.get("result", msg.get("content", ""))

            chat_msg = Message(
                role="tool",
                contents=[Content.from_function_result(call_id=str(tool_call_id), result=result_content)],
            )
            if "id" in msg:
                chat_msg.message_id = msg["id"]
            result.append(chat_msg)
            continue

        # If assistant message includes tool calls, convert to Content.from_function_call(s)
        tool_calls = msg.get("tool_calls") or msg.get("toolCalls")
        if tool_calls:
            contents: list[Any] = []
            # Include any assistant content if present
            content_value = msg.get("content")
            if content_value not in (None, ""):
                contents.extend(_convert_agui_content_to_framework(content_value))
            # Convert each tool call entry
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                # Cast to typed dict for proper type inference
                tc_dict = cast(dict[str, Any], tc)
                tc_type = tc_dict.get("type")
                if tc_type == "function":
                    func_data = tc_dict.get("function", {})
                    func_dict = cast(dict[str, Any], func_data) if isinstance(func_data, dict) else {}

                    call_id = str(tc_dict.get("id", ""))
                    name = str(func_dict.get("name", ""))
                    arguments = func_dict.get("arguments")

                    contents.append(
                        Content.from_function_call(
                            call_id=call_id,
                            name=name,
                            arguments=arguments,
                        )
                    )
            chat_msg = Message(role="assistant", contents=contents)
            if "id" in msg:
                chat_msg.message_id = msg["id"]
            result.append(chat_msg)
            continue

        # No special handling required for assistant/plain messages here

        role = AGUI_TO_FRAMEWORK_ROLE.get(role_str, "user")

        # Check if this message contains function approvals
        if "function_approvals" in msg and msg["function_approvals"]:
            # Convert function approvals to function_approval_response content
            approval_contents: list[Any] = []
            for approval in msg["function_approvals"]:
                # Create FunctionCallContent with the modified arguments
                func_call = Content.from_function_call(
                    call_id=approval.get("call_id", ""),
                    name=approval.get("name", ""),
                    arguments=approval.get("arguments", {}),
                )

                # Create the approval response
                approval_response = Content.from_function_approval_response(
                    approved=approval.get("approved", True),
                    id=approval.get("id", ""),
                    function_call=func_call,
                )
                approval_contents.append(approval_response)

            chat_msg = Message(role=role, contents=approval_contents)  # type: ignore[call-overload]
        else:
            # Regular message content (text or multimodal)
            content = msg.get("content", "")
            converted_contents = _convert_agui_content_to_framework(content)
            if not converted_contents:
                converted_contents = [Content.from_text(text="")]
            chat_msg = Message(role=role, contents=converted_contents)  # type: ignore[call-overload]

        if "id" in msg:
            chat_msg.message_id = msg["id"]

        result.append(chat_msg)

    return result


def agent_framework_messages_to_agui(messages: list[Message] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Agent Framework messages to AG-UI format.

    Args:
        messages: List of Agent Framework Message objects or AG-UI dicts (already converted)

    Returns:
        List of AG-UI message dictionaries
    """
    from ._utils import generate_event_id

    result: list[dict[str, Any]] = []
    for msg in messages:
        # If already a dict (AG-UI format), ensure it has an ID and normalize keys for Pydantic
        if isinstance(msg, dict):
            # Always work on a copy to avoid mutating input
            normalized_msg = msg.copy()
            normalized_msg["role"] = normalize_agui_role(normalized_msg.get("role"))
            # Ensure ID exists
            if "id" not in normalized_msg:
                normalized_msg["id"] = generate_event_id()
            # Normalize tool_call_id to toolCallId for Pydantic's alias_generator=to_camel
            if normalized_msg.get("role") == "tool":
                if "tool_call_id" in normalized_msg:
                    normalized_msg["toolCallId"] = normalized_msg["tool_call_id"]
                    del normalized_msg["tool_call_id"]
                elif "toolCallId" not in normalized_msg:
                    # Tool message missing toolCallId - add empty string to satisfy schema
                    normalized_msg["toolCallId"] = ""
            # Always append the normalized copy, not the original
            result.append(normalized_msg)
            continue

        # Convert Message to AG-UI format
        role_value: str = msg.role if hasattr(msg.role, "value") else msg.role  # type: ignore[assignment]
        role = FRAMEWORK_TO_AGUI_ROLE.get(role_value, "user")

        content_text = ""
        tool_calls: list[dict[str, Any]] = []
        tool_result_call_id: str | None = None

        for content in msg.contents:
            if content.type == "text":
                content_text += content.text  # type: ignore[operator]
            elif content.type == "function_call":
                tool_calls.append(
                    {
                        "id": content.call_id,
                        "type": "function",
                        "function": {
                            "name": content.name,
                            "arguments": content.arguments,
                        },
                    }
                )
            elif content.type == "function_result":
                # Tool result content - extract call_id and result
                tool_result_call_id = content.call_id
                content_text = content.result if content.result is not None else ""

        agui_msg: dict[str, Any] = {
            "id": msg.message_id if msg.message_id else generate_event_id(),  # Always include id
            "role": role,
            "content": content_text,
        }

        if tool_calls:
            agui_msg["tool_calls"] = tool_calls

        # If this is a tool result message, add toolCallId (using camelCase for Pydantic)
        if tool_result_call_id:
            agui_msg["toolCallId"] = tool_result_call_id
            # Tool result messages should have role="tool"
            agui_msg["role"] = "tool"

        result.append(agui_msg)

    return result


def extract_text_from_contents(contents: list[Any]) -> str:
    """Extract text from Agent Framework contents.

    Args:
        contents: List of content objects

    Returns:
        Concatenated text
    """
    text_parts: list[str] = []
    for content in contents:
        if type_ := getattr(content, "type", None):
            if type_ == "text_reasoning":
                continue
            if text := getattr(content, "text", None):
                text_parts.append(text)
            continue
        # TODO (moonbox3): should this handle both text and text_reasoning?
        elif hasattr(content, "text"):
            text_parts.append(content.text)
    return "".join(text_parts)


def agui_messages_to_snapshot_format(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize AG-UI messages for MessagesSnapshotEvent.

    Converts AG-UI input format (with 'input_text' type) to snapshot format (with 'text' type).

    Args:
        messages: List of AG-UI messages in input format

    Returns:
        List of normalized messages suitable for MessagesSnapshotEvent
    """
    from ._utils import generate_event_id

    result: list[dict[str, Any]] = []
    for msg in messages:
        normalized_msg = msg.copy()

        # Ensure ID exists
        if "id" not in normalized_msg:
            normalized_msg["id"] = generate_event_id()

        # Normalize content field
        normalized_msg["content"] = _normalize_snapshot_content(normalized_msg.get("content"))

        tool_calls = normalized_msg.get("tool_calls") or normalized_msg.get("toolCalls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function_payload = tool_call.get("function")
                if not isinstance(function_payload, dict):
                    continue
                if "arguments" not in function_payload:
                    continue
                arguments = function_payload.get("arguments")
                if arguments is None:
                    function_payload["arguments"] = ""
                elif not isinstance(arguments, str):
                    function_payload["arguments"] = json.dumps(arguments)

        # Normalize tool_call_id to toolCallId for tool messages
        normalized_msg["role"] = normalize_agui_role(normalized_msg.get("role"))
        if normalized_msg.get("role") == "tool":
            if "tool_call_id" in normalized_msg:
                normalized_msg["toolCallId"] = normalized_msg["tool_call_id"]
                del normalized_msg["tool_call_id"]
            elif "toolCallId" not in normalized_msg:
                normalized_msg["toolCallId"] = ""

        result.append(normalized_msg)

    return result
