# Copyright (c) Microsoft. All rights reserved.

"""Tests for _agent_run.py helper functions and FlowState."""

import pytest
from ag_ui.core import (
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
)
from agent_framework import AgentResponseUpdate, Content, Message, ResponseStream
from agent_framework.exceptions import AgentInvalidResponseException

from agent_framework_ag_ui._agent_run import (
    _build_safe_metadata,
    _create_state_context_message,
    _inject_state_context,
    _normalize_response_stream,
    _resume_to_tool_messages,
    _should_suppress_intermediate_snapshot,
)
from agent_framework_ag_ui._run_common import (
    FlowState,
    _build_run_finished_event,
    _emit_approval_request,
    _emit_content,
    _emit_text,
    _emit_tool_call,
    _emit_tool_result,
    _extract_resume_payload,
    _has_only_tool_calls,
)


class TestBuildSafeMetadata:
    """Tests for _build_safe_metadata function."""

    def test_none_metadata(self):
        """Returns empty dict for None."""
        result = _build_safe_metadata(None)
        assert result == {}

    def test_empty_metadata(self):
        """Returns empty dict for empty dict."""
        result = _build_safe_metadata({})
        assert result == {}

    def test_short_string_values(self):
        """Preserves short string values."""
        metadata = {"key1": "short", "key2": "value"}
        result = _build_safe_metadata(metadata)
        assert result == metadata

    def test_truncates_long_strings(self):
        """Truncates strings over 512 chars."""
        long_value = "x" * 1000
        metadata = {"key": long_value}
        result = _build_safe_metadata(metadata)
        assert len(result["key"]) == 512

    def test_serializes_non_strings(self):
        """Serializes non-string values to JSON."""
        metadata = {"count": 42, "items": [1, 2, 3]}
        result = _build_safe_metadata(metadata)
        assert result["count"] == "42"
        assert result["items"] == "[1, 2, 3]"

    def test_truncates_serialized_values(self):
        """Truncates serialized values over 512 chars."""
        long_list = list(range(200))
        metadata = {"data": long_list}
        result = _build_safe_metadata(metadata)
        assert len(result["data"]) == 512


class TestHasOnlyToolCalls:
    """Tests for _has_only_tool_calls function."""

    def test_only_tool_calls(self):
        """Returns True when only function_call content."""
        contents = [
            Content.from_function_call(call_id="call_1", name="tool1", arguments="{}"),
        ]
        assert _has_only_tool_calls(contents) is True

    def test_tool_call_with_text(self):
        """Returns False when both tool call and text."""
        contents = [
            Content.from_text("Some text"),
            Content.from_function_call(call_id="call_1", name="tool1", arguments="{}"),
        ]
        assert _has_only_tool_calls(contents) is False

    def test_only_text(self):
        """Returns False when only text."""
        contents = [Content.from_text("Just text")]
        assert _has_only_tool_calls(contents) is False

    def test_empty_contents(self):
        """Returns False for empty contents."""
        assert _has_only_tool_calls([]) is False

    def test_tool_call_with_empty_text(self):
        """Returns True when text content has empty text."""
        contents = [
            Content.from_text(""),
            Content.from_function_call(call_id="call_1", name="tool1", arguments="{}"),
        ]
        assert _has_only_tool_calls(contents) is True


class TestShouldSuppressIntermediateSnapshot:
    """Tests for _should_suppress_intermediate_snapshot function."""

    def test_no_tool_name(self):
        """Returns False when no tool name."""
        result = _should_suppress_intermediate_snapshot(
            None, {"key": {"tool": "write_doc", "tool_argument": "content"}}, False
        )
        assert result is False

    def test_no_config(self):
        """Returns False when no config."""
        result = _should_suppress_intermediate_snapshot("write_doc", None, False)
        assert result is False

    def test_confirmation_required(self):
        """Returns False when confirmation is required."""
        config = {"key": {"tool": "write_doc", "tool_argument": "content"}}
        result = _should_suppress_intermediate_snapshot("write_doc", config, True)
        assert result is False

    def test_tool_not_in_config(self):
        """Returns False when tool not in config."""
        config = {"key": {"tool": "other_tool", "tool_argument": "content"}}
        result = _should_suppress_intermediate_snapshot("write_doc", config, False)
        assert result is False

    def test_suppresses_predictive_tool(self):
        """Returns True for predictive tool without confirmation."""
        config = {"document": {"tool": "write_doc", "tool_argument": "content"}}
        result = _should_suppress_intermediate_snapshot("write_doc", config, False)
        assert result is True


class TestFlowState:
    """Tests for FlowState dataclass."""

    def test_default_values(self):
        """Tests default initialization."""
        flow = FlowState()
        assert flow.message_id is None
        assert flow.tool_call_id is None
        assert flow.tool_call_name is None
        assert flow.waiting_for_approval is False
        assert flow.current_state == {}
        assert flow.accumulated_text == ""
        assert flow.pending_tool_calls == []
        assert flow.tool_calls_by_id == {}
        assert flow.tool_results == []
        assert flow.tool_calls_ended == set()
        assert flow.interrupts == []

    def test_get_tool_name(self):
        """Tests get_tool_name method."""
        flow = FlowState()
        flow.tool_calls_by_id = {"call_123": {"function": {"name": "get_weather", "arguments": "{}"}}}

        assert flow.get_tool_name("call_123") == "get_weather"
        assert flow.get_tool_name("nonexistent") is None
        assert flow.get_tool_name(None) is None

    def test_get_tool_name_empty_name(self):
        """Tests get_tool_name with empty name."""
        flow = FlowState()
        flow.tool_calls_by_id = {"call_123": {"function": {"name": "", "arguments": "{}"}}}

        assert flow.get_tool_name("call_123") is None

    def test_get_pending_without_end(self):
        """Tests get_pending_without_end method."""
        flow = FlowState()
        flow.pending_tool_calls = [
            {"id": "call_1", "function": {"name": "tool1"}},
            {"id": "call_2", "function": {"name": "tool2"}},
            {"id": "call_3", "function": {"name": "tool3"}},
        ]
        flow.tool_calls_ended = {"call_1", "call_3"}

        result = flow.get_pending_without_end()
        assert len(result) == 1
        assert result[0]["id"] == "call_2"


class TestNormalizeResponseStream:
    """Tests for _normalize_response_stream helper."""

    async def test_accepts_response_stream(self):
        """Accept standard ResponseStream values."""

        async def _stream():
            yield AgentResponseUpdate(contents=[Content.from_text("hello")], role="assistant")

        stream = await _normalize_response_stream(ResponseStream(_stream()))
        updates = [update async for update in stream]

        assert len(updates) == 1
        assert updates[0].contents[0].text == "hello"

    async def test_accepts_async_iterable(self):
        """Accept workflow-style async generator streams."""

        async def _stream():
            yield AgentResponseUpdate(contents=[Content.from_text("hello")], role="assistant")

        stream = await _normalize_response_stream(_stream())
        updates = [update async for update in stream]

        assert len(updates) == 1
        assert updates[0].contents[0].text == "hello"

    async def test_accepts_awaitable_resolving_to_async_iterable(self):
        """Accept awaitables that resolve to async iterable streams."""

        async def _stream():
            yield AgentResponseUpdate(contents=[Content.from_text("hello")], role="assistant")

        async def _resolve():
            return _stream()

        stream = await _normalize_response_stream(_resolve())
        updates = [update async for update in stream]

        assert len(updates) == 1
        assert updates[0].contents[0].text == "hello"

    async def test_rejects_non_stream_values(self):
        """Reject unsupported stream return values."""
        with pytest.raises(AgentInvalidResponseException):
            await _normalize_response_stream("not-a-stream")


class TestCreateStateContextMessage:
    """Tests for _create_state_context_message function."""

    def test_no_state(self):
        """Returns None when no state."""
        result = _create_state_context_message({}, {"properties": {}})
        assert result is None

    def test_no_schema(self):
        """Returns None when no schema."""
        result = _create_state_context_message({"key": "value"}, {})
        assert result is None

    def test_creates_message(self):
        """Creates state context message."""

        state = {"document": "Hello world"}
        schema = {"properties": {"document": {"type": "string"}}}

        result = _create_state_context_message(state, schema)

        assert result is not None
        assert result.role == "system"
        assert len(result.contents) == 1
        assert "Hello world" in result.contents[0].text
        assert "Current state" in result.contents[0].text


class TestInjectStateContext:
    """Tests for _inject_state_context function."""

    def test_no_state_message(self):
        """Returns original messages when no state context needed."""
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        result = _inject_state_context(messages, {}, {})
        assert result == messages

    def test_empty_messages(self):
        """Returns empty list for empty messages."""
        result = _inject_state_context([], {"key": "value"}, {"properties": {}})
        assert result == []

    def test_last_message_not_user(self):
        """Returns original messages when last message is not from user."""
        messages = [
            Message(role="user", contents=[Content.from_text("Hello")]),
            Message(role="assistant", contents=[Content.from_text("Hi")]),
        ]
        state = {"key": "value"}
        schema = {"properties": {"key": {"type": "string"}}}

        result = _inject_state_context(messages, state, schema)
        assert result == messages

    def test_injects_before_last_user_message(self):
        """Injects state context before last user message."""

        messages = [
            Message(role="system", contents=[Content.from_text("You are helpful")]),
            Message(role="user", contents=[Content.from_text("Hello")]),
        ]
        state = {"document": "content"}
        schema = {"properties": {"document": {"type": "string"}}}

        result = _inject_state_context(messages, state, schema)

        assert len(result) == 3
        # System message first
        assert result[0].role == "system"
        assert "helpful" in result[0].contents[0].text
        # State context second
        assert result[1].role == "system"
        assert "Current state" in result[1].contents[0].text
        # User message last
        assert result[2].role == "user"
        assert "Hello" in result[2].contents[0].text


# Additional tests for _agent_run.py functions


def test_emit_text_basic():
    """Test _emit_text emits correct events."""
    flow = FlowState()
    content = Content.from_text("Hello world")

    events = _emit_text(content, flow)

    assert len(events) == 2  # TextMessageStartEvent + TextMessageContentEvent
    assert flow.message_id is not None
    assert flow.accumulated_text == "Hello world"


def test_emit_text_skip_empty():
    """Test _emit_text skips empty text."""
    flow = FlowState()
    content = Content.from_text("")

    events = _emit_text(content, flow)

    assert len(events) == 0


def test_emit_text_continues_existing_message():
    """Test _emit_text continues existing message."""
    flow = FlowState()
    flow.message_id = "existing-id"
    content = Content.from_text("more text")

    events = _emit_text(content, flow)

    assert len(events) == 1  # Only TextMessageContentEvent, no new start
    assert flow.message_id == "existing-id"


def test_emit_text_skips_duplicate_full_message_delta():
    """Test _emit_text skips replayed full-message chunks on an open message."""
    flow = FlowState()
    flow.message_id = "existing-id"
    flow.accumulated_text = "Case complete."
    content = Content.from_text("Case complete.")

    events = _emit_text(content, flow)

    assert events == []
    assert flow.accumulated_text == "Case complete."


def test_emit_text_skips_when_waiting_for_approval():
    """Test _emit_text skips when waiting for approval."""
    flow = FlowState()
    flow.waiting_for_approval = True
    content = Content.from_text("should skip")

    events = _emit_text(content, flow)

    assert len(events) == 0


def test_emit_text_skips_when_skip_text_flag():
    """Test _emit_text skips with skip_text flag."""
    flow = FlowState()
    content = Content.from_text("should skip")

    events = _emit_text(content, flow, skip_text=True)

    assert len(events) == 0


def test_emit_tool_call_basic():
    """Test _emit_tool_call emits correct events."""
    flow = FlowState()
    content = Content.from_function_call(
        call_id="call_123",
        name="get_weather",
        arguments='{"city": "NYC"}',
    )

    events = _emit_tool_call(content, flow)

    assert len(events) >= 1  # At least ToolCallStartEvent
    assert flow.tool_call_id == "call_123"
    assert flow.tool_call_name == "get_weather"


def test_emit_tool_call_generates_id():
    """Test _emit_tool_call generates ID when not provided."""
    flow = FlowState()
    # Create content without call_id
    content = Content(type="function_call", name="test_tool", arguments="{}")

    events = _emit_tool_call(content, flow)

    assert len(events) >= 1
    assert flow.tool_call_id is not None  # ID should be generated


def test_emit_tool_call_skips_duplicate_full_arguments_replay():
    """Test _emit_tool_call skips replayed full-arguments on an existing tool call.

    This is a regression test for issue #4194 where some streaming providers
    send the full arguments string again after streaming deltas, causing the
    arguments to be doubled in MESSAGES_SNAPSHOT events.

    Mirrors test_emit_text_skips_duplicate_full_message_delta for consistency.
    """
    flow = FlowState()
    full_args = '{"city": "Seattle"}'

    # Step 1: Initial tool call with name + arguments (normal start)
    content_start = Content.from_function_call(
        call_id="call_dup",
        name="get_weather",
        arguments=full_args,
    )
    events_start = _emit_tool_call(content_start, flow)

    # Should emit ToolCallStartEvent + ToolCallArgsEvent
    assert any(isinstance(e, ToolCallArgsEvent) for e in events_start)
    assert flow.tool_calls_by_id["call_dup"]["function"]["arguments"] == full_args

    # Step 2: Provider replays the full arguments (duplicate)
    content_replay = Content(type="function_call", call_id="call_dup", arguments=full_args)
    events_replay = _emit_tool_call(content_replay, flow)

    # Should NOT emit any ToolCallArgsEvent (early return on replay)
    args_events = [e for e in events_replay if isinstance(e, ToolCallArgsEvent)]
    assert args_events == [], "Duplicate full-arguments replay should not emit ToolCallArgsEvent"

    # Accumulated arguments should remain unchanged
    assert flow.tool_calls_by_id["call_dup"]["function"]["arguments"] == full_args


def test_emit_tool_result_closes_open_message():
    """Test _emit_tool_result emits TextMessageEndEvent for open text message.

    This is a regression test for where TEXT_MESSAGE_END was not
    emitted when using MCP tools because the message_id was reset without
    closing the message first.
    """
    flow = FlowState()
    # Simulate an open text message (e.g., from Feature #4 tool-only detection)
    flow.message_id = "open-msg-123"
    flow.tool_call_id = "call_456"

    content = Content.from_function_result(call_id="call_456", result="tool result")

    events = _emit_tool_result(content, flow, predictive_handler=None)

    # Should have: ToolCallEndEvent, ToolCallResultEvent, TextMessageEndEvent
    assert len(events) == 3

    # Verify TextMessageEndEvent is emitted for the open message
    text_end_events = [e for e in events if isinstance(e, TextMessageEndEvent)]
    assert len(text_end_events) == 1
    assert text_end_events[0].message_id == "open-msg-123"

    # Verify message_id is reset after
    assert flow.message_id is None


def test_emit_tool_result_no_open_message():
    """Test _emit_tool_result works when there's no open text message."""
    flow = FlowState()
    # No open message
    flow.message_id = None
    flow.tool_call_id = "call_456"

    content = Content.from_function_result(call_id="call_456", result="tool result")

    events = _emit_tool_result(content, flow, predictive_handler=None)

    # Should have: ToolCallEndEvent, ToolCallResultEvent (no TextMessageEndEvent)
    text_end_events = [e for e in events if isinstance(e, TextMessageEndEvent)]
    assert len(text_end_events) == 0


def test_emit_tool_result_serializes_non_string_result():
    """Non-string tool results should be serialized before emitting TOOL_CALL_RESULT."""
    flow = FlowState()
    content = Content.from_function_result(call_id="call_789", result={"ok": True, "items": [1, 2]})

    events = _emit_tool_result(content, flow, predictive_handler=None)
    result_event = next(event for event in events if getattr(event, "type", None) == "TOOL_CALL_RESULT")

    assert isinstance(result_event.content, str)
    assert '"ok": true' in result_event.content
    assert flow.tool_results[0]["content"] == result_event.content


def test_emit_content_usage_emits_custom_usage_event():
    """Usage content should be emitted as a custom usage event."""
    flow = FlowState()
    content = Content.from_usage({"input_token_count": 3, "output_token_count": 2, "total_token_count": 5})

    events = _emit_content(content, flow)

    assert len(events) == 1
    assert events[0].type == "CUSTOM"
    assert events[0].name == "usage"
    assert events[0].value["total_token_count"] == 5


def test_emit_approval_request_populates_interrupt_metadata():
    """Approval requests should populate FlowState interrupts for RUN_FINISHED metadata."""
    flow = FlowState(message_id="msg-1")
    function_call = Content.from_function_call(call_id="call_123", name="write_doc", arguments={"content": "x"})
    approval_content = Content.from_function_approval_request(id="approval_1", function_call=function_call)

    _emit_approval_request(approval_content, flow)

    assert flow.waiting_for_approval is True
    assert len(flow.interrupts) == 1
    assert flow.interrupts[0]["id"] == "call_123"
    assert flow.interrupts[0]["value"]["type"] == "function_approval_request"


def test_resume_to_tool_messages_from_interrupts_payload():
    """Resume payload interrupt responses map to tool messages."""
    resume = {
        "interrupts": [
            {"id": "req_1", "value": {"accepted": True, "steps": []}},
            {"id": "req_2", "value": "plain value"},
        ]
    }

    messages = _resume_to_tool_messages(resume)
    assert len(messages) == 2
    assert messages[0]["role"] == "tool"
    assert messages[0]["toolCallId"] == "req_1"
    assert '"accepted": true' in messages[0]["content"]
    assert messages[1]["content"] == "plain value"


def test_extract_resume_payload_prefers_top_level_resume():
    """Top-level resume should take precedence over forwarded props."""
    payload = {
        "resume": {"interrupts": [{"id": "req_1", "value": "approved"}]},
        "forwarded_props": {"command": {"resume": "ignored"}},
    }

    result = _extract_resume_payload(payload)
    assert result == {"interrupts": [{"id": "req_1", "value": "approved"}]}


def test_extract_resume_payload_reads_forwarded_command_resume():
    """Forwarded command.resume should be treated as a resume payload."""
    payload = {
        "forwarded_props": {
            "command": {"resume": '{"airline":"KLM","departure":"Amsterdam (AMS)","arrival":"San Francisco (SFO)"}'}
        }
    }

    result = _extract_resume_payload(payload)
    assert isinstance(result, str)
    assert "KLM" in result


def test_build_run_finished_event_with_interrupt():
    """RUN_FINISHED helper should preserve interrupt payloads."""
    event = _build_run_finished_event("run-1", "thread-1", interrupts=[{"id": "req_1", "value": {"x": 1}}])
    dumped = event.model_dump()

    assert dumped["run_id"] == "run-1"
    assert dumped["thread_id"] == "thread-1"
    assert dumped["interrupt"] == [{"id": "req_1", "value": {"x": 1}}]


def test_extract_approved_state_updates_no_handler():
    """Test _extract_approved_state_updates returns empty with no handler."""
    from agent_framework_ag_ui._agent_run import _extract_approved_state_updates

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    result = _extract_approved_state_updates(messages, None)
    assert result == {}


def test_extract_approved_state_updates_no_approval():
    """Test _extract_approved_state_updates returns empty when no approval content."""
    from agent_framework_ag_ui._agent_run import _extract_approved_state_updates
    from agent_framework_ag_ui._orchestration._predictive_state import PredictiveStateHandler

    handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "content"}})
    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    result = _extract_approved_state_updates(messages, handler)
    assert result == {}


class TestBuildMessagesSnapshot:
    """Tests for _build_messages_snapshot function."""

    def test_tool_calls_and_text_are_separate_messages(self):
        """Test that tool calls and text content are emitted as separate messages.

        This is a regression test for issue #3619 where tool calls and content
        were incorrectly merged into a single assistant message.
        """
        from agent_framework_ag_ui._agent_run import FlowState, _build_messages_snapshot

        flow = FlowState()
        flow.message_id = "msg-123"
        flow.pending_tool_calls = [
            {"id": "call_1", "function": {"name": "get_weather", "arguments": '{"city": "NYC"}'}},
        ]
        flow.accumulated_text = "Here is the weather information."
        flow.tool_results = [{"id": "result-1", "role": "tool", "content": '{"temp": 72}', "toolCallId": "call_1"}]

        result = _build_messages_snapshot(flow, [])

        # Should have 3 messages: tool call msg, tool result, text content msg
        assert len(result.messages) == 3

        # First message: assistant with tool calls only (no content)
        assistant_tool_msg = result.messages[0]
        assert assistant_tool_msg.role == "assistant"
        assert assistant_tool_msg.tool_calls is not None
        assert len(assistant_tool_msg.tool_calls) == 1
        assert assistant_tool_msg.content is None

        # Second message: tool result
        tool_result_msg = result.messages[1]
        assert tool_result_msg.role == "tool"

        # Third message: assistant with content only (no tool calls)
        assistant_text_msg = result.messages[2]
        assert assistant_text_msg.role == "assistant"
        assert assistant_text_msg.content == "Here is the weather information."
        assert assistant_text_msg.tool_calls is None

        # The text message should have a different ID than the tool call message
        assert assistant_text_msg.id != assistant_tool_msg.id

    def test_only_tool_calls_no_text(self):
        """Test snapshot with only tool calls and no accumulated text."""
        from agent_framework_ag_ui._agent_run import FlowState, _build_messages_snapshot

        flow = FlowState()
        flow.message_id = "msg-123"
        flow.pending_tool_calls = [
            {"id": "call_1", "function": {"name": "get_weather", "arguments": "{}"}},
        ]
        flow.accumulated_text = ""
        flow.tool_results = []

        result = _build_messages_snapshot(flow, [])

        # Should have 1 message: tool call msg only
        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert result.messages[0].tool_calls is not None
        assert result.messages[0].content is None

    def test_only_text_no_tool_calls(self):
        """Test snapshot with only text and no tool calls."""
        from agent_framework_ag_ui._agent_run import FlowState, _build_messages_snapshot

        flow = FlowState()
        flow.message_id = "msg-123"
        flow.pending_tool_calls = []
        flow.accumulated_text = "Hello world"
        flow.tool_results = []

        result = _build_messages_snapshot(flow, [])

        # Should have 1 message: text content msg only
        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert result.messages[0].content == "Hello world"
        assert result.messages[0].tool_calls is None
        # Should use the existing message_id
        assert result.messages[0].id == "msg-123"

    def test_preserves_snapshot_messages(self):
        """Test that existing snapshot messages are preserved."""
        from agent_framework_ag_ui._agent_run import FlowState, _build_messages_snapshot

        flow = FlowState()
        flow.pending_tool_calls = []
        flow.accumulated_text = ""

        existing_messages = [
            {"id": "user-1", "role": "user", "content": "Hello"},
            {"id": "assist-1", "role": "assistant", "content": "Hi there"},
        ]

        result = _build_messages_snapshot(flow, existing_messages)

        assert len(result.messages) == 2
        assert result.messages[0].id == "user-1"
        assert result.messages[1].id == "assist-1"


def test_malformed_json_in_confirm_args_skips_confirmation():
    """Test that malformed JSON in tool arguments skips confirm_changes flow.

    This is a regression test to ensure that when tool arguments contain malformed
    JSON, the code skips the confirmation flow entirely rather than crashing or
    showing incomplete data to the user.
    """
    import json

    # Simulate the parsing logic - malformed JSON should trigger skip
    malformed_arguments = "{ invalid json }"
    tool_call = {"function": {"name": "write_doc", "arguments": malformed_arguments}}

    # This is what the code should do - detect parsing failure and skip
    should_skip_confirmation = False
    try:
        json.loads(tool_call.get("function", {}).get("arguments", "{}"))
    except json.JSONDecodeError:
        should_skip_confirmation = True

    # Should skip confirmation when JSON is malformed
    assert should_skip_confirmation is True

    # Valid JSON should proceed with confirmation
    valid_arguments = '{"content": "hello"}'
    tool_call_valid = {"function": {"name": "write_doc", "arguments": valid_arguments}}
    should_skip_confirmation = False
    try:
        function_arguments = json.loads(tool_call_valid.get("function", {}).get("arguments", "{}"))
    except json.JSONDecodeError:
        should_skip_confirmation = True

    assert should_skip_confirmation is False
    assert function_arguments == {"content": "hello"}


class TestTextMessageEventBalancing:
    """Tests for proper TEXT_MESSAGE_START/END event balancing.

    These tests verify that the streaming flow produces balanced pairs of
    TextMessageStartEvent and TextMessageEndEvent, especially when tool
    execution is involved.
    """

    def test_tool_only_flow_produces_balanced_events(self):
        """Test that a tool-only response produces balanced TEXT_MESSAGE events.

        This simulates the scenario where the LLM immediately calls a tool
        without any initial text, then returns text after the tool result.
        """
        flow = FlowState()
        all_events: list = []

        # Step 1: LLM outputs function_call only (no text)
        func_call_content = Content.from_function_call(
            call_id="call_weather",
            name="get_weather",
            arguments='{"city": "Seattle"}',
        )

        # Feature #4 check: this should trigger TextMessageStartEvent
        contents = [func_call_content]
        if not flow.message_id and _has_only_tool_calls(contents):
            flow.message_id = "tool-msg-1"
            all_events.append(TextMessageStartEvent(message_id=flow.message_id, role="assistant"))

        # Emit tool call events
        all_events.extend(_emit_content(func_call_content, flow))

        # Step 2: Tool executes and returns result
        func_result_content = Content.from_function_result(
            call_id="call_weather",
            result='{"temp": 55, "conditions": "rainy"}',
        )

        # This should close the text message
        all_events.extend(_emit_tool_result(func_result_content, flow))

        # Verify message_id was reset
        assert flow.message_id is None, "message_id should be reset after tool result"

        # Step 3: LLM outputs text response
        text_content = Content.from_text("The weather in Seattle is 55°F and rainy.")

        # Since message_id is None, _emit_text should create a new one
        for event in _emit_content(text_content, flow):
            all_events.append(event)

        # Step 4: End of stream - emit final TextMessageEndEvent
        if flow.message_id:
            all_events.append(TextMessageEndEvent(message_id=flow.message_id))

        # Verify event counts
        start_events = [e for e in all_events if isinstance(e, TextMessageStartEvent)]
        end_events = [e for e in all_events if isinstance(e, TextMessageEndEvent)]

        # Should have 2 TextMessageStartEvent and 2 TextMessageEndEvent
        assert len(start_events) == 2, f"Expected 2 start events, got {len(start_events)}"
        assert len(end_events) == 2, f"Expected 2 end events, got {len(end_events)}"

        # Verify order: first message should start and end before second starts
        # Find indices
        start_indices = [i for i, e in enumerate(all_events) if isinstance(e, TextMessageStartEvent)]
        end_indices = [i for i, e in enumerate(all_events) if isinstance(e, TextMessageEndEvent)]

        # First end should come before second start
        assert end_indices[0] < start_indices[1], (
            f"First TextMessageEndEvent (index {end_indices[0]}) should come "
            f"before second TextMessageStartEvent (index {start_indices[1]})"
        )

    def test_text_then_tool_flow(self):
        """Test flow where LLM outputs text first, then calls a tool.

        This simulates: "Let me check the weather..." -> tool call -> tool result -> "The weather is..."
        """
        flow = FlowState()
        all_events: list = []

        # Step 1: LLM outputs text first
        text1 = Content.from_text("Let me check the weather for you.")
        all_events.extend(_emit_content(text1, flow))

        # Verify message_id is set
        assert flow.message_id is not None, "message_id should be set after text"
        first_msg_id = flow.message_id

        # Step 2: LLM outputs function_call
        func_call = Content.from_function_call(
            call_id="call_1",
            name="get_weather",
            arguments="{}",
        )
        all_events.extend(_emit_content(func_call, flow))

        # Step 3: Tool result comes back
        func_result = Content.from_function_result(call_id="call_1", result="sunny")
        all_events.extend(_emit_tool_result(func_result, flow))

        # Verify message_id was reset and first message was closed
        assert flow.message_id is None
        end_events_so_far = [e for e in all_events if isinstance(e, TextMessageEndEvent)]
        assert len(end_events_so_far) == 1
        assert end_events_so_far[0].message_id == first_msg_id

        # Step 4: LLM outputs follow-up text
        text2 = Content.from_text("The weather is sunny!")
        all_events.extend(_emit_content(text2, flow))

        # Step 5: End of stream
        if flow.message_id:
            all_events.append(TextMessageEndEvent(message_id=flow.message_id))

        # Verify balance
        start_events = [e for e in all_events if isinstance(e, TextMessageStartEvent)]
        end_events = [e for e in all_events if isinstance(e, TextMessageEndEvent)]

        assert len(start_events) == 2
        assert len(end_events) == 2
