# Copyright (c) Microsoft. All rights reserved.

"""Message hygiene utilities for orchestrators."""

import json
import logging
from typing import Any

from agent_framework import ChatMessage, FunctionCallContent, FunctionResultContent, TextContent

logger = logging.getLogger(__name__)


def sanitize_tool_history(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Normalize tool ordering and inject synthetic results for AG-UI edge cases."""
    sanitized: list[ChatMessage] = []
    pending_tool_call_ids: set[str] | None = None
    pending_confirm_changes_id: str | None = None

    for msg in messages:
        role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)

        if role_value == "assistant":
            tool_ids = {
                str(content.call_id)
                for content in msg.contents or []
                if isinstance(content, FunctionCallContent) and content.call_id
            }
            confirm_changes_call = None
            for content in msg.contents or []:
                if isinstance(content, FunctionCallContent) and content.name == "confirm_changes":
                    confirm_changes_call = content
                    break

            sanitized.append(msg)
            pending_tool_call_ids = tool_ids if tool_ids else None
            pending_confirm_changes_id = (
                str(confirm_changes_call.call_id) if confirm_changes_call and confirm_changes_call.call_id else None
            )
            continue

        if role_value == "user":
            if pending_confirm_changes_id:
                user_text = ""
                for content in msg.contents or []:
                    if isinstance(content, TextContent):
                        user_text = content.text
                        break

                try:
                    parsed = json.loads(user_text)
                    if "accepted" in parsed:
                        logger.info(
                            f"Injecting synthetic tool result for confirm_changes call_id={pending_confirm_changes_id}"
                        )
                        synthetic_result = ChatMessage(
                            role="tool",
                            contents=[
                                FunctionResultContent(
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
                    logger.debug("Could not parse user message as confirm_changes response: %s", type(exc).__name__)

            if pending_tool_call_ids:
                logger.info(
                    f"User message arrived with {len(pending_tool_call_ids)} pending tool calls - injecting synthetic results"
                )
                for pending_call_id in pending_tool_call_ids:
                    logger.info(f"Injecting synthetic tool result for pending call_id={pending_call_id}")
                    synthetic_result = ChatMessage(
                        role="tool",
                        contents=[
                            FunctionResultContent(
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
                if isinstance(content, FunctionResultContent):
                    call_id = str(content.call_id)
                    if call_id in pending_tool_call_ids:
                        keep = True
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


def deduplicate_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Remove duplicate messages while preserving order."""
    seen_keys: dict[Any, int] = {}
    unique_messages: list[ChatMessage] = []

    for idx, msg in enumerate(messages):
        role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)

        if role_value == "tool" and msg.contents and isinstance(msg.contents[0], FunctionResultContent):
            call_id = str(msg.contents[0].call_id)
            key: Any = (role_value, call_id)

            if key in seen_keys:
                existing_idx = seen_keys[key]
                existing_msg = unique_messages[existing_idx]

                existing_result = None
                if existing_msg.contents and isinstance(existing_msg.contents[0], FunctionResultContent):
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

        elif (
            role_value == "assistant" and msg.contents and any(isinstance(c, FunctionCallContent) for c in msg.contents)
        ):
            tool_call_ids = tuple(
                sorted(str(c.call_id) for c in msg.contents if isinstance(c, FunctionCallContent) and c.call_id)
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
