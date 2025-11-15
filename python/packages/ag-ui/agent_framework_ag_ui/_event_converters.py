# Copyright (c) Microsoft. All rights reserved.

"""Event converter for AG-UI protocol events to Agent Framework types."""

from typing import Any

from agent_framework import (
    ChatResponseUpdate,
    ErrorContent,
    FinishReason,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
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
        event_type = event.get("type", "")

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

        return None

    def _handle_run_started(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle RUN_STARTED event."""
        self.thread_id = event.get("threadId")
        self.run_id = event.get("runId")

        return ChatResponseUpdate(
            role=Role.ASSISTANT,
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
            role=Role.ASSISTANT,
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
            role=Role.ASSISTANT,
            message_id=self.current_message_id,
            contents=[TextContent(text=delta)],
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
            role=Role.ASSISTANT,
            contents=[
                FunctionCallContent(
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
            role=Role.ASSISTANT,
            contents=[
                FunctionCallContent(
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
            role=Role.TOOL,
            contents=[
                FunctionResultContent(
                    call_id=tool_call_id,
                    result=result,
                )
            ],
        )

    def _handle_run_finished(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle RUN_FINISHED event."""
        return ChatResponseUpdate(
            role=Role.ASSISTANT,
            finish_reason=FinishReason.STOP,
            contents=[],
            additional_properties={
                "thread_id": self.thread_id,
                "run_id": self.run_id,
            },
        )

    def _handle_run_error(self, event: dict[str, Any]) -> ChatResponseUpdate:
        """Handle RUN_ERROR event."""
        error_message = event.get("message", "Unknown error")

        return ChatResponseUpdate(
            role=Role.ASSISTANT,
            finish_reason=FinishReason.CONTENT_FILTER,
            contents=[
                ErrorContent(
                    message=error_message,
                    error_code="RUN_ERROR",
                )
            ],
            additional_properties={
                "thread_id": self.thread_id,
                "run_id": self.run_id,
            },
        )
