# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for WorkflowState class."""

import pytest

from agent_framework_declarative._workflows._state import WorkflowState


class TestWorkflowStateInitialization:
    """Tests for WorkflowState initialization."""

    def test_empty_initialization(self):
        """Test creating a WorkflowState with no inputs."""
        state = WorkflowState()
        assert state.inputs == {}
        assert state.outputs == {}
        assert state.local == {}
        assert state.agent == {}

    def test_initialization_with_inputs(self):
        """Test creating a WorkflowState with inputs."""
        state = WorkflowState(inputs={"query": "Hello", "count": 5})
        assert state.inputs == {"query": "Hello", "count": 5}
        assert state.outputs == {}

    def test_inputs_are_immutable(self):
        """Test that inputs cannot be modified through set()."""
        state = WorkflowState(inputs={"query": "Hello"})
        with pytest.raises(ValueError, match="Cannot modify Workflow.Inputs"):
            state.set("Workflow.Inputs.query", "Modified")


class TestWorkflowStateGetSet:
    """Tests for get and set operations."""

    def test_set_and_get_turn_variable(self):
        """Test setting and getting a turn variable."""
        state = WorkflowState()
        state.set("Local.counter", 10)
        assert state.get("Local.counter") == 10

    def test_set_and_get_nested_turn_variable(self):
        """Test setting and getting a nested turn variable."""
        state = WorkflowState()
        state.set("Local.data.nested.value", "test")
        assert state.get("Local.data.nested.value") == "test"

    def test_set_and_get_workflow_output(self):
        """Test setting and getting workflow output."""
        state = WorkflowState()
        state.set("Workflow.Outputs.result", "success")
        assert state.get("Workflow.Outputs.result") == "success"
        assert state.outputs["result"] == "success"

    def test_get_with_default(self):
        """Test get with default value."""
        state = WorkflowState()
        assert state.get("Local.nonexistent") is None
        assert state.get("Local.nonexistent", "default") == "default"

    def test_get_workflow_inputs(self):
        """Test getting workflow inputs."""
        state = WorkflowState(inputs={"query": "test"})
        assert state.get("Workflow.Inputs.query") == "test"

    def test_set_custom_namespace(self):
        """Test setting a custom namespace variable."""
        state = WorkflowState()
        state.set("custom.myvar", "value")
        assert state.get("custom.myvar") == "value"


class TestWorkflowStateAppend:
    """Tests for append operation."""

    def test_append_to_nonexistent_list(self):
        """Test appending to a path that doesn't exist yet."""
        state = WorkflowState()
        state.append("Local.results", "item1")
        assert state.get("Local.results") == ["item1"]

    def test_append_to_existing_list(self):
        """Test appending to an existing list."""
        state = WorkflowState()
        state.set("Local.results", ["item1"])
        state.append("Local.results", "item2")
        assert state.get("Local.results") == ["item1", "item2"]

    def test_append_to_non_list_raises(self):
        """Test that appending to a non-list raises ValueError."""
        state = WorkflowState()
        state.set("Local.value", "not a list")
        with pytest.raises(ValueError, match="Cannot append to non-list"):
            state.append("Local.value", "item")


class TestWorkflowStateAgentResult:
    """Tests for agent result management."""

    def test_set_agent_result(self):
        """Test setting agent result."""
        state = WorkflowState()
        state.set_agent_result(
            text="Agent response",
            messages=[{"role": "assistant", "content": "Hello"}],
            tool_calls=[{"name": "tool1"}],
        )
        assert state.agent["text"] == "Agent response"
        assert len(state.agent["messages"]) == 1
        assert len(state.agent["toolCalls"]) == 1

    def test_get_agent_result_via_path(self):
        """Test getting agent result via path."""
        state = WorkflowState()
        state.set_agent_result(text="Response")
        assert state.get("Agent.text") == "Response"

    def test_reset_agent(self):
        """Test resetting agent result."""
        state = WorkflowState()
        state.set_agent_result(text="Response")
        state.reset_agent()
        assert state.agent == {}


class TestWorkflowStateConversation:
    """Tests for conversation management."""

    def test_add_conversation_message(self):
        """Test adding a conversation message."""
        state = WorkflowState()
        message = {"role": "user", "content": "Hello"}
        state.add_conversation_message(message)
        assert len(state.conversation["messages"]) == 1
        assert state.conversation["messages"][0] == message

    def test_get_conversation_history(self):
        """Test getting conversation history."""
        state = WorkflowState()
        state.add_conversation_message({"role": "user", "content": "Hi"})
        state.add_conversation_message({"role": "assistant", "content": "Hello"})
        assert len(state.get("Conversation.history")) == 2


class TestWorkflowStatePowerFx:
    """Tests for PowerFx expression evaluation."""

    def test_eval_non_expression(self):
        """Test that non-expressions are returned as-is."""
        state = WorkflowState()
        assert state.eval("plain text") == "plain text"

    def test_eval_if_expression_with_literal(self):
        """Test eval_if_expression with a literal value."""
        state = WorkflowState()
        assert state.eval_if_expression(42) == 42
        assert state.eval_if_expression(["a", "b"]) == ["a", "b"]

    def test_eval_if_expression_with_non_expression_string(self):
        """Test eval_if_expression with a non-expression string."""
        state = WorkflowState()
        assert state.eval_if_expression("plain text") == "plain text"

    def test_to_powerfx_symbols(self):
        """Test converting state to PowerFx symbols."""
        state = WorkflowState(inputs={"query": "test"})
        state.set("Local.counter", 5)
        state.set("Workflow.Outputs.result", "done")

        symbols = state.to_powerfx_symbols()
        assert symbols["Workflow"]["Inputs"]["query"] == "test"
        assert symbols["Workflow"]["Outputs"]["result"] == "done"
        assert symbols["Local"]["counter"] == 5


class TestWorkflowStateClone:
    """Tests for state cloning."""

    def test_clone_creates_copy(self):
        """Test that clone creates a copy of the state."""
        state = WorkflowState(inputs={"query": "test"})
        state.set("Local.counter", 5)

        cloned = state.clone()
        assert cloned.get("Workflow.Inputs.query") == "test"
        assert cloned.get("Local.counter") == 5

    def test_clone_is_independent(self):
        """Test that modifications to clone don't affect original."""
        state = WorkflowState()
        state.set("Local.value", "original")

        cloned = state.clone()
        cloned.set("Local.value", "modified")

        assert state.get("Local.value") == "original"
        assert cloned.get("Local.value") == "modified"


class TestWorkflowStateResetTurn:
    """Tests for turn reset."""

    def test_reset_local_clears_turn_variables(self):
        """Test that reset_local clears turn variables."""
        state = WorkflowState()
        state.set("Local.var1", "value1")
        state.set("Local.var2", "value2")

        state.reset_local()

        assert state.get("Local.var1") is None
        assert state.get("Local.var2") is None
        assert state.local == {}

    def test_reset_local_preserves_other_state(self):
        """Test that reset_local preserves other state."""
        state = WorkflowState(inputs={"query": "test"})
        state.set("Workflow.Outputs.result", "done")
        state.set("Local.temp", "will be cleared")

        state.reset_local()

        assert state.get("Workflow.Inputs.query") == "test"
        assert state.get("Workflow.Outputs.result") == "done"


class TestWorkflowStateEvalSimple:
    """Tests for _eval_simple fallback PowerFx evaluation."""

    def test_negation_prefix(self):
        """Test negation with ! prefix."""
        state = WorkflowState()
        state.set("Local.value", True)
        assert state._eval_simple("!Local.value") is False
        state.set("Local.value", False)
        assert state._eval_simple("!Local.value") is True

    def test_not_function(self):
        """Test Not() function."""
        state = WorkflowState()
        state.set("Local.flag", True)
        assert state._eval_simple("Not(Local.flag)") is False
        state.set("Local.flag", False)
        assert state._eval_simple("Not(Local.flag)") is True

    def test_and_operator(self):
        """Test And operator."""
        state = WorkflowState()
        state.set("Local.a", True)
        state.set("Local.b", True)
        assert state._eval_simple("Local.a And Local.b") is True
        state.set("Local.b", False)
        assert state._eval_simple("Local.a And Local.b") is False

    def test_or_operator(self):
        """Test Or operator."""
        state = WorkflowState()
        state.set("Local.a", False)
        state.set("Local.b", False)
        assert state._eval_simple("Local.a Or Local.b") is False
        state.set("Local.b", True)
        assert state._eval_simple("Local.a Or Local.b") is True

    def test_or_operator_double_pipe(self):
        """Test || operator."""
        state = WorkflowState()
        state.set("Local.x", False)
        state.set("Local.y", True)
        assert state._eval_simple("Local.x || Local.y") is True

    def test_less_than(self):
        """Test < comparison."""
        state = WorkflowState()
        state.set("Local.num", 5)
        assert state._eval_simple("Local.num < 10") is True
        assert state._eval_simple("Local.num < 3") is False

    def test_greater_than(self):
        """Test > comparison."""
        state = WorkflowState()
        state.set("Local.num", 5)
        assert state._eval_simple("Local.num > 3") is True
        assert state._eval_simple("Local.num > 10") is False

    def test_less_than_or_equal(self):
        """Test <= comparison."""
        state = WorkflowState()
        state.set("Local.num", 5)
        assert state._eval_simple("Local.num <= 5") is True
        assert state._eval_simple("Local.num <= 4") is False

    def test_greater_than_or_equal(self):
        """Test >= comparison."""
        state = WorkflowState()
        state.set("Local.num", 5)
        assert state._eval_simple("Local.num >= 5") is True
        assert state._eval_simple("Local.num >= 6") is False

    def test_not_equal(self):
        """Test <> comparison."""
        state = WorkflowState()
        state.set("Local.val", "hello")
        assert state._eval_simple('Local.val <> "world"') is True
        assert state._eval_simple('Local.val <> "hello"') is False

    def test_equal(self):
        """Test = comparison."""
        state = WorkflowState()
        state.set("Local.val", "test")
        assert state._eval_simple('Local.val = "test"') is True
        assert state._eval_simple('Local.val = "other"') is False

    def test_addition_numeric(self):
        """Test + operator with numbers."""
        state = WorkflowState()
        state.set("Local.a", 3)
        state.set("Local.b", 4)
        assert state._eval_simple("Local.a + Local.b") == 7.0

    def test_addition_string_concat(self):
        """Test + operator falls back to string concat."""
        state = WorkflowState()
        state.set("Local.a", "hello")
        state.set("Local.b", "world")
        assert state._eval_simple("Local.a + Local.b") == "helloworld"

    def test_addition_with_none(self):
        """Test + treats None as 0."""
        state = WorkflowState()
        state.set("Local.a", 5)
        # Local.b doesn't exist, so it's None
        assert state._eval_simple("Local.a + Local.b") == 5.0

    def test_subtraction(self):
        """Test - operator."""
        state = WorkflowState()
        state.set("Local.a", 10)
        state.set("Local.b", 3)
        assert state._eval_simple("Local.a - Local.b") == 7.0

    def test_subtraction_with_none(self):
        """Test - treats None as 0."""
        state = WorkflowState()
        state.set("Local.a", 5)
        assert state._eval_simple("Local.a - Local.missing") == 5.0

    def test_multiplication(self):
        """Test * operator."""
        state = WorkflowState()
        state.set("Local.a", 4)
        state.set("Local.b", 5)
        assert state._eval_simple("Local.a * Local.b") == 20.0

    def test_multiplication_with_none(self):
        """Test * treats None as 0."""
        state = WorkflowState()
        state.set("Local.a", 5)
        assert state._eval_simple("Local.a * Local.missing") == 0.0

    def test_division(self):
        """Test / operator."""
        state = WorkflowState()
        state.set("Local.a", 20)
        state.set("Local.b", 4)
        assert state._eval_simple("Local.a / Local.b") == 5.0

    def test_division_by_zero(self):
        """Test / by zero returns None."""
        state = WorkflowState()
        state.set("Local.a", 10)
        state.set("Local.b", 0)
        assert state._eval_simple("Local.a / Local.b") is None

    def test_string_literal_double_quotes(self):
        """Test string literal with double quotes."""
        state = WorkflowState()
        assert state._eval_simple('"hello world"') == "hello world"

    def test_string_literal_single_quotes(self):
        """Test string literal with single quotes."""
        state = WorkflowState()
        assert state._eval_simple("'hello world'") == "hello world"

    def test_integer_literal(self):
        """Test integer literal."""
        state = WorkflowState()
        assert state._eval_simple("42") == 42

    def test_float_literal(self):
        """Test float literal."""
        state = WorkflowState()
        assert state._eval_simple("3.14") == 3.14

    def test_boolean_true_literal(self):
        """Test true literal (case insensitive)."""
        state = WorkflowState()
        assert state._eval_simple("true") is True
        assert state._eval_simple("True") is True
        assert state._eval_simple("TRUE") is True

    def test_boolean_false_literal(self):
        """Test false literal (case insensitive)."""
        state = WorkflowState()
        assert state._eval_simple("false") is False
        assert state._eval_simple("False") is False
        assert state._eval_simple("FALSE") is False

    def test_variable_reference(self):
        """Test simple variable reference."""
        state = WorkflowState()
        state.set("Local.myvar", "myvalue")
        assert state._eval_simple("Local.myvar") == "myvalue"

    def test_unknown_expression_returned_as_is(self):
        """Test that unknown expressions are returned as-is."""
        state = WorkflowState()
        result = state._eval_simple("unknown_identifier")
        assert result == "unknown_identifier"

    def test_agent_namespace_reference(self):
        """Test Agent namespace variable reference."""
        state = WorkflowState()
        state.set_agent_result(text="agent response")
        assert state._eval_simple("Agent.text") == "agent response"

    def test_conversation_namespace_reference(self):
        """Test Conversation namespace variable reference."""
        state = WorkflowState()
        state.add_conversation_message({"role": "user", "content": "hello"})
        result = state._eval_simple("Conversation.messages")
        assert len(result) == 1

    def test_workflow_inputs_reference(self):
        """Test Workflow.Inputs reference."""
        state = WorkflowState(inputs={"name": "test"})
        assert state._eval_simple("Workflow.Inputs.name") == "test"


class TestWorkflowStateParseFunctionArgs:
    """Tests for _parse_function_args helper."""

    def test_simple_args(self):
        """Test parsing simple comma-separated args."""
        state = WorkflowState()
        args = state._parse_function_args("1, 2, 3")
        assert args == ["1", "2", "3"]

    def test_string_args_with_commas(self):
        """Test parsing string args containing commas."""
        state = WorkflowState()
        args = state._parse_function_args('"hello, world", "another"')
        assert args == ['"hello, world"', '"another"']

    def test_nested_function_args(self):
        """Test parsing nested function calls."""
        state = WorkflowState()
        args = state._parse_function_args("Concat(a, b), c")
        assert args == ["Concat(a, b)", "c"]

    def test_empty_args(self):
        """Test parsing empty args string."""
        state = WorkflowState()
        args = state._parse_function_args("")
        assert args == []

    def test_single_arg(self):
        """Test parsing single argument."""
        state = WorkflowState()
        args = state._parse_function_args("single")
        assert args == ["single"]

    def test_deeply_nested_parens(self):
        """Test parsing deeply nested parentheses."""
        state = WorkflowState()
        args = state._parse_function_args("Func1(Func2(a, b)), c")
        assert args == ["Func1(Func2(a, b))", "c"]


class TestWorkflowStateEvalIfExpression:
    """Tests for eval_if_expression method."""

    def test_dict_values_evaluated(self):
        """Test that dict values are recursively evaluated."""
        state = WorkflowState()
        state.set("Local.name", "World")
        result = state.eval_if_expression({"greeting": "=Local.name", "static": "value"})
        assert result == {"greeting": "World", "static": "value"}

    def test_list_values_evaluated(self):
        """Test that list values are recursively evaluated."""
        state = WorkflowState()
        state.set("Local.val", 42)
        result = state.eval_if_expression(["=Local.val", "static"])
        assert result == [42, "static"]

    def test_nested_dict_in_list(self):
        """Test nested dict in list is evaluated."""
        state = WorkflowState()
        state.set("Local.x", 10)
        result = state.eval_if_expression([{"key": "=Local.x"}])
        assert result == [{"key": 10}]


class TestWorkflowStateSetErrors:
    """Tests for set() error handling."""

    def test_set_workflow_directly_raises(self):
        """Test that setting Workflow directly raises error."""
        state = WorkflowState()
        with pytest.raises(ValueError, match="Cannot set 'Workflow' directly"):
            state.set("Workflow", "value")

    def test_set_unknown_workflow_namespace_raises(self):
        """Test that setting unknown Workflow sub-namespace raises."""
        state = WorkflowState()
        with pytest.raises(ValueError, match="Unknown Workflow namespace"):
            state.set("Workflow.Unknown.path", "value")

    def test_set_namespace_root_raises(self):
        """Test that setting namespace root raises error."""
        state = WorkflowState()
        with pytest.raises(ValueError, match="Cannot replace entire namespace"):
            state.set("Local", "value")


class TestWorkflowStateGetEdgeCases:
    """Tests for get() edge cases."""

    def test_get_empty_path(self):
        """Test get with empty path returns default."""
        state = WorkflowState()
        assert state.get("", "default") == "default"

    def test_get_unknown_namespace(self):
        """Test get from unknown namespace returns default."""
        state = WorkflowState()
        assert state.get("Unknown.path") is None
        assert state.get("Unknown.path", "fallback") == "fallback"

    def test_get_with_object_attribute(self):
        """Test get navigates object attributes."""
        state = WorkflowState()

        class MockObj:
            attr = "attribute_value"

        state.set("Local.obj", MockObj())
        assert state.get("Local.obj.attr") == "attribute_value"

    def test_get_unknown_workflow_subspace(self):
        """Test get from unknown Workflow sub-namespace."""
        state = WorkflowState()
        assert state.get("Workflow.Unknown.path") is None


class TestWorkflowStateConversationIdInit:
    """Tests that WorkflowState generates a real UUID for System.ConversationId."""

    def test_conversation_id_is_not_default(self):
        """System.ConversationId should be a UUID, not 'default'."""
        import uuid

        state = WorkflowState()
        conv_id = state.get("System.ConversationId")
        assert conv_id is not None
        assert conv_id != "default"
        uuid.UUID(conv_id)  # Raises ValueError if not a valid UUID

    def test_conversations_dict_initialized(self):
        """System.conversations should contain an entry matching ConversationId."""
        state = WorkflowState()
        conv_id = state.get("System.ConversationId")
        conversations = state.get("System.conversations")
        assert conversations is not None
        assert conv_id in conversations
        assert conversations[conv_id]["id"] == conv_id
        assert conversations[conv_id]["messages"] == []

    def test_each_instance_generates_unique_id(self):
        """Each WorkflowState instance should have a different ConversationId."""
        state1 = WorkflowState()
        state2 = WorkflowState()
        assert state1.get("System.ConversationId") != state2.get("System.ConversationId")
