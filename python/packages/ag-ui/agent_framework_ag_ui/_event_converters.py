# Copyright (c) Microsoft. All rights reserved.

"""Event converter for AG-UI protocol events to Agent Framework types."""

from __future__ import annotations

from typing import Any

from agent_framework import (
    ChatResponseUpdate,
    Content,
)


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
            contents=[Content.from_text(text=delta)],
        )

    def _handle_text_message_end(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Handle TEXT_MESSAGE_END event."""
        return None

    def _handle_tool_call_start(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle TOOL_CALL_START event."""
        self.current_tool_call_id = event.get("toolCallId")
        self.current_tool_name = event.get("toolName") or event.get("toolCallName") or event.get("tool_call_name")
        self.accumulated_tool_args = ""

        return ChatResponseUpdate(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id=self.current_tool_call_id or "",
                    name=self.current_tool_name or "",
                    arguments="",
                )
            ],
        )

    def _handle_tool_call_args(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle TOOL_CALL_ARGS event."""
        delta = event.get("delta", "")
        self.accumulated_tool_args += delta

        return ChatResponseUpdate(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id=self.current_tool_call_id or "",
                    name=self.current_tool_name or "",
                    arguments=delta,
                )
            ],
        )

    def _handle_tool_call_end(self, event: dict[str, Any]) -> ChatResponseUpdate | None:
        """Handle TOOL_CALL_END event."""
        self.accumulated_tool_args = ""
        return None

    def _handle_tool_call_result(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle TOOL_CALL_RESULT event."""
        tool_call_id = event.get("toolCallId", "")
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

        return ChatResponseUpdate(
            role="assistant",
            finish_reason="content_filter",
            contents=[
                Content.from_error(
                    message=error_message,
                    error_code="RUN_ERROR",
                )
            ],
            additional_properties={
                "thread_id": self.thread_id,
                "run_id": self.run_id,
            },
        )

    def _handle_custom_event(self, event: dict[str, Any], raw_event_type: str) -> ChatResponseUpdate:
        """Handle CUSTOM/CUSTOM_EVENT events.

        Custom events are surfaced as metadata so callers can inspect protocol-specific payloads.
        """
        return ChatResponseUpdate(
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
