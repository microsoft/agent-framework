# Copyright (c) Microsoft. All rights reserved.

"""Tests for _run.py helper functions and FlowState."""

from agent_framework import ChatMessage, Content

from agent_framework_ag_ui._run import (
    FlowState,
    _build_safe_metadata,
    _create_state_context_message,
    _has_only_tool_calls,
    _inject_state_context,
    _should_suppress_intermediate_snapshot,
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
        from agent_framework import Role

        state = {"document": "Hello world"}
        schema = {"properties": {"document": {"type": "string"}}}

        result = _create_state_context_message(state, schema)

        assert result is not None
        assert result.role == Role.SYSTEM
        assert len(result.contents) == 1
        assert "Hello world" in result.contents[0].text
        assert "Current state" in result.contents[0].text


class TestInjectStateContext:
    """Tests for _inject_state_context function."""

    def test_no_state_message(self):
        """Returns original messages when no state context needed."""
        messages = [ChatMessage(role="user", contents=[Content.from_text("Hello")])]
        result = _inject_state_context(messages, {}, {})
        assert result == messages

    def test_empty_messages(self):
        """Returns empty list for empty messages."""
        result = _inject_state_context([], {"key": "value"}, {"properties": {}})
        assert result == []

    def test_last_message_not_user(self):
        """Returns original messages when last message is not from user."""
        messages = [
            ChatMessage(role="user", contents=[Content.from_text("Hello")]),
            ChatMessage(role="assistant", contents=[Content.from_text("Hi")]),
        ]
        state = {"key": "value"}
        schema = {"properties": {"key": {"type": "string"}}}

        result = _inject_state_context(messages, state, schema)
        assert result == messages

    def test_injects_before_last_user_message(self):
        """Injects state context before last user message."""
        from agent_framework import Role

        messages = [
            ChatMessage(role="system", contents=[Content.from_text("You are helpful")]),
            ChatMessage(role="user", contents=[Content.from_text("Hello")]),
        ]
        state = {"document": "content"}
        schema = {"properties": {"document": {"type": "string"}}}

        result = _inject_state_context(messages, state, schema)

        assert len(result) == 3
        # System message first
        assert result[0].role == Role.SYSTEM
        assert "helpful" in result[0].contents[0].text
        # State context second
        assert result[1].role == Role.SYSTEM
        assert "Current state" in result[1].contents[0].text
        # User message last
        assert result[2].role == Role.USER
        assert "Hello" in result[2].contents[0].text


# Additional tests for _run.py functions


def test_emit_text_basic():
    """Test _emit_text emits correct events."""
    from agent_framework_ag_ui._run import _emit_text

    flow = FlowState()
    content = Content.from_text("Hello world")

    events = _emit_text(content, flow)

    assert len(events) == 2  # TextMessageStartEvent + TextMessageContentEvent
    assert flow.message_id is not None
    assert flow.accumulated_text == "Hello world"


def test_emit_text_skip_empty():
    """Test _emit_text skips empty text."""
    from agent_framework_ag_ui._run import _emit_text

    flow = FlowState()
    content = Content.from_text("")

    events = _emit_text(content, flow)

    assert len(events) == 0


def test_emit_text_continues_existing_message():
    """Test _emit_text continues existing message."""
    from agent_framework_ag_ui._run import _emit_text

    flow = FlowState()
    flow.message_id = "existing-id"
    content = Content.from_text("more text")

    events = _emit_text(content, flow)

    assert len(events) == 1  # Only TextMessageContentEvent, no new start
    assert flow.message_id == "existing-id"


def test_emit_text_skips_when_waiting_for_approval():
    """Test _emit_text skips when waiting for approval."""
    from agent_framework_ag_ui._run import _emit_text

    flow = FlowState()
    flow.waiting_for_approval = True
    content = Content.from_text("should skip")

    events = _emit_text(content, flow)

    assert len(events) == 0


def test_emit_text_skips_when_skip_text_flag():
    """Test _emit_text skips with skip_text flag."""
    from agent_framework_ag_ui._run import _emit_text

    flow = FlowState()
    content = Content.from_text("should skip")

    events = _emit_text(content, flow, skip_text=True)

    assert len(events) == 0


def test_emit_tool_call_basic():
    """Test _emit_tool_call emits correct events."""
    from agent_framework_ag_ui._run import _emit_tool_call

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
    from agent_framework_ag_ui._run import _emit_tool_call

    flow = FlowState()
    # Create content without call_id
    content = Content(type="function_call", name="test_tool", arguments="{}")

    events = _emit_tool_call(content, flow)

    assert len(events) >= 1
    assert flow.tool_call_id is not None  # ID should be generated


def test_extract_approved_state_updates_no_handler():
    """Test _extract_approved_state_updates returns empty with no handler."""
    from agent_framework_ag_ui._run import _extract_approved_state_updates

    messages = [ChatMessage(role="user", contents=[Content.from_text("Hello")])]
    result = _extract_approved_state_updates(messages, None)
    assert result == {}


def test_extract_approved_state_updates_no_approval():
    """Test _extract_approved_state_updates returns empty when no approval content."""
    from agent_framework_ag_ui._orchestration._predictive_state import PredictiveStateHandler
    from agent_framework_ag_ui._run import _extract_approved_state_updates

    handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "content"}})
    messages = [ChatMessage(role="user", contents=[Content.from_text("Hello")])]
    result = _extract_approved_state_updates(messages, handler)
    assert result == {}
