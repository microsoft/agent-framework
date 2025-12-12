# Copyright (c) Microsoft. All rights reserved.

"""Tests for the graph-based declarative workflow executors."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework_declarative._workflows._graph import (
    ALL_ACTION_EXECUTORS,
    DECLARATIVE_STATE_KEY,
    ActionComplete,
    ActionTrigger,
    DeclarativeGraphBuilder,
    DeclarativeWorkflowState,
)
from agent_framework_declarative._workflows._graph._base import (
    LoopIterationResult,
)
from agent_framework_declarative._workflows._graph._executors_basic import (
    SendActivityExecutor,
    SetValueExecutor,
)
from agent_framework_declarative._workflows._graph._executors_control_flow import (
    ForeachInitExecutor,
)


class TestDeclarativeWorkflowState:
    """Tests for DeclarativeWorkflowState."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state with async get/set methods."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)

        return shared_state

    @pytest.mark.asyncio
    async def test_initialize_state(self, mock_shared_state):
        """Test initializing the workflow state."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"query": "test"})

        # Verify state was set
        mock_shared_state.set.assert_called_once()
        call_args = mock_shared_state.set.call_args
        assert call_args[0][0] == DECLARATIVE_STATE_KEY
        state_data = call_args[0][1]
        assert state_data["inputs"] == {"query": "test"}
        assert state_data["outputs"] == {}
        assert state_data["turn"] == {}

    @pytest.mark.asyncio
    async def test_get_and_set_values(self, mock_shared_state):
        """Test getting and setting values."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Set a turn value
        await state.set("turn.counter", 5)

        # Get the value
        result = await state.get("turn.counter")
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_inputs(self, mock_shared_state):
        """Test getting workflow inputs."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"name": "Alice", "age": 30})

        # Get via path
        name = await state.get("workflow.inputs.name")
        assert name == "Alice"

        # Get all inputs
        inputs = await state.get_inputs()
        assert inputs == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_append_value(self, mock_shared_state):
        """Test appending values to a list."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Append to non-existent list creates it
        await state.append("turn.items", "first")
        result = await state.get("turn.items")
        assert result == ["first"]

        # Append to existing list
        await state.append("turn.items", "second")
        result = await state.get("turn.items")
        assert result == ["first", "second"]

    @pytest.mark.asyncio
    async def test_eval_expression(self, mock_shared_state):
        """Test evaluating expressions."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Non-expression returns as-is
        result = await state.eval("plain text")
        assert result == "plain text"

        # Boolean literals
        result = await state.eval("=true")
        assert result is True

        result = await state.eval("=false")
        assert result is False

        # String literals
        result = await state.eval('="hello"')
        assert result == "hello"

        # Numeric literals
        result = await state.eval("=42")
        assert result == 42


class TestDeclarativeActionExecutor:
    """Tests for DeclarativeActionExecutor subclasses."""

    @pytest.fixture
    def mock_context(self, mock_shared_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.shared_state = mock_shared_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)

        return shared_state

    @pytest.mark.asyncio
    async def test_set_value_executor(self, mock_context, mock_shared_state):
        """Test SetValueExecutor."""
        # Initialize state
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "SetValue",
            "path": "turn.result",
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
    async def test_send_activity_executor(self, mock_context, mock_shared_state):
        """Test SendActivityExecutor."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

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

    async def test_foreach_init_with_items(self, mock_context, mock_shared_state):
        """Test ForeachInitExecutor with items."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("turn.items", ["a", "b", "c"])

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=turn.items",
            "iteratorVariable": "turn.item",
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
    async def test_foreach_init_empty(self, mock_context, mock_shared_state):
        """Test ForeachInitExecutor with empty items."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=turn.empty",
            "iteratorVariable": "turn.item",
        }
        executor = ForeachInitExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify result
        mock_context.send_message.assert_called_once()
        message = mock_context.send_message.call_args[0][0]
        assert isinstance(message, LoopIterationResult)
        assert message.has_next is False


class TestDeclarativeGraphBuilder:
    """Tests for DeclarativeGraphBuilder."""

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
        builder = DeclarativeGraphBuilder(yaml_def)

        with pytest.raises(ValueError, match="Cannot build workflow with no actions"):
            builder.build()

    def test_build_simple_workflow(self):
        """Test building a workflow with simple sequential actions."""
        yaml_def = {
            "name": "simple_workflow",
            "actions": [
                {"kind": "SendActivity", "id": "greet", "activity": {"text": "Hello!"}},
                {"kind": "SetValue", "id": "set_count", "path": "turn.count", "value": 1},
            ],
        }
        builder = DeclarativeGraphBuilder(yaml_def)
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
                    "condition": "=turn.flag",
                    "then": [
                        {"kind": "SendActivity", "id": "say_yes", "activity": {"text": "Yes!"}},
                    ],
                    "else": [
                        {"kind": "SendActivity", "id": "say_no", "activity": {"text": "No!"}},
                    ],
                },
            ],
        }
        builder = DeclarativeGraphBuilder(yaml_def)
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
                    "itemsSource": "=turn.items",
                    "iteratorVariable": "turn.item",
                    "actions": [
                        {"kind": "SendActivity", "id": "show_item", "activity": {"text": "=turn.item"}},
                    ],
                },
            ],
        }
        builder = DeclarativeGraphBuilder(yaml_def)
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
                            "condition": '=turn.status = "active"',
                            "actions": [
                                {"kind": "SendActivity", "id": "say_active", "activity": {"text": "Active"}},
                            ],
                        },
                        {
                            "condition": '=turn.status = "pending"',
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
        builder = DeclarativeGraphBuilder(yaml_def)
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
    def mock_context(self, mock_shared_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.shared_state = mock_shared_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)

        return shared_state

    @pytest.mark.asyncio
    async def test_invoke_agent_not_found(self, mock_context, mock_shared_state):
        """Test InvokeAzureAgentExecutor raises error when agent not found."""
        from agent_framework_declarative._workflows._graph._executors_agents import (
            AgentInvocationError,
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "non_existent_agent",
            "input": "test input",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        # Execute - should raise AgentInvocationError
        with pytest.raises(AgentInvocationError) as exc_info:
            await executor.handle_action(ActionTrigger(), mock_context)

        assert "non_existent_agent" in str(exc_info.value)
        assert "not found in registry" in str(exc_info.value)


class TestHumanInputExecutors:
    """Tests for human input executors."""

    @pytest.fixture
    def mock_context(self, mock_shared_state):
        """Create a mock workflow context."""
        ctx = MagicMock()
        ctx.shared_state = mock_shared_state
        ctx.send_message = AsyncMock()
        ctx.yield_output = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)

        return shared_state

    @pytest.mark.asyncio
    async def test_question_executor(self, mock_context, mock_shared_state):
        """Test QuestionExecutor."""
        from agent_framework_declarative._workflows._graph._executors_human_input import (
            HumanInputRequest,
            QuestionExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "Question",
            "text": "What is your name?",
            "property": "turn.name",
            "defaultValue": "Anonymous",
        }
        executor = QuestionExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify human input request was yielded
        assert mock_context.yield_output.called
        request = mock_context.yield_output.call_args_list[0][0][0]
        assert isinstance(request, HumanInputRequest)
        assert request.request_type == "question"
        assert "What is your name?" in request.message

    @pytest.mark.asyncio
    async def test_confirmation_executor(self, mock_context, mock_shared_state):
        """Test ConfirmationExecutor."""
        from agent_framework_declarative._workflows._graph._executors_human_input import (
            ConfirmationExecutor,
            HumanInputRequest,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "Confirmation",
            "text": "Do you want to continue?",
            "property": "turn.confirmed",
            "yesLabel": "Yes, continue",
            "noLabel": "No, stop",
        }
        executor = ConfirmationExecutor(action_def)

        # Execute
        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify confirmation request was yielded
        assert mock_context.yield_output.called
        request = mock_context.yield_output.call_args_list[0][0][0]
        assert isinstance(request, HumanInputRequest)
        assert request.request_type == "confirmation"
        assert "continue" in request.message.lower()
