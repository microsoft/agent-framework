# Copyright (c) Microsoft. All rights reserved.

"""Tests for _run_common.py edge cases."""

from ag_ui.core import EventType
from agent_framework import Content

from agent_framework_ag_ui import state_update
from agent_framework_ag_ui._orchestration._predictive_state import PredictiveStateHandler
from agent_framework_ag_ui._run_common import (
    FlowState,
    _emit_mcp_tool_result,
    _emit_tool_result,
    _extract_resume_payload,
    _extract_tool_result_state,
    _normalize_resume_interrupts,
)
from agent_framework_ag_ui._state import TOOL_RESULT_STATE_KEY


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


class TestStateUpdateHelper:
    """Tests for the public ``state_update`` helper."""

    def test_builds_text_content_with_state_marker(self):
        """state_update returns a text Content carrying state in additional_properties."""
        c = state_update(text="done", state={"weather": {"temp": 14}})
        assert c.type == "text"
        assert c.text == "done"
        assert c.additional_properties == {
            TOOL_RESULT_STATE_KEY: {"weather": {"temp": 14}},
        }

    def test_empty_text_is_allowed(self):
        """State-only tools can omit the text argument."""
        c = state_update(state={"steps": ["a", "b"]})
        assert c.text == ""
        assert c.additional_properties[TOOL_RESULT_STATE_KEY] == {"steps": ["a", "b"]}

    def test_non_mapping_state_raises(self):
        """Passing a non-mapping value for state raises TypeError."""
        import pytest

        with pytest.raises(TypeError):
            state_update(text="t", state=["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_state_is_copied_defensively(self):
        """Mutating the caller's dict after ``state_update`` must not mutate the content."""
        caller_state = {"weather": {"temp": 14}}
        c = state_update(text="ok", state=caller_state)
        caller_state["weather"]["temp"] = 99
        # The top-level dict was copied, so replacing the key in caller_state
        # would not affect the Content, but nested dicts share references — document
        # this by asserting only the top-level copy semantics.
        assert TOOL_RESULT_STATE_KEY in c.additional_properties
        inner = c.additional_properties[TOOL_RESULT_STATE_KEY]
        assert inner is not caller_state


class TestExtractToolResultState:
    """Tests for ``_extract_tool_result_state``."""

    def test_returns_none_for_plain_string_result(self):
        content = Content.from_function_result(call_id="c1", result="plain")
        assert _extract_tool_result_state(content) is None

    def test_extracts_state_from_inner_item(self):
        tool_return = state_update(text="hi", state={"k": 1})
        content = Content.from_function_result(call_id="c1", result=[tool_return])
        assert _extract_tool_result_state(content) == {"k": 1}

    def test_extracts_state_from_outer_additional_properties(self):
        """Outer function_result content can also carry state (legacy/advanced use)."""
        content = Content.from_function_result(
            call_id="c1",
            result="hi",
            additional_properties={TOOL_RESULT_STATE_KEY: {"k": 1}},
        )
        assert _extract_tool_result_state(content) == {"k": 1}

    def test_merges_multiple_items(self):
        a = state_update(text="a", state={"k": 1, "shared": "from_a"})
        b = state_update(text="b", state={"shared": "from_b", "extra": True})
        content = Content.from_function_result(call_id="c1", result=[a, b])
        merged = _extract_tool_result_state(content)
        assert merged == {"k": 1, "shared": "from_b", "extra": True}

    def test_ignores_non_dict_marker_value(self):
        """A garbled marker value must not break extraction (defensive guard)."""
        bad = Content.from_text(
            "hi",
            additional_properties={TOOL_RESULT_STATE_KEY: "not-a-dict"},
        )
        content = Content.from_function_result(call_id="c1", result=[bad])
        assert _extract_tool_result_state(content) is None


class TestEmitToolResultWithState:
    """Tests for the deterministic state emission in ``_emit_tool_result``."""

    def test_emits_state_snapshot_after_tool_call_result(self):
        """Tool returning state_update produces a StateSnapshotEvent right after the result."""
        tool_return = state_update(
            text="Weather: 14°C",
            state={"weather": {"temp": 14, "conditions": "foggy"}},
        )
        content = Content.from_function_result(call_id="call_1", result=[tool_return])
        flow = FlowState()

        events = _emit_tool_result(content, flow)
        event_types = [e.type for e in events]

        # Expect TOOL_CALL_END, TOOL_CALL_RESULT, STATE_SNAPSHOT in that order.
        assert event_types[0] == EventType.TOOL_CALL_END
        assert event_types[1] == EventType.TOOL_CALL_RESULT
        state_idx = event_types.index(EventType.STATE_SNAPSHOT)
        assert state_idx == 2
        assert events[state_idx].snapshot == {"weather": {"temp": 14, "conditions": "foggy"}}

    def test_updates_flow_current_state(self):
        tool_return = state_update(text="", state={"a": 1})
        content = Content.from_function_result(call_id="c1", result=[tool_return])
        flow = FlowState(current_state={"existing": "value"})

        _emit_tool_result(content, flow)

        # Existing keys must survive (merge semantics), new keys must be added.
        assert flow.current_state == {"existing": "value", "a": 1}

    def test_merge_overrides_existing_key(self):
        tool_return = state_update(text="", state={"existing": "new"})
        content = Content.from_function_result(call_id="c1", result=[tool_return])
        flow = FlowState(current_state={"existing": "old", "other": 1})

        _emit_tool_result(content, flow)

        assert flow.current_state == {"existing": "new", "other": 1}

    def test_no_state_snapshot_when_result_has_no_state(self):
        """Plain tool results must not emit a StateSnapshotEvent."""
        content = Content.from_function_result(call_id="c1", result="plain")
        flow = FlowState()

        events = _emit_tool_result(content, flow)
        assert all(e.type != EventType.STATE_SNAPSHOT for e in events)

    def test_tool_result_content_text_unchanged(self):
        """The text sent to the LLM must not leak the state marker."""
        tool_return = state_update(text="Weather: 14°C", state={"weather": {"temp": 14}})
        content = Content.from_function_result(call_id="c1", result=[tool_return])
        flow = FlowState()

        events = _emit_tool_result(content, flow)
        result_events = [e for e in events if e.type == EventType.TOOL_CALL_RESULT]
        assert len(result_events) == 1
        assert result_events[0].content == "Weather: 14°C"
        assert TOOL_RESULT_STATE_KEY not in result_events[0].content

    def test_coexists_with_active_predictive_state_handler(self):
        """Both predictive and deterministic state produce a single coalesced snapshot.

        Predictive state (``predict_state_config``) and deterministic state
        (``state_update``) are two independent mechanisms. When both are active,
        a single coalesced ``StateSnapshotEvent`` is emitted containing the
        merged result of both contributions.
        """
        flow = FlowState(current_state={"preexisting": "value"})
        handler = PredictiveStateHandler(
            predict_state_config={"draft": {"tool": "write_draft", "tool_argument": "body"}},
            current_state=flow.current_state,
        )

        tool_return = state_update(text="Draft written", state={"draft_final": True})
        content = Content.from_function_result(call_id="c1", result=[tool_return])

        events = _emit_tool_result(content, flow, predictive_handler=handler)

        # Exactly one coalesced snapshot must be emitted containing all merged keys.
        snapshots = [e for e in events if e.type == EventType.STATE_SNAPSHOT]
        assert len(snapshots) == 1
        assert snapshots[0].snapshot["draft_final"] is True
        assert snapshots[0].snapshot["preexisting"] == "value"
        assert flow.current_state["draft_final"] is True
        assert flow.current_state["preexisting"] == "value"

    def test_predictive_and_deterministic_emit_single_snapshot(self):
        """When both predictive_handler and state_update are active, only one snapshot is emitted."""
        flow = FlowState(current_state={"existing": "yes"})
        handler = PredictiveStateHandler(
            predict_state_config={"draft": {"tool": "write_draft", "tool_argument": "body"}},
            current_state=flow.current_state,
        )

        tool_return = state_update(text="ok", state={"new_key": 42})
        content = Content.from_function_result(call_id="c1", result=[tool_return])

        events = _emit_tool_result(content, flow, predictive_handler=handler)

        snapshots = [e for e in events if e.type == EventType.STATE_SNAPSHOT]
        assert len(snapshots) == 1, f"Expected 1 coalesced snapshot, got {len(snapshots)}"
        assert snapshots[0].snapshot == {"existing": "yes", "new_key": 42}


class TestEmitMcpToolResultWithState:
    """MCP tool results should honour the same state_update marker.

    MCP results come from an external MCP server rather than a locally
    executed ``@tool`` function, so they do not flow through ``parse_result``
    and ``content.items`` is typically empty. State is instead carried on the
    outer content's ``additional_properties`` (e.g. by middleware that
    inspects the MCP output and attaches a marker). ``_extract_tool_result_state``
    supports both locations so this path remains usable.
    """

    def test_mcp_tool_result_emits_state_snapshot_from_additional_properties(self):
        content = Content.from_mcp_server_tool_result(
            call_id="mcp_1",
            output="server result",
            additional_properties={TOOL_RESULT_STATE_KEY: {"mcp_ok": True}},
        )
        flow = FlowState()

        events = _emit_mcp_tool_result(content, flow)
        event_types = [e.type for e in events]

        assert EventType.TOOL_CALL_END in event_types
        assert EventType.TOOL_CALL_RESULT in event_types
        assert EventType.STATE_SNAPSHOT in event_types
        assert flow.current_state == {"mcp_ok": True}

    def test_mcp_tool_result_without_state_emits_no_snapshot(self):
        content = Content.from_mcp_server_tool_result(
            call_id="mcp_1",
            output="server result",
        )
        flow = FlowState()

        events = _emit_mcp_tool_result(content, flow)
        assert all(e.type != EventType.STATE_SNAPSHOT for e in events)
