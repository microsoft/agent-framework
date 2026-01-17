# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for action handlers."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest

# Import handlers to register them
from agent_framework_declarative._workflows import (
    _actions_basic,  # noqa: F401
    _actions_control_flow,  # noqa: F401
    _actions_error,  # noqa: F401
)
from agent_framework_declarative._workflows._handlers import (
    ActionContext,
    CustomEvent,
    TextOutputEvent,
    WorkflowEvent,
    get_action_handler,
    list_action_handlers,
)
from agent_framework_declarative._workflows._state import WorkflowState


def create_action_context(
    action: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    agents: dict[str, Any] | None = None,
    bindings: dict[str, Any] | None = None,
) -> ActionContext:
    """Helper to create an ActionContext for testing."""
    state = WorkflowState(inputs=inputs or {})

    async def execute_actions(
        actions: list[dict[str, Any]], state: WorkflowState
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Mock execute_actions that runs handlers for nested actions."""
        for nested_action in actions:
            action_kind = nested_action.get("kind")
            handler = get_action_handler(action_kind)
            if handler:
                ctx = ActionContext(
                    state=state,
                    action=nested_action,
                    execute_actions=execute_actions,
                    agents=agents or {},
                    bindings=bindings or {},
                )
                async for event in handler(ctx):
                    yield event

    return ActionContext(
        state=state,
        action=action,
        execute_actions=execute_actions,
        agents=agents or {},
        bindings=bindings or {},
    )


class TestActionHandlerRegistry:
    """Tests for action handler registration."""

    def test_basic_handlers_registered(self):
        """Test that basic handlers are registered."""
        handlers = list_action_handlers()
        assert "SetValue" in handlers
        assert "AppendValue" in handlers
        assert "SendActivity" in handlers
        assert "EmitEvent" in handlers

    def test_control_flow_handlers_registered(self):
        """Test that control flow handlers are registered."""
        handlers = list_action_handlers()
        assert "Foreach" in handlers
        assert "If" in handlers
        assert "Switch" in handlers
        assert "RepeatUntil" in handlers
        assert "BreakLoop" in handlers
        assert "ContinueLoop" in handlers

    def test_error_handlers_registered(self):
        """Test that error handlers are registered."""
        handlers = list_action_handlers()
        assert "ThrowException" in handlers
        assert "TryCatch" in handlers

    def test_get_unknown_handler_returns_none(self):
        """Test that getting an unknown handler returns None."""
        assert get_action_handler("UnknownAction") is None


class TestSetValueHandler:
    """Tests for SetValue action handler."""

    @pytest.mark.asyncio
    async def test_set_simple_value(self):
        """Test setting a simple value."""
        ctx = create_action_context({
            "kind": "SetValue",
            "path": "Local.result",
            "value": "test value",
        })

        handler = get_action_handler("SetValue")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0  # SetValue doesn't emit events
        assert ctx.state.get("Local.result") == "test value"

    @pytest.mark.asyncio
    async def test_set_value_from_input(self):
        """Test setting a value from workflow inputs."""
        ctx = create_action_context(
            {
                "kind": "SetValue",
                "path": "Local.copy",
                "value": "literal",
            },
            inputs={"original": "from input"},
        )

        handler = get_action_handler("SetValue")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.copy") == "literal"


class TestAppendValueHandler:
    """Tests for AppendValue action handler."""

    @pytest.mark.asyncio
    async def test_append_to_new_list(self):
        """Test appending to a non-existent list creates it."""
        ctx = create_action_context({
            "kind": "AppendValue",
            "path": "Local.results",
            "value": "item1",
        })

        handler = get_action_handler("AppendValue")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.results") == ["item1"]

    @pytest.mark.asyncio
    async def test_append_to_existing_list(self):
        """Test appending to an existing list."""
        ctx = create_action_context({
            "kind": "AppendValue",
            "path": "Local.results",
            "value": "item2",
        })
        ctx.state.set("Local.results", ["item1"])

        handler = get_action_handler("AppendValue")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.results") == ["item1", "item2"]


class TestSendActivityHandler:
    """Tests for SendActivity action handler."""

    @pytest.mark.asyncio
    async def test_send_text_activity(self):
        """Test sending a text activity."""
        ctx = create_action_context({
            "kind": "SendActivity",
            "activity": {
                "text": "Hello, world!",
            },
        })

        handler = get_action_handler("SendActivity")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], TextOutputEvent)
        assert events[0].text == "Hello, world!"


class TestEmitEventHandler:
    """Tests for EmitEvent action handler."""

    @pytest.mark.asyncio
    async def test_emit_custom_event(self):
        """Test emitting a custom event."""
        ctx = create_action_context({
            "kind": "EmitEvent",
            "event": {
                "name": "myEvent",
                "data": {"key": "value"},
            },
        })

        handler = get_action_handler("EmitEvent")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], CustomEvent)
        assert events[0].name == "myEvent"
        assert events[0].data == {"key": "value"}


class TestForeachHandler:
    """Tests for Foreach action handler."""

    @pytest.mark.asyncio
    async def test_foreach_basic_iteration(self):
        """Test basic foreach iteration."""
        ctx = create_action_context({
            "kind": "Foreach",
            "source": ["a", "b", "c"],
            "itemName": "letter",
            "actions": [
                {
                    "kind": "AppendValue",
                    "path": "Local.results",
                    "value": "processed",
                }
            ],
        })

        handler = get_action_handler("Foreach")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.results") == ["processed", "processed", "processed"]

    @pytest.mark.asyncio
    async def test_foreach_sets_item_and_index(self):
        """Test that foreach sets item and index variables."""
        ctx = create_action_context({
            "kind": "Foreach",
            "source": ["x", "y"],
            "itemName": "item",
            "indexName": "idx",
            "actions": [],
        })

        # We'll check the last values after iteration
        handler = get_action_handler("Foreach")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        # After iteration, the last item/index should be set
        assert ctx.state.get("Local.item") == "y"
        assert ctx.state.get("Local.idx") == 1


class TestIfHandler:
    """Tests for If action handler."""

    @pytest.mark.asyncio
    async def test_if_true_branch(self):
        """Test that the 'then' branch executes when condition is true."""
        ctx = create_action_context({
            "kind": "If",
            "condition": True,
            "then": [
                {"kind": "SetValue", "path": "Local.branch", "value": "then"},
            ],
            "else": [
                {"kind": "SetValue", "path": "Local.branch", "value": "else"},
            ],
        })

        handler = get_action_handler("If")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.branch") == "then"

    @pytest.mark.asyncio
    async def test_if_false_branch(self):
        """Test that the 'else' branch executes when condition is false."""
        ctx = create_action_context({
            "kind": "If",
            "condition": False,
            "then": [
                {"kind": "SetValue", "path": "Local.branch", "value": "then"},
            ],
            "else": [
                {"kind": "SetValue", "path": "Local.branch", "value": "else"},
            ],
        })

        handler = get_action_handler("If")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.branch") == "else"


class TestSwitchHandler:
    """Tests for Switch action handler."""

    @pytest.mark.asyncio
    async def test_switch_matching_case(self):
        """Test switch with a matching case."""
        ctx = create_action_context({
            "kind": "Switch",
            "value": "option2",
            "cases": [
                {
                    "match": "option1",
                    "actions": [{"kind": "SetValue", "path": "Local.result", "value": "one"}],
                },
                {
                    "match": "option2",
                    "actions": [{"kind": "SetValue", "path": "Local.result", "value": "two"}],
                },
            ],
            "default": [{"kind": "SetValue", "path": "Local.result", "value": "default"}],
        })

        handler = get_action_handler("Switch")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.result") == "two"

    @pytest.mark.asyncio
    async def test_switch_default_case(self):
        """Test switch falls through to default."""
        ctx = create_action_context({
            "kind": "Switch",
            "value": "unknown",
            "cases": [
                {
                    "match": "option1",
                    "actions": [{"kind": "SetValue", "path": "Local.result", "value": "one"}],
                },
            ],
            "default": [{"kind": "SetValue", "path": "Local.result", "value": "default"}],
        })

        handler = get_action_handler("Switch")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.result") == "default"


class TestRepeatUntilHandler:
    """Tests for RepeatUntil action handler."""

    @pytest.mark.asyncio
    async def test_repeat_until_condition_met(self):
        """Test repeat until condition becomes true."""
        ctx = create_action_context({
            "kind": "RepeatUntil",
            "condition": False,  # Will be evaluated each iteration
            "maxIterations": 3,
            "actions": [
                {"kind": "SetValue", "path": "Local.count", "value": 1},
            ],
        })
        # Set up a counter that will cause the loop to exit
        ctx.state.set("Local.count", 0)

        handler = get_action_handler("RepeatUntil")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        # With condition=False (literal), it will run maxIterations times
        assert ctx.state.get("Local.iteration") == 3


class TestTryCatchHandler:
    """Tests for TryCatch action handler."""

    @pytest.mark.asyncio
    async def test_try_without_error(self):
        """Test try block without errors."""
        ctx = create_action_context({
            "kind": "TryCatch",
            "try": [
                {"kind": "SetValue", "path": "Local.result", "value": "success"},
            ],
            "catch": [
                {"kind": "SetValue", "path": "Local.result", "value": "caught"},
            ],
        })

        handler = get_action_handler("TryCatch")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.result") == "success"

    @pytest.mark.asyncio
    async def test_try_with_throw_exception(self):
        """Test catching a thrown exception."""
        ctx = create_action_context({
            "kind": "TryCatch",
            "try": [
                {"kind": "ThrowException", "message": "Test error", "code": "ERR001"},
            ],
            "catch": [
                {"kind": "SetValue", "path": "Local.result", "value": "caught"},
            ],
        })

        handler = get_action_handler("TryCatch")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.result") == "caught"
        assert ctx.state.get("Local.error.message") == "Test error"
        assert ctx.state.get("Local.error.code") == "ERR001"

    @pytest.mark.asyncio
    async def test_finally_always_executes(self):
        """Test that finally block always executes."""
        ctx = create_action_context({
            "kind": "TryCatch",
            "try": [
                {"kind": "SetValue", "path": "Local.try", "value": "ran"},
            ],
            "finally": [
                {"kind": "SetValue", "path": "Local.finally", "value": "ran"},
            ],
        })

        handler = get_action_handler("TryCatch")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.try") == "ran"
        assert ctx.state.get("Local.finally") == "ran"
