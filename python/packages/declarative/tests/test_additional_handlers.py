# Copyright (c) Microsoft. All rights reserved.

"""Tests for additional action handlers (conversation, variables, etc.)."""

import pytest

import agent_framework_declarative._workflows._actions_basic  # noqa: F401
import agent_framework_declarative._workflows._actions_control_flow  # noqa: F401
from agent_framework_declarative._workflows._handlers import get_action_handler
from agent_framework_declarative._workflows._state import WorkflowState


def create_action_context(action: dict, state: WorkflowState | None = None):
    """Create a minimal action context for testing."""
    from agent_framework_declarative._workflows._handlers import ActionContext

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


class TestSetTextVariableHandler:
    """Tests for SetTextVariable action handler."""

    @pytest.mark.asyncio
    async def test_set_text_variable_simple(self):
        """Test setting a simple text variable."""
        ctx = create_action_context({
            "kind": "SetTextVariable",
            "variable": "Local.greeting",
            "value": "Hello, World!",
        })

        handler = get_action_handler("SetTextVariable")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.greeting") == "Hello, World!"

    @pytest.mark.asyncio
    async def test_set_text_variable_with_interpolation(self):
        """Test setting text with variable interpolation."""
        state = WorkflowState()
        state.set("Local.name", "Alice")

        ctx = create_action_context(
            {
                "kind": "SetTextVariable",
                "variable": "Local.message",
                "value": "Hello, {Local.name}!",
            },
            state=state,
        )

        handler = get_action_handler("SetTextVariable")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.message") == "Hello, Alice!"


class TestResetVariableHandler:
    """Tests for ResetVariable action handler."""

    @pytest.mark.asyncio
    async def test_reset_variable(self):
        """Test resetting a variable to None."""
        state = WorkflowState()
        state.set("Local.counter", 5)

        ctx = create_action_context(
            {
                "kind": "ResetVariable",
                "variable": "Local.counter",
            },
            state=state,
        )

        handler = get_action_handler("ResetVariable")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.counter") is None


class TestSetMultipleVariablesHandler:
    """Tests for SetMultipleVariables action handler."""

    @pytest.mark.asyncio
    async def test_set_multiple_variables(self):
        """Test setting multiple variables at once."""
        ctx = create_action_context({
            "kind": "SetMultipleVariables",
            "variables": [
                {"variable": "Local.a", "value": 1},
                {"variable": "Local.b", "value": 2},
                {"variable": "Local.c", "value": "three"},
            ],
        })

        handler = get_action_handler("SetMultipleVariables")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.a") == 1
        assert ctx.state.get("Local.b") == 2
        assert ctx.state.get("Local.c") == "three"


class TestClearAllVariablesHandler:
    """Tests for ClearAllVariables action handler."""

    @pytest.mark.asyncio
    async def test_clear_all_variables(self):
        """Test clearing all turn-scoped variables."""
        state = WorkflowState()
        state.set("Local.a", 1)
        state.set("Local.b", 2)
        state.set("Workflow.Outputs.result", "kept")

        ctx = create_action_context(
            {
                "kind": "ClearAllVariables",
            },
            state=state,
        )

        handler = get_action_handler("ClearAllVariables")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.a") is None
        assert ctx.state.get("Local.b") is None
        # Workflow outputs should be preserved
        assert ctx.state.get("Workflow.Outputs.result") == "kept"


class TestCreateConversationHandler:
    """Tests for CreateConversation action handler."""

    @pytest.mark.asyncio
    async def test_create_conversation_with_output_binding(self):
        """Test creating a new conversation with output variable binding.

        The conversationId field specifies the OUTPUT variable where the
        auto-generated conversation ID is stored.
        """
        ctx = create_action_context({
            "kind": "CreateConversation",
            "conversationId": "Local.myConvId",  # Output variable
        })

        handler = get_action_handler("CreateConversation")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        # Check conversation was created with auto-generated ID
        conversations = ctx.state.get("System.conversations")
        assert conversations is not None
        assert len(conversations) == 1

        # Get the generated ID
        generated_id = list(conversations.keys())[0]
        assert conversations[generated_id]["messages"] == []

        # Check output binding - the ID should be stored in the specified variable
        assert ctx.state.get("Local.myConvId") == generated_id

    @pytest.mark.asyncio
    async def test_create_conversation_legacy_output(self):
        """Test creating a conversation with legacy output binding."""
        ctx = create_action_context({
            "kind": "CreateConversation",
            "output": {
                "conversationId": "Local.myConvId",
            },
        })

        handler = get_action_handler("CreateConversation")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        # Check conversation was created
        conversations = ctx.state.get("System.conversations")
        assert conversations is not None
        assert len(conversations) == 1

        # Get the generated ID
        generated_id = list(conversations.keys())[0]

        # Check legacy output binding
        assert ctx.state.get("Local.myConvId") == generated_id

    @pytest.mark.asyncio
    async def test_create_conversation_auto_id(self):
        """Test creating a conversation with auto-generated ID."""
        ctx = create_action_context({
            "kind": "CreateConversation",
        })

        handler = get_action_handler("CreateConversation")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        # Check conversation was created with some ID
        conversations = ctx.state.get("System.conversations")
        assert conversations is not None
        assert len(conversations) == 1


class TestAddConversationMessageHandler:
    """Tests for AddConversationMessage action handler."""

    @pytest.mark.asyncio
    async def test_add_conversation_message(self):
        """Test adding a message to a conversation."""
        state = WorkflowState()
        state.set(
            "System.conversations",
            {
                "conv-123": {"id": "conv-123", "messages": []},
            },
        )

        ctx = create_action_context(
            {
                "kind": "AddConversationMessage",
                "conversationId": "conv-123",
                "message": {
                    "role": "user",
                    "content": "Hello!",
                },
            },
            state=state,
        )

        handler = get_action_handler("AddConversationMessage")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        conversations = ctx.state.get("System.conversations")
        assert len(conversations["conv-123"]["messages"]) == 1
        assert conversations["conv-123"]["messages"][0]["content"] == "Hello!"


class TestEndWorkflowHandler:
    """Tests for EndWorkflow action handler."""

    @pytest.mark.asyncio
    async def test_end_workflow_signal(self):
        """Test that EndWorkflow emits correct signal."""
        from agent_framework_declarative._workflows._actions_control_flow import EndWorkflowSignal

        ctx = create_action_context({
            "kind": "EndWorkflow",
            "reason": "Completed successfully",
        })

        handler = get_action_handler("EndWorkflow")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], EndWorkflowSignal)
        assert events[0].reason == "Completed successfully"


class TestEndConversationHandler:
    """Tests for EndConversation action handler."""

    @pytest.mark.asyncio
    async def test_end_conversation_signal(self):
        """Test that EndConversation emits correct signal."""
        from agent_framework_declarative._workflows._actions_control_flow import EndConversationSignal

        ctx = create_action_context({
            "kind": "EndConversation",
            "conversationId": "conv-123",
        })

        handler = get_action_handler("EndConversation")
        events = [e async for e in handler(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], EndConversationSignal)
        assert events[0].conversation_id == "conv-123"


class TestConditionGroupWithElseActions:
    """Tests for ConditionGroup with elseActions."""

    @pytest.mark.asyncio
    async def test_condition_group_else_actions(self):
        """Test that elseActions execute when no condition matches."""
        ctx = create_action_context({
            "kind": "ConditionGroup",
            "conditions": [
                {
                    "condition": False,
                    "actions": [
                        {"kind": "SetValue", "path": "Local.result", "value": "matched"},
                    ],
                },
            ],
            "elseActions": [
                {"kind": "SetValue", "path": "Local.result", "value": "else"},
            ],
        })

        handler = get_action_handler("ConditionGroup")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.result") == "else"

    @pytest.mark.asyncio
    async def test_condition_group_match_skips_else(self):
        """Test that elseActions don't execute when a condition matches."""
        ctx = create_action_context({
            "kind": "ConditionGroup",
            "conditions": [
                {
                    "condition": True,
                    "actions": [
                        {"kind": "SetValue", "path": "Local.result", "value": "matched"},
                    ],
                },
            ],
            "elseActions": [
                {"kind": "SetValue", "path": "Local.result", "value": "else"},
            ],
        })

        handler = get_action_handler("ConditionGroup")
        _events = [e async for e in handler(ctx)]  # noqa: F841

        assert ctx.state.get("Local.result") == "matched"
