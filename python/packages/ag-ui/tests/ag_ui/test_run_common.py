# Copyright (c) Microsoft. All rights reserved.

"""Tests for _run_common.py edge cases."""

from agent_framework import Content

from agent_framework_ag_ui._run_common import (
    FlowState,
    _emit_tool_result,
    _extract_resume_payload,
    _normalize_resume_interrupts,
)


class TestNormalizeResumeInterrupts:
    """Tests for _normalize_resume_interrupts edge cases."""

    def test_plain_list_of_dicts(self):
        """Resume payload as a plain list of interrupt dicts."""
        result = _normalize_resume_interrupts([{"id": "x", "value": "y"}])
        assert result == [{"id": "x", "value": "y"}]

    def test_dict_with_singular_interrupt_key(self):
        """Resume dict using 'interrupt' (singular) instead of 'interrupts'."""
        result = _normalize_resume_interrupts({"interrupt": [{"id": "x", "value": "y"}]})
        assert result == [{"id": "x", "value": "y"}]

    def test_dict_without_interrupts_key_wraps_as_candidate(self):
        """Resume dict without interrupts/interrupt key wraps the dict itself."""
        result = _normalize_resume_interrupts({"id": "x", "value": "y"})
        assert result == [{"id": "x", "value": "y"}]

    def test_non_dict_items_in_list_are_skipped(self):
        """Non-dict items in candidate list are silently skipped."""
        result = _normalize_resume_interrupts([None, "string", {"id": "x", "value": "y"}])
        assert result == [{"id": "x", "value": "y"}]

    def test_items_missing_id_are_skipped(self):
        """Dict items without any id field are skipped."""
        result = _normalize_resume_interrupts([{"name": "test"}])
        assert result == []

    def test_response_key_used_as_value(self):
        """'response' key is used as value when 'value' is absent."""
        result = _normalize_resume_interrupts([{"id": "x", "response": "approved"}])
        assert result == [{"id": "x", "value": "approved"}]

    def test_neither_value_nor_response_uses_remaining_fields(self):
        """When neither 'value' nor 'response' key exists, remaining fields become value."""
        result = _normalize_resume_interrupts([{"id": "x", "extra": "data", "more": 42}])
        assert result == [{"id": "x", "value": {"extra": "data", "more": 42}}]

    def test_none_payload_returns_empty(self):
        """None resume payload returns empty list."""
        assert _normalize_resume_interrupts(None) == []

    def test_non_dict_non_list_returns_empty(self):
        """Non-dict, non-list payload returns empty list."""
        assert _normalize_resume_interrupts(42) == []

    def test_interrupt_id_key_used_as_id(self):
        """interruptId key is accepted as identifier."""
        result = _normalize_resume_interrupts([{"interruptId": "abc", "value": "yes"}])
        assert result == [{"id": "abc", "value": "yes"}]

    def test_tool_call_id_key_used_as_id(self):
        """toolCallId key is accepted as identifier."""
        result = _normalize_resume_interrupts([{"toolCallId": "tc1", "value": "done"}])
        assert result == [{"id": "tc1", "value": "done"}]


class TestExtractResumePayload:
    """Tests for _extract_resume_payload edge cases."""

    def test_forwarded_props_resume_not_nested_in_command(self):
        """forwarded_props.resume (not nested in command) is extracted."""
        result = _extract_resume_payload({"forwarded_props": {"resume": "data"}})
        assert result == "data"

    def test_forwarded_props_not_dict_returns_none(self):
        """Non-dict forwarded_props returns None."""
        result = _extract_resume_payload({"forwarded_props": "string"})
        assert result is None

    def test_resume_key_has_priority(self):
        """Direct resume key takes priority over forwarded_props."""
        result = _extract_resume_payload({"resume": "direct", "forwarded_props": {"resume": "fp"}})
        assert result == "direct"

    def test_no_resume_at_all(self):
        """No resume key anywhere returns None."""
        result = _extract_resume_payload({"messages": []})
        assert result is None

    def test_forwarded_props_camelcase(self):
        """camelCase forwardedProps is also supported."""
        result = _extract_resume_payload({"forwardedProps": {"resume": "camel"}})
        assert result == "camel"


class TestEmitToolResult:
    """Tests for _emit_tool_result edge cases."""

    def test_tool_result_without_call_id_returns_empty(self):
        """Tool result Content without call_id returns empty event list."""
        content = Content.from_function_result(call_id=None, result="some result")
        flow = FlowState()
        events = _emit_tool_result(content, flow)
        assert events == []

    def test_tool_result_closes_open_text_message(self):
        """Tool result closes any open text message (issue #3568 fix)."""
        content = Content.from_function_result(call_id="call_1", result="done")
        flow = FlowState(message_id="msg_1", accumulated_text="Hello")
        events = _emit_tool_result(content, flow)

        event_types = [e.type for e in events]
        assert "TOOL_CALL_END" in event_types
        assert "TOOL_CALL_RESULT" in event_types
        assert "TEXT_MESSAGE_END" in event_types
        assert flow.message_id is None
        assert flow.accumulated_text == ""
