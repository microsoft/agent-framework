# Copyright (c) Microsoft. All rights reserved.
# pyright: reportUnknownParameterType=false, reportUnknownArgumentType=false
# pyright: reportMissingParameterType=false, reportUnknownMemberType=false
# pyright: reportPrivateUsage=false, reportUnknownVariableType=false
# pyright: reportGeneralTypeIssues=false

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework_declarative._workflows import (
    ActionComplete,
    ActionTrigger,
    DeclarativeWorkflowState,
)
from agent_framework_declarative._workflows._declarative_base import (
    ConditionResult,
    LoopControl,
    LoopIterationResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_shared_state() -> MagicMock:
    """Create a mock shared state with async get/set/delete methods."""
    shared_state = MagicMock()
    shared_state._data = {}

    async def mock_get(key: str) -> Any:
        if key not in shared_state._data:
            raise KeyError(key)
        return shared_state._data[key]

    async def mock_set(key: str, value: Any) -> None:
        shared_state._data[key] = value

    async def mock_delete(key: str) -> None:
        if key in shared_state._data:
            del shared_state._data[key]

    shared_state.get = AsyncMock(side_effect=mock_get)
    shared_state.set = AsyncMock(side_effect=mock_set)
    shared_state.delete = AsyncMock(side_effect=mock_delete)

    return shared_state


@pytest.fixture
def mock_context(mock_shared_state: MagicMock) -> MagicMock:
    """Create a mock workflow context."""
    ctx = MagicMock()
    ctx.shared_state = mock_shared_state
    ctx.send_message = AsyncMock()
    ctx.yield_output = AsyncMock()
    ctx.request_info = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# DeclarativeWorkflowState Tests - Covering _base.py gaps
# ---------------------------------------------------------------------------


class TestDeclarativeWorkflowStateExtended:
    """Extended tests for DeclarativeWorkflowState covering uncovered code paths."""

    async def test_get_with_local_namespace(self, mock_shared_state):
        """Test Local. namespace mapping."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.myVar", "value123")

        # Access via Local. namespace
        result = await state.get("Local.myVar")
        assert result == "value123"

    async def test_get_with_system_namespace(self, mock_shared_state):
        """Test System. namespace mapping."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("System.ConversationId", "conv-123")

        result = await state.get("System.ConversationId")
        assert result == "conv-123"

    async def test_get_with_workflow_namespace(self, mock_shared_state):
        """Test Workflow. namespace mapping."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"query": "test"})

        result = await state.get("Workflow.Inputs.query")
        assert result == "test"

    async def test_get_with_inputs_shorthand(self, mock_shared_state):
        """Test inputs. shorthand namespace mapping."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"query": "test"})

        result = await state.get("Workflow.Inputs.query")
        assert result == "test"

    async def test_get_agent_namespace(self, mock_shared_state):
        """Test agent namespace access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Agent.response", "Hello!")

        result = await state.get("Agent.response")
        assert result == "Hello!"

    async def test_get_conversation_namespace(self, mock_shared_state):
        """Test conversation namespace access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Conversation.messages", [{"role": "user", "text": "hi"}])

        result = await state.get("Conversation.messages")
        assert result == [{"role": "user", "text": "hi"}]

    async def test_get_custom_namespace(self, mock_shared_state):
        """Test custom namespace access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Set via direct state data manipulation to create custom namespace
        state_data = await state.get_state_data()
        state_data["Custom"] = {"myns": {"value": 42}}
        await state.set_state_data(state_data)

        result = await state.get("myns.value")
        assert result == 42

    async def test_get_object_attribute_access(self, mock_shared_state):
        """Test accessing object attributes via hasattr/getattr path."""

        @dataclass
        class MockObj:
            name: str
            value: int

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.obj", MockObj(name="test", value=99))

        result = await state.get("Local.obj.name")
        assert result == "test"

    async def test_set_with_local_namespace(self, mock_shared_state):
        """Test Local. namespace mapping for set."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set("Local.myVar", "value123")
        result = await state.get("Local.myVar")
        assert result == "value123"

    async def test_set_with_system_namespace(self, mock_shared_state):
        """Test System. namespace mapping for set."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set("System.ConversationId", "conv-456")
        result = await state.get("System.ConversationId")
        assert result == "conv-456"

    async def test_set_workflow_outputs(self, mock_shared_state):
        """Test setting workflow outputs."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set("Workflow.Outputs.result", "done")
        outputs = await state.get("Workflow.Outputs")
        assert outputs.get("result") == "done"

    async def test_set_workflow_inputs_raises_error(self, mock_shared_state):
        """Test that setting Workflow.Inputs raises an error (read-only)."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"query": "test"})

        with pytest.raises(ValueError, match="Cannot modify Workflow.Inputs"):
            await state.set("Workflow.Inputs.query", "modified")

    async def test_set_workflow_directly_raises_error(self, mock_shared_state):
        """Test that setting 'Workflow' directly raises an error."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        with pytest.raises(ValueError, match="Cannot set 'Workflow' directly"):
            await state.set("Workflow", {})

    async def test_set_unknown_workflow_subnamespace_raises_error(self, mock_shared_state):
        """Test unknown workflow sub-namespace raises error."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        with pytest.raises(ValueError, match="Unknown Workflow namespace"):
            await state.set("Workflow.unknown.field", "value")

    async def test_set_creates_custom_namespace(self, mock_shared_state):
        """Test setting value in custom namespace creates it."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set("myns.field.nested", "value")
        result = await state.get("myns.field.nested")
        assert result == "value"

    async def test_set_cannot_replace_entire_namespace(self, mock_shared_state):
        """Test that replacing entire namespace raises error."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        with pytest.raises(ValueError, match="Cannot replace entire namespace"):
            await state.set("turn", {})

    async def test_append_to_nonlist_raises_error(self, mock_shared_state):
        """Test appending to non-list raises error."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.scalar", "string value")

        with pytest.raises(ValueError, match="Cannot append to non-list"):
            await state.append("Local.scalar", "new item")

    async def test_eval_empty_string(self, mock_shared_state):
        """Test evaluating empty string returns as-is."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        result = await state.eval("")
        assert result == ""

    async def test_eval_non_string_returns_as_is(self, mock_shared_state):
        """Test evaluating non-string returns as-is."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Cast to Any to test the runtime behavior with non-string inputs
        result = await state.eval(42)  # type: ignore[arg-type]
        assert result == 42

        result = await state.eval([1, 2, 3])  # type: ignore[arg-type]
        assert result == [1, 2, 3]

    async def test_eval_simple_and_operator(self, mock_shared_state):
        """Test simple And operator evaluation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.a", True)
        await state.set("Local.b", False)

        result = await state.eval("=Local.a And Local.b")
        assert result is False

        await state.set("Local.b", True)
        result = await state.eval("=Local.a And Local.b")
        assert result is True

    async def test_eval_simple_or_operator(self, mock_shared_state):
        """Test simple Or operator evaluation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.a", True)
        await state.set("Local.b", False)

        result = await state.eval("=Local.a Or Local.b")
        assert result is True

        await state.set("Local.a", False)
        result = await state.eval("=Local.a Or Local.b")
        assert result is False

    async def test_eval_negation(self, mock_shared_state):
        """Test negation (!) evaluation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.flag", True)

        result = await state.eval("=!Local.flag")
        assert result is False

    async def test_eval_not_function(self, mock_shared_state):
        """Test Not() function evaluation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.flag", True)

        result = await state.eval("=Not(Local.flag)")
        assert result is False

    async def test_eval_comparison_operators(self, mock_shared_state):
        """Test comparison operators."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 5)
        await state.set("Local.y", 10)

        assert await state.eval("=Local.x < Local.y") is True
        assert await state.eval("=Local.x > Local.y") is False
        assert await state.eval("=Local.x <= 5") is True
        assert await state.eval("=Local.x >= 5") is True
        assert await state.eval("=Local.x <> Local.y") is True
        assert await state.eval("=Local.x = 5") is True

    async def test_eval_arithmetic_operators(self, mock_shared_state):
        """Test arithmetic operators."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 10)
        await state.set("Local.y", 3)

        assert await state.eval("=Local.x + Local.y") == 13
        assert await state.eval("=Local.x - Local.y") == 7
        assert await state.eval("=Local.x * Local.y") == 30
        assert await state.eval("=Local.x / Local.y") == pytest.approx(3.333, rel=0.01)

    async def test_eval_string_literal(self, mock_shared_state):
        """Test string literal evaluation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        result = await state.eval('="hello world"')
        assert result == "hello world"

    async def test_eval_float_literal(self, mock_shared_state):
        """Test float literal evaluation."""
        from decimal import Decimal

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        result = await state.eval("=3.14")
        # Accepts both float (Python fallback) and Decimal (pythonnet/PowerFx)
        assert result == 3.14 or result == Decimal("3.14")

    async def test_eval_variable_reference_with_namespace_mappings(self, mock_shared_state):
        """Test variable reference with PowerFx symbols."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"query": "test"})
        await state.set("Local.myVar", "localValue")

        # Test Local namespace (PowerFx symbol)
        result = await state.eval("=Local.myVar")
        assert result == "localValue"

        # Test Workflow.Inputs (PowerFx symbol)
        result = await state.eval("=Workflow.Inputs.query")
        assert result == "test"

    async def test_eval_if_expression_with_dict(self, mock_shared_state):
        """Test eval_if_expression recursively evaluates dicts."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.name", "Alice")

        result = await state.eval_if_expression({"greeting": "=Local.name", "static": "hello"})
        assert result == {"greeting": "Alice", "static": "hello"}

    async def test_eval_if_expression_with_list(self, mock_shared_state):
        """Test eval_if_expression recursively evaluates lists."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 10)

        result = await state.eval_if_expression(["=Local.x", "static", "=5"])
        assert result == [10, "static", 5]

    async def test_interpolate_string_with_local_vars(self, mock_shared_state):
        """Test string interpolation with Local. variables."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.TicketId", "TKT-001")
        await state.set("Local.TeamName", "Support")

        result = await state.interpolate_string("Created ticket #{Local.TicketId} for team {Local.TeamName}")
        assert result == "Created ticket #TKT-001 for team Support"

    async def test_interpolate_string_with_system_vars(self, mock_shared_state):
        """Test string interpolation with System. variables."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("System.ConversationId", "conv-789")

        result = await state.interpolate_string("Conversation: {System.ConversationId}")
        assert result == "Conversation: conv-789"

    async def test_interpolate_string_with_none_value(self, mock_shared_state):
        """Test string interpolation with None value returns empty string."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        result = await state.interpolate_string("Value: {Local.Missing}")
        assert result == "Value: "


# ---------------------------------------------------------------------------
# Basic Executors Tests - Covering _executors_basic.py gaps
# ---------------------------------------------------------------------------


class TestBasicExecutorsCoverage:
    """Tests for basic executors covering uncovered code paths."""

    async def test_set_variable_executor(self, mock_context, mock_shared_state):
        """Test SetVariableExecutor (distinct from SetValueExecutor)."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetVariableExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "SetVariable",
            "variable": "Local.result",
            "value": "test value",
        }
        executor = SetVariableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.result")
        assert result == "test value"

    async def test_set_variable_executor_with_nested_variable(self, mock_context, mock_shared_state):
        """Test SetVariableExecutor with nested variable object."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetVariableExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "SetVariable",
            "variable": {"path": "Local.nested"},
            "value": 42,
        }
        executor = SetVariableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.nested")
        assert result == 42

    async def test_set_text_variable_executor(self, mock_context, mock_shared_state):
        """Test SetTextVariableExecutor."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetTextVariableExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.name", "World")

        action_def = {
            "kind": "SetTextVariable",
            "variable": "Local.greeting",
            "text": "=Local.name",
        }
        executor = SetTextVariableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.greeting")
        assert result == "World"

    async def test_set_multiple_variables_executor(self, mock_context, mock_shared_state):
        """Test SetMultipleVariablesExecutor."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetMultipleVariablesExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "SetMultipleVariables",
            "assignments": [
                {"variable": "Local.a", "value": 1},
                {"variable": {"path": "Local.b"}, "value": 2},
                {"path": "Local.c", "value": 3},
            ],
        }
        executor = SetMultipleVariablesExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        assert await state.get("Local.a") == 1
        assert await state.get("Local.b") == 2
        assert await state.get("Local.c") == 3

    async def test_append_value_executor(self, mock_context, mock_shared_state):
        """Test AppendValueExecutor."""
        from agent_framework_declarative._workflows._executors_basic import (
            AppendValueExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.items", ["a"])

        action_def = {
            "kind": "AppendValue",
            "path": "Local.items",
            "value": "b",
        }
        executor = AppendValueExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.items")
        assert result == ["a", "b"]

    async def test_reset_variable_executor(self, mock_context, mock_shared_state):
        """Test ResetVariableExecutor."""
        from agent_framework_declarative._workflows._executors_basic import (
            ResetVariableExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.myVar", "some value")

        action_def = {
            "kind": "ResetVariable",
            "variable": "Local.myVar",
        }
        executor = ResetVariableExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.myVar")
        assert result is None

    async def test_clear_all_variables_executor(self, mock_context, mock_shared_state):
        """Test ClearAllVariablesExecutor."""
        from agent_framework_declarative._workflows._executors_basic import (
            ClearAllVariablesExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.a", 1)
        await state.set("Local.b", 2)

        action_def = {"kind": "ClearAllVariables"}
        executor = ClearAllVariablesExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        # Turn namespace should be cleared
        assert await state.get("Local.a") is None
        assert await state.get("Local.b") is None

    async def test_send_activity_with_dict_activity(self, mock_context, mock_shared_state):
        """Test SendActivityExecutor with dict activity containing text field."""
        from agent_framework_declarative._workflows._executors_basic import (
            SendActivityExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.name", "Alice")

        action_def = {
            "kind": "SendActivity",
            "activity": {"text": "Hello, {Local.name}!"},
        }
        executor = SendActivityExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.yield_output.assert_called_once_with("Hello, Alice!")

    async def test_send_activity_with_string_activity(self, mock_context, mock_shared_state):
        """Test SendActivityExecutor with string activity."""
        from agent_framework_declarative._workflows._executors_basic import (
            SendActivityExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "SendActivity",
            "activity": "Plain text message",
        }
        executor = SendActivityExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.yield_output.assert_called_once_with("Plain text message")

    async def test_send_activity_with_expression(self, mock_context, mock_shared_state):
        """Test SendActivityExecutor evaluates expressions."""
        from agent_framework_declarative._workflows._executors_basic import (
            SendActivityExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.msg", "Dynamic message")

        action_def = {
            "kind": "SendActivity",
            "activity": "=Local.msg",
        }
        executor = SendActivityExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.yield_output.assert_called_once_with("Dynamic message")

    async def test_emit_event_executor_graph_mode(self, mock_context, mock_shared_state):
        """Test EmitEventExecutor with graph-mode schema (eventName/eventValue)."""
        from agent_framework_declarative._workflows._executors_basic import (
            EmitEventExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "EmitEvent",
            "eventName": "myEvent",
            "eventValue": {"key": "value"},
        }
        executor = EmitEventExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.yield_output.assert_called_once()
        event_data = mock_context.yield_output.call_args[0][0]
        assert event_data["eventName"] == "myEvent"
        assert event_data["eventValue"] == {"key": "value"}

    async def test_emit_event_executor_interpreter_mode(self, mock_context, mock_shared_state):
        """Test EmitEventExecutor with interpreter-mode schema (event.name/event.data)."""
        from agent_framework_declarative._workflows._executors_basic import (
            EmitEventExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "EmitEvent",
            "event": {
                "name": "interpreterEvent",
                "data": {"payload": "test"},
            },
        }
        executor = EmitEventExecutor(action_def)
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.yield_output.assert_called_once()
        event_data = mock_context.yield_output.call_args[0][0]
        assert event_data["eventName"] == "interpreterEvent"
        assert event_data["eventValue"] == {"payload": "test"}


# ---------------------------------------------------------------------------
# Agent Executors Tests - Covering _executors_agents.py gaps
# ---------------------------------------------------------------------------


class TestAgentExecutorsCoverage:
    """Tests for agent executors covering uncovered code paths."""

    async def test_normalize_variable_path_all_cases(self):
        """Test _normalize_variable_path with all namespace prefixes."""
        from agent_framework_declarative._workflows._executors_agents import (
            _normalize_variable_path,
        )

        # Local. -> Local. (unchanged)
        assert _normalize_variable_path("Local.MyVar") == "Local.MyVar"

        # System. -> System. (unchanged)
        assert _normalize_variable_path("System.ConvId") == "System.ConvId"

        # Workflow. -> Workflow. (unchanged)
        assert _normalize_variable_path("Workflow.Outputs.result") == "Workflow.Outputs.result"

        # Already has a namespace with dots - pass through
        assert _normalize_variable_path("custom.existing") == "custom.existing"

        # No namespace - default to Local.
        assert _normalize_variable_path("simpleVar") == "Local.simpleVar"

    async def test_agent_executor_get_agent_name_string(self, mock_context, mock_shared_state):
        """Test agent name extraction from simple string config."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "MyAgent",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        name = executor._get_agent_name(state)
        assert name == "MyAgent"

    async def test_agent_executor_get_agent_name_dict(self, mock_context, mock_shared_state):
        """Test agent name extraction from nested dict config."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": {"name": "NestedAgent"},
        }
        executor = InvokeAzureAgentExecutor(action_def)

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        name = executor._get_agent_name(state)
        assert name == "NestedAgent"

    async def test_agent_executor_get_agent_name_legacy(self, mock_context, mock_shared_state):
        """Test agent name extraction from agentName (legacy)."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agentName": "LegacyAgent",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        name = executor._get_agent_name(state)
        assert name == "LegacyAgent"

    async def test_agent_executor_get_input_config_simple(self, mock_context, mock_shared_state):
        """Test input config parsing with simple non-dict input."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "input": "simple string input",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        args, messages, external_loop, max_iterations = executor._get_input_config()
        assert args == {}
        assert messages == "simple string input"
        assert external_loop is None
        assert max_iterations == 100  # Default

    async def test_agent_executor_get_input_config_full(self, mock_context, mock_shared_state):
        """Test input config parsing with full structured input."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "input": {
                "arguments": {"param1": "=Local.value"},
                "messages": "=conversation.messages",
                "externalLoop": {"when": "=Local.needsMore", "maxIterations": 50},
            },
        }
        executor = InvokeAzureAgentExecutor(action_def)

        args, messages, external_loop, max_iterations = executor._get_input_config()
        assert args == {"param1": "=Local.value"}
        assert messages == "=conversation.messages"
        assert external_loop == "=Local.needsMore"
        assert max_iterations == 50

    async def test_agent_executor_get_output_config_simple(self, mock_context, mock_shared_state):
        """Test output config parsing with simple resultProperty."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "resultProperty": "Local.result",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        messages_var, response_obj, result_prop, auto_send = executor._get_output_config()
        assert messages_var is None
        assert response_obj is None
        assert result_prop == "Local.result"
        assert auto_send is True

    async def test_agent_executor_get_output_config_full(self, mock_context, mock_shared_state):
        """Test output config parsing with full structured output."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "output": {
                "messages": "Local.ResponseMessages",
                "responseObject": "Local.ParsedResponse",
                "property": "Local.result",
                "autoSend": False,
            },
        }
        executor = InvokeAzureAgentExecutor(action_def)

        messages_var, response_obj, result_prop, auto_send = executor._get_output_config()
        assert messages_var == "Local.ResponseMessages"
        assert response_obj == "Local.ParsedResponse"
        assert result_prop == "Local.result"
        assert auto_send is False

    async def test_agent_executor_build_input_text_from_string_messages(self, mock_context, mock_shared_state):
        """Test _build_input_text with string messages expression."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.userInput", "Hello agent!")

        action_def = {"kind": "InvokeAzureAgent", "agent": "Test"}
        executor = InvokeAzureAgentExecutor(action_def)

        input_text = await executor._build_input_text(state, {}, "=Local.userInput")
        assert input_text == "Hello agent!"

    async def test_agent_executor_build_input_text_from_message_list(self, mock_context, mock_shared_state):
        """Test _build_input_text extracts text from message list."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set(
            "Conversation.messages",
            [
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "Response"},
                {"role": "user", "content": "Last message"},
            ],
        )

        action_def = {"kind": "InvokeAzureAgent", "agent": "Test"}
        executor = InvokeAzureAgentExecutor(action_def)

        input_text = await executor._build_input_text(state, {}, "=Conversation.messages")
        assert input_text == "Last message"

    async def test_agent_executor_build_input_text_from_message_with_text_attr(self, mock_context, mock_shared_state):
        """Test _build_input_text extracts text from message with text attribute."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.messages", [{"text": "From attribute"}])

        action_def = {"kind": "InvokeAzureAgent", "agent": "Test"}
        executor = InvokeAzureAgentExecutor(action_def)

        input_text = await executor._build_input_text(state, {}, "=Local.messages")
        assert input_text == "From attribute"

    async def test_agent_executor_build_input_text_fallback_chain(self, mock_context, mock_shared_state):
        """Test _build_input_text fallback chain when no messages expression."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"query": "workflow input"})

        action_def = {"kind": "InvokeAzureAgent", "agent": "Test"}
        executor = InvokeAzureAgentExecutor(action_def)

        # No messages_expr, so falls back to workflow.inputs
        input_text = await executor._build_input_text(state, {}, None)
        assert input_text == "workflow input"

    async def test_agent_executor_build_input_text_from_system_last_message(self, mock_context, mock_shared_state):
        """Test _build_input_text falls back to system.LastMessage.Text."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("System.LastMessage", {"Text": "From last message"})

        action_def = {"kind": "InvokeAzureAgent", "agent": "Test"}
        executor = InvokeAzureAgentExecutor(action_def)

        input_text = await executor._build_input_text(state, {}, None)
        assert input_text == "From last message"

    async def test_agent_executor_missing_agent_name(self, mock_context, mock_shared_state):
        """Test agent executor with missing agent name logs warning."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "InvokeAzureAgent"}  # No agent specified
        executor = InvokeAzureAgentExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should complete without error
        mock_context.send_message.assert_called_once()
        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ActionComplete)

    async def test_agent_executor_with_working_agent(self, mock_context, mock_shared_state):
        """Test agent executor with a working mock agent."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        # Create mock agent
        @dataclass
        class MockResult:
            text: str
            messages: list[Any]

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MockResult(text="Agent response", messages=[]))

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.input", "User query")

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "resultProperty": "Local.result",
        }
        executor = InvokeAzureAgentExecutor(action_def, agents={"TestAgent": mock_agent})

        await executor.handle_action(ActionTrigger(), mock_context)

        # Verify agent was called
        mock_agent.run.assert_called_once()

        # Verify result was stored
        result = await state.get("Local.result")
        assert result == "Agent response"

        # Verify agent state was set
        assert await state.get("Agent.response") == "Agent response"
        assert await state.get("Agent.name") == "TestAgent"
        assert await state.get("Agent.text") == "Agent response"

    async def test_agent_executor_with_agent_from_registry(self, mock_context, mock_shared_state):
        """Test agent executor retrieves agent from shared state registry."""
        from agent_framework_declarative._workflows._executors_agents import (
            AGENT_REGISTRY_KEY,
            InvokeAzureAgentExecutor,
        )

        # Create mock agent
        @dataclass
        class MockResult:
            text: str
            messages: list[Any]

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MockResult(text="Registry agent", messages=[]))

        # Store in registry
        mock_shared_state._data[AGENT_REGISTRY_KEY] = {"RegistryAgent": mock_agent}

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.input", "Query")

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "RegistryAgent",
        }
        executor = InvokeAzureAgentExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        mock_agent.run.assert_called_once()

    async def test_agent_executor_parses_json_response(self, mock_context, mock_shared_state):
        """Test agent executor parses JSON response into responseObject."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        @dataclass
        class MockResult:
            text: str
            messages: list[Any]

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=MockResult(text='{"status": "ok", "count": 42}', messages=[]))

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.input", "Query")

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "output": {
                "responseObject": "Local.Parsed",
            },
        }
        executor = InvokeAzureAgentExecutor(action_def, agents={"TestAgent": mock_agent})

        await executor.handle_action(ActionTrigger(), mock_context)

        parsed = await state.get("Local.Parsed")
        assert parsed == {"status": "ok", "count": 42}

    async def test_invoke_tool_executor_not_found(self, mock_context, mock_shared_state):
        """Test InvokeToolExecutor when tool not found."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeToolExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "InvokeTool",
            "tool": "MissingTool",
            "resultProperty": "Local.result",
        }
        executor = InvokeToolExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.result")
        assert result == {"error": "Tool 'MissingTool' not found in registry"}

    async def test_invoke_tool_executor_sync_tool(self, mock_context, mock_shared_state):
        """Test InvokeToolExecutor with synchronous tool."""
        from agent_framework_declarative._workflows._executors_agents import (
            TOOL_REGISTRY_KEY,
            InvokeToolExecutor,
        )

        def my_tool(x: int, y: int) -> int:
            return x + y

        mock_shared_state._data[TOOL_REGISTRY_KEY] = {"add": my_tool}

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "InvokeTool",
            "tool": "add",
            "parameters": {"x": 5, "y": 3},
            "resultProperty": "Local.result",
        }
        executor = InvokeToolExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.result")
        assert result == 8

    async def test_invoke_tool_executor_async_tool(self, mock_context, mock_shared_state):
        """Test InvokeToolExecutor with asynchronous tool."""
        from agent_framework_declarative._workflows._executors_agents import (
            TOOL_REGISTRY_KEY,
            InvokeToolExecutor,
        )

        async def my_async_tool(input: str) -> str:
            return f"Processed: {input}"

        mock_shared_state._data[TOOL_REGISTRY_KEY] = {"process": my_async_tool}

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "InvokeTool",
            "tool": "process",
            "input": "test data",
            "resultProperty": "Local.result",
        }
        executor = InvokeToolExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.result")
        assert result == "Processed: test data"


# ---------------------------------------------------------------------------
# Control Flow Executors Tests - Additional coverage
# ---------------------------------------------------------------------------


class TestControlFlowCoverage:
    """Tests for control flow executors covering uncovered code paths."""

    async def test_foreach_with_source_alias(self, mock_context, mock_shared_state):
        """Test ForeachInitExecutor with 'source' alias (interpreter mode)."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            ForeachInitExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.data", [10, 20, 30])

        action_def = {
            "kind": "Foreach",
            "source": "=Local.data",
            "itemName": "item",
            "indexName": "idx",
        }
        executor = ForeachInitExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopIterationResult)
        assert msg.has_next is True
        assert msg.current_item == 10
        assert msg.current_index == 0

    async def test_foreach_next_continues_iteration(self, mock_context, mock_shared_state):
        """Test ForeachNextExecutor continues to next item."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            LOOP_STATE_KEY,
            ForeachNextExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.data", ["a", "b", "c"])

        # Set up loop state as ForeachInitExecutor would
        state_data = await state.get_state_data()
        state_data[LOOP_STATE_KEY] = {
            "foreach_init": {
                "items": ["a", "b", "c"],
                "index": 0,
                "length": 3,
            }
        }
        await state.set_state_data(state_data)

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=Local.data",
            "iteratorVariable": "Local.item",
        }
        executor = ForeachNextExecutor(action_def, init_executor_id="foreach_init")

        await executor.handle_action(LoopIterationResult(has_next=True), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopIterationResult)
        assert msg.current_index == 1
        assert msg.current_item == "b"

    async def test_switch_evaluator_with_value_cases(self, mock_context, mock_shared_state):
        """Test SwitchEvaluatorExecutor with value/cases schema."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            SwitchEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.status", "pending")

        action_def = {
            "kind": "Switch",
            "value": "=Local.status",
        }
        cases = [
            {"match": "active"},
            {"match": "pending"},
        ]
        executor = SwitchEvaluatorExecutor(action_def, cases=cases)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is True
        assert msg.branch_index == 1  # Second case matched

    async def test_switch_evaluator_default_case(self, mock_context, mock_shared_state):
        """Test SwitchEvaluatorExecutor falls through to default."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            SwitchEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.status", "unknown")

        action_def = {
            "kind": "Switch",
            "value": "=Local.status",
        }
        cases = [
            {"match": "active"},
            {"match": "pending"},
        ]
        executor = SwitchEvaluatorExecutor(action_def, cases=cases)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is False
        assert msg.branch_index == -1  # Default case

    async def test_switch_evaluator_no_value(self, mock_context, mock_shared_state):
        """Test SwitchEvaluatorExecutor with no value defaults to else."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            SwitchEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "Switch"}  # No value
        cases = [{"match": "x"}]
        executor = SwitchEvaluatorExecutor(action_def, cases=cases)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.branch_index == -1

    async def test_join_executor_accepts_condition_result(self, mock_context, mock_shared_state):
        """Test JoinExecutor accepts ConditionResult as trigger."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            JoinExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "_Join"}
        executor = JoinExecutor(action_def)

        # Trigger with ConditionResult
        await executor.handle_action(ConditionResult(matched=True, branch_index=0), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ActionComplete)

    async def test_break_loop_executor(self, mock_context, mock_shared_state):
        """Test BreakLoopExecutor emits LoopControl."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            BreakLoopExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "BreakLoop"}
        executor = BreakLoopExecutor(action_def, loop_next_executor_id="loop_next")

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopControl)
        assert msg.action == "break"

    async def test_continue_loop_executor(self, mock_context, mock_shared_state):
        """Test ContinueLoopExecutor emits LoopControl."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            ContinueLoopExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "ContinueLoop"}
        executor = ContinueLoopExecutor(action_def, loop_next_executor_id="loop_next")

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopControl)
        assert msg.action == "continue"

    async def test_foreach_next_no_loop_state(self, mock_context, mock_shared_state):
        """Test ForeachNextExecutor with missing loop state."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            ForeachNextExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=Local.data",
            "iteratorVariable": "Local.item",
        }
        executor = ForeachNextExecutor(action_def, init_executor_id="missing_loop")

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopIterationResult)
        assert msg.has_next is False

    async def test_foreach_next_loop_complete(self, mock_context, mock_shared_state):
        """Test ForeachNextExecutor when loop is complete."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            LOOP_STATE_KEY,
            ForeachNextExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Set up loop state at last item
        state_data = await state.get_state_data()
        state_data[LOOP_STATE_KEY] = {
            "loop_id": {
                "items": ["a", "b"],
                "index": 1,  # Already at last item
                "length": 2,
            }
        }
        await state.set_state_data(state_data)

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=Local.data",
            "iteratorVariable": "Local.item",
        }
        executor = ForeachNextExecutor(action_def, init_executor_id="loop_id")

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopIterationResult)
        assert msg.has_next is False

    async def test_foreach_next_handle_break_control(self, mock_context, mock_shared_state):
        """Test ForeachNextExecutor handles break LoopControl."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            LOOP_STATE_KEY,
            ForeachNextExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Set up loop state
        state_data = await state.get_state_data()
        state_data[LOOP_STATE_KEY] = {
            "loop_id": {
                "items": ["a", "b", "c"],
                "index": 0,
                "length": 3,
            }
        }
        await state.set_state_data(state_data)

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=Local.data",
            "iteratorVariable": "Local.item",
        }
        executor = ForeachNextExecutor(action_def, init_executor_id="loop_id")

        await executor.handle_loop_control(LoopControl(action="break"), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopIterationResult)
        assert msg.has_next is False

    async def test_foreach_next_handle_continue_control(self, mock_context, mock_shared_state):
        """Test ForeachNextExecutor handles continue LoopControl."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            LOOP_STATE_KEY,
            ForeachNextExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Set up loop state
        state_data = await state.get_state_data()
        state_data[LOOP_STATE_KEY] = {
            "loop_id": {
                "items": ["a", "b", "c"],
                "index": 0,
                "length": 3,
            }
        }
        await state.set_state_data(state_data)

        action_def = {
            "kind": "Foreach",
            "itemsSource": "=Local.data",
            "iteratorVariable": "Local.item",
        }
        executor = ForeachNextExecutor(action_def, init_executor_id="loop_id")

        await executor.handle_loop_control(LoopControl(action="continue"), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, LoopIterationResult)
        assert msg.has_next is True
        assert msg.current_index == 1

    async def test_end_workflow_executor(self, mock_context, mock_shared_state):
        """Test EndWorkflowExecutor does not send continuation."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            EndWorkflowExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "EndWorkflow"}
        executor = EndWorkflowExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should NOT send any message
        mock_context.send_message.assert_not_called()

    async def test_end_conversation_executor(self, mock_context, mock_shared_state):
        """Test EndConversationExecutor does not send continuation."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            EndConversationExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "EndConversation"}
        executor = EndConversationExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should NOT send any message
        mock_context.send_message.assert_not_called()

    async def test_condition_group_evaluator_first_match(self, mock_context, mock_shared_state):
        """Test ConditionGroupEvaluatorExecutor returns first match."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            ConditionGroupEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 10)

        action_def = {"kind": "ConditionGroup"}
        conditions = [
            {"condition": "=Local.x > 20"},
            {"condition": "=Local.x > 5"},
            {"condition": "=Local.x > 0"},
        ]
        executor = ConditionGroupEvaluatorExecutor(action_def, conditions=conditions)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is True
        assert msg.branch_index == 1  # Second condition (x > 5) is first match

    async def test_condition_group_evaluator_no_match(self, mock_context, mock_shared_state):
        """Test ConditionGroupEvaluatorExecutor with no matches."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            ConditionGroupEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 0)

        action_def = {"kind": "ConditionGroup"}
        conditions = [
            {"condition": "=Local.x > 10"},
            {"condition": "=Local.x > 5"},
        ]
        executor = ConditionGroupEvaluatorExecutor(action_def, conditions=conditions)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is False
        assert msg.branch_index == -1

    async def test_condition_group_evaluator_boolean_true_condition(self, mock_context, mock_shared_state):
        """Test ConditionGroupEvaluatorExecutor with boolean True condition."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            ConditionGroupEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {"kind": "ConditionGroup"}
        conditions = [
            {"condition": False},  # Should skip
            {"condition": True},  # Should match
        ]
        executor = ConditionGroupEvaluatorExecutor(action_def, conditions=conditions)

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is True
        assert msg.branch_index == 1

    async def test_if_condition_evaluator_true(self, mock_context, mock_shared_state):
        """Test IfConditionEvaluatorExecutor with true condition."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            IfConditionEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.flag", True)

        action_def = {"kind": "If"}
        executor = IfConditionEvaluatorExecutor(action_def, condition_expr="=Local.flag")

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is True
        assert msg.branch_index == 0  # Then branch

    async def test_if_condition_evaluator_false(self, mock_context, mock_shared_state):
        """Test IfConditionEvaluatorExecutor with false condition."""
        from agent_framework_declarative._workflows._executors_control_flow import (
            IfConditionEvaluatorExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.flag", False)

        action_def = {"kind": "If"}
        executor = IfConditionEvaluatorExecutor(action_def, condition_expr="=Local.flag")

        await executor.handle_action(ActionTrigger(), mock_context)

        msg = mock_context.send_message.call_args[0][0]
        assert isinstance(msg, ConditionResult)
        assert msg.matched is False
        assert msg.branch_index == -1  # Else branch


# ---------------------------------------------------------------------------
# Declarative Action Executor Base Tests
# ---------------------------------------------------------------------------


class TestDeclarativeActionExecutorBase:
    """Tests for DeclarativeActionExecutor base class."""

    async def test_ensure_state_initialized_with_dict_input(self, mock_context, mock_shared_state):
        """Test _ensure_state_initialized with dict input."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetValueExecutor,
        )

        action_def = {"kind": "SetValue", "path": "Local.x", "value": 1}
        executor = SetValueExecutor(action_def)

        # Trigger with dict - should initialize state with it
        await executor.handle_action({"custom": "input"}, mock_context)

        # State should have been initialized with the dict
        state = DeclarativeWorkflowState(mock_shared_state)
        inputs = await state.get("Workflow.Inputs")
        assert inputs == {"custom": "input"}

    async def test_ensure_state_initialized_with_string_input(self, mock_context, mock_shared_state):
        """Test _ensure_state_initialized with string input."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetValueExecutor,
        )

        action_def = {"kind": "SetValue", "path": "Local.x", "value": 1}
        executor = SetValueExecutor(action_def)

        # Trigger with string - should wrap in {"input": ...}
        await executor.handle_action("string trigger", mock_context)

        state = DeclarativeWorkflowState(mock_shared_state)
        inputs = await state.get("Workflow.Inputs")
        assert inputs == {"input": "string trigger"}

    async def test_ensure_state_initialized_with_custom_object(self, mock_context, mock_shared_state):
        """Test _ensure_state_initialized with custom object converts to string."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetValueExecutor,
        )

        class CustomObj:
            def __str__(self):
                return "custom string"

        action_def = {"kind": "SetValue", "path": "Local.x", "value": 1}
        executor = SetValueExecutor(action_def)

        await executor.handle_action(CustomObj(), mock_context)

        state = DeclarativeWorkflowState(mock_shared_state)
        inputs = await state.get("Workflow.Inputs")
        assert inputs == {"input": "custom string"}

    async def test_executor_display_name_property(self, mock_context, mock_shared_state):
        """Test executor display_name property."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetValueExecutor,
        )

        action_def = {
            "kind": "SetValue",
            "displayName": "My Custom Action",
            "path": "Local.x",
            "value": 1,
        }
        executor = SetValueExecutor(action_def)

        assert executor.display_name == "My Custom Action"

    async def test_executor_action_def_property(self, mock_context, mock_shared_state):
        """Test executor action_def property."""
        from agent_framework_declarative._workflows._executors_basic import (
            SetValueExecutor,
        )

        action_def = {"kind": "SetValue", "path": "Local.x", "value": 1}
        executor = SetValueExecutor(action_def)

        assert executor.action_def == action_def


# ---------------------------------------------------------------------------
# Human Input Executors Tests - Covering _executors_external_input.py gaps
# ---------------------------------------------------------------------------


class TestHumanInputExecutorsCoverage:
    """Tests for human input executors covering uncovered code paths."""

    async def test_wait_for_input_executor_with_prompt(self, mock_context, mock_shared_state):
        """Test WaitForInputExecutor with prompt."""
        from agent_framework_declarative._workflows._executors_external_input import (
            ExternalInputRequest,
            WaitForInputExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "WaitForInput",
            "prompt": "Please enter your name:",
            "property": "Local.userName",
            "timeout": 30,
        }
        executor = WaitForInputExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should yield prompt first, then call request_info
        assert mock_context.yield_output.call_count == 1
        assert mock_context.yield_output.call_args_list[0][0][0] == "Please enter your name:"
        # request_info call for ExternalInputRequest
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ExternalInputRequest)
        assert request.request_type == "user_input"

    async def test_wait_for_input_executor_no_prompt(self, mock_context, mock_shared_state):
        """Test WaitForInputExecutor without prompt."""
        from agent_framework_declarative._workflows._executors_external_input import (
            ExternalInputRequest,
            WaitForInputExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "WaitForInput",
            "property": "Local.input",
        }
        executor = WaitForInputExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should not yield output (no prompt), just call request_info
        assert mock_context.yield_output.call_count == 0
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ExternalInputRequest)
        assert request.request_type == "user_input"

    async def test_request_external_input_executor(self, mock_context, mock_shared_state):
        """Test RequestExternalInputExecutor."""
        from agent_framework_declarative._workflows._executors_external_input import (
            ExternalInputRequest,
            RequestExternalInputExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "RequestExternalInput",
            "requestType": "approval",
            "message": "Please approve this request",
            "property": "Local.approvalResult",
            "timeout": 3600,
            "requiredFields": ["approver", "notes"],
            "metadata": {"priority": "high"},
        }
        executor = RequestExternalInputExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ExternalInputRequest)
        assert request.request_type == "approval"
        assert request.message == "Please approve this request"
        assert request.metadata["priority"] == "high"
        assert request.metadata["required_fields"] == ["approver", "notes"]
        assert request.metadata["timeout_seconds"] == 3600

    async def test_question_executor_with_choices(self, mock_context, mock_shared_state):
        """Test QuestionExecutor with choices as dicts and strings."""
        from agent_framework_declarative._workflows._executors_external_input import (
            ExternalInputRequest,
            QuestionExecutor,
        )

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "Question",
            "question": "Select an option:",
            "property": "Local.selection",
            "choices": [
                {"value": "a", "label": "Option A"},
                {"value": "b"},  # No label, should use value
                "c",  # String choice
            ],
            "allowFreeText": False,
        }
        executor = QuestionExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ExternalInputRequest)
        assert request.request_type == "question"
        choices = request.metadata["choices"]
        assert len(choices) == 3
        assert choices[0] == {"value": "a", "label": "Option A"}
        assert choices[1] == {"value": "b", "label": "b"}
        assert choices[2] == {"value": "c", "label": "c"}
        assert request.metadata["allow_free_text"] is False


# ---------------------------------------------------------------------------
# Additional Agent Executor Tests - External Loop Coverage
# ---------------------------------------------------------------------------


class TestAgentExternalLoopCoverage:
    """Tests for agent executor external loop handling."""

    async def test_agent_executor_with_external_loop(self, mock_context, mock_shared_state):
        """Test agent executor with external loop that triggers."""
        from unittest.mock import patch

        from agent_framework_declarative._workflows._executors_agents import (
            AgentExternalInputRequest,
            InvokeAzureAgentExecutor,
        )

        mock_agent = MagicMock()

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.input", "User query")
        await state.set("Local.needsMore", True)  # Loop condition will be true

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "input": {
                "externalLoop": {"when": "=Local.needsMore"},
            },
        }
        executor = InvokeAzureAgentExecutor(action_def, agents={"TestAgent": mock_agent})

        # Mock the internal method to avoid storing ChatMessage objects in state
        # (PowerFx cannot serialize ChatMessage)
        with patch.object(
            executor,
            "_invoke_agent_and_store_results",
            new=AsyncMock(return_value=("Need more info", [], [])),
        ):
            await executor.handle_action(ActionTrigger(), mock_context)

        # Should request external input via request_info
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, AgentExternalInputRequest)
        assert request.agent_name == "TestAgent"

    async def test_agent_executor_agent_error_handling(self, mock_context, mock_shared_state):
        """Test agent executor raises AgentInvocationError on failure."""
        from agent_framework_declarative._workflows._executors_agents import (
            AgentInvocationError,
            InvokeAzureAgentExecutor,
        )

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("Agent failed"))

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.input", "Query")

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "resultProperty": "Local.result",
        }
        executor = InvokeAzureAgentExecutor(action_def, agents={"TestAgent": mock_agent})

        with pytest.raises(AgentInvocationError) as exc_info:
            await executor.handle_action(ActionTrigger(), mock_context)

        assert "TestAgent" in str(exc_info.value)
        assert "Agent failed" in str(exc_info.value)

        # Should still store error in state before raising
        error = await state.get("Agent.error")
        assert "Agent failed" in error
        result = await state.get("Local.result")
        assert result == {"error": "Agent failed"}

    async def test_agent_executor_string_result(self, mock_context, mock_shared_state):
        """Test agent executor with agent that returns string directly."""
        from agent_framework_declarative._workflows._executors_agents import (
            InvokeAzureAgentExecutor,
        )

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="Direct string response")

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.input", "Query")

        action_def = {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "resultProperty": "Local.result",
            "output": {"autoSend": True},
        }
        executor = InvokeAzureAgentExecutor(action_def, agents={"TestAgent": mock_agent})

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should auto-send output
        mock_context.yield_output.assert_called_with("Direct string response")
        result = await state.get("Local.result")
        assert result == "Direct string response"

    async def test_invoke_tool_with_error(self, mock_context, mock_shared_state):
        """Test InvokeToolExecutor handles tool errors."""
        from agent_framework_declarative._workflows._executors_agents import (
            TOOL_REGISTRY_KEY,
            InvokeToolExecutor,
        )

        def failing_tool(**kwargs):
            raise ValueError("Tool error")

        mock_shared_state._data[TOOL_REGISTRY_KEY] = {"bad_tool": failing_tool}

        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        action_def = {
            "kind": "InvokeTool",
            "tool": "bad_tool",
            "resultProperty": "Local.result",
        }
        executor = InvokeToolExecutor(action_def)

        await executor.handle_action(ActionTrigger(), mock_context)

        result = await state.get("Local.result")
        assert result == {"error": "Tool error"}


# ---------------------------------------------------------------------------
# PowerFx Functions Coverage
# ---------------------------------------------------------------------------


class TestPowerFxFunctionsCoverage:
    """Tests for PowerFx function evaluation coverage."""

    async def test_eval_lower_upper_functions(self, mock_shared_state):
        """Test Lower and Upper functions."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.text", "Hello World")

        result = await state.eval("=Lower(Local.text)")
        assert result == "hello world"

        result = await state.eval("=Upper(Local.text)")
        assert result == "HELLO WORLD"

    async def test_eval_if_function(self, mock_shared_state):
        """Test If function."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.flag", True)

        result = await state.eval('=If(Local.flag, "yes", "no")')
        assert result == "yes"

        await state.set("Local.flag", False)
        result = await state.eval('=If(Local.flag, "yes", "no")')
        assert result == "no"

    async def test_eval_not_function(self, mock_shared_state):
        """Test Not function."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.flag", True)

        result = await state.eval("=Not(Local.flag)")
        assert result is False

    async def test_eval_and_or_functions(self, mock_shared_state):
        """Test And and Or functions."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.a", True)
        await state.set("Local.b", False)

        result = await state.eval("=And(Local.a, Local.b)")
        assert result is False

        result = await state.eval("=Or(Local.a, Local.b)")
        assert result is True


# ---------------------------------------------------------------------------
# Builder control flow tests - Covering Goto/Break/Continue creation
# ---------------------------------------------------------------------------


class TestBuilderControlFlowCreation:
    """Tests for Goto, Break, Continue executor creation in builder."""

    def test_create_goto_reference(self):
        """Test creating a goto reference executor."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        # Create builder with minimal yaml definition
        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        action_def = {
            "kind": "GotoAction",
            "target": "some_target_action",
            "id": "goto_test",
        }

        executor = graph_builder._create_goto_reference(action_def, wb, None)

        assert executor is not None
        assert executor.id == "goto_test"
        # Verify pending goto was recorded
        assert len(graph_builder._pending_gotos) == 1
        assert graph_builder._pending_gotos[0][1] == "some_target_action"

    def test_create_goto_reference_auto_id(self):
        """Test creating a goto with auto-generated ID."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        action_def = {
            "kind": "GotoAction",
            "target": "target_action",
        }

        executor = graph_builder._create_goto_reference(action_def, wb, None)

        assert executor is not None
        assert "goto_target_action" in executor.id

    def test_create_goto_reference_no_target(self):
        """Test creating a goto with no target returns None."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        action_def = {
            "kind": "GotoAction",
            # No target specified
        }

        executor = graph_builder._create_goto_reference(action_def, wb, None)
        assert executor is None

    def test_goto_invalid_target_raises_error(self):
        """Test that goto to non-existent target raises ValueError."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [
                {"kind": "SendActivity", "id": "action1", "activity": {"text": "Hello"}},
                {"kind": "GotoAction", "target": "non_existent_action"},
            ],
        }
        builder = DeclarativeWorkflowBuilder(yaml_def)

        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "non_existent_action" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_create_break_executor(self):
        """Test creating a break executor within a loop context."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_control_flow import ForeachNextExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        # Create a mock loop_next executor
        loop_next = ForeachNextExecutor(
            {"kind": "Foreach", "itemsProperty": "items"},
            init_executor_id="foreach_init",
            id="foreach_next",
        )
        wb._add_executor(loop_next)

        parent_context = {"loop_next_executor": loop_next}

        action_def = {
            "kind": "BreakLoop",
            "id": "break_test",
        }

        executor = graph_builder._create_break_executor(action_def, wb, parent_context)

        assert executor is not None
        assert executor.id == "break_test"

    def test_create_break_executor_no_loop_context(self):
        """Test creating a break executor without loop context raises ValueError."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        action_def = {
            "kind": "BreakLoop",
        }

        # No parent_context should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            graph_builder._create_break_executor(action_def, wb, None)
        assert "BreakLoop action can only be used inside a Foreach loop" in str(exc_info.value)

        # Empty context should also raise ValueError
        with pytest.raises(ValueError) as exc_info:
            graph_builder._create_break_executor(action_def, wb, {})
        assert "BreakLoop action can only be used inside a Foreach loop" in str(exc_info.value)

    def test_create_continue_executor(self):
        """Test creating a continue executor within a loop context."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_control_flow import ForeachNextExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        # Create a mock loop_next executor
        loop_next = ForeachNextExecutor(
            {"kind": "Foreach", "itemsProperty": "items"},
            init_executor_id="foreach_init",
            id="foreach_next",
        )
        wb._add_executor(loop_next)

        parent_context = {"loop_next_executor": loop_next}

        action_def = {
            "kind": "ContinueLoop",
            "id": "continue_test",
        }

        executor = graph_builder._create_continue_executor(action_def, wb, parent_context)

        assert executor is not None
        assert executor.id == "continue_test"

    def test_create_continue_executor_no_loop_context(self):
        """Test creating a continue executor without loop context raises ValueError."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        action_def = {
            "kind": "ContinueLoop",
        }

        # No parent_context should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            graph_builder._create_continue_executor(action_def, wb, None)
        assert "ContinueLoop action can only be used inside a Foreach loop" in str(exc_info.value)


class TestBuilderEdgeWiring:
    """Tests for builder edge wiring methods."""

    def test_wire_to_target_with_if_structure(self):
        """Test wiring to an If structure routes to evaluator."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_basic import SendActivityExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        # Create a mock source executor
        source = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "test"}}, id="source")
        wb._add_executor(source)

        # Create a mock If structure with evaluator
        class MockIfStructure:
            _is_if_structure = True

            def __init__(self):
                self.evaluator = SendActivityExecutor(
                    {"kind": "SendActivity", "activity": {"text": "evaluator"}}, id="evaluator"
                )

        target = MockIfStructure()
        wb._add_executor(target.evaluator)

        # Wire should add edge to evaluator
        graph_builder._wire_to_target(wb, source, target)

        # Verify edge was added (would need to inspect workflow internals)
        # For now, just verify no exception was raised

    def test_wire_to_target_normal_executor(self):
        """Test wiring to a normal executor adds direct edge."""
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_basic import SendActivityExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)
        wb = WorkflowBuilder()

        source = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "source"}}, id="source")
        target = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "target"}}, id="target")

        wb._add_executor(source)
        wb._add_executor(target)

        graph_builder._wire_to_target(wb, source, target)
        # Verify edge creation (no exception = success)

    def test_collect_all_exits_for_nested_structure(self):
        """Test collecting all exits from nested structures."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_basic import SendActivityExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)

        # Create mock nested structure
        exit1 = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "exit1"}}, id="exit1")
        exit2 = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "exit2"}}, id="exit2")

        class InnerStructure:
            def __init__(self):
                self.branch_exits = [exit1, exit2]

        class OuterStructure:
            def __init__(self):
                self.branch_exits = [InnerStructure()]

        outer = OuterStructure()
        exits = graph_builder._collect_all_exits(outer)

        assert len(exits) == 2
        assert exit1 in exits
        assert exit2 in exits

    def test_collect_all_exits_for_simple_executor(self):
        """Test collecting exits from a simple executor."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_basic import SendActivityExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)

        executor = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "test"}}, id="test")

        exits = graph_builder._collect_all_exits(executor)

        assert len(exits) == 1
        assert executor in exits

    def test_get_branch_exit_with_chain(self):
        """Test getting branch exit from a chain of executors."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder
        from agent_framework_declarative._workflows._executors_basic import SendActivityExecutor

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)

        exec1 = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "1"}}, id="e1")
        exec2 = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "2"}}, id="e2")
        exec3 = SendActivityExecutor({"kind": "SendActivity", "activity": {"text": "3"}}, id="e3")

        # Simulate a chain by dynamically setting attribute
        exec1._chain_executors = [exec1, exec2, exec3]  # type: ignore[attr-defined]

        exit_exec = graph_builder._get_branch_exit(exec1)

        assert exit_exec == exec3

    def test_get_branch_exit_none(self):
        """Test getting branch exit from None."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {"name": "test_workflow", "actions": []}
        graph_builder = DeclarativeWorkflowBuilder(yaml_def)

        exit_exec = graph_builder._get_branch_exit(None)
        assert exit_exec is None


# ---------------------------------------------------------------------------
# Agent executor external loop response handler tests
# ---------------------------------------------------------------------------


class TestAgentExecutorExternalLoop:
    """Tests for InvokeAzureAgentExecutor external loop response handling."""

    async def test_handle_external_input_response_no_state(self, mock_context, mock_shared_state):
        """Test handling external input response when loop state not found."""
        from agent_framework_declarative._workflows._executors_agents import (
            AgentExternalInputRequest,
            AgentExternalInputResponse,
            InvokeAzureAgentExecutor,
        )

        executor = InvokeAzureAgentExecutor({"kind": "InvokeAzureAgent", "agent": "TestAgent"})

        # No external loop state in shared_state
        original_request = AgentExternalInputRequest(
            request_id="req-1",
            agent_name="TestAgent",
            agent_response="Hello",
            iteration=1,
        )
        response = AgentExternalInputResponse(user_input="hi there")

        await executor.handle_external_input_response(original_request, response, mock_context)

        # Should send ActionComplete due to missing state
        mock_context.send_message.assert_called()
        call_args = mock_context.send_message.call_args[0][0]
        from agent_framework_declarative._workflows import ActionComplete

        assert isinstance(call_args, ActionComplete)

    async def test_handle_external_input_response_agent_not_found(self, mock_context, mock_shared_state):
        """Test handling external input raises error when agent not found during resumption."""
        from agent_framework_declarative._workflows._executors_agents import (
            EXTERNAL_LOOP_STATE_KEY,
            AgentExternalInputRequest,
            AgentExternalInputResponse,
            AgentInvocationError,
            ExternalLoopState,
            InvokeAzureAgentExecutor,
        )

        # Set up loop state with always true condition (literal)
        loop_state = ExternalLoopState(
            agent_name="NonExistentAgent",
            iteration=1,
            external_loop_when="true",  # Literal true
            messages_var=None,
            response_obj_var=None,
            result_property=None,
            auto_send=True,
            messages_path="Conversation.messages",
        )
        mock_shared_state._data[EXTERNAL_LOOP_STATE_KEY] = loop_state

        # Initialize declarative state with simple value
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        executor = InvokeAzureAgentExecutor({"kind": "InvokeAzureAgent", "agent": "NonExistentAgent"})

        original_request = AgentExternalInputRequest(
            request_id="req-1",
            agent_name="NonExistentAgent",
            agent_response="Hello",
            iteration=1,
        )
        response = AgentExternalInputResponse(user_input="continue")

        with pytest.raises(AgentInvocationError) as exc_info:
            await executor.handle_external_input_response(original_request, response, mock_context)

        assert "NonExistentAgent" in str(exc_info.value)
        assert "not found during loop resumption" in str(exc_info.value)


class TestBuilderValidation:
    """Tests for builder validation features (P1 fixes)."""

    def test_duplicate_explicit_action_id_raises_error(self):
        """Test that duplicate explicit action IDs are detected."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [
                {"id": "my_action", "kind": "SendActivity", "activity": {"text": "First"}},
                {"id": "my_action", "kind": "SendActivity", "activity": {"text": "Second"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "Duplicate action ID 'my_action'" in str(exc_info.value)

    def test_duplicate_id_in_nested_actions(self):
        """Test duplicate ID detection in nested If/Switch branches."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [
                {
                    "kind": "If",
                    "condition": "=true",
                    "then": [{"id": "shared_id", "kind": "SendActivity", "activity": {"text": "Then"}}],
                    "else": [{"id": "shared_id", "kind": "SendActivity", "activity": {"text": "Else"}}],
                }
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "Duplicate action ID 'shared_id'" in str(exc_info.value)

    def test_missing_required_field_sendactivity(self):
        """Test that missing required fields are detected."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [{"kind": "SendActivity"}],  # Missing 'activity' field
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "SendActivity" in str(exc_info.value)
        assert "missing required field" in str(exc_info.value)
        assert "activity" in str(exc_info.value)

    def test_missing_required_field_setvalue(self):
        """Test SetValue without path raises error."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [{"kind": "SetValue", "value": "test"}],  # Missing 'path' field
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "SetValue" in str(exc_info.value)
        assert "path" in str(exc_info.value)

    def test_setvalue_accepts_alternate_variable_field(self):
        """Test SetValue accepts 'variable' as alternate to 'path'."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [{"kind": "SetValue", "variable": {"path": "Local.x"}, "value": "test"}],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        # Should not raise - 'variable' is accepted as alternate
        workflow = builder.build()
        assert workflow is not None

    def test_missing_required_field_foreach(self):
        """Test Foreach without items raises error."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [{"kind": "Foreach", "actions": [{"kind": "SendActivity", "activity": {"text": "Hi"}}]}],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "Foreach" in str(exc_info.value)
        assert "items" in str(exc_info.value)

    def test_self_referencing_goto_raises_error(self):
        """Test that a goto referencing itself is detected."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [{"id": "loop", "kind": "Goto", "target": "loop"}],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "loop" in str(exc_info.value)
        assert "self-referencing" in str(exc_info.value)

    def test_validation_can_be_disabled(self):
        """Test that validation can be disabled for early schema/duplicate checks.

        Note: Even with validation disabled, the underlying WorkflowBuilder may
        still catch duplicates during graph construction. This flag disables
        our upfront validation pass but not runtime checks.
        """
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        # Test with missing required field - validation disabled should skip our check
        yaml_def = {
            "name": "test_workflow",
            "actions": [{"kind": "SendActivity"}],  # Missing 'activity' - normally caught by validation
        }

        # With validation disabled, our upfront check is skipped
        builder = DeclarativeWorkflowBuilder(yaml_def, validate=False)
        # The workflow may still fail for other reasons, but our validation pass is skipped
        # In this case, it should succeed because SendActivityExecutor handles missing fields gracefully
        workflow = builder.build()
        assert workflow is not None

    def test_validation_in_switch_branches(self):
        """Test validation catches issues in Switch branches."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [
                {
                    "kind": "Switch",
                    "value": "=Local.choice",
                    "cases": [
                        {
                            "match": "a",
                            "actions": [{"id": "dup", "kind": "SendActivity", "activity": {"text": "A"}}],
                        },
                        {
                            "match": "b",
                            "actions": [{"id": "dup", "kind": "SendActivity", "activity": {"text": "B"}}],
                        },
                    ],
                }
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "Duplicate action ID 'dup'" in str(exc_info.value)

    def test_validation_in_foreach_body(self):
        """Test validation catches issues in Foreach body."""
        from agent_framework_declarative._workflows._declarative_builder import DeclarativeWorkflowBuilder

        yaml_def = {
            "name": "test_workflow",
            "actions": [
                {
                    "kind": "Foreach",
                    "items": "=Local.items",
                    "actions": [{"kind": "SendActivity"}],  # Missing 'activity'
                }
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        with pytest.raises(ValueError) as exc_info:
            builder.build()

        assert "SendActivity" in str(exc_info.value)
        assert "activity" in str(exc_info.value)


class TestExpressionEdgeCases:
    """Tests for expression evaluation edge cases."""

    async def test_division_with_valid_values(self, mock_shared_state):
        """Test normal division works correctly."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 10)
        await state.set("Local.y", 4)

        result = await state.eval("=Local.x / Local.y")
        assert result == 2.5

    async def test_multiplication_normal(self, mock_shared_state):
        """Test normal multiplication."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()
        await state.set("Local.x", 6)
        await state.set("Local.y", 7)

        result = await state.eval("=Local.x * Local.y")
        assert result == 42


class TestLongMessageTextHandling:
    """Tests for handling long MessageText results that exceed PowerFx limits."""

    async def test_short_message_text_embedded_inline(self, mock_shared_state):
        """Test that short MessageText results are embedded inline."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Store a short message
        short_text = "Hello world"
        await state.set("Local.Messages", [{"text": short_text, "contents": [{"type": "text", "text": short_text}]}])

        # Evaluate a formula with MessageText - should embed inline
        result = await state.eval("=Upper(MessageText(Local.Messages))")
        assert result == "HELLO WORLD"

        # No temp variable should be created for short strings
        temp_var = await state.get("Local._TempMessageText0")
        assert temp_var is None

    async def test_long_message_text_stored_in_temp_variable(self, mock_shared_state):
        """Test that long MessageText results are stored in temp variables."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Create a message longer than 500 characters
        long_text = "A" * 600  # 600 characters exceeds the 500 char threshold
        await state.set("Local.Messages", [{"text": long_text, "contents": [{"type": "text", "text": long_text}]}])

        # Evaluate a formula with MessageText
        result = await state.eval("=Upper(MessageText(Local.Messages))")
        assert result == "A" * 600  # Upper on 'A' is still 'A'

        # A temp variable should have been created
        temp_var = await state.get("Local._TempMessageText0")
        assert temp_var == long_text

    async def test_find_with_long_message_text(self, mock_shared_state):
        """Test Find function works with long MessageText stored in temp variable."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Create a long message with a keyword to find
        long_text = "X" * 550 + "CONGRATULATIONS" + "Y" * 50
        await state.set("Local.Messages", [{"text": long_text, "contents": [{"type": "text", "text": long_text}]}])

        # Test the pattern used in student_teacher workflow
        result = await state.eval('=!IsBlank(Find("CONGRATULATIONS", Upper(MessageText(Local.Messages))))')
        assert result is True

    async def test_find_without_keyword_in_long_text(self, mock_shared_state):
        """Test Find returns blank when keyword not found in long text."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Long text without the keyword
        long_text = "X" * 600
        await state.set("Local.Messages", [{"text": long_text, "contents": [{"type": "text", "text": long_text}]}])

        result = await state.eval('=!IsBlank(Find("CONGRATULATIONS", Upper(MessageText(Local.Messages))))')
        assert result is False
