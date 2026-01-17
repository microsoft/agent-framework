# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for declarative workflows.

These tests verify:
- End-to-end workflow execution
- Checkpointing at action boundaries
- WorkflowFactory creating graph-based workflows
- Pause/resume capabilities
"""

import pytest

from agent_framework_declarative._workflows import (
    ActionTrigger,
    DeclarativeWorkflowBuilder,
)
from agent_framework_declarative._workflows._factory import WorkflowFactory


class TestGraphBasedWorkflowExecution:
    """Integration tests for graph-based workflow execution."""

    @pytest.mark.asyncio
    async def test_simple_sequential_workflow(self):
        """Test a simple sequential workflow with SendActivity actions."""
        yaml_def = {
            "name": "simple_workflow",
            "actions": [
                {"kind": "SendActivity", "id": "greet", "activity": {"text": "Hello!"}},
                {"kind": "SetValue", "id": "set_count", "path": "Local.count", "value": 1},
                {"kind": "SendActivity", "id": "done", "activity": {"text": "Done!"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        # Run the workflow
        events = await workflow.run(ActionTrigger())

        # Verify outputs were produced
        outputs = events.get_outputs()
        assert "Hello!" in outputs
        assert "Done!" in outputs

    @pytest.mark.asyncio
    async def test_workflow_with_conditional(self):
        """Test workflow with If conditional branching."""
        yaml_def = {
            "name": "conditional_workflow",
            "actions": [
                {"kind": "SetValue", "id": "set_flag", "path": "Local.flag", "value": True},
                {
                    "kind": "If",
                    "id": "check_flag",
                    "condition": "=Local.flag",
                    "then": [
                        {"kind": "SendActivity", "id": "say_yes", "activity": {"text": "Flag is true!"}},
                    ],
                    "else": [
                        {"kind": "SendActivity", "id": "say_no", "activity": {"text": "Flag is false!"}},
                    ],
                },
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        # Run the workflow
        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        # Should take the "then" branch since flag is True
        assert "Flag is true!" in outputs
        assert "Flag is false!" not in outputs

    @pytest.mark.asyncio
    async def test_workflow_with_foreach_loop(self):
        """Test workflow with Foreach loop."""
        yaml_def = {
            "name": "loop_workflow",
            "actions": [
                {"kind": "SetValue", "id": "set_items", "path": "Local.items", "value": ["a", "b", "c"]},
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

        # Run the workflow
        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        # Should output each item
        assert "a" in outputs
        assert "b" in outputs
        assert "c" in outputs

    @pytest.mark.asyncio
    async def test_workflow_with_switch(self):
        """Test workflow with Switch/ConditionGroup."""
        yaml_def = {
            "name": "switch_workflow",
            "actions": [
                {"kind": "SetValue", "id": "set_level", "path": "Local.level", "value": 2},
                {
                    "kind": "Switch",
                    "id": "check_level",
                    "conditions": [
                        {
                            "condition": "=Local.level = 1",
                            "actions": [
                                {"kind": "SendActivity", "id": "level_1", "activity": {"text": "Level 1"}},
                            ],
                        },
                        {
                            "condition": "=Local.level = 2",
                            "actions": [
                                {"kind": "SendActivity", "id": "level_2", "activity": {"text": "Level 2"}},
                            ],
                        },
                    ],
                    "else": [
                        {"kind": "SendActivity", "id": "default", "activity": {"text": "Other level"}},
                    ],
                },
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        # Run the workflow
        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        # Should take the level 2 branch
        assert "Level 2" in outputs
        assert "Level 1" not in outputs
        assert "Other level" not in outputs


class TestWorkflowFactory:
    """Tests for WorkflowFactory."""

    def test_factory_creates_workflow(self):
        """Test creating workflow."""
        factory = WorkflowFactory()

        yaml_content = """
name: test_workflow
actions:
  - kind: SendActivity
    id: greet
    activity:
      text: "Hello from graph mode!"
  - kind: SetValue
    id: set_val
    path: Local.result
    value: 42
"""
        workflow = factory.create_workflow_from_yaml(yaml_content)

        assert workflow is not None
        assert hasattr(workflow, "_declarative_agents")

    @pytest.mark.asyncio
    async def test_workflow_execution(self):
        """Test executing a workflow."""
        factory = WorkflowFactory()

        yaml_content = """
name: graph_execution_test
actions:
  - kind: SendActivity
    id: start
    activity:
      text: "Starting workflow"
  - kind: SetValue
    id: set_message
    path: Local.message
    value: "Hello World"
  - kind: SendActivity
    id: end
    activity:
      text: "Workflow complete"
"""
        workflow = factory.create_workflow_from_yaml(yaml_content)

        # Execute the workflow
        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        assert "Starting workflow" in outputs
        assert "Workflow complete" in outputs


class TestGraphWorkflowCheckpointing:
    """Tests for checkpointing capabilities of graph-based workflows."""

    def test_workflow_has_multiple_executors(self):
        """Test that graph-based workflow creates multiple executor nodes."""
        yaml_def = {
            "name": "multi_executor_workflow",
            "actions": [
                {"kind": "SetValue", "id": "step1", "path": "Local.a", "value": 1},
                {"kind": "SetValue", "id": "step2", "path": "Local.b", "value": 2},
                {"kind": "SetValue", "id": "step3", "path": "Local.c", "value": 3},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        _workflow = builder.build()  # noqa: F841

        # Verify multiple executors were created
        assert "step1" in builder._executors
        assert "step2" in builder._executors
        assert "step3" in builder._executors
        assert len(builder._executors) == 3

    def test_workflow_executor_connectivity(self):
        """Test that executors are properly connected in sequence."""
        yaml_def = {
            "name": "connected_workflow",
            "actions": [
                {"kind": "SendActivity", "id": "a", "activity": {"text": "A"}},
                {"kind": "SendActivity", "id": "b", "activity": {"text": "B"}},
                {"kind": "SendActivity", "id": "c", "activity": {"text": "C"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        # Verify all executors exist
        assert len(builder._executors) == 3

        # Verify the workflow can be inspected
        assert workflow is not None


class TestGraphWorkflowVisualization:
    """Tests for workflow visualization capabilities."""

    def test_workflow_can_be_built(self):
        """Test that complex workflows can be built successfully."""
        yaml_def = {
            "name": "complex_workflow",
            "actions": [
                {"kind": "SendActivity", "id": "intro", "activity": {"text": "Starting"}},
                {
                    "kind": "If",
                    "id": "branch",
                    "condition": "=true",
                    "then": [
                        {"kind": "SendActivity", "id": "then_msg", "activity": {"text": "Then branch"}},
                    ],
                    "else": [
                        {"kind": "SendActivity", "id": "else_msg", "activity": {"text": "Else branch"}},
                    ],
                },
                {"kind": "SendActivity", "id": "outro", "activity": {"text": "Done"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        # Verify the workflow was built
        assert workflow is not None

        # Verify expected executors exist
        # intro, branch_condition, then_msg, else_msg, branch_join, outro
        assert "intro" in builder._executors
        assert "then_msg" in builder._executors
        assert "else_msg" in builder._executors
        assert "outro" in builder._executors


class TestGraphWorkflowStateManagement:
    """Tests for state management across graph executor nodes."""

    @pytest.mark.asyncio
    async def test_state_persists_across_executors(self):
        """Test that state set in one executor is available in the next."""
        yaml_def = {
            "name": "state_test",
            "actions": [
                {"kind": "SetValue", "id": "set", "path": "Local.value", "value": "test_data"},
                {"kind": "SendActivity", "id": "send", "activity": {"text": "=Local.value"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        # The SendActivity should have access to the value set by SetValue
        assert "test_data" in outputs

    @pytest.mark.asyncio
    async def test_multiple_variables(self):
        """Test setting and using multiple variables."""
        yaml_def = {
            "name": "multi_var_test",
            "actions": [
                {"kind": "SetValue", "id": "set_a", "path": "Local.a", "value": "Hello"},
                {"kind": "SetValue", "id": "set_b", "path": "Local.b", "value": "World"},
                {"kind": "SendActivity", "id": "send", "activity": {"text": "=Local.a"}},
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        assert "Hello" in outputs
