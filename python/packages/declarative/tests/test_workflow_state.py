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
        assert state.turn == {}
        assert state.agent == {}

    def test_initialization_with_inputs(self):
        """Test creating a WorkflowState with inputs."""
        state = WorkflowState(inputs={"query": "Hello", "count": 5})
        assert state.inputs == {"query": "Hello", "count": 5}
        assert state.outputs == {}

    def test_inputs_are_immutable(self):
        """Test that inputs cannot be modified through set()."""
        state = WorkflowState(inputs={"query": "Hello"})
        with pytest.raises(ValueError, match="Cannot modify workflow.inputs"):
            state.set("workflow.inputs.query", "Modified")


class TestWorkflowStateGetSet:
    """Tests for get and set operations."""

    def test_set_and_get_turn_variable(self):
        """Test setting and getting a turn variable."""
        state = WorkflowState()
        state.set("turn.counter", 10)
        assert state.get("turn.counter") == 10

    def test_set_and_get_nested_turn_variable(self):
        """Test setting and getting a nested turn variable."""
        state = WorkflowState()
        state.set("turn.data.nested.value", "test")
        assert state.get("turn.data.nested.value") == "test"

    def test_set_and_get_workflow_output(self):
        """Test setting and getting workflow output."""
        state = WorkflowState()
        state.set("workflow.outputs.result", "success")
        assert state.get("workflow.outputs.result") == "success"
        assert state.outputs["result"] == "success"

    def test_get_with_default(self):
        """Test get with default value."""
        state = WorkflowState()
        assert state.get("turn.nonexistent") is None
        assert state.get("turn.nonexistent", "default") == "default"

    def test_get_workflow_inputs(self):
        """Test getting workflow inputs."""
        state = WorkflowState(inputs={"query": "test"})
        assert state.get("workflow.inputs.query") == "test"

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
        state.append("turn.results", "item1")
        assert state.get("turn.results") == ["item1"]

    def test_append_to_existing_list(self):
        """Test appending to an existing list."""
        state = WorkflowState()
        state.set("turn.results", ["item1"])
        state.append("turn.results", "item2")
        assert state.get("turn.results") == ["item1", "item2"]

    def test_append_to_non_list_raises(self):
        """Test that appending to a non-list raises ValueError."""
        state = WorkflowState()
        state.set("turn.value", "not a list")
        with pytest.raises(ValueError, match="Cannot append to non-list"):
            state.append("turn.value", "item")


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
        assert state.get("agent.text") == "Response"

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
        assert len(state.get("conversation.history")) == 2


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
        state.set("turn.counter", 5)
        state.set("workflow.outputs.result", "done")

        symbols = state.to_powerfx_symbols()
        assert symbols["workflow"]["inputs"]["query"] == "test"
        assert symbols["workflow"]["outputs"]["result"] == "done"
        assert symbols["turn"]["counter"] == 5


class TestWorkflowStateClone:
    """Tests for state cloning."""

    def test_clone_creates_copy(self):
        """Test that clone creates a copy of the state."""
        state = WorkflowState(inputs={"query": "test"})
        state.set("turn.counter", 5)

        cloned = state.clone()
        assert cloned.get("workflow.inputs.query") == "test"
        assert cloned.get("turn.counter") == 5

    def test_clone_is_independent(self):
        """Test that modifications to clone don't affect original."""
        state = WorkflowState()
        state.set("turn.value", "original")

        cloned = state.clone()
        cloned.set("turn.value", "modified")

        assert state.get("turn.value") == "original"
        assert cloned.get("turn.value") == "modified"


class TestWorkflowStateResetTurn:
    """Tests for turn reset."""

    def test_reset_turn_clears_turn_variables(self):
        """Test that reset_turn clears turn variables."""
        state = WorkflowState()
        state.set("turn.var1", "value1")
        state.set("turn.var2", "value2")

        state.reset_turn()

        assert state.get("turn.var1") is None
        assert state.get("turn.var2") is None
        assert state.turn == {}

    def test_reset_turn_preserves_other_state(self):
        """Test that reset_turn preserves other state."""
        state = WorkflowState(inputs={"query": "test"})
        state.set("workflow.outputs.result", "done")
        state.set("turn.temp", "will be cleared")

        state.reset_turn()

        assert state.get("workflow.inputs.query") == "test"
        assert state.get("workflow.outputs.result") == "done"
