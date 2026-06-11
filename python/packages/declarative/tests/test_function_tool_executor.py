# Copyright (c) Microsoft. All rights reserved.

"""Tests for InvokeFunctionTool executor.

These tests verify:
- Basic function invocation (sync and async)
- Expression evaluation for functionName and arguments
- Output formatting (messages and result)
- Error handling (function not found, execution errors)
- WorkflowFactory registration
- Approval flow (requireApproval=true with yield/resume)
- Variable path normalization
- Non-callable tool error handling
- JSON serialization fallbacks
"""

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

pytestmark = pytest.mark.skipif(
    not _powerfx_available or sys.version_info >= (3, 14),
    reason="PowerFx engine not available (requires dotnet runtime)",
)

from agent_framework_declarative._workflows import (  # noqa: E402
    DECLARATIVE_STATE_KEY,
    FUNCTION_TOOL_REGISTRY_KEY,
    TOOL_APPROVAL_STATE_KEY,
    ActionComplete,
    ActionTrigger,
    DeclarativeWorkflowBuilder,
    InvokeFunctionToolExecutor,
    ToolApprovalRequest,
    ToolApprovalResponse,
    ToolApprovalState,
    ToolInvocationResult,
    WorkflowFactory,
)
from agent_framework_declarative._workflows._executors_tools import (  # noqa: E402
    _normalize_variable_path,
)


class TestInvokeFunctionToolExecutor:
    """Tests for InvokeFunctionToolExecutor."""

    @pytest.mark.asyncio
    async def test_basic_sync_function_invocation(self):
        """Test invoking a simple synchronous function."""

        def get_weather(location: str, unit: str = "F") -> dict:
            return {"temp": 72, "unit": unit, "location": location}

        yaml_def = {
            "name": "function_tool_test",
            "actions": [
                {"kind": "SetValue", "id": "set_location", "path": "Local.city", "value": "Seattle"},
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_weather",
                    "functionName": "get_weather",
                    "arguments": {"location": "=Local.city", "unit": "C"},
                    "output": {"result": "Local.weatherData"},
                },
                # Use SendActivity to output the result so we can check it
                {"kind": "SendActivity", "id": "output_location", "activity": {"text": "=Local.weatherData.location"}},
                {"kind": "SendActivity", "id": "output_unit", "activity": {"text": "=Local.weatherData.unit"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"get_weather": get_weather})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Verify the function was called with correct arguments
        assert "Seattle" in outputs  # location
        assert "C" in outputs  # unit

    @pytest.mark.asyncio
    async def test_async_function_invocation(self):
        """Test invoking an async function."""

        async def fetch_data(url: str) -> dict:
            return {"url": url, "status": "success"}

        yaml_def = {
            "name": "async_function_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "fetch",
                    "functionName": "fetch_data",
                    "arguments": {"url": "https://example.com/api"},
                    "output": {"result": "Local.response"},
                },
                {"kind": "SendActivity", "id": "output_url", "activity": {"text": "=Local.response.url"}},
                {"kind": "SendActivity", "id": "output_status", "activity": {"text": "=Local.response.status"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"fetch_data": fetch_data})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "https://example.com/api" in outputs
        assert "success" in outputs

    @pytest.mark.asyncio
    async def test_expression_function_name(self):
        """Test dynamic function name via expression."""

        def tool_a() -> str:
            return "result_a"

        def tool_b() -> str:
            return "result_b"

        yaml_def = {
            "name": "dynamic_function_name_test",
            "actions": [
                {"kind": "SetValue", "id": "set_tool", "path": "Local.toolName", "value": "tool_b"},
                {
                    "kind": "InvokeFunctionTool",
                    "id": "dynamic_call",
                    "functionName": "=Local.toolName",
                    "arguments": {},
                    "output": {"result": "Local.result"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.result"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"tool_a": tool_a, "tool_b": tool_b})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "result_b" in outputs

    @pytest.mark.asyncio
    async def test_function_not_found(self):
        """Test error handling when function is not in registry."""
        yaml_def = {
            "name": "function_not_found_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_missing",
                    "functionName": "nonexistent_function",
                    "arguments": {},
                    "output": {"result": "Local.result"},
                },
                # Check if error is stored
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.result.error"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={})  # Empty registry
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Result should contain error info
        assert "not found" in outputs[0].lower()

    @pytest.mark.asyncio
    async def test_function_execution_error(self):
        """Test error handling when function raises exception."""

        def failing_function() -> str:
            raise ValueError("Intentional test error")

        yaml_def = {
            "name": "function_error_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_failing",
                    "functionName": "failing_function",
                    "arguments": {},
                    "output": {"result": "Local.result"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.result.error"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"failing_function": failing_function})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Result should contain error info
        assert "Intentional test error" in outputs[0]

    @pytest.mark.asyncio
    async def test_function_with_no_output_config(self):
        """Test that function works even without output configuration."""

        counter = {"value": 0}

        def increment() -> int:
            counter["value"] += 1
            return counter["value"]

        yaml_def = {
            "name": "no_output_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "increment_call",
                    "functionName": "increment",
                    "arguments": {},
                    # No output configuration
                },
                {"kind": "SendActivity", "id": "done", "activity": {"text": "Done"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"increment": increment})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Workflow should complete
        assert "Done" in outputs
        # Function should have been called
        assert counter["value"] == 1


class TestInvokeFunctionToolWithWorkflowFactory:
    """Tests for InvokeFunctionTool with WorkflowFactory registration."""

    @pytest.mark.asyncio
    async def test_register_tool_method(self):
        """Test registering tools via WorkflowFactory.register_tool()."""

        def multiply(a: int, b: int) -> int:
            return a * b

        yaml_content = """
name: factory_tool_test
actions:
  - kind: InvokeFunctionTool
    id: multiply_call
    functionName: multiply
    arguments:
      a: 6
      b: 7
    output:
      result: Local.product
  - kind: SendActivity
    id: output
    activity:
      text: =Local.product
"""
        factory = WorkflowFactory().register_tool("multiply", multiply)
        workflow = factory.create_workflow_from_yaml(yaml_content)

        events = await workflow.run({})
        outputs = events.get_outputs()

        # PowerFx outputs integers as floats, so we check for 42 or 42.0
        assert any("42" in out for out in outputs)

    @pytest.mark.asyncio
    async def test_fluent_registration(self):
        """Test fluent chaining for tool registration."""

        def add(a: int, b: int) -> int:
            return a + b

        def subtract(a: int, b: int) -> int:
            return a - b

        yaml_content = """
name: fluent_test
actions:
  - kind: InvokeFunctionTool
    id: add_call
    functionName: add
    arguments:
      a: 10
      b: 5
    output:
      result: Local.sum
  - kind: InvokeFunctionTool
    id: subtract_call
    functionName: subtract
    arguments:
      a: 10
      b: 5
    output:
      result: Local.diff
  - kind: SendActivity
    id: output_sum
    activity:
      text: =Local.sum
  - kind: SendActivity
    id: output_diff
    activity:
      text: =Local.diff
"""
        factory = WorkflowFactory().register_tool("add", add).register_tool("subtract", subtract)

        workflow = factory.create_workflow_from_yaml(yaml_content)

        events = await workflow.run({})
        outputs = events.get_outputs()

        # PowerFx outputs integers as floats, so we check for 15 or 15.0
        assert any("15" in out for out in outputs)  # sum
        assert any("5" in out for out in outputs)  # diff


class TestToolInvocationResult:
    """Tests for ToolInvocationResult dataclass."""

    def test_success_result(self):
        """Test creating a successful result."""
        result = ToolInvocationResult(
            success=True,
            result={"data": "value"},
            messages=[],
        )
        assert result.success is True
        assert result.result == {"data": "value"}
        assert result.rejected is False
        assert result.error is None

    def test_error_result(self):
        """Test creating an error result."""
        result = ToolInvocationResult(
            success=False,
            error="Function failed",
        )
        assert result.success is False
        assert result.error == "Function failed"
        assert result.result is None

    def test_rejected_result(self):
        """Test creating a rejected result."""
        result = ToolInvocationResult(
            success=False,
            rejected=True,
            rejection_reason="User denied approval",
        )
        assert result.success is False
        assert result.rejected is True
        assert result.rejection_reason == "User denied approval"


class TestToolApprovalTypes:
    """Tests for approval-related dataclasses."""

    def test_approval_request(self):
        """Test creating an approval request."""
        request = ToolApprovalRequest(
            request_id="test-123",
            function_name="dangerous_operation",
            arguments={"target": "production"},
        )
        assert request.request_id == "test-123"
        assert request.function_name == "dangerous_operation"
        assert request.arguments == {"target": "production"}

    def test_approval_response_approved(self):
        """Test creating an approved response."""
        response = ToolApprovalResponse(approved=True)
        assert response.approved is True
        assert response.reason is None

    def test_approval_response_rejected(self):
        """Test creating a rejected response."""
        response = ToolApprovalResponse(approved=False, reason="Not authorized")
        assert response.approved is False
        assert response.reason == "Not authorized"

    def test_approval_state(self):
        """Test creating approval state for yield/resume."""
        state = ToolApprovalState(
            function_name="delete_user",
            arguments={"user_id": "123"},
            output_messages_var="Local.messages",
            output_result_var="Local.result",
            auto_send=True,
        )
        assert state.function_name == "delete_user"
        assert state.arguments == {"user_id": "123"}
        assert state.output_messages_var == "Local.messages"
        assert state.output_result_var == "Local.result"
        assert state.auto_send is True


class TestInvokeFunctionToolEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_function_name_field_raises_validation_error(self):
        """Test that missing functionName raises validation error at build time."""
        yaml_def = {
            "name": "missing_function_name_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "no_name",
                    # Missing functionName field
                    "arguments": {},
                },
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={})

        # Should raise validation error
        with pytest.raises(ValueError, match="missing required field 'functionName'"):
            builder.build()

    @pytest.mark.asyncio
    async def test_empty_function_name_expression(self):
        """Test handling when functionName expression evaluates to empty."""
        yaml_def = {
            "name": "empty_function_name_test",
            "actions": [
                {"kind": "SetValue", "id": "set_empty", "path": "Local.toolName", "value": ""},
                {
                    "kind": "InvokeFunctionTool",
                    "id": "empty_name",
                    "functionName": "=Local.toolName",
                    "arguments": {},
                },
                {"kind": "SendActivity", "id": "done", "activity": {"text": "Completed"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Should complete without crashing
        assert "Completed" in outputs

    @pytest.mark.asyncio
    async def test_messages_output_configuration(self):
        """Test that messages output stores Message list."""

        def simple_func(x: int) -> int:
            return x * 2

        yaml_def = {
            "name": "messages_output_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_func",
                    "functionName": "simple_func",
                    "arguments": {"x": 5},
                    "output": {
                        "messages": "Local.toolMessages",
                        "result": "Local.result",
                    },
                },
                {"kind": "SendActivity", "id": "output_result", "activity": {"text": "=Local.result"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"simple_func": simple_func})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Result should be doubled
        assert any("10" in out for out in outputs)

    @pytest.mark.asyncio
    async def test_function_returning_none(self):
        """Test handling function that returns None."""

        def returns_none() -> None:
            pass

        yaml_def = {
            "name": "returns_none_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_none",
                    "functionName": "returns_none",
                    "arguments": {},
                    "output": {"result": "Local.result"},
                },
                {"kind": "SendActivity", "id": "done", "activity": {"text": "Completed"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"returns_none": returns_none})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "Completed" in outputs

    @pytest.mark.asyncio
    async def test_function_with_complex_return_type(self):
        """Test function returning complex nested data."""

        def complex_return() -> dict:
            return {
                "nested": {
                    "array": [1, 2, 3],
                    "string": "test",
                },
                "boolean": True,
                "number": 42.5,
            }

        yaml_def = {
            "name": "complex_return_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_complex",
                    "functionName": "complex_return",
                    "arguments": {},
                    "output": {"result": "Local.data"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.data.nested.string"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"complex_return": complex_return})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "test" in outputs

    @pytest.mark.asyncio
    async def test_function_with_list_argument(self):
        """Test passing list as argument."""

        def sum_list(numbers: list) -> int:
            return sum(numbers)

        yaml_def = {
            "name": "list_argument_test",
            "actions": [
                {"kind": "SetValue", "id": "set_list", "path": "Local.numbers", "value": [1, 2, 3, 4, 5]},
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_sum",
                    "functionName": "sum_list",
                    "arguments": {"numbers": "=Local.numbers"},
                    "output": {"result": "Local.total"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.total"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"sum_list": sum_list})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert any("15" in out for out in outputs)

    @pytest.mark.asyncio
    async def test_auto_send_disabled(self):
        """Test autoSend=false prevents automatic output yielding."""

        def echo_id(msg: str) -> str:
            return msg

        yaml_def = {
            "name": "auto_send_disabled_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_no_auto_send",
                    "functionName": "echo_id",
                    "arguments": {"msg": "hello"},
                    "output": {"result": "Local.result", "autoSend": False},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.result"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"echo_id": echo_id})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Result should still be available via explicit SendActivity
        assert "hello" in outputs

    @pytest.mark.asyncio
    async def test_function_with_only_result_output(self):
        """Test output config with only result, no messages."""

        def double(x: int) -> int:
            return x * 2

        yaml_def = {
            "name": "result_only_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_double",
                    "functionName": "double",
                    "arguments": {"x": 21},
                    "output": {"result": "Local.doubled"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.doubled"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"double": double})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert any("42" in out for out in outputs)

    @pytest.mark.asyncio
    async def test_function_with_only_messages_output(self):
        """Test output config with only messages, no result."""

        def simple() -> str:
            return "done"

        yaml_def = {
            "name": "messages_only_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_simple",
                    "functionName": "simple",
                    "arguments": {},
                    "output": {"messages": "Local.msgs"},
                },
                {"kind": "SendActivity", "id": "done", "activity": {"text": "Completed"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"simple": simple})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "Completed" in outputs

    @pytest.mark.asyncio
    async def test_function_string_return(self):
        """Test function that returns a simple string."""

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        yaml_def = {
            "name": "string_return_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_greet",
                    "functionName": "greet",
                    "arguments": {"name": "World"},
                    "output": {"result": "Local.greeting"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.greeting"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"greet": greet})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "Hello, World!" in outputs


class TestInvokeFunctionToolBuilder:
    """Tests for InvokeFunctionTool executor registration in builder."""

    def test_executor_registered_in_all_executors(self):
        """Test that InvokeFunctionTool is registered in ALL_ACTION_EXECUTORS."""
        from agent_framework_declarative._workflows import ALL_ACTION_EXECUTORS

        assert "InvokeFunctionTool" in ALL_ACTION_EXECUTORS
        assert ALL_ACTION_EXECUTORS["InvokeFunctionTool"] == InvokeFunctionToolExecutor

    def test_builder_creates_tool_executor(self):
        """Test that builder creates InvokeFunctionToolExecutor for InvokeFunctionTool actions."""

        def dummy() -> str:
            return "test"

        yaml_def = {
            "name": "builder_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "my_tool",
                    "functionName": "dummy",
                    "arguments": {},
                },
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"dummy": dummy})
        _ = builder.build()

        # Verify the executor was created
        assert "my_tool" in builder._executors
        executor = builder._executors["my_tool"]
        assert isinstance(executor, InvokeFunctionToolExecutor)


# ============================================================================
# Helper: Mock State and Context
# ============================================================================


@pytest.fixture
def mock_state() -> MagicMock:
    """Create a mock state with sync get/set/delete methods."""
    mock_state = MagicMock()
    mock_state._data = {}

    def mock_get(key: str, default: Any = None) -> Any:
        if key not in mock_state._data:
            if default is not None:
                return default
            raise KeyError(key)
        return mock_state._data[key]

    def mock_set(key: str, value: Any) -> None:
        mock_state._data[key] = value

    def mock_has(key: str) -> bool:
        return key in mock_state._data

    def mock_delete(key: str) -> None:
        if key in mock_state._data:
            del mock_state._data[key]
        else:
            raise KeyError(key)

    mock_state.get = MagicMock(side_effect=mock_get)
    mock_state.set = MagicMock(side_effect=mock_set)
    mock_state.has = MagicMock(side_effect=mock_has)
    mock_state.delete = MagicMock(side_effect=mock_delete)

    return mock_state


@pytest.fixture
def mock_context(mock_state: MagicMock) -> MagicMock:
    """Create a mock workflow context."""
    ctx = MagicMock()
    ctx.state = mock_state
    ctx.send_message = AsyncMock()
    ctx.yield_output = AsyncMock()
    ctx.request_info = AsyncMock()
    return ctx


# ============================================================================
# _normalize_variable_path unit tests (lines 153-155)
# ============================================================================


class TestNormalizeVariablePath:
    """Tests for _normalize_variable_path helper."""

    def test_known_prefix_local(self):
        assert _normalize_variable_path("Local.myVar") == "Local.myVar"

    def test_known_prefix_system(self):
        assert _normalize_variable_path("System.ConversationId") == "System.ConversationId"

    def test_known_prefix_workflow(self):
        assert _normalize_variable_path("Workflow.Inputs.x") == "Workflow.Inputs.x"

    def test_known_prefix_agent(self):
        assert _normalize_variable_path("Agent.LastResponse") == "Agent.LastResponse"

    def test_known_prefix_conversation(self):
        assert _normalize_variable_path("Conversation.messages") == "Conversation.messages"

    def test_dotted_unknown_prefix(self):
        """Dotted path without a known prefix is returned as-is."""
        assert _normalize_variable_path("Custom.myVar") == "Custom.myVar"

    def test_bare_name_gets_local_prefix(self):
        """Bare name without any dots defaults to Local. prefix."""
        assert _normalize_variable_path("weatherResult") == "Local.weatherResult"

    def test_bare_name_with_underscore(self):
        assert _normalize_variable_path("my_var") == "Local.my_var"


# ============================================================================
# Non-dict output config (line 275)
# ============================================================================


class TestNonDictOutputConfig:
    """Tests for non-dict output config handling."""

    @pytest.mark.asyncio
    async def test_output_as_string_is_ignored(self):
        """When output is a string instead of dict, both vars should be None."""

        def noop() -> str:
            return "done"

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "test_nondictoutput",
            "functionName": "noop",
            "arguments": {},
            "output": "Local.result",  # wrong: should be dict
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={"noop": noop})
        messages_var, result_var, auto_send = executor._get_output_config()
        assert messages_var is None
        assert result_var is None
        assert auto_send is True

    @pytest.mark.asyncio
    async def test_output_as_list_is_ignored(self):
        """When output is a list instead of dict, both vars should be None."""

        def noop() -> str:
            return "done"

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "test_listoutput",
            "functionName": "noop",
            "arguments": {},
            "output": ["Local.result"],
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={"noop": noop})
        messages_var, result_var, auto_send = executor._get_output_config()
        assert messages_var is None
        assert result_var is None
        assert auto_send is True


# ============================================================================
# Non-callable tool error (line 696)
# ============================================================================


class TestNonCallableTool:
    """Tests for non-callable tool invocation."""

    @pytest.mark.asyncio
    async def test_non_callable_stores_error(self):
        """Non-callable tool should produce an error result."""
        yaml_def = {
            "name": "non_callable_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_noncallable",
                    "functionName": "not_a_func",
                    "arguments": {},
                    "output": {"result": "Local.result"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.result.error"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"not_a_func": "i_am_a_string"})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert any("not callable" in out.lower() for out in outputs)


# ============================================================================
# Non-dict arguments warning (line 491)
# ============================================================================


class TestNonDictArguments:
    """Tests for non-dict arguments handling."""

    @pytest.mark.asyncio
    async def test_non_dict_arguments_ignored(self):
        """When arguments is not a dict, it should be ignored with a warning."""

        def no_args_needed() -> str:
            return "ok"

        yaml_def = {
            "name": "nondict_args_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_with_bad_args",
                    "functionName": "no_args_needed",
                    "arguments": "invalid_string_args",
                    "output": {"result": "Local.result"},
                },
                {"kind": "SendActivity", "id": "output", "activity": {"text": "=Local.result"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"no_args_needed": no_args_needed})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        assert "ok" in outputs


# ============================================================================
# JSON serialization fallbacks (lines 351-353, 369-371)
# ============================================================================


class TestFormatMessagesSerialization:
    """Tests for JSON serialization fallbacks in _format_messages."""

    @pytest.mark.asyncio
    async def test_non_serializable_result_uses_str_fallback(self):
        """When the function returns a non-JSON-serializable object, str() is used."""

        class CustomObj:
            def __str__(self):
                return "custom_string_repr"

        def returns_custom() -> object:
            return CustomObj()

        yaml_def = {
            "name": "nonserializable_result_test",
            "actions": [
                {
                    "kind": "InvokeFunctionTool",
                    "id": "call_custom",
                    "functionName": "returns_custom",
                    "arguments": {},
                    "output": {"messages": "Local.msgs", "result": "Local.result"},
                },
                {"kind": "SendActivity", "id": "done", "activity": {"text": "Done"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def, tools={"returns_custom": returns_custom})
        workflow = builder.build()

        events = await workflow.run({})
        outputs = events.get_outputs()

        # Should complete without crashing
        assert "Done" in outputs

    @pytest.mark.asyncio
    async def test_format_messages_directly_with_non_serializable(self):
        """Directly test _format_messages with non-serializable arguments and result."""

        class Unserializable:
            def __str__(self):
                return "unserializable_obj"

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "test_serialize",
            "functionName": "dummy",
        }
        executor = InvokeFunctionToolExecutor(action_def, tools={})

        # Non-serializable arguments
        messages = await executor._format_messages(
            function_name="test_func",
            arguments={"obj": Unserializable()},
            result=Unserializable(),
        )

        # Should produce 2 messages (tool_call + tool_result) without crashing
        assert len(messages) == 2
        assert messages[0].role == "assistant"
        assert messages[1].role == "tool"


# ============================================================================
# Approval flow tests (lines 512-532, 557-613)
# ============================================================================


class TestApprovalFlow:
    """Tests for the requireApproval=true flow with yield/resume pattern."""

    def _init_state(self, mock_state: MagicMock) -> None:
        """Pre-populate the state with declarative workflow data so _ensure_state_initialized works."""
        from agent_framework_declarative._workflows import DECLARATIVE_STATE_KEY

        mock_state._data[DECLARATIVE_STATE_KEY] = {
            "Inputs": {},
            "Outputs": {},
            "Local": {},
            "System": {
                "ConversationId": "test-conv",
                "LastMessage": {"Text": "", "Id": ""},
                "LastMessageText": "",
                "LastMessageId": "",
            },
            "Agent": {},
            "Conversation": {"messages": [], "history": []},
        }

    @pytest.mark.asyncio
    async def test_approval_required_emits_request(self, mock_state, mock_context):
        """When requireApproval=true, handle_action should emit ToolApprovalRequest and return."""
        self._init_state(mock_state)

        def my_tool(x: int) -> int:
            return x * 2

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "approval_test",
            "functionName": "my_tool",
            "requireApproval": True,
            "arguments": {"x": 5},
            "output": {"result": "Local.result"},
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={"my_tool": my_tool})

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should have called request_info with ToolApprovalRequest
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, ToolApprovalRequest)
        assert request.function_name == "my_tool"
        assert request.arguments == {"x": 5}

        # Should NOT have sent ActionComplete (workflow yields)
        mock_context.send_message.assert_not_called()

        # Approval state should be saved in state
        approval_key = f"{TOOL_APPROVAL_STATE_KEY}_approval_test"
        saved_state = mock_state._data[approval_key]
        assert isinstance(saved_state, ToolApprovalState)
        assert saved_state.function_name == "my_tool"
        assert saved_state.arguments == {"x": 5}

    @pytest.mark.asyncio
    async def test_approval_response_approved(self, mock_state, mock_context):
        """When approval response is approved, the tool should be invoked."""
        self._init_state(mock_state)

        call_log = []

        def my_tool(x: int) -> int:
            call_log.append(x)
            return x * 2

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "approval_approved",
            "functionName": "my_tool",
            "requireApproval": True,
            "arguments": {"x": 7},
            "output": {"result": "Local.result"},
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={"my_tool": my_tool})

        # Pre-populate approval state (simulating what handle_action stores)
        approval_key = f"{TOOL_APPROVAL_STATE_KEY}_approval_approved"
        mock_state._data[approval_key] = ToolApprovalState(
            function_name="my_tool",
            arguments={"x": 7},
            output_messages_var=None,
            output_result_var="Local.result",
            auto_send=True,
        )

        # Simulate the response
        original_request = ToolApprovalRequest(
            request_id="req-123",
            function_name="my_tool",
            arguments={"x": 7},
        )
        response = ToolApprovalResponse(approved=True)

        await executor.handle_approval_response(original_request, response, mock_context)

        # Tool should have been called
        assert call_log == [7]

        # ActionComplete should have been sent
        mock_context.send_message.assert_called_once()
        sent = mock_context.send_message.call_args[0][0]
        assert isinstance(sent, ActionComplete)

        # Approval state should be cleaned up
        assert approval_key not in mock_state._data

    @pytest.mark.asyncio
    async def test_approval_response_rejected(self, mock_state, mock_context):
        """When approval response is rejected, rejection status should be stored."""
        self._init_state(mock_state)

        def my_tool(x: int) -> int:
            raise AssertionError("Should not be called when rejected")

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "approval_rejected",
            "functionName": "my_tool",
            "requireApproval": True,
            "arguments": {"x": 5},
            "output": {"result": "Local.result"},
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={"my_tool": my_tool})

        # Pre-populate approval state
        approval_key = f"{TOOL_APPROVAL_STATE_KEY}_approval_rejected"
        mock_state._data[approval_key] = ToolApprovalState(
            function_name="my_tool",
            arguments={"x": 5},
            output_messages_var=None,
            output_result_var="Local.result",
            auto_send=True,
        )

        original_request = ToolApprovalRequest(
            request_id="req-456",
            function_name="my_tool",
            arguments={"x": 5},
        )
        response = ToolApprovalResponse(approved=False, reason="Not authorized")

        await executor.handle_approval_response(original_request, response, mock_context)

        # ActionComplete should have been sent
        mock_context.send_message.assert_called_once()

        # Result var should contain rejection info
        state_data = mock_state._data.get(DECLARATIVE_STATE_KEY, {})
        local_data = state_data.get("Local", {})
        result = local_data.get("result")
        assert result is not None
        assert result["rejected"] is True
        assert result["reason"] == "Not authorized"
        assert result["approved"] is False

    @pytest.mark.asyncio
    async def test_approval_response_missing_state(self, mock_state, mock_context):
        """When approval state is missing on resume, should log error and complete."""
        self._init_state(mock_state)

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "missing_state_test",
            "functionName": "my_tool",
            "requireApproval": True,
            "output": {"result": "Local.result"},
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={})

        # Don't populate approval state - simulate missing state
        original_request = ToolApprovalRequest(
            request_id="req-789",
            function_name="my_tool",
            arguments={},
        )
        response = ToolApprovalResponse(approved=True)

        await executor.handle_approval_response(original_request, response, mock_context)

        # Should still send ActionComplete
        mock_context.send_message.assert_called_once()
        sent = mock_context.send_message.call_args[0][0]
        assert isinstance(sent, ActionComplete)


# ============================================================================
# State registry tool lookup (lines 255-257)
# ============================================================================


class TestStateRegistryLookup:
    """Tests for tool lookup from State registry."""

    @pytest.mark.asyncio
    async def test_tool_found_in_state_registry(self, mock_state, mock_context):
        """Tool should be found from State registry when not in constructor tools."""
        self._init_state(mock_state)

        def state_registered_tool() -> str:
            return "from_state"

        # Register tool in State registry
        mock_state._data[FUNCTION_TOOL_REGISTRY_KEY] = {"state_tool": state_registered_tool}

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "state_lookup",
            "functionName": "state_tool",
            "arguments": {},
            "output": {"result": "Local.result"},
        }

        # Empty constructor tools - should fall back to State registry
        executor = InvokeFunctionToolExecutor(action_def, tools={})

        tool = executor._get_tool("state_tool", mock_context)
        assert tool is state_registered_tool

    def _init_state(self, mock_state: MagicMock) -> None:
        from agent_framework_declarative._workflows import DECLARATIVE_STATE_KEY

        mock_state._data[DECLARATIVE_STATE_KEY] = {
            "Inputs": {},
            "Outputs": {},
            "Local": {},
            "System": {
                "ConversationId": "test-conv",
                "LastMessage": {"Text": "", "Id": ""},
                "LastMessageText": "",
                "LastMessageId": "",
            },
            "Agent": {},
            "Conversation": {"messages": [], "history": []},
        }

    @pytest.mark.asyncio
    async def test_tool_not_found_in_state_registry_key_error(self, mock_state, mock_context):
        """When State registry key doesn't exist, should return None."""
        # Don't populate FUNCTION_TOOL_REGISTRY_KEY - will raise KeyError

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "missing_registry",
            "functionName": "missing",
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={})

        tool = executor._get_tool("missing", mock_context)
        assert tool is None

    @pytest.mark.asyncio
    async def test_tool_not_in_registry_returns_none(self, mock_state, mock_context):
        """When State registry exists but tool isn't in it, should return None."""
        mock_state._data[FUNCTION_TOOL_REGISTRY_KEY] = {"other_tool": lambda: None}

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "wrong_name",
            "functionName": "missing",
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={})

        tool = executor._get_tool("missing", mock_context)
        assert tool is None


# ============================================================================
# Missing/empty functionName at runtime (lines 470-475, 482)
# ============================================================================


class TestMissingFunctionNameRuntime:
    """Tests for missing/empty functionName at runtime with result_var."""

    def _init_state(self, mock_state: MagicMock) -> None:
        from agent_framework_declarative._workflows import DECLARATIVE_STATE_KEY

        mock_state._data[DECLARATIVE_STATE_KEY] = {
            "Inputs": {},
            "Outputs": {},
            "Local": {},
            "System": {
                "ConversationId": "test-conv",
                "LastMessage": {"Text": "", "Id": ""},
                "LastMessageText": "",
                "LastMessageId": "",
            },
            "Agent": {},
            "Conversation": {"messages": [], "history": []},
        }

    @pytest.mark.asyncio
    async def test_missing_function_name_stores_error_in_result_var(self, mock_state, mock_context):
        """Missing functionName should store error in result_var and complete."""
        self._init_state(mock_state)

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "no_name",
            # No functionName field
            "output": {"result": "Local.errorResult"},
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={})

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should send ActionComplete
        mock_context.send_message.assert_called_once()
        sent = mock_context.send_message.call_args[0][0]
        assert isinstance(sent, ActionComplete)

        # Error should be stored in result_var
        state_data = mock_state._data.get("_declarative_workflow_state", {})
        local_data = state_data.get("Local", {})
        assert "error" in local_data.get("errorResult", {})

    @pytest.mark.asyncio
    async def test_empty_function_name_with_result_var(self, mock_state, mock_context):
        """Empty functionName expression should store error in result_var."""
        self._init_state(mock_state)

        # Pre-set an empty value for toolName
        mock_state._data["_declarative_workflow_state"]["Local"]["toolName"] = ""

        action_def = {
            "kind": "InvokeFunctionTool",
            "id": "empty_name",
            "functionName": "=Local.toolName",
            "output": {"result": "Local.errorResult"},
        }

        executor = InvokeFunctionToolExecutor(action_def, tools={})

        await executor.handle_action(ActionTrigger(), mock_context)

        # Should send ActionComplete
        mock_context.send_message.assert_called_once()

        # Error should be stored in result_var
        state_data = mock_state._data.get("_declarative_workflow_state", {})
        local_data = state_data.get("Local", {})
        assert "error" in local_data.get("errorResult", {})
