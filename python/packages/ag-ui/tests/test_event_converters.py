"""Tests for AG-UI event converter."""

from agent_framework import FinishReason, Role

from agent_framework_ag_ui._event_converters import AGUIEventConverter


class TestAGUIEventConverter:
    """Test suite for AGUIEventConverter."""

    def test_run_started_event(self) -> None:
        """Test conversion of RUN_STARTED event."""
        converter = AGUIEventConverter()
        event = {
            "type": "RUN_STARTED",
            "threadId": "thread_123",
            "runId": "run_456",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.ASSISTANT
        assert update.additional_properties["thread_id"] == "thread_123"
        assert update.additional_properties["run_id"] == "run_456"
        assert converter.thread_id == "thread_123"
        assert converter.run_id == "run_456"

    def test_text_message_start_event(self) -> None:
        """Test conversion of TEXT_MESSAGE_START event."""
        converter = AGUIEventConverter()
        event = {
            "type": "TEXT_MESSAGE_START",
            "messageId": "msg_789",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.ASSISTANT
        assert update.message_id == "msg_789"
        assert converter.current_message_id == "msg_789"

    def test_text_message_content_event(self) -> None:
        """Test conversion of TEXT_MESSAGE_CONTENT event."""
        converter = AGUIEventConverter()
        event = {
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": "msg_1",
            "delta": "Hello",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.ASSISTANT
        assert update.message_id == "msg_1"
        assert len(update.contents) == 1
        assert update.contents[0].text == "Hello"

    def test_text_message_streaming(self) -> None:
        """Test streaming text across multiple TEXT_MESSAGE_CONTENT events."""
        converter = AGUIEventConverter()
        events = [
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "Hello"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": " world"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "!"},
        ]

        updates = [converter.convert_event(event) for event in events]

        assert all(update is not None for update in updates)
        assert all(update.message_id == "msg_1" for update in updates)
        assert updates[0].contents[0].text == "Hello"
        assert updates[1].contents[0].text == " world"
        assert updates[2].contents[0].text == "!"

    def test_text_message_end_event(self) -> None:
        """Test conversion of TEXT_MESSAGE_END event."""
        converter = AGUIEventConverter()
        event = {
            "type": "TEXT_MESSAGE_END",
            "messageId": "msg_1",
        }

        update = converter.convert_event(event)

        assert update is None

    def test_tool_call_start_event(self) -> None:
        """Test conversion of TOOL_CALL_START event."""
        converter = AGUIEventConverter()
        event = {
            "type": "TOOL_CALL_START",
            "toolCallId": "call_123",
            "toolName": "get_weather",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.ASSISTANT
        assert len(update.contents) == 1
        assert update.contents[0].call_id == "call_123"
        assert update.contents[0].name == "get_weather"
        assert update.contents[0].arguments == ""
        assert converter.current_tool_call_id == "call_123"
        assert converter.current_tool_name == "get_weather"

    def test_tool_call_start_with_tool_call_name(self) -> None:
        """Ensure TOOL_CALL_START with toolCallName still sets the tool name."""
        converter = AGUIEventConverter()
        event = {
            "type": "TOOL_CALL_START",
            "toolCallId": "call_abc",
            "toolCallName": "get_weather",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.contents[0].name == "get_weather"
        assert converter.current_tool_name == "get_weather"

    def test_tool_call_start_with_tool_call_name_snake_case(self) -> None:
        """Support tool_call_name snake_case field for backwards compatibility."""
        converter = AGUIEventConverter()
        event = {
            "type": "TOOL_CALL_START",
            "toolCallId": "call_snake",
            "tool_call_name": "get_weather",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.contents[0].name == "get_weather"
        assert converter.current_tool_name == "get_weather"

    def test_tool_call_args_streaming(self) -> None:
        """Test streaming tool arguments across multiple TOOL_CALL_ARGS events."""
        converter = AGUIEventConverter()
        converter.current_tool_call_id = "call_123"
        converter.current_tool_name = "search"

        events = [
            {"type": "TOOL_CALL_ARGS", "delta": '{"query": "'},
            {"type": "TOOL_CALL_ARGS", "delta": 'latest news"}'},
        ]

        updates = [converter.convert_event(event) for event in events]

        assert all(update is not None for update in updates)
        assert updates[0].contents[0].arguments == '{"query": "'
        assert updates[1].contents[0].arguments == 'latest news"}'
        assert converter.accumulated_tool_args == '{"query": "latest news"}'

    def test_tool_call_end_event(self) -> None:
        """Test conversion of TOOL_CALL_END event."""
        converter = AGUIEventConverter()
        converter.accumulated_tool_args = '{"location": "Seattle"}'

        event = {
            "type": "TOOL_CALL_END",
            "toolCallId": "call_123",
        }

        update = converter.convert_event(event)

        assert update is None
        assert converter.accumulated_tool_args == ""

    def test_tool_call_result_event(self) -> None:
        """Test conversion of TOOL_CALL_RESULT event."""
        converter = AGUIEventConverter()
        event = {
            "type": "TOOL_CALL_RESULT",
            "toolCallId": "call_123",
            "result": {"temperature": 22, "condition": "sunny"},
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.TOOL
        assert len(update.contents) == 1
        assert update.contents[0].call_id == "call_123"
        assert update.contents[0].result == {"temperature": 22, "condition": "sunny"}

    def test_run_finished_event(self) -> None:
        """Test conversion of RUN_FINISHED event."""
        converter = AGUIEventConverter()
        converter.thread_id = "thread_123"
        converter.run_id = "run_456"

        event = {
            "type": "RUN_FINISHED",
            "threadId": "thread_123",
            "runId": "run_456",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.ASSISTANT
        assert update.finish_reason == FinishReason.STOP
        assert update.additional_properties["thread_id"] == "thread_123"
        assert update.additional_properties["run_id"] == "run_456"

    def test_run_error_event(self) -> None:
        """Test conversion of RUN_ERROR event."""
        converter = AGUIEventConverter()
        converter.thread_id = "thread_123"
        converter.run_id = "run_456"

        event = {
            "type": "RUN_ERROR",
            "message": "Connection timeout",
        }

        update = converter.convert_event(event)

        assert update is not None
        assert update.role == Role.ASSISTANT
        assert update.finish_reason == FinishReason.CONTENT_FILTER
        assert len(update.contents) == 1
        assert update.contents[0].message == "Connection timeout"
        assert update.contents[0].error_code == "RUN_ERROR"

    def test_unknown_event_type(self) -> None:
        """Test handling of unknown event types."""
        converter = AGUIEventConverter()
        event = {
            "type": "UNKNOWN_EVENT",
            "data": "some data",
        }

        update = converter.convert_event(event)

        assert update is None

    def test_full_conversation_flow(self) -> None:
        """Test complete conversation flow with multiple event types."""
        converter = AGUIEventConverter()

        events = [
            {"type": "RUN_STARTED", "threadId": "thread_1", "runId": "run_1"},
            {"type": "TEXT_MESSAGE_START", "messageId": "msg_1"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": "I'll check"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_1", "delta": " the weather."},
            {"type": "TEXT_MESSAGE_END", "messageId": "msg_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "get_weather"},
            {"type": "TOOL_CALL_ARGS", "delta": '{"location": "Seattle"}'},
            {"type": "TOOL_CALL_END", "toolCallId": "call_1"},
            {"type": "TOOL_CALL_RESULT", "toolCallId": "call_1", "result": "Sunny, 72°F"},
            {"type": "TEXT_MESSAGE_START", "messageId": "msg_2"},
            {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_2", "delta": "It's sunny!"},
            {"type": "TEXT_MESSAGE_END", "messageId": "msg_2"},
            {"type": "RUN_FINISHED", "threadId": "thread_1", "runId": "run_1"},
        ]

        updates = [converter.convert_event(event) for event in events]
        non_none_updates = [u for u in updates if u is not None]

        assert len(non_none_updates) == 10
        assert converter.thread_id == "thread_1"
        assert converter.run_id == "run_1"

    def test_multiple_tool_calls(self) -> None:
        """Test handling multiple tool calls in sequence."""
        converter = AGUIEventConverter()

        events = [
            {"type": "TOOL_CALL_START", "toolCallId": "call_1", "toolName": "search"},
            {"type": "TOOL_CALL_ARGS", "delta": '{"query": "weather"}'},
            {"type": "TOOL_CALL_END", "toolCallId": "call_1"},
            {"type": "TOOL_CALL_START", "toolCallId": "call_2", "toolName": "fetch"},
            {"type": "TOOL_CALL_ARGS", "delta": '{"url": "http://api.weather.com"}'},
            {"type": "TOOL_CALL_END", "toolCallId": "call_2"},
        ]

        updates = [converter.convert_event(event) for event in events]
        non_none_updates = [u for u in updates if u is not None]

        assert len(non_none_updates) == 4
        assert non_none_updates[0].contents[0].name == "search"
        assert non_none_updates[2].contents[0].name == "fetch"
