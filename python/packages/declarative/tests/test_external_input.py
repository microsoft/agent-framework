# Copyright (c) Microsoft. All rights reserved.

"""Tests for human-in-the-loop action handlers."""

import pytest

from agent_framework_declarative._workflows._handlers import ActionContext, get_action_handler
from agent_framework_declarative._workflows._human_input import (
    QuestionRequest,
    process_external_loop,
    validate_input_response,
)
from agent_framework_declarative._workflows._state import WorkflowState


def create_action_context(action: dict, state: WorkflowState | None = None):
    """Create a minimal action context for testing."""
    if state is None:
        state = WorkflowState()

    async def execute_actions(actions, state):
        for act in actions:
            handler = get_action_handler(act.get("kind"))
            if handler:
                async for event in handler(
                    ActionContext(
                        state=state,
                        action=act,
                        execute_actions=execute_actions,
                        agents={},
                        bindings={},
                    )
                ):
                    yield event

    return ActionContext(
        state=state,
        action=action,
        execute_actions=execute_actions,
        agents={},
        bindings={},
    )


class TestQuestionHandler:
    """Tests for Question action handler."""

    @pytest.mark.asyncio
    async def test_question_emits_request_info_event(self):
        """Test that Question handler emits QuestionRequest."""
        ctx = create_action_context({
            "kind": "Question",
            "id": "ask_name",
            "variable": "Local.userName",
            "prompt": "What is your name?",
        })

        handler = get_action_handler("Question")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], QuestionRequest)
        assert events[0].request_id == "ask_name"
        assert events[0].prompt == "What is your name?"
        assert events[0].variable == "Local.userName"

    @pytest.mark.asyncio
    async def test_question_with_choices(self):
        """Test Question with multiple choice options."""
        ctx = create_action_context({
            "kind": "Question",
            "id": "ask_choice",
            "variable": "Local.selection",
            "prompt": "Select an option:",
            "choices": ["Option A", "Option B", "Option C"],
            "default": "Option A",
        })

        handler = get_action_handler("Question")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, QuestionRequest)
        assert event.choices == ["Option A", "Option B", "Option C"]
        assert event.default_value == "Option A"

    @pytest.mark.asyncio
    async def test_question_with_validation(self):
        """Test Question with validation rules."""
        ctx = create_action_context({
            "kind": "Question",
            "id": "ask_email",
            "variable": "Local.email",
            "prompt": "Enter your email:",
            "validation": {
                "required": True,
                "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$",
            },
        })

        handler = get_action_handler("Question")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        event = events[0]
        assert event.validation == {
            "required": True,
            "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$",
        }


class TestRequestExternalInputHandler:
    """Tests for RequestExternalInput action handler."""

    @pytest.mark.asyncio
    async def test_request_external_input(self):
        """Test RequestExternalInput handler emits event."""
        ctx = create_action_context({
            "kind": "RequestExternalInput",
            "id": "get_approval",
            "variable": "Local.approval",
            "prompt": "Please approve or reject",
            "timeout": 300,
        })

        handler = get_action_handler("RequestExternalInput")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, QuestionRequest)
        assert event.request_id == "get_approval"
        assert event.variable == "Local.approval"
        assert event.validation == {"timeout": 300}


class TestWaitForInputHandler:
    """Tests for WaitForInput action handler."""

    @pytest.mark.asyncio
    async def test_wait_for_input(self):
        """Test WaitForInput handler."""
        ctx = create_action_context({
            "kind": "WaitForInput",
            "id": "wait",
            "variable": "Local.response",
            "message": "Waiting...",
        })

        handler = get_action_handler("WaitForInput")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, QuestionRequest)
        assert event.request_id == "wait"
        assert event.prompt == "Waiting..."


class TestProcessExternalLoop:
    """Tests for process_external_loop helper function."""

    def test_no_external_loop(self):
        """Test when no external loop is configured."""
        state = WorkflowState()
        result, expr = process_external_loop({}, state)

        assert result is False
        assert expr is None

    def test_external_loop_true_condition(self):
        """Test when external loop condition evaluates to true."""
        state = WorkflowState()
        state.set("Local.isComplete", False)

        input_config = {
            "externalLoop": {
                "when": "=!Local.isComplete",
            },
        }

        result, expr = process_external_loop(input_config, state)

        # !False = True, so loop should continue
        assert result is True
        assert expr == "=!Local.isComplete"

    def test_external_loop_false_condition(self):
        """Test when external loop condition evaluates to false."""
        state = WorkflowState()
        state.set("Local.isComplete", True)

        input_config = {
            "externalLoop": {
                "when": "=!Local.isComplete",
            },
        }

        result, expr = process_external_loop(input_config, state)

        # !True = False, so loop should stop
        assert result is False


class TestValidateInputResponse:
    """Tests for validate_input_response helper function."""

    def test_no_validation(self):
        """Test with no validation rules."""
        is_valid, error = validate_input_response("any value", None)
        assert is_valid is True
        assert error is None

    def test_required_valid(self):
        """Test required validation with valid value."""
        is_valid, error = validate_input_response("value", {"required": True})
        assert is_valid is True
        assert error is None

    def test_required_empty_string(self):
        """Test required validation with empty string."""
        is_valid, error = validate_input_response("", {"required": True})
        assert is_valid is False
        assert "required" in error.lower()

    def test_required_none(self):
        """Test required validation with None."""
        is_valid, error = validate_input_response(None, {"required": True})
        assert is_valid is False
        assert "required" in error.lower()

    def test_min_length_valid(self):
        """Test minLength validation with valid value."""
        is_valid, error = validate_input_response("hello", {"minLength": 3})
        assert is_valid is True

    def test_min_length_invalid(self):
        """Test minLength validation with too short value."""
        is_valid, error = validate_input_response("hi", {"minLength": 3})
        assert is_valid is False
        assert "minimum length" in error.lower()

    def test_max_length_valid(self):
        """Test maxLength validation with valid value."""
        is_valid, error = validate_input_response("hello", {"maxLength": 10})
        assert is_valid is True

    def test_max_length_invalid(self):
        """Test maxLength validation with too long value."""
        is_valid, error = validate_input_response("hello world", {"maxLength": 5})
        assert is_valid is False
        assert "maximum length" in error.lower()

    def test_min_value_valid(self):
        """Test min validation for numbers."""
        is_valid, error = validate_input_response(10, {"min": 5})
        assert is_valid is True

    def test_min_value_invalid(self):
        """Test min validation with too small number."""
        is_valid, error = validate_input_response(3, {"min": 5})
        assert is_valid is False
        assert "minimum value" in error.lower()

    def test_max_value_valid(self):
        """Test max validation for numbers."""
        is_valid, error = validate_input_response(5, {"max": 10})
        assert is_valid is True

    def test_max_value_invalid(self):
        """Test max validation with too large number."""
        is_valid, error = validate_input_response(15, {"max": 10})
        assert is_valid is False
        assert "maximum value" in error.lower()

    def test_pattern_valid(self):
        """Test pattern validation with matching value."""
        is_valid, error = validate_input_response("test@example.com", {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"})
        assert is_valid is True

    def test_pattern_invalid(self):
        """Test pattern validation with non-matching value."""
        is_valid, error = validate_input_response("not-an-email", {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"})
        assert is_valid is False
        assert "pattern" in error.lower()
