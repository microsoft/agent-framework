# Copyright (c) Microsoft. All rights reserved.

"""Event converter for AG-UI protocol events to Agent Framework types."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from copy import copy
from typing import Any, TypeVar, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Annotation,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
)

AGUIUpdateT = TypeVar("AGUIUpdateT", ChatResponseUpdate, AgentResponseUpdate)
AGUIResponseT = TypeVar("AGUIResponseT", bound=ChatResponse[Any] | AgentResponse[Any])

logger = logging.getLogger(__name__)


def _annotation_batch_from_update(
    update: ChatResponseUpdate | AgentResponseUpdate,
) -> tuple[str, list[Annotation]] | None:
    """Extract a message-linked annotation batch produced by this converter."""
    # Replacement snapshots must keep their message identity during aggregation.
    if update.merge_mode == "replace":
        return None

    custom_event = (update.additional_properties or {}).get("ag_ui_custom_event")
    if not isinstance(custom_event, dict) or custom_event.get("name") != "annotations" or not update.message_id:
        return None
    # Buffered middleware can copy this response-level event metadata onto a rebuilt message.
    # Only the original annotation-only update should be excluded from message aggregation.
    value = custom_event.get("value")
    if not isinstance(value, dict) or value.get("messageId") != update.message_id:
        return None
    if any(
        content.type != "text" or content.text or content.additional_properties or content.merge_mode == "replace"
        for content in update.contents
    ):
        return None
    annotations = [
        annotation for content in update.contents if content.type == "text" for annotation in content.annotations or []
    ]
    return update.message_id, annotations


def _finalize_agui_response(
    updates: Sequence[ChatResponseUpdate], *, response_format: Any | None = None
) -> ChatResponse[Any]:
    """Aggregate chat updates while attaching annotation events by message ID."""
    return _finalize_agui_updates(
        updates, lambda items: ChatResponse.from_updates(items, output_format_type=response_format)
    )


def _finalize_agui_updates(
    updates: Sequence[AGUIUpdateT], aggregate: Callable[[Sequence[AGUIUpdateT]], AGUIResponseT]
) -> AGUIResponseT:
    """Attach citations while preserving the response type and original update metadata."""
    annotation_batches: list[tuple[str, list[Annotation]]] = []
    aggregatable_updates: list[AGUIUpdateT] = []
    run_id: str | None = None
    scope = 0
    local_tool_result_pending = False
    scoped_message_ids: dict[tuple[int, str], str] = {}
    original_message_ids: dict[str, str] = {}
    for update in updates:
        # A local result separates model turns even if middleware removes run markers.
        # Server-side AG-UI tool results have no local occurrence id and stay in the run.
        if update.role == "tool" and any(
            content.type == "function_result" and content.id for content in update.contents
        ):
            local_tool_result_pending = True
        elif local_tool_result_pending and update.message_id:
            scope += 1
            run_id = None
            local_tool_result_pending = False
        update_run_id = (update.additional_properties or {}).get("run_id")
        if isinstance(update_run_id, str):
            if run_id is not None and update_run_id != run_id:
                scope += 1
                local_tool_result_pending = False
            # The first observed id names the existing scope; it may arrive after text.
            run_id = update_run_id
        annotation_batch = _annotation_batch_from_update(update)
        if update.message_id:
            # A later model turn can reuse a protocol ID. Scope aggregation copies only.
            key = (scope, update.message_id)
            scoped_id = scoped_message_ids.setdefault(key, str(len(scoped_message_ids)))
            original_message_ids[scoped_id] = update.message_id
            update = copy(update)
            update.message_id = scoped_id
        if annotation_batch is None:
            aggregatable_updates.append(update)
        else:
            annotation_batches.append((cast("str", update.message_id), annotation_batch[1]))
            # Keep response-level fields from the event without changing any message.
            metadata_update = copy(update)
            metadata_update.contents = []
            metadata_update.message_id = metadata_update.role = metadata_update.author_name = None
            aggregatable_updates.append(metadata_update)

    response = aggregate(aggregatable_updates)

    for message_id, batch_annotations in annotation_batches:
        if not batch_annotations:
            continue
        message = next((message for message in response.messages if message.message_id == message_id), None)
        if message is None:
            response.messages.append(
                Message(
                    role="assistant",
                    contents=[Content.from_text(text="", annotations=batch_annotations)],
                    message_id=message_id,
                )
            )
            continue
        text_content = next((content for content in message.contents if content.type == "text"), None)
        if text_content is None:
            message.contents.append(Content.from_text(text="", annotations=batch_annotations))
        else:
            text_content.annotations = [*(text_content.annotations or []), *batch_annotations]

    for message in response.messages:
        if message.message_id is not None and message.message_id in original_message_ids:
            message.message_id = original_message_ids[message.message_id]
    return response


class AGUIEventConverter:
    """Converter for AG-UI events to Agent Framework types.

    Handles conversion of AG-UI protocol events to ChatResponseUpdate objects
    while maintaining state, aggregating content, and tracking metadata.
    """

    def __init__(self) -> None:
        """Initialize the converter with fresh state."""
        self.current_message_id: str | None = None
        self.current_tool_call_id: str | None = None
        self.current_tool_name: str | None = None
        self.accumulated_tool_args: str = ""
        self.thread_id: str | None = None
        self.run_id: str | None = None

    @staticmethod
    def _get_tool_call_id(event: dict[str, Any]) -> str | None:
        """Return the tool call ID from either AG-UI field spelling."""
        tool_call_id = event.get("toolCallId")
        if tool_call_id is None:
            tool_call_id = event.get("tool_call_id")
        if tool_call_id is None:
            return None
        return str(tool_call_id)

    def convert_event(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Convert a single AG-UI event to ChatResponseUpdate.

        Args:
            event: AG-UI event dictionary

        Returns:
            ChatResponseUpdate if event produces content, None otherwise

        Examples:
            RUN_STARTED event:

            .. code-block:: python

                converter = AGUIEventConverter()
                event = {"type": "RUN_STARTED", "threadId": "t1", "runId": "r1"}
                update = converter.convert_event(event)
                assert update.additional_properties["thread_id"] == "t1"

            TEXT_MESSAGE_CONTENT event:

            .. code-block:: python

                event = {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m1", "delta": "Hello"}
                update = converter.convert_event(event)
                assert update.contents[0].text == "Hello"
        """
        raw_event_type = str(event.get("type", ""))
        event_type = raw_event_type.upper()

        if event_type == "RUN_STARTED":
            return self._handle_run_started(event)
        elif event_type == "TEXT_MESSAGE_START":
            return self._handle_text_message_start(event)
        elif event_type == "TEXT_MESSAGE_CONTENT":
            return self._handle_text_message_content(event)
        elif event_type == "TEXT_MESSAGE_END":
            return self._handle_text_message_end(event)
        elif event_type == "TOOL_CALL_START":
            return self._handle_tool_call_start(event)
        elif event_type == "TOOL_CALL_ARGS":
            return self._handle_tool_call_args(event)
        elif event_type == "TOOL_CALL_END":
            return self._handle_tool_call_end(event)
        elif event_type == "TOOL_CALL_RESULT":
            return self._handle_tool_call_result(event)
        elif event_type == "RUN_FINISHED":
            return self._handle_run_finished(event)
        elif event_type == "RUN_ERROR":
            return self._handle_run_error(event)
        elif event_type in {"CUSTOM", "CUSTOM_EVENT"}:
            return self._handle_custom_event(event, raw_event_type)

        return None

    def _handle_run_started(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle RUN_STARTED event."""
        self.thread_id = event.get("threadId")
        self.run_id = event.get("runId")

        return ChatResponseUpdate(
            role="assistant",
            contents=[],
            additional_properties={
                "thread_id": self.thread_id,
                "run_id": self.run_id,
            },
        )

    def _handle_text_message_start(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Handle TEXT_MESSAGE_START event."""
        self.current_message_id = event.get("messageId")
        return ChatResponseUpdate(
            role="assistant",
            message_id=self.current_message_id,
            contents=[],
        )

    def _handle_text_message_content(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle TEXT_MESSAGE_CONTENT event."""
        message_id = event.get("messageId")
        delta = event.get("delta", "")

        if message_id != self.current_message_id:
            self.current_message_id = message_id

        return ChatResponseUpdate(
            role="assistant",
            message_id=self.current_message_id,
            contents=[Content.from_text(text=delta, merge_mode="append")],
        )

    def _handle_text_message_end(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Handle TEXT_MESSAGE_END event."""
        return None

    def _handle_tool_call_start(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle TOOL_CALL_START event."""
        self.current_tool_call_id = self._get_tool_call_id(event)
        self.current_tool_name = event.get("toolName") or event.get("toolCallName") or event.get("tool_call_name")
        self.accumulated_tool_args = ""

        return ChatResponseUpdate(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id=self.current_tool_call_id or "",
                    name=self.current_tool_name or "",
                    arguments="",
                    merge_mode="append",
                )
            ],
        )

    def _handle_tool_call_args(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Handle TOOL_CALL_ARGS event."""
        event_tool_call_id = self._get_tool_call_id(event)
        if event_tool_call_id is not None:
            if self.current_tool_call_id and event_tool_call_id != self.current_tool_call_id:
                logger.warning(
                    "Ignoring TOOL_CALL_ARGS for toolCallId=%s while current toolCallId=%s",
                    event_tool_call_id,
                    self.current_tool_call_id,
                )
                return None
            if not self.current_tool_call_id:
                self.current_tool_call_id = event_tool_call_id

        delta = event.get("delta", "")
        self.accumulated_tool_args += delta

        return ChatResponseUpdate(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id=self.current_tool_call_id or "",
                    name=self.current_tool_name or "",
                    arguments=delta,
                    merge_mode="append",
                )
            ],
        )

    def _handle_tool_call_end(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Handle TOOL_CALL_END event."""
        event_tool_call_id = self._get_tool_call_id(event)
        if (
            self.current_tool_call_id is None
            or event_tool_call_id is None
            or event_tool_call_id == self.current_tool_call_id
        ):
            self.current_tool_call_id = None
            self.current_tool_name = None
            self.accumulated_tool_args = ""
        return None

    def _handle_tool_call_result(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle TOOL_CALL_RESULT event."""
        tool_call_id = self._get_tool_call_id(event) or ""
        result = event.get("result") if event.get("result") is not None else event.get("content")

        return ChatResponseUpdate(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id=tool_call_id,
                    result=result,
                )
            ],
        )

    def _handle_run_finished(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle RUN_FINISHED event."""
        additional_properties: dict[str, Any] = {
            "thread_id": self.thread_id,
            "run_id": self.run_id,
        }
        if "interrupt" in event:
            additional_properties["interrupt"] = event.get("interrupt")
        if "outcome" in event:
            outcome = event.get("outcome")
            additional_properties["outcome"] = outcome
            if not isinstance(outcome, dict):
                logger.warning(
                    "RUN_FINISHED outcome should be an object; got %s. Preserving raw outcome.",
                    type(outcome).__name__,
                )
            elif outcome.get("type") == "interrupt":
                interrupts = outcome.get("interrupts")
                if isinstance(interrupts, list):
                    additional_properties["interrupts"] = interrupts
        if "result" in event:
            additional_properties["result"] = event.get("result")

        return ChatResponseUpdate(
            role="assistant",
            finish_reason="stop",
            contents=[],
            additional_properties=additional_properties,
        )

    def _handle_run_error(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle RUN_ERROR event."""
        error_message = event.get("message", "Unknown error")
        raw_code = event.get("code")
        error_code = str(raw_code) if raw_code else "RUN_ERROR"

        return ChatResponseUpdate(
            role="assistant",
            contents=[
                Content.from_error(
                    message=error_message,
                    error_code=error_code,
                )
            ],
            additional_properties={
                "thread_id": self.thread_id,
                "run_id": self.run_id,
            },
        )

    def _handle_custom_event(self, event: dict[str, Any], raw_event_type: str) -> ChatResponseUpdate:
        """Handle CUSTOM/CUSTOM_EVENT events.

        Custom events remain inspectable as metadata; annotation batches also restore text annotations.
        """
        update = ChatResponseUpdate(
            role="assistant",
            contents=[],
            additional_properties={
                "thread_id": self.thread_id,
                "run_id": self.run_id,
                "ag_ui_custom_event": {
                    "name": event.get("name"),
                    "value": event.get("value"),
                    "raw_type": raw_event_type,
                },
            },
        )
        if event.get("name") == "annotations":
            value = event.get("value")
            message_id = value.get("messageId") if isinstance(value, dict) else None
            annotations = value.get("annotations") if isinstance(value, dict) else None
            if (
                not isinstance(message_id, str)
                or not message_id
                or not isinstance(annotations, list)
                or not all(isinstance(annotation, dict) for annotation in annotations)
            ):
                logger.warning("Invalid annotations custom event: expected messageId and an annotations array")
            else:
                update.message_id = message_id
                if annotations:
                    update.contents = [
                        Content.from_text(
                            text="",
                            merge_mode="append",
                            annotations=cast("list[Annotation]", annotations),
                        )
                    ]
        return update
