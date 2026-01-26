# Copyright (c) Microsoft. All rights reserved.

"""Tests for orchestration helper functions."""

from agent_framework import ChatMessage, Content

from agent_framework_ag_ui._orchestration._helpers import (
    approval_steps,
    build_safe_metadata,
    ensure_tool_call_entry,
    is_state_context_message,
    is_step_based_approval,
    latest_approval_response,
    pending_tool_call_ids,
    schema_has_steps,
    select_approval_tool_name,
    tool_name_for_call_id,
)


class TestPendingToolCallIds:
    """Tests for pending_tool_call_ids function."""

    def test_empty_messages(self):
        """Returns empty set for empty messages list."""
        result = pending_tool_call_ids([])
        assert result == set()

    def test_no_tool_calls(self):
        """Returns empty set when no tool calls in messages."""
        messages = [
            ChatMessage(role="user", contents=[Content.from_text("Hello")]),
            ChatMessage(role="assistant", contents=[Content.from_text("Hi there")]),
        ]
        result = pending_tool_call_ids(messages)
        assert result == set()

    def test_pending_tool_call(self):
        """Returns pending tool call ID when no result exists."""
        messages = [
            ChatMessage(
                role="assistant",
                contents=[Content.from_function_call(call_id="call_123", name="get_weather", arguments="{}")],
            ),
        ]
        result = pending_tool_call_ids(messages)
        assert result == {"call_123"}

    def test_resolved_tool_call(self):
        """Returns empty set when tool call has result."""
        messages = [
            ChatMessage(
                role="assistant",
                contents=[Content.from_function_call(call_id="call_123", name="get_weather", arguments="{}")],
            ),
            ChatMessage(
                role="tool",
                contents=[Content.from_function_result(call_id="call_123", result="sunny")],
            ),
        ]
        result = pending_tool_call_ids(messages)
        assert result == set()

    def test_multiple_tool_calls_some_resolved(self):
        """Returns only unresolved tool call IDs."""
        messages = [
            ChatMessage(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="call_1", name="tool_a", arguments="{}"),
                    Content.from_function_call(call_id="call_2", name="tool_b", arguments="{}"),
                    Content.from_function_call(call_id="call_3", name="tool_c", arguments="{}"),
                ],
            ),
            ChatMessage(
                role="tool",
                contents=[Content.from_function_result(call_id="call_1", result="result_a")],
            ),
            ChatMessage(
                role="tool",
                contents=[Content.from_function_result(call_id="call_3", result="result_c")],
            ),
        ]
        result = pending_tool_call_ids(messages)
        assert result == {"call_2"}


class TestIsStateContextMessage:
    """Tests for is_state_context_message function."""

    def test_state_context_message(self):
        """Returns True for state context message."""
        message = ChatMessage(
            role="system",
            contents=[Content.from_text("Current state of the application: {}")],
        )
        assert is_state_context_message(message) is True

    def test_non_system_message(self):
        """Returns False for non-system message."""
        message = ChatMessage(
            role="user",
            contents=[Content.from_text("Current state of the application: {}")],
        )
        assert is_state_context_message(message) is False

    def test_system_message_without_state_prefix(self):
        """Returns False for system message without state prefix."""
        message = ChatMessage(
            role="system",
            contents=[Content.from_text("You are a helpful assistant.")],
        )
        assert is_state_context_message(message) is False

    def test_empty_contents(self):
        """Returns False for message with empty contents."""
        message = ChatMessage(role="system", contents=[])
        assert is_state_context_message(message) is False


class TestEnsureToolCallEntry:
    """Tests for ensure_tool_call_entry function."""

    def test_creates_new_entry(self):
        """Creates new entry when ID not found."""
        tool_calls_by_id: dict = {}
        pending_tool_calls: list = []

        entry = ensure_tool_call_entry("call_123", tool_calls_by_id, pending_tool_calls)

        assert entry["id"] == "call_123"
        assert entry["type"] == "function"
        assert entry["function"]["name"] == ""
        assert entry["function"]["arguments"] == ""
        assert "call_123" in tool_calls_by_id
        assert len(pending_tool_calls) == 1

    def test_returns_existing_entry(self):
        """Returns existing entry when ID found."""
        existing_entry = {
            "id": "call_123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city": "NYC"}'},
        }
        tool_calls_by_id = {"call_123": existing_entry}
        pending_tool_calls: list = []

        entry = ensure_tool_call_entry("call_123", tool_calls_by_id, pending_tool_calls)

        assert entry is existing_entry
        assert entry["function"]["name"] == "get_weather"
        assert len(pending_tool_calls) == 0  # Not added again


class TestToolNameForCallId:
    """Tests for tool_name_for_call_id function."""

    def test_returns_tool_name(self):
        """Returns tool name for valid entry."""
        tool_calls_by_id = {
            "call_123": {
                "id": "call_123",
                "function": {"name": "get_weather", "arguments": "{}"},
            }
        }
        result = tool_name_for_call_id(tool_calls_by_id, "call_123")
        assert result == "get_weather"

    def test_returns_none_for_missing_id(self):
        """Returns None when ID not found."""
        tool_calls_by_id: dict = {}
        result = tool_name_for_call_id(tool_calls_by_id, "call_123")
        assert result is None

    def test_returns_none_for_missing_function(self):
        """Returns None when function key missing."""
        tool_calls_by_id = {"call_123": {"id": "call_123"}}
        result = tool_name_for_call_id(tool_calls_by_id, "call_123")
        assert result is None

    def test_returns_none_for_non_dict_function(self):
        """Returns None when function is not a dict."""
        tool_calls_by_id = {"call_123": {"id": "call_123", "function": "not_a_dict"}}
        result = tool_name_for_call_id(tool_calls_by_id, "call_123")
        assert result is None

    def test_returns_none_for_empty_name(self):
        """Returns None when name is empty."""
        tool_calls_by_id = {"call_123": {"id": "call_123", "function": {"name": "", "arguments": "{}"}}}
        result = tool_name_for_call_id(tool_calls_by_id, "call_123")
        assert result is None


class TestSchemaHasSteps:
    """Tests for schema_has_steps function."""

    def test_schema_with_steps_array(self):
        """Returns True when schema has steps array property."""
        schema = {"properties": {"steps": {"type": "array"}}}
        assert schema_has_steps(schema) is True

    def test_schema_without_steps(self):
        """Returns False when schema doesn't have steps."""
        schema = {"properties": {"name": {"type": "string"}}}
        assert schema_has_steps(schema) is False

    def test_schema_with_non_array_steps(self):
        """Returns False when steps is not array type."""
        schema = {"properties": {"steps": {"type": "string"}}}
        assert schema_has_steps(schema) is False

    def test_non_dict_schema(self):
        """Returns False for non-dict schema."""
        assert schema_has_steps(None) is False
        assert schema_has_steps("not a dict") is False
        assert schema_has_steps([]) is False

    def test_missing_properties(self):
        """Returns False when properties key is missing."""
        schema = {"type": "object"}
        assert schema_has_steps(schema) is False

    def test_non_dict_properties(self):
        """Returns False when properties is not a dict."""
        schema = {"properties": "not a dict"}
        assert schema_has_steps(schema) is False

    def test_non_dict_steps(self):
        """Returns False when steps is not a dict."""
        schema = {"properties": {"steps": "not a dict"}}
        assert schema_has_steps(schema) is False


class TestSelectApprovalToolName:
    """Tests for select_approval_tool_name function."""

    def test_none_client_tools(self):
        """Returns None when client_tools is None."""
        result = select_approval_tool_name(None)
        assert result is None

    def test_empty_client_tools(self):
        """Returns None when client_tools is empty."""
        result = select_approval_tool_name([])
        assert result is None

    def test_finds_approval_tool(self):
        """Returns tool name when tool has steps schema."""

        class MockTool:
            name = "generate_task_steps"

            def parameters(self):
                return {"properties": {"steps": {"type": "array"}}}

        result = select_approval_tool_name([MockTool()])
        assert result == "generate_task_steps"

    def test_skips_tool_without_name(self):
        """Skips tools without name attribute."""

        class MockToolNoName:
            def parameters(self):
                return {"properties": {"steps": {"type": "array"}}}

        result = select_approval_tool_name([MockToolNoName()])
        assert result is None

    def test_skips_tool_without_parameters_method(self):
        """Skips tools without callable parameters method."""

        class MockToolNoParams:
            name = "some_tool"
            parameters = "not callable"

        result = select_approval_tool_name([MockToolNoParams()])
        assert result is None

    def test_skips_tool_without_steps_schema(self):
        """Skips tools that don't have steps in schema."""

        class MockToolNoSteps:
            name = "other_tool"

            def parameters(self):
                return {"properties": {"data": {"type": "string"}}}

        result = select_approval_tool_name([MockToolNoSteps()])
        assert result is None


class TestBuildSafeMetadata:
    """Tests for build_safe_metadata function."""

    def test_none_metadata(self):
        """Returns empty dict for None metadata."""
        result = build_safe_metadata(None)
        assert result == {}

    def test_empty_metadata(self):
        """Returns empty dict for empty metadata."""
        result = build_safe_metadata({})
        assert result == {}

    def test_string_values_under_limit(self):
        """Preserves string values under 512 chars."""
        metadata = {"key1": "short value", "key2": "another value"}
        result = build_safe_metadata(metadata)
        assert result == metadata

    def test_truncates_long_string_values(self):
        """Truncates string values over 512 chars."""
        long_value = "x" * 1000
        metadata = {"key": long_value}
        result = build_safe_metadata(metadata)
        assert len(result["key"]) == 512
        assert result["key"] == "x" * 512

    def test_non_string_values_serialized(self):
        """Serializes non-string values to JSON."""
        metadata = {"count": 42, "items": ["a", "b"]}
        result = build_safe_metadata(metadata)
        assert result["count"] == "42"
        assert result["items"] == '["a", "b"]'

    def test_truncates_serialized_values(self):
        """Truncates serialized JSON values over 512 chars."""
        long_list = list(range(200))  # Will serialize to >512 chars
        metadata = {"data": long_list}
        result = build_safe_metadata(metadata)
        assert len(result["data"]) == 512


class TestLatestApprovalResponse:
    """Tests for latest_approval_response function."""

    def test_empty_messages(self):
        """Returns None for empty messages."""
        result = latest_approval_response([])
        assert result is None

    def test_no_approval_response(self):
        """Returns None when no approval response in last message."""
        messages = [
            ChatMessage(role="assistant", contents=[Content.from_text("Hello")]),
        ]
        result = latest_approval_response(messages)
        assert result is None

    def test_finds_approval_response(self):
        """Returns approval response from last message."""
        # Create a function call content first
        fc = Content.from_function_call(call_id="call_123", name="test_tool", arguments="{}")
        approval_content = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        messages = [
            ChatMessage(role="user", contents=[approval_content]),
        ]
        result = latest_approval_response(messages)
        assert result is approval_content


class TestApprovalSteps:
    """Tests for approval_steps function."""

    def test_steps_from_ag_ui_state_args(self):
        """Extracts steps from ag_ui_state_args."""
        fc = Content.from_function_call(call_id="call_123", name="test_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
            additional_properties={"ag_ui_state_args": {"steps": [{"id": 1}, {"id": 2}]}},
        )
        result = approval_steps(approval)
        assert result == [{"id": 1}, {"id": 2}]

    def test_steps_from_function_call(self):
        """Extracts steps from function call arguments."""
        fc = Content.from_function_call(
            call_id="call_123",
            name="test",
            arguments='{"steps": [{"step": 1}]}',
        )
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        result = approval_steps(approval)
        assert result == [{"step": 1}]

    def test_empty_steps_when_no_state_args(self):
        """Returns empty list when no ag_ui_state_args."""
        fc = Content.from_function_call(call_id="call_123", name="test_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        result = approval_steps(approval)
        assert result == []

    def test_empty_steps_when_state_args_not_dict(self):
        """Returns empty list when ag_ui_state_args is not a dict."""
        fc = Content.from_function_call(call_id="call_123", name="test_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
            additional_properties={"ag_ui_state_args": "not a dict"},
        )
        result = approval_steps(approval)
        assert result == []

    def test_empty_steps_when_steps_not_list(self):
        """Returns empty list when steps is not a list."""
        fc = Content.from_function_call(call_id="call_123", name="test_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
            additional_properties={"ag_ui_state_args": {"steps": "not a list"}},
        )
        result = approval_steps(approval)
        assert result == []


class TestIsStepBasedApproval:
    """Tests for is_step_based_approval function."""

    def test_returns_true_when_has_steps(self):
        """Returns True when approval has steps."""
        fc = Content.from_function_call(call_id="call_123", name="test_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
            additional_properties={"ag_ui_state_args": {"steps": [{"id": 1}]}},
        )
        result = is_step_based_approval(approval, None)
        assert result is True

    def test_returns_false_no_steps_no_function_call(self):
        """Returns False when no steps and no function call."""
        # Create content directly to have no function_call
        approval = Content(
            type="function_approval_response",
            function_call=None,
        )
        result = is_step_based_approval(approval, None)
        assert result is False

    def test_returns_false_no_predict_config(self):
        """Returns False when no predict_state_config."""
        fc = Content.from_function_call(call_id="call_123", name="some_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        result = is_step_based_approval(approval, None)
        assert result is False

    def test_returns_true_when_tool_matches_config(self):
        """Returns True when tool matches predict_state_config with steps."""
        fc = Content.from_function_call(call_id="call_123", name="generate_steps", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        config = {"steps": {"tool": "generate_steps", "tool_argument": "steps"}}
        result = is_step_based_approval(approval, config)
        assert result is True

    def test_returns_false_when_tool_not_in_config(self):
        """Returns False when tool not in predict_state_config."""
        fc = Content.from_function_call(call_id="call_123", name="other_tool", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        config = {"steps": {"tool": "generate_steps", "tool_argument": "steps"}}
        result = is_step_based_approval(approval, config)
        assert result is False

    def test_returns_false_when_tool_arg_not_steps(self):
        """Returns False when tool_argument is not 'steps'."""
        fc = Content.from_function_call(call_id="call_123", name="generate_steps", arguments="{}")
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval_123",
            function_call=fc,
        )
        config = {"document": {"tool": "generate_steps", "tool_argument": "content"}}
        result = is_step_based_approval(approval, config)
        assert result is False
