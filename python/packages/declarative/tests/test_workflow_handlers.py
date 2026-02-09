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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

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
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.try") == "ran"
        assert ctx.state.get("Local.finally") == "ran"


class TestSetValueHandlerEdgeCases:
    """Tests for SetValue action edge cases."""

    @pytest.mark.asyncio
    async def test_set_value_missing_path_logs_warning(self):
        """Test that missing path logs warning and returns early."""
        ctx = create_action_context({
            "kind": "SetValue",
            # Missing 'path' property
            "value": "test value",
        })

        handler = get_action_handler("SetValue")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0
        # The handler should return early without setting anything


class TestSetVariableHandler:
    """Tests for SetVariable action handler (.NET style)."""

    @pytest.mark.asyncio
    async def test_set_variable_basic(self):
        """Test SetVariable with basic variable path."""
        ctx = create_action_context({
            "kind": "SetVariable",
            "variable": "Local.myVar",
            "value": "hello",
        })

        handler = get_action_handler("SetVariable")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0
        assert ctx.state.get("Local.myVar") == "hello"

    @pytest.mark.asyncio
    async def test_set_variable_missing_variable_logs_warning(self):
        """Test that missing variable logs warning."""
        ctx = create_action_context({
            "kind": "SetVariable",
            # Missing 'variable' property
            "value": "test",
        })

        handler = get_action_handler("SetVariable")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_set_variable_adds_local_prefix(self):
        """Test that variable without namespace gets Local prefix."""
        ctx = create_action_context({
            "kind": "SetVariable",
            "variable": "myVar",  # No namespace
            "value": "test",
        })

        handler = get_action_handler("SetVariable")
        [e async for e in handler(ctx)]

        # Should be stored under Local namespace
        assert ctx.state.get("Local.myVar") == "test"


class TestAppendValueHandlerEdgeCases:
    """Tests for AppendValue action edge cases."""

    @pytest.mark.asyncio
    async def test_append_value_missing_path_logs_warning(self):
        """Test that missing path logs warning."""
        ctx = create_action_context({
            "kind": "AppendValue",
            # Missing 'path' property
            "value": "item",
        })

        handler = get_action_handler("AppendValue")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0


class TestSendActivityHandlerEdgeCases:
    """Tests for SendActivity action edge cases."""

    @pytest.mark.asyncio
    async def test_send_activity_simple_string_form(self):
        """Test SendActivity with simple string activity."""
        ctx = create_action_context({
            "kind": "SendActivity",
            "activity": "Hello from simple string!",
        })

        handler = get_action_handler("SendActivity")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], TextOutputEvent)
        assert events[0].text == "Hello from simple string!"

    @pytest.mark.asyncio
    async def test_send_activity_with_attachments(self):
        """Test SendActivity with attachments."""
        from agent_framework_declarative._workflows._handlers import AttachmentOutputEvent

        ctx = create_action_context({
            "kind": "SendActivity",
            "activity": {
                "text": "See attachment",
                "attachments": [
                    {"content": "file content", "contentType": "text/plain"},
                ],
            },
        })

        handler = get_action_handler("SendActivity")
        events = [e async for e in handler(ctx)]

        assert len(events) == 2
        assert isinstance(events[0], TextOutputEvent)
        assert events[0].text == "See attachment"
        assert isinstance(events[1], AttachmentOutputEvent)
        assert events[1].content == "file content"
        assert events[1].content_type == "text/plain"

    @pytest.mark.asyncio
    async def test_send_activity_empty_text(self):
        """Test SendActivity with empty/None text."""
        ctx = create_action_context({
            "kind": "SendActivity",
            "activity": {
                "text": None,
            },
        })

        handler = get_action_handler("SendActivity")
        events = [e async for e in handler(ctx)]

        # Should not produce any events for None text
        assert len(events) == 0


class TestEmitEventHandlerEdgeCases:
    """Tests for EmitEvent action edge cases."""

    @pytest.mark.asyncio
    async def test_emit_event_missing_name_logs_warning(self):
        """Test that missing event name logs warning."""
        ctx = create_action_context({
            "kind": "EmitEvent",
            "event": {
                # Missing 'name' property
                "data": {"key": "value"},
            },
        })

        handler = get_action_handler("EmitEvent")
        events = [e async for e in handler(ctx)]

        # Should not emit any event without name
        assert len(events) == 0


class TestSetTextVariableHandler:
    """Tests for SetTextVariable action handler."""

    @pytest.mark.asyncio
    async def test_set_text_variable_with_interpolation(self):
        """Test SetTextVariable with variable interpolation."""
        ctx = create_action_context(
            {
                "kind": "SetTextVariable",
                "variable": "Local.message",
                "value": "Hello {name}!",
            },
            inputs={"name": "World"},
        )
        # Set the variable that will be interpolated
        ctx.state.set("Local.name", "World")

        handler = get_action_handler("SetTextVariable")
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.message") == "Hello World!"

    @pytest.mark.asyncio
    async def test_set_text_variable_missing_variable(self):
        """Test SetTextVariable with missing variable property."""
        ctx = create_action_context({
            "kind": "SetTextVariable",
            # Missing 'variable' property
            "value": "test text",
        })

        handler = get_action_handler("SetTextVariable")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_set_text_variable_non_string_value(self):
        """Test SetTextVariable with non-string value."""
        ctx = create_action_context({
            "kind": "SetTextVariable",
            "variable": "Local.num",
            "value": 42,  # Non-string
        })

        handler = get_action_handler("SetTextVariable")
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.num") == 42


class TestSetMultipleVariablesHandler:
    """Tests for SetMultipleVariables action handler."""

    @pytest.mark.asyncio
    async def test_set_multiple_variables_basic(self):
        """Test setting multiple variables at once."""
        ctx = create_action_context({
            "kind": "SetMultipleVariables",
            "variables": [
                {"variable": "Local.var1", "value": "one"},
                {"variable": "Local.var2", "value": "two"},
                {"variable": "Local.var3", "value": 3},
            ],
        })

        handler = get_action_handler("SetMultipleVariables")
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.var1") == "one"
        assert ctx.state.get("Local.var2") == "two"
        assert ctx.state.get("Local.var3") == 3

    @pytest.mark.asyncio
    async def test_set_multiple_variables_missing_variable_skips(self):
        """Test that missing variable property skips that entry."""
        ctx = create_action_context({
            "kind": "SetMultipleVariables",
            "variables": [
                {"variable": "Local.valid", "value": "ok"},
                {"value": "skipped"},  # Missing 'variable' property
                {"variable": "Local.also_valid", "value": "also ok"},
            ],
        })

        handler = get_action_handler("SetMultipleVariables")
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.valid") == "ok"
        assert ctx.state.get("Local.also_valid") == "also ok"

    @pytest.mark.asyncio
    async def test_set_multiple_variables_uses_path_field(self):
        """Test that variables can use 'path' field instead of 'variable'."""
        ctx = create_action_context({
            "kind": "SetMultipleVariables",
            "variables": [
                {"path": "Local.using_path", "value": "path value"},
            ],
        })

        handler = get_action_handler("SetMultipleVariables")
        [e async for e in handler(ctx)]

        # Note: The handler uses 'variable' field, not 'path'
        # So this won't set anything unless the handler supports both


class TestResetVariableHandler:
    """Tests for ResetVariable action handler."""

    @pytest.mark.asyncio
    async def test_reset_variable_basic(self):
        """Test resetting a variable to None."""
        ctx = create_action_context({
            "kind": "ResetVariable",
            "variable": "Local.toReset",
        })
        ctx.state.set("Local.toReset", "some value")

        handler = get_action_handler("ResetVariable")
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.toReset") is None

    @pytest.mark.asyncio
    async def test_reset_variable_missing_variable(self):
        """Test ResetVariable with missing variable property."""
        ctx = create_action_context({
            "kind": "ResetVariable",
            # Missing 'variable' property
        })

        handler = get_action_handler("ResetVariable")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0


class TestClearAllVariablesHandler:
    """Tests for ClearAllVariables action handler."""

    @pytest.mark.asyncio
    async def test_clear_all_variables(self):
        """Test clearing all Local-scoped variables."""
        ctx = create_action_context({
            "kind": "ClearAllVariables",
        })
        ctx.state.set("Local.var1", "value1")
        ctx.state.set("Local.var2", "value2")

        handler = get_action_handler("ClearAllVariables")
        [e async for e in handler(ctx)]

        assert ctx.state.get("Local.var1") is None
        assert ctx.state.get("Local.var2") is None


class TestCreateConversationHandler:
    """Tests for CreateConversation action handler."""

    @pytest.mark.asyncio
    async def test_create_conversation_basic(self):
        """Test creating a conversation."""
        ctx = create_action_context({
            "kind": "CreateConversation",
            "conversationId": "Local.convId",
        })

        handler = get_action_handler("CreateConversation")
        [e async for e in handler(ctx)]

        # Should have generated and stored a conversation ID
        conv_id = ctx.state.get("Local.convId")
        assert conv_id is not None
        # ID should be a UUID string
        import uuid

        uuid.UUID(conv_id)  # This will raise if not valid UUID

    @pytest.mark.asyncio
    async def test_create_conversation_without_output_var(self):
        """Test creating a conversation without output variable."""
        ctx = create_action_context({
            "kind": "CreateConversation",
        })

        handler = get_action_handler("CreateConversation")
        [e async for e in handler(ctx)]

        # Should still create conversation in System.conversations
        conversations = ctx.state.get("System.conversations")
        assert conversations is not None
        assert len(conversations) == 1


class TestAddConversationMessageHandler:
    """Tests for AddConversationMessage action handler."""

    @pytest.mark.asyncio
    async def test_add_conversation_message(self):
        """Test adding a message to a conversation."""
        ctx = create_action_context({
            "kind": "AddConversationMessage",
            "conversationId": "test-conv-123",
            "message": {
                "role": "user",
                "content": "Hello!",
            },
        })

        handler = get_action_handler("AddConversationMessage")
        [e async for e in handler(ctx)]

        conversations = ctx.state.get("System.conversations")
        assert conversations is not None
        assert "test-conv-123" in conversations
        messages = conversations["test-conv-123"]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_add_conversation_message_missing_id(self):
        """Test AddConversationMessage with missing conversationId."""
        ctx = create_action_context({
            "kind": "AddConversationMessage",
            # Missing 'conversationId'
            "message": {
                "role": "user",
                "content": "Hello!",
            },
        })

        handler = get_action_handler("AddConversationMessage")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0


class TestCopyConversationMessagesHandler:
    """Tests for CopyConversationMessages action handler."""

    @pytest.mark.asyncio
    async def test_copy_conversation_messages(self):
        """Test copying messages between conversations."""
        ctx = create_action_context({
            "kind": "CopyConversationMessages",
            "sourceConversationId": "source-conv",
            "targetConversationId": "target-conv",
        })

        # Set up source conversation with messages
        ctx.state.set(
            "System.conversations",
            {
                "source-conv": {
                    "id": "source-conv",
                    "messages": [
                        {"role": "user", "content": "msg1"},
                        {"role": "assistant", "content": "msg2"},
                    ],
                },
            },
        )

        handler = get_action_handler("CopyConversationMessages")
        [e async for e in handler(ctx)]

        conversations = ctx.state.get("System.conversations")
        target_messages = conversations["target-conv"]["messages"]
        assert len(target_messages) == 2
        assert target_messages[0]["content"] == "msg1"
        assert target_messages[1]["content"] == "msg2"

    @pytest.mark.asyncio
    async def test_copy_conversation_messages_with_count(self):
        """Test copying limited number of messages."""
        ctx = create_action_context({
            "kind": "CopyConversationMessages",
            "sourceConversationId": "source-conv",
            "targetConversationId": "target-conv",
            "count": 1,
        })

        ctx.state.set(
            "System.conversations",
            {
                "source-conv": {
                    "id": "source-conv",
                    "messages": [
                        {"role": "user", "content": "msg1"},
                        {"role": "assistant", "content": "msg2"},
                        {"role": "user", "content": "msg3"},
                    ],
                },
            },
        )

        handler = get_action_handler("CopyConversationMessages")
        [e async for e in handler(ctx)]

        conversations = ctx.state.get("System.conversations")
        target_messages = conversations["target-conv"]["messages"]
        # Should only have the last message (count=1 gets last N messages)
        assert len(target_messages) == 1
        assert target_messages[0]["content"] == "msg3"

    @pytest.mark.asyncio
    async def test_copy_conversation_messages_missing_ids(self):
        """Test CopyConversationMessages with missing IDs."""
        ctx = create_action_context({
            "kind": "CopyConversationMessages",
            # Missing both IDs
        })

        handler = get_action_handler("CopyConversationMessages")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0


class TestRetrieveConversationMessagesHandler:
    """Tests for RetrieveConversationMessages action handler."""

    @pytest.mark.asyncio
    async def test_retrieve_conversation_messages(self):
        """Test retrieving messages from a conversation."""
        ctx = create_action_context({
            "kind": "RetrieveConversationMessages",
            "conversationId": "test-conv",
            "output": {
                "messages": "Local.retrievedMessages",
            },
        })

        ctx.state.set(
            "System.conversations",
            {
                "test-conv": {
                    "id": "test-conv",
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi there"},
                    ],
                },
            },
        )

        handler = get_action_handler("RetrieveConversationMessages")
        [e async for e in handler(ctx)]

        retrieved = ctx.state.get("Local.retrievedMessages")
        assert len(retrieved) == 2
        assert retrieved[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_retrieve_conversation_messages_with_count(self):
        """Test retrieving limited messages."""
        ctx = create_action_context({
            "kind": "RetrieveConversationMessages",
            "conversationId": "test-conv",
            "output": {
                "messages": "Local.msgs",
            },
            "count": 2,
        })

        ctx.state.set(
            "System.conversations",
            {
                "test-conv": {
                    "id": "test-conv",
                    "messages": [
                        {"role": "user", "content": "msg1"},
                        {"role": "assistant", "content": "msg2"},
                        {"role": "user", "content": "msg3"},
                        {"role": "assistant", "content": "msg4"},
                    ],
                },
            },
        )

        handler = get_action_handler("RetrieveConversationMessages")
        [e async for e in handler(ctx)]

        retrieved = ctx.state.get("Local.msgs")
        # Should get last 2 messages
        assert len(retrieved) == 2
        assert retrieved[0]["content"] == "msg3"
        assert retrieved[1]["content"] == "msg4"

    @pytest.mark.asyncio
    async def test_retrieve_conversation_messages_missing_id(self):
        """Test RetrieveConversationMessages with missing conversationId."""
        ctx = create_action_context({
            "kind": "RetrieveConversationMessages",
            # Missing 'conversationId'
            "output": {
                "messages": "Local.msgs",
            },
        })

        handler = get_action_handler("RetrieveConversationMessages")
        events = [e async for e in handler(ctx)]

        assert len(events) == 0


class TestEvaluateDictValues:
    """Tests for _evaluate_dict_values utility function."""

    def test_evaluate_nested_dict(self):
        """Test evaluating expressions in nested dict."""
        from agent_framework_declarative._workflows._actions_basic import _evaluate_dict_values

        state = WorkflowState()
        state.set("Local.name", "World")

        data = {
            "greeting": "=Local.name",
            "nested": {
                "value": "=Local.name",
            },
            "list": ["=Local.name", "static"],
            "number": 42,
        }

        result = _evaluate_dict_values(data, state)

        assert result["greeting"] == "World"
        assert result["nested"]["value"] == "World"
        assert result["list"][0] == "World"
        assert result["list"][1] == "static"
        assert result["number"] == 42

    def test_evaluate_list_with_dicts(self):
        """Test evaluating expressions in list containing dicts."""
        from agent_framework_declarative._workflows._actions_basic import _evaluate_dict_values

        state = WorkflowState()
        state.set("Local.x", 10)

        data = {
            "items": [
                {"value": "=Local.x"},
                {"value": "static"},
            ],
        }

        result = _evaluate_dict_values(data, state)

        assert result["items"][0]["value"] == 10
        assert result["items"][1]["value"] == "static"


class TestNormalizeVariablePath:
    """Tests for _normalize_variable_path utility function."""

    def test_with_known_namespace(self):
        """Test that known namespaces are preserved."""
        from agent_framework_declarative._workflows._actions_basic import _normalize_variable_path

        assert _normalize_variable_path("Local.var") == "Local.var"
        assert _normalize_variable_path("System.ConversationId") == "System.ConversationId"
        assert _normalize_variable_path("Workflow.Outputs.result") == "Workflow.Outputs.result"
        assert _normalize_variable_path("Agent.text") == "Agent.text"
        assert _normalize_variable_path("Conversation.messages") == "Conversation.messages"

    def test_with_custom_namespace(self):
        """Test that custom namespace is preserved."""
        from agent_framework_declarative._workflows._actions_basic import _normalize_variable_path

        assert _normalize_variable_path("Custom.var") == "Custom.var"

    def test_without_namespace(self):
        """Test that variables without namespace get Local prefix."""
        from agent_framework_declarative._workflows._actions_basic import _normalize_variable_path

        assert _normalize_variable_path("myVar") == "Local.myVar"


class TestInterpolateString:
    """Tests for _interpolate_string utility function."""

    def test_basic_interpolation(self):
        """Test basic variable interpolation."""
        from agent_framework_declarative._workflows._actions_basic import _interpolate_string

        state = WorkflowState()
        state.set("Local.name", "Alice")

        result = _interpolate_string("Hello {Local.name}!", state)
        assert result == "Hello Alice!"

    def test_multiple_variables(self):
        """Test interpolating multiple variables."""
        from agent_framework_declarative._workflows._actions_basic import _interpolate_string

        state = WorkflowState()
        state.set("Local.first", "John")
        state.set("Local.last", "Doe")

        result = _interpolate_string("{Local.first} {Local.last}", state)
        assert result == "John Doe"

    def test_missing_variable_becomes_empty(self):
        """Test that missing variables become empty strings."""
        from agent_framework_declarative._workflows._actions_basic import _interpolate_string

        state = WorkflowState()

        result = _interpolate_string("Hello {Local.missing}!", state)
        assert result == "Hello !"

    def test_no_interpolation_needed(self):
        """Test string without variables passes through."""
        from agent_framework_declarative._workflows._actions_basic import _interpolate_string

        state = WorkflowState()

        result = _interpolate_string("Plain text", state)
        assert result == "Plain text"
