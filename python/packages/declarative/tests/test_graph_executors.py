# Copyright (c) Microsoft. All rights reserved.

"""Tests for the graph-based declarative workflow executors."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

_requires_powerfx = pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")

from agent_framework_declarative._workflows import (  # noqa: E402
    ALL_ACTION_EXECUTORS,
    DECLARATIVE_STATE_KEY,
    ActionComplete,
    ActionTrigger,
    DeclarativeWorkflowBuilder,
    DeclarativeWorkflowState,
    ForeachInitExecutor,
    LoopIterationResult,
    SendActivityExecutor,
    SetValueExecutor,
)


class TestDeclarativeWorkflowState:
    """Tests for DeclarativeWorkflowState."""

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state with async get/set methods."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_initialize_state(self, mock_state):
        """Test initializing the workflow state."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize({"query": "test"})

        # Verify state was set
        mock_state.set.assert_called_once()
        call_args = mock_state.set.call_args
        assert call_args[0][0] == DECLARATIVE_STATE_KEY
        state_data = call_args[0][1]
        assert state_data["Inputs"] == {"query": "test"}
        assert state_data["Outputs"] == {}
        assert state_data["Local"] == {}

    @pytest.mark.asyncio
    async def test_get_and_set_values(self, mock_state):
        """Test getting and setting values."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        # Set a turn value
        state.set("Local.counter", 5)

        # Get the value
        result = state.get("Local.counter")
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_inputs(self, mock_state):
        """Test getting workflow inputs."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize({"name": "Alice", "age": 30})

        # Get via path
        name = state.get("Workflow.Inputs.name")
        assert name == "Alice"

        # Get all inputs
        inputs = state.get("Workflow.Inputs")
        assert inputs == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_append_value(self, mock_state):
        """Test appending values to a list."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        # Append to non-existent list creates it
        state.append("Local.items", "first")
        result = state.get("Local.items")
        assert result == ["first"]

        # Append to existing list
        state.append("Local.items", "second")
        result = state.get("Local.items")
        assert result == ["first", "second"]

    @_requires_powerfx
    @pytest.mark.asyncio
    async def test_eval_expression(self, mock_state):
        """Test evaluating expressions."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        # Non-expression returns as-is
        result = state.eval("plain text")
        assert result == "plain text"

        # Boolean literals
        result = state.eval("=true")
        assert result is True

        result = state.eval("=false")
        assert result is False

        # String literals
        result = state.eval('="hello"')
        assert result == "hello"

        # Numeric literals
        result = state.eval("=42")
        assert result == 42


class TestDeclarativeActionExecutor:
    """Tests for DeclarativeActionExecutor subclasses."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_set_value_executor(self, mock_context, mock_state):
        """Test SetValueExecutor."""
        # Initialize state
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "SetValue",
            "path": "Local.result",
            "value": "test value",
        }
        executor = SetValueExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify action complete was sent
        mock_context.send_message.assert_called_once()
        message = mock_context.send_message.call_args[0][0]
        assert isinstance(message, ActionComplete)

    @pytest.mark.asyncio
    async def test_send_activity_executor(self, mock_context, mock_state):
        """Test SendActivityExecutor."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "SendActivity",
            "activity": {"text": "Hello, world!"},
        }
        executor = SendActivityExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify output was yielded
        mock_context.yield_output.assert_called_once_with("Hello, world!")

    # Note: ConditionEvaluatorExecutor tests removed - conditions are now evaluated on edges

    @_requires_powerfx
    async def test_foreach_init_with_items(self, mock_context, mock_state):
        """Test ForeachInitExecutor with items."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "b", "c"])

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=Local.items",
            "iteratorVariable": "Local.item",
        }
        executor = ForeachInitExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify result
        mock_context.send_message.assert_called_once()
        message = mock_context.send_message.call_args[0][0]
        assert isinstance(message, LoopIterationResult)
        assert message.has_next is True
        assert message.current_index == 0
        assert message.current_item == "a"

    @pytest.mark.asyncio
    async def test_foreach_init_empty(self, mock_context, mock_state):
        """Test ForeachInitExecutor with empty items list."""
        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        # Use a literal empty list - no expression evaluation needed
        action_def = {
            "kind": "Foreach",
            "itemsSource": [],  # Direct empty list, not an expression
            "iteratorVariable": "Local.item",
        }
        executor = ForeachInitExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify result
        mock_context.send_message.assert_called_once()
        message = mock_context.send_message.call_args[0][0]
        assert isinstance(message, LoopIterationResult)
        assert message.has_next is False


class TestDeclarativeWorkflowBuilder:
    """Tests for DeclarativeWorkflowBuilder."""

    def test_all_action_executors_available(self):
        """Test that all expected action types have executors."""
        expected_actions = [
            "SetValue",
            "SetVariable",
            "SendActivity",
            "EmitEvent",
            "EndWorkflow",
            "InvokeAzureAgent",
            "Question",
        ]

        for action in expected_actions:
            assert action in ALL_ACTION_EXECUTORS, f"Missing executor for {action}"

    def test_build_empty_workflow(self):
        """Test building a workflow with no actions raises an error."""
        yaml_def = {"name": "empty_workflow", "actions": []}
        builder = DeclarativeWorkflowBuilder(yaml_def)

        with pytest.raises(ValueError, match="Cannot build workflow with no actions"):
            builder.build()

    def test_build_simple_workflow(self):
        """Test building a workflow with simple sequential actions."""
        yaml_def = {
            "name": "simple_workflow",
            "actions": [
                {"kind": "SendActivity", "id": "greet", "activity": {"text": "Hello!"}},
                {"kind": "SetValue", "id": "set_count", "path": "Local.count", "value": 1},
            ],
        }
        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        assert workflow is not None
        # Verify executors were created
        assert "greet" in builder._executors
        assert "set_count" in builder._executors

    def test_build_workflow_with_if(self):
        """Test building a workflow with If control flow."""
        yaml_def = {
            "name": "conditional_workflow",
            "actions": [
                {
                    "kind": "If",
                    "id": "check_flag",
                    "condition": "=Local.flag",
                    "then": [
                        {"kind": "SendActivity", "id": "say_yes", "activity": {"text": "Yes!"}},
                    ],
                    "else": [
                        {"kind": "SendActivity", "id": "say_no", "activity": {"text": "No!"}},
                    ],
                },
            ],
        }
        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        assert workflow is not None
        # Verify branch executors were created
        # Note: No join executors - branches wire directly to successor
        assert "say_yes" in builder._executors
        assert "say_no" in builder._executors
        # Entry node is created when If is first action
        assert "_workflow_entry" in builder._executors

    def test_build_workflow_with_foreach(self):
        """Test building a workflow with Foreach loop."""
        yaml_def = {
            "name": "loop_workflow",
            "actions": [
                {
                    "kind": "Foreach",
                    "id": "process_items",
                    "itemsSource": "=Local.items",
                    "iteratorVariable": "Local.item",
                    "actions": [
                        {"kind": "SendActivity", "id": "show_item", "activity": {"text": "=Local.item"}},
                    ],
                },
            ],
        }
        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        assert workflow is not None
        # Verify loop executors were created
        assert "process_items_init" in builder._executors
        assert "process_items_next" in builder._executors
        assert "process_items_exit" in builder._executors
        assert "show_item" in builder._executors

    def test_build_workflow_with_switch(self):
        """Test building a workflow with Switch control flow."""
        yaml_def = {
            "name": "switch_workflow",
            "actions": [
                {
                    "kind": "Switch",
                    "id": "check_status",
                    "conditions": [
                        {
                            "condition": '=Local.status = "active"',
                            "actions": [
                                {"kind": "SendActivity", "id": "say_active", "activity": {"text": "Active"}},
                            ],
                        },
                        {
                            "condition": '=Local.status = "pending"',
                            "actions": [
                                {"kind": "SendActivity", "id": "say_pending", "activity": {"text": "Pending"}},
                            ],
                        },
                    ],
                    "else": [
                        {"kind": "SendActivity", "id": "say_unknown", "activity": {"text": "Unknown"}},
                    ],
                },
            ],
        }
        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        assert workflow is not None
        # Verify switch executors were created
        # Note: No join executors - branches wire directly to successor
        assert "say_active" in builder._executors
        assert "say_pending" in builder._executors
        assert "say_unknown" in builder._executors
        # Entry node is created when Switch is first action
        assert "_workflow_entry" in builder._executors


class TestAgentExecutors:
    """Tests for agent-related executors."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_invoke_agent_not_found(self, mock_context, mock_state):
        """Test InvokeAzureAgentExecutor raises error when agent not found."""
        from agent_framework.exceptions import AgentInvalidRequestException

        from agent_framework_declarative._workflows import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "non_existent_agent",
            "input": "test input",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        # Execute - should raise AgentInvalidRequestException
        with pytest.raises(AgentInvalidRequestException) as exc_info:
            await executor.handle_action(ActionTrigger(), mock_context)

        assert "non_existent_agent" in str(exc_info.value)
        assert "not found in registry" in str(exc_info.value)


class TestHumanInputExecutors:
    """Tests for human input executors."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        ctx.request_info = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_question_executor(self, mock_context, mock_state):
        """Test QuestionExecutor."""
        from agent_framework_declarative._workflows import (
            ExternalInputRequest,
            QuestionExecutor,
        )

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "Question",
            "text": "What is your name?",
            "property": "Local.name",
            "defaultValue": "Anonymous",
        }
        executor = QuestionExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify request_info was called with ExternalInputRequest
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ExternalInputRequest)
        assert request.request_type == "question"
        assert "What is your name?" in request.message

    @pytest.mark.asyncio
    async def test_confirmation_executor(self, mock_context, mock_state):
        """Test ConfirmationExecutor."""
        from agent_framework_declarative._workflows import (
            ConfirmationExecutor,
            ExternalInputRequest,
        )

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "Confirmation",
            "text": "Do you want to continue?",
            "property": "Local.confirmed",
            "yesLabel": "Yes, continue",
            "noLabel": "No, stop",
        }
        executor = ConfirmationExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify request_info was called with ExternalInputRequest
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ExternalInputRequest)
        assert request.request_type == "confirmation"
        assert "continue" in request.message.lower()


@_requires_powerfx
class TestParseValueExecutor:
    """Tests for the ParseValue action executor."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_parse_value_string(self, mock_context, mock_state):
        """Test ParseValue with string type."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", "hello world")

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "string",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_parse_value_number(self, mock_context, mock_state):
        """Test ParseValue with number type."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", "123")

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "number",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result == 123

    @pytest.mark.asyncio
    async def test_parse_value_float(self, mock_context, mock_state):
        """Test ParseValue with float number."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", "3.14")

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "number",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result == 3.14

    @pytest.mark.asyncio
    async def test_parse_value_boolean_true(self, mock_context, mock_state):
        """Test ParseValue with boolean type (true)."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", "true")

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "boolean",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result is True

    @pytest.mark.asyncio
    async def test_parse_value_boolean_false(self, mock_context, mock_state):
        """Test ParseValue with boolean type (false)."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", "no")

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "boolean",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result is False

    @pytest.mark.asyncio
    async def test_parse_value_object_from_json(self, mock_context, mock_state):
        """Test ParseValue with object type from JSON string."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", '{"name": "Alice", "age": 30}')

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "object",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_parse_value_array_from_json(self, mock_context, mock_state):
        """Test ParseValue with array type from JSON string."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", '["a", "b", "c"]')

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
            "valueType": "array",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_parse_value_no_type_conversion(self, mock_context, mock_state):
        """Test ParseValue without type conversion."""
        from agent_framework_declarative._workflows._executors_basic import ParseValueExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.rawValue", {"status": "active"})

        action_def = {
            "kind": "ParseValue",
            "variable": "Local.parsedValue",
            "value": "=Local.rawValue",
        }
        executor = ParseValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.parsedValue")
        assert result == {"status": "active"}


class TestEditTableExecutor:
    """Tests for the EditTable action executor."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_edit_table_add(self, mock_context, mock_state):
        """Test EditTable with add operation."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "b"])

        action_def = {
            "kind": "EditTable",
            "table": "Local.items",
            "operation": "add",
            "value": "c",
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.items")
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_edit_table_insert_at_index(self, mock_context, mock_state):
        """Test EditTable with insert at specific index."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "c"])

        action_def = {
            "kind": "EditTable",
            "table": "Local.items",
            "operation": "add",
            "value": "b",
            "index": 1,
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.items")
        assert result == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_edit_table_remove_by_value(self, mock_context, mock_state):
        """Test EditTable with remove by value."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "b", "c"])

        action_def = {
            "kind": "EditTable",
            "table": "Local.items",
            "operation": "remove",
            "value": "b",
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.items")
        assert result == ["a", "c"]

    @pytest.mark.asyncio
    async def test_edit_table_remove_by_index(self, mock_context, mock_state):
        """Test EditTable with remove by index."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "b", "c"])

        action_def = {
            "kind": "EditTable",
            "table": "Local.items",
            "operation": "remove",
            "index": 1,
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.items")
        assert result == ["a", "c"]

    @pytest.mark.asyncio
    async def test_edit_table_clear(self, mock_context, mock_state):
        """Test EditTable with clear operation."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "b", "c"])

        action_def = {
            "kind": "EditTable",
            "table": "Local.items",
            "operation": "clear",
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.items")
        assert result == []

    @pytest.mark.asyncio
    async def test_edit_table_update_at_index(self, mock_context, mock_state):
        """Test EditTable with update at index."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.items", ["a", "b", "c"])

        action_def = {
            "kind": "EditTable",
            "table": "Local.items",
            "operation": "update",
            "value": "B",
            "index": 1,
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.items")
        assert result == ["a", "B", "c"]

    @pytest.mark.asyncio
    async def test_edit_table_creates_new_list(self, mock_context, mock_state):
        """Test EditTable creates new list if not exists."""
        from agent_framework_declarative._workflows._executors_basic import EditTableExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "EditTable",
            "table": "Local.newItems",
            "operation": "add",
            "value": "first",
        }
        executor = EditTableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.newItems")
        assert result == ["first"]


class TestEditTableV2Executor:
    """Tests for the EditTableV2 action executor."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_edit_table_v2_add(self, mock_context, mock_state):
        """Test EditTableV2 with add operation."""
        from agent_framework_declarative._workflows._executors_basic import EditTableV2Executor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.records", [{"id": 1, "name": "Alice"}])

        action_def = {
            "kind": "EditTableV2",
            "table": "Local.records",
            "operation": "add",
            "item": {"id": 2, "name": "Bob"},
        }
        executor = EditTableV2Executor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.records")
        assert result == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    @pytest.mark.asyncio
    async def test_edit_table_v2_add_or_update_new(self, mock_context, mock_state):
        """Test EditTableV2 with addOrUpdate - adding new record."""
        from agent_framework_declarative._workflows._executors_basic import EditTableV2Executor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.records", [{"id": 1, "name": "Alice"}])

        action_def = {
            "kind": "EditTableV2",
            "table": "Local.records",
            "operation": "addOrUpdate",
            "item": {"id": 2, "name": "Bob"},
            "key": "id",
        }
        executor = EditTableV2Executor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.records")
        assert result == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    @pytest.mark.asyncio
    async def test_edit_table_v2_add_or_update_existing(self, mock_context, mock_state):
        """Test EditTableV2 with addOrUpdate - updating existing record."""
        from agent_framework_declarative._workflows._executors_basic import EditTableV2Executor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.records", [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

        action_def = {
            "kind": "EditTableV2",
            "table": "Local.records",
            "operation": "addOrUpdate",
            "item": {"id": 1, "name": "Alice Updated"},
            "key": "id",
        }
        executor = EditTableV2Executor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.records")
        assert result == [{"id": 1, "name": "Alice Updated"}, {"id": 2, "name": "Bob"}]

    @pytest.mark.asyncio
    async def test_edit_table_v2_remove_by_key(self, mock_context, mock_state):
        """Test EditTableV2 with remove by key."""
        from agent_framework_declarative._workflows._executors_basic import EditTableV2Executor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.records", [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

        action_def = {
            "kind": "EditTableV2",
            "table": "Local.records",
            "operation": "remove",
            "item": {"id": 1},
            "key": "id",
        }
        executor = EditTableV2Executor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.records")
        assert result == [{"id": 2, "name": "Bob"}]

    @pytest.mark.asyncio
    async def test_edit_table_v2_clear(self, mock_context, mock_state):
        """Test EditTableV2 with clear operation."""
        from agent_framework_declarative._workflows._executors_basic import EditTableV2Executor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.records", [{"id": 1}, {"id": 2}])

        action_def = {
            "kind": "EditTableV2",
            "table": "Local.records",
            "operation": "clear",
        }
        executor = EditTableV2Executor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.records")
        assert result == []

    @pytest.mark.asyncio
    async def test_edit_table_v2_update_by_key(self, mock_context, mock_state):
        """Test EditTableV2 with update by key."""
        from agent_framework_declarative._workflows._executors_basic import EditTableV2Executor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()
        state.set("Local.records", [{"id": 1, "status": "pending"}, {"id": 2, "status": "pending"}])

        action_def = {
            "kind": "EditTableV2",
            "table": "Local.records",
            "operation": "update",
            "item": {"id": 1, "status": "complete"},
            "key": "id",
        }
        executor = EditTableV2Executor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = state.get("Local.records")
        assert result == [{"id": 1, "status": "complete"}, {"id": 2, "status": "pending"}]


class TestCancelDialogExecutors:
    """Tests for CancelDialog and CancelAllDialogs executors."""

    @pytest.fixture
    def mock_context(self, mock_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.state = mock_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_state(self):
        """Create a mock shared state."""
        mock_state = MagicMock()
        mock_state._data = {}

        def mock_get(key, default=None):
            return mock_state._data.get(key, default)

        def mock_set(key, value):
            mock_state._data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        return mock_state

    @pytest.mark.asyncio
    async def test_cancel_dialog_executor(self, mock_context, mock_state):
        """Test CancelDialogExecutor completes without error."""
        from agent_framework_declarative._workflows._executors_control_flow import CancelDialogExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "CancelDialog",
        }
        executor = CancelDialogExecutor(action_def)
        # Should complete without raising
        await executor.handle_action(ActionTrigger(), mock_context)
        # CancelDialog is a no-op that signals termination
        # No assertions needed - just verify it doesn't raise

    @pytest.mark.asyncio
    async def test_cancel_all_dialogs_executor(self, mock_context, mock_state):
        """Test CancelAllDialogsExecutor completes without error."""
        from agent_framework_declarative._workflows._executors_control_flow import CancelAllDialogsExecutor

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        action_def = {
            "kind": "CancelAllDialogs",
        }
        executor = CancelAllDialogsExecutor(action_def)
        # Should complete without raising
        await executor.handle_action(ActionTrigger(), mock_context)
        # CancelAllDialogs is a no-op that signals termination
        # No assertions needed - just verify it doesn't raise


class TestExtractJsonFromResponse:
    """Tests for the _extract_json_from_response helper function."""

    def test_pure_json_object(self):
        """Test parsing pure JSON object."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = '{"TicketId": "123", "Status": "pending"}'
        result = _extract_json_from_response(text)
        assert result == {"TicketId": "123", "Status": "pending"}

    def test_pure_json_array(self):
        """Test parsing pure JSON array."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = '["item1", "item2", "item3"]'
        result = _extract_json_from_response(text)
        assert result == ["item1", "item2", "item3"]

    def test_json_in_markdown_code_block(self):
        """Test extracting JSON from markdown code block."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = """Here's the response:
```json
{"TicketId": "456", "Summary": "Test ticket"}
```
"""
        result = _extract_json_from_response(text)
        assert result == {"TicketId": "456", "Summary": "Test ticket"}

    def test_json_in_plain_code_block(self):
        """Test extracting JSON from plain markdown code block."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = """The result:
```
{"Status": "complete"}
```
"""
        result = _extract_json_from_response(text)
        assert result == {"Status": "complete"}

    def test_json_with_leading_text(self):
        """Test extracting JSON with leading text."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = 'Here is the ticket information: {"TicketId": "789", "Priority": "high"}'
        result = _extract_json_from_response(text)
        assert result == {"TicketId": "789", "Priority": "high"}

    def test_json_with_trailing_text(self):
        """Test extracting JSON with trailing text."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = '{"IsResolved": true, "NeedsTicket": false} That is the status.'
        result = _extract_json_from_response(text)
        assert result == {"IsResolved": True, "NeedsTicket": False}

    def test_nested_json_object(self):
        """Test extracting nested JSON object."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = 'Result: {"outer": {"inner": {"value": 42}}}'
        result = _extract_json_from_response(text)
        assert result == {"outer": {"inner": {"value": 42}}}

    def test_json_with_array_inside(self):
        """Test extracting JSON with arrays inside."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = 'Data: {"items": ["a", "b", "c"], "count": 3}'
        result = _extract_json_from_response(text)
        assert result == {"items": ["a", "b", "c"], "count": 3}

    def test_json_with_escaped_quotes(self):
        """Test extracting JSON with escaped quotes in strings."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = r'Response: {"message": "He said \"hello\"", "valid": true}'
        result = _extract_json_from_response(text)
        assert result == {"message": 'He said "hello"', "valid": True}

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        result = _extract_json_from_response("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Test that whitespace-only string returns None."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        result = _extract_json_from_response("   \n\t  ")
        assert result is None

    def test_no_json_raises_error(self):
        """Test that text without JSON raises JSONDecodeError."""
        import json

        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        with pytest.raises(json.JSONDecodeError):
            _extract_json_from_response("This is just plain text with no JSON")

    def test_json_with_braces_in_string(self):
        """Test JSON with braces inside string values."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = 'Info: {"template": "Hello {name}, your id is {id}"}'
        result = _extract_json_from_response(text)
        assert result == {"template": "Hello {name}, your id is {id}"}

    def test_multiple_json_objects_returns_last(self):
        """Test that multiple JSON objects returns the last one (final result)."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        # Simulates streaming agent output with partial then final result
        text = '{"TicketId":"TBD","TicketSummary":"partial"}{"TicketId":"75178c95","TicketSummary":"final result"}'
        result = _extract_json_from_response(text)
        assert result == {"TicketId": "75178c95", "TicketSummary": "final result"}

    def test_multiple_json_objects_with_different_schemas(self):
        """Test multiple JSON objects with different structures returns the last."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        # First object is from one agent, second is from another
        text = '{"IsResolved":false,"NeedsTicket":true}{"TicketId":"abc123","Summary":"Issue logged"}'
        result = _extract_json_from_response(text)
        assert result == {"TicketId": "abc123", "Summary": "Issue logged"}

    def test_multiple_json_objects_with_text_between(self):
        """Test multiple JSON objects separated by text."""
        from agent_framework_declarative._workflows._executors_agents import (
            _extract_json_from_response,
        )

        text = 'First: {"status": "pending"} then later: {"status": "complete", "id": 42}'
        result = _extract_json_from_response(text)
        assert result == {"status": "complete", "id": 42}


class TestPowerFxConditionalImport:
    """The _declarative_base module should be importable without dotnet/powerfx."""

    def test_import_guard_exists(self):
        """The powerfx import must be wrapped in try/except."""
        import agent_framework_declarative._workflows._declarative_base as base_mod

        assert hasattr(base_mod, "DeclarativeWorkflowState")
        assert hasattr(base_mod, "Engine")

        # Engine should either be the real class or None — never an ImportError
        engine = base_mod.Engine
        assert engine is None or callable(engine)

    def test_eval_raises_when_engine_unavailable(self):
        """eval() should raise RuntimeError when Engine is None."""
        import agent_framework_declarative._workflows._declarative_base as base_mod

        mock_state = MagicMock()
        mock_state._data: dict[str, Any] = {}
        mock_state.get = MagicMock(side_effect=lambda k, d=None: mock_state._data.get(k, d))
        mock_state.set = MagicMock(side_effect=lambda k, v: mock_state._data.__setitem__(k, v))

        state = DeclarativeWorkflowState(mock_state)
        state.initialize({"name": "test"})

        original_engine = base_mod.Engine
        try:
            base_mod.Engine = None
            with pytest.raises(RuntimeError, match="PowerFx is not available"):
                state.eval("=Local.counter + 1")
        finally:
            base_mod.Engine = original_engine

    def test_eval_passes_through_plain_strings_without_engine(self):
        """Non-PowerFx strings (no leading '=') should work without Engine."""
        import agent_framework_declarative._workflows._declarative_base as base_mod

        mock_state = MagicMock()
        mock_state._data: dict[str, Any] = {}
        mock_state.get = MagicMock(side_effect=lambda k, d=None: mock_state._data.get(k, d))
        mock_state.set = MagicMock(side_effect=lambda k, v: mock_state._data.__setitem__(k, v))

        state = DeclarativeWorkflowState(mock_state)
        state.initialize()

        original_engine = base_mod.Engine
        try:
            base_mod.Engine = None
            assert state.eval("hello world") == "hello world"
            assert state.eval("") == ""
            assert state.eval(42) == 42
        finally:
            base_mod.Engine = original_engine


class TestExecutorKwargsForwarding:
    """Workflow run kwargs should be forwarded through executor agent invocations."""

    @pytest.mark.asyncio
    async def test_invoke_agent_forwards_kwargs(self):
        """InvokeAzureAgentExecutor should forward run_kwargs to agent.run()."""
        from agent_framework._workflows._const import WORKFLOW_RUN_KWARGS_KEY
        from agent_framework._workflows._state import State

        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        # Create a mock State with kwargs stored
        mock_state = MagicMock(spec=State)
        state_data: dict[str, Any] = {}

        def mock_get(key, default=None):
            return state_data.get(key, default)

        def mock_set(key, value):
            state_data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        # Store kwargs in state like Workflow.run() does
        test_kwargs = {"user_token": "abc123", "service_config": {"endpoint": "http://test"}}
        state_data[WORKFLOW_RUN_KWARGS_KEY] = test_kwargs

        # Initialize declarative state
        dws = DeclarativeWorkflowState(mock_state)
        dws.initialize({"input": "hello"})

        # Create a mock agent
        mock_response = MagicMock()
        mock_response.text = "response text"
        mock_response.messages = []
        mock_response.tool_calls = []
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_response)

        # Create a mock workflow context
        mock_ctx = MagicMock()
        mock_ctx.get_state = MagicMock(side_effect=mock_get)
        mock_ctx.yield_output = AsyncMock()

        executor = InvokeAzureAgentExecutor.__new__(InvokeAzureAgentExecutor)
        executor._agents = {"test_agent": mock_agent}

        await executor._invoke_agent_and_store_results(
            agent=mock_agent,
            agent_name="test_agent",
            input_text="hello",
            state=dws,
            ctx=mock_ctx,
            messages_var=None,
            response_obj_var=None,
            result_property=None,
            auto_send=True,
        )

        # Verify agent.run was called with kwargs
        mock_agent.run.assert_called_once()
        call_kwargs = mock_agent.run.call_args

        # Check options contains additional_function_arguments
        assert "options" in call_kwargs.kwargs
        assert call_kwargs.kwargs["options"]["additional_function_arguments"] == test_kwargs

        # Check direct kwargs were passed
        assert call_kwargs.kwargs.get("user_token") == "abc123"
        assert call_kwargs.kwargs.get("service_config") == {"endpoint": "http://test"}

    @pytest.mark.asyncio
    async def test_invoke_agent_merges_caller_options(self):
        """Caller-provided options in run_kwargs should be merged, not cause TypeError."""
        from agent_framework._workflows._const import WORKFLOW_RUN_KWARGS_KEY
        from agent_framework._workflows._state import State

        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        mock_state = MagicMock(spec=State)
        state_data: dict[str, Any] = {}

        def mock_get(key, default=None):
            return state_data.get(key, default)

        def mock_set(key, value):
            state_data[key] = value

        mock_state.get = MagicMock(side_effect=mock_get)
        mock_state.set = MagicMock(side_effect=mock_set)

        # Include 'options' in run_kwargs to test merge behavior
        test_kwargs = {
            "user_token": "abc123",
            "options": {"temperature": 0.5},
        }
        state_data[WORKFLOW_RUN_KWARGS_KEY] = test_kwargs

        dws = DeclarativeWorkflowState(mock_state)
        dws.initialize({"input": "hello"})

        mock_response = MagicMock()
        mock_response.text = "response text"
        mock_response.messages = []
        mock_response.tool_calls = []
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_response)

        mock_ctx = MagicMock()
        mock_ctx.get_state = MagicMock(side_effect=mock_get)
        mock_ctx.yield_output = AsyncMock()

        executor = InvokeAzureAgentExecutor.__new__(InvokeAzureAgentExecutor)
        executor._agents = {"test_agent": mock_agent}

        await executor._invoke_agent_and_store_results(
            agent=mock_agent,
            agent_name="test_agent",
            input_text="hello",
            state=dws,
            ctx=mock_ctx,
            messages_var=None,
            response_obj_var=None,
            result_property=None,
            auto_send=True,
        )

        mock_agent.run.assert_called_once()
        call_kwargs = mock_agent.run.call_args

        # Caller options should be merged with additional_function_arguments
        merged_options = call_kwargs.kwargs["options"]
        assert merged_options["temperature"] == 0.5
        assert "additional_function_arguments" in merged_options

        # Direct kwargs should be passed without 'options' (no duplicate keyword)
        assert call_kwargs.kwargs.get("user_token") == "abc123"
