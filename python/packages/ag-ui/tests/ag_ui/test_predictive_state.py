# Copyright (c) Microsoft. All rights reserved.

"""Tests for predictive state handling."""

from ag_ui.core import StateDeltaEvent

from agent_framework_ag_ui._orchestration._predictive_state import PredictiveStateHandler


class TestPredictiveStateHandlerInit:
    """Tests for PredictiveStateHandler initialization."""

    def test_default_init(self):
        """Initializes with default values."""
        handler = PredictiveStateHandler()
        assert handler.predict_state_config == {}
        assert handler.current_state == {}
        assert handler.streaming_tool_args == ""
        assert handler.last_emitted_state == {}
        assert handler.state_delta_count == 0
        assert handler.pending_state_updates == {}

    def test_init_with_config(self):
        """Initializes with provided config."""
        config = {"document": {"tool": "write_doc", "tool_argument": "content"}}
        state = {"document": "initial"}
        handler = PredictiveStateHandler(predict_state_config=config, current_state=state)
        assert handler.predict_state_config == config
        assert handler.current_state == state


class TestResetStreaming:
    """Tests for reset_streaming method."""

    def test_resets_streaming_state(self):
        """Resets streaming-related state."""
        handler = PredictiveStateHandler()
        handler.streaming_tool_args = "some accumulated args"
        handler.state_delta_count = 5

        handler.reset_streaming()

        assert handler.streaming_tool_args == ""
        assert handler.state_delta_count == 0


class TestExtractStateValue:
    """Tests for extract_state_value method."""

    def test_no_config(self):
        """Returns None when no config."""
        handler = PredictiveStateHandler()
        result = handler.extract_state_value("some_tool", {"arg": "value"})
        assert result is None

    def test_no_args(self):
        """Returns None when args is None."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "tool", "tool_argument": "arg"}})
        result = handler.extract_state_value("tool", None)
        assert result is None

    def test_empty_args(self):
        """Returns None when args is empty string."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "tool", "tool_argument": "arg"}})
        result = handler.extract_state_value("tool", "")
        assert result is None

    def test_tool_not_in_config(self):
        """Returns None when tool not in config."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "other_tool", "tool_argument": "arg"}})
        result = handler.extract_state_value("some_tool", {"arg": "value"})
        assert result is None

    def test_extracts_specific_argument(self):
        """Extracts value from specific tool argument."""
        handler = PredictiveStateHandler(
            predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}}
        )
        result = handler.extract_state_value("write_doc", {"content": "Hello world"})
        assert result == ("document", "Hello world")

    def test_extracts_with_wildcard(self):
        """Extracts entire args with * wildcard."""
        handler = PredictiveStateHandler(predict_state_config={"data": {"tool": "update_data", "tool_argument": "*"}})
        args = {"key1": "value1", "key2": "value2"}
        result = handler.extract_state_value("update_data", args)
        assert result == ("data", args)

    def test_extracts_from_json_string(self):
        """Extracts value from JSON string args."""
        handler = PredictiveStateHandler(
            predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}}
        )
        result = handler.extract_state_value("write_doc", '{"content": "Hello world"}')
        assert result == ("document", "Hello world")

    def test_argument_not_in_args(self):
        """Returns None when tool_argument not in args."""
        handler = PredictiveStateHandler(
            predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}}
        )
        result = handler.extract_state_value("write_doc", {"other": "value"})
        assert result is None


class TestIsPredictiveTool:
    """Tests for is_predictive_tool method."""

    def test_none_tool_name(self):
        """Returns False for None tool name."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "some_tool", "tool_argument": "arg"}})
        assert handler.is_predictive_tool(None) is False

    def test_no_config(self):
        """Returns False when no config."""
        handler = PredictiveStateHandler()
        assert handler.is_predictive_tool("some_tool") is False

    def test_tool_in_config(self):
        """Returns True when tool is in config."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "some_tool", "tool_argument": "arg"}})
        assert handler.is_predictive_tool("some_tool") is True

    def test_tool_not_in_config(self):
        """Returns False when tool not in config."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "other_tool", "tool_argument": "arg"}})
        assert handler.is_predictive_tool("some_tool") is False


class TestEmitStreamingDeltas:
    """Tests for emit_streaming_deltas method."""

    def test_no_tool_name(self):
        """Returns empty list for None tool name."""
        handler = PredictiveStateHandler(predict_state_config={"key": {"tool": "tool", "tool_argument": "arg"}})
        result = handler.emit_streaming_deltas(None, '{"arg": "value"}')
        assert result == []

    def test_no_config(self):
        """Returns empty list when no config."""
        handler = PredictiveStateHandler()
        result = handler.emit_streaming_deltas("some_tool", '{"arg": "value"}')
        assert result == []

    def test_accumulates_args(self):
        """Accumulates argument chunks."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        handler.emit_streaming_deltas("write", '{"text')
        handler.emit_streaming_deltas("write", '": "hello')
        assert handler.streaming_tool_args == '{"text": "hello'

    def test_emits_delta_on_complete_json(self):
        """Emits delta when JSON is complete."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        events = handler.emit_streaming_deltas("write", '{"text": "hello"}')
        assert len(events) == 1
        assert isinstance(events[0], StateDeltaEvent)
        assert events[0].delta[0]["path"] == "/doc"
        assert events[0].delta[0]["value"] == "hello"
        assert events[0].delta[0]["op"] == "replace"

    def test_emits_delta_on_partial_json(self):
        """Emits delta from partial JSON using regex."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        # First chunk - partial
        events = handler.emit_streaming_deltas("write", '{"text": "hel')
        assert len(events) == 1
        assert events[0].delta[0]["value"] == "hel"

    def test_does_not_emit_duplicate_deltas(self):
        """Does not emit delta when value unchanged."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        # First emission
        events1 = handler.emit_streaming_deltas("write", '{"text": "hello"}')
        assert len(events1) == 1

        # Reset and emit same value again
        handler.streaming_tool_args = ""
        events2 = handler.emit_streaming_deltas("write", '{"text": "hello"}')
        assert len(events2) == 0  # No duplicate

    def test_emits_delta_on_value_change(self):
        """Emits delta when value changes."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        # First value
        events1 = handler.emit_streaming_deltas("write", '{"text": "hello"}')
        assert len(events1) == 1

        # Reset and new value
        handler.streaming_tool_args = ""
        events2 = handler.emit_streaming_deltas("write", '{"text": "world"}')
        assert len(events2) == 1
        assert events2[0].delta[0]["value"] == "world"

    def test_tracks_pending_updates(self):
        """Tracks pending state updates."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        handler.emit_streaming_deltas("write", '{"text": "hello"}')
        assert handler.pending_state_updates == {"doc": "hello"}


class TestEmitPartialDeltas:
    """Tests for _emit_partial_deltas method."""

    def test_unescapes_newlines(self):
        """Unescapes \\n in partial values."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        handler.streaming_tool_args = '{"text": "line1\\nline2'
        events = handler._emit_partial_deltas("write")
        assert len(events) == 1
        assert events[0].delta[0]["value"] == "line1\nline2"

    def test_handles_escaped_quotes_partially(self):
        """Handles escaped quotes - regex stops at quote character."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        # The regex pattern [^"]* stops at ANY quote, including escaped ones.
        # This is expected behavior for partial streaming - the full JSON
        # will be parsed correctly when complete.
        handler.streaming_tool_args = '{"text": "say \\"hi'
        events = handler._emit_partial_deltas("write")
        assert len(events) == 1
        # Captures "say \" then the backslash gets converted to empty string
        # by the replace("\\\\", "\\") first, then replace('\\"', '"')
        # but since there's no closing quote, we get "say \"
        # After .replace("\\\\", "\\") -> "say \"
        # After .replace('\\"', '"') -> "say "  (but actually still "say \" due to order)
        # The actual result: backslash is preserved since it's not a valid escape sequence
        assert events[0].delta[0]["value"] == "say \\"

    def test_unescapes_backslashes(self):
        """Unescapes \\\\ in partial values."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        handler.streaming_tool_args = '{"text": "path\\\\to\\\\file'
        events = handler._emit_partial_deltas("write")
        assert len(events) == 1
        assert events[0].delta[0]["value"] == "path\\to\\file"


class TestEmitCompleteDeltas:
    """Tests for _emit_complete_deltas method."""

    def test_emits_for_matching_tool(self):
        """Emits delta for tool matching config."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        events = handler._emit_complete_deltas("write", {"text": "content"})
        assert len(events) == 1
        assert events[0].delta[0]["value"] == "content"

    def test_skips_non_matching_tool(self):
        """Skips tools not matching config."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        events = handler._emit_complete_deltas("other_tool", {"text": "content"})
        assert len(events) == 0

    def test_handles_wildcard_argument(self):
        """Handles * wildcard for entire args."""
        handler = PredictiveStateHandler(predict_state_config={"data": {"tool": "update", "tool_argument": "*"}})
        args = {"key1": "val1", "key2": "val2"}
        events = handler._emit_complete_deltas("update", args)
        assert len(events) == 1
        assert events[0].delta[0]["value"] == args

    def test_skips_missing_argument(self):
        """Skips when tool_argument not in args."""
        handler = PredictiveStateHandler(predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}})
        events = handler._emit_complete_deltas("write", {"other": "value"})
        assert len(events) == 0


class TestCreateDeltaEvent:
    """Tests for _create_delta_event method."""

    def test_creates_event(self):
        """Creates StateDeltaEvent with correct structure."""
        handler = PredictiveStateHandler()
        event = handler._create_delta_event("key", "value")

        assert isinstance(event, StateDeltaEvent)
        assert event.delta[0]["op"] == "replace"
        assert event.delta[0]["path"] == "/key"
        assert event.delta[0]["value"] == "value"

    def test_increments_count(self):
        """Increments state_delta_count."""
        handler = PredictiveStateHandler()
        handler._create_delta_event("key", "value")
        assert handler.state_delta_count == 1
        handler._create_delta_event("key", "value2")
        assert handler.state_delta_count == 2


class TestApplyPendingUpdates:
    """Tests for apply_pending_updates method."""

    def test_applies_pending_to_current(self):
        """Applies pending updates to current state."""
        handler = PredictiveStateHandler(current_state={"existing": "value"})
        handler.pending_state_updates = {"doc": "new content", "count": 5}

        handler.apply_pending_updates()

        assert handler.current_state == {"existing": "value", "doc": "new content", "count": 5}

    def test_clears_pending_updates(self):
        """Clears pending updates after applying."""
        handler = PredictiveStateHandler()
        handler.pending_state_updates = {"doc": "content"}

        handler.apply_pending_updates()

        assert handler.pending_state_updates == {}

    def test_overwrites_existing_keys(self):
        """Overwrites existing keys in current state."""
        handler = PredictiveStateHandler(current_state={"doc": "old"})
        handler.pending_state_updates = {"doc": "new"}

        handler.apply_pending_updates()

        assert handler.current_state["doc"] == "new"
