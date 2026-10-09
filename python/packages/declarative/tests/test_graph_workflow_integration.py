# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for declarative workflows.

These tests verify:
- End-to-end workflow execution
- Checkpointing at action boundaries
- WorkflowFactory creating graph-based workflows
- Pause/resume capabilities
"""

import sys
from typing import Any

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

from agent_framework import InMemoryCheckpointStorage  # noqa: E402

from agent_framework_declarative._workflows import (  # noqa: E402
    ActionTrigger,
    DeclarativeWorkflowBuilder,
)
from agent_framework_declarative._workflows._declarative_base import LoopControl  # noqa: E402
from agent_framework_declarative._workflows._factory import WorkflowFactory  # noqa: E402


class TestGraphWorkflowLoopControl:
    """Exercise loop-control messages through the public workflow factory."""

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("stop_item", [1, 2, 3])
    async def test_break_loop_stops_at_selected_item(self, stream: bool, stop_item: int) -> None:
        definition = {
            "kind": "Workflow",
            "name": "break_selected_item",
            "actions": [
                {
                    "kind": "Foreach",
                    "source": [1, 2, 3],
                    "actions": [
                        {"kind": "SendActivity", "activity": "before"},
                        {"kind": "If", "condition": f"=Local.item = {stop_item}", "then": [{"kind": "BreakLoop"}]},
                        {"kind": "SendActivity", "activity": "after"},
                    ],
                },
                {"kind": "SendActivity", "activity": "done"},
            ],
        }
        workflow = WorkflowFactory().create_workflow_from_definition(definition)
        if stream:
            response = workflow.run({}, stream=True)
            events = [event async for event in response]
            result = await response.get_final_response()
            assert [event.data for event in events if event.type == "output"] == result.get_outputs()
        else:
            result = await workflow.run({})
        assert result.get_outputs() == ["before", "after"] * (stop_item - 1) + ["before", "done"]

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("continue_item", [1, 2, 3])
    async def test_continue_loop_preserves_remaining_iterations(self, stream: bool, continue_item: int) -> None:
        definition = {
            "kind": "Workflow",
            "name": "continue_selected_item",
            "actions": [
                {
                    "kind": "Foreach",
                    "source": [1, 2, 3],
                    "actions": [
                        {"kind": "SendActivity", "activity": "before"},
                        {
                            "kind": "If",
                            "condition": f"=Local.item = {continue_item}",
                            "then": [{"kind": "ContinueLoop"}],
                        },
                        {"kind": "SendActivity", "activity": "after"},
                    ],
                },
                {"kind": "SendActivity", "activity": "done"},
            ],
        }
        workflow = WorkflowFactory().create_workflow_from_definition(definition)
        result = await workflow.run({}, stream=True).get_final_response() if stream else await workflow.run({})
        expected = [
            text for item in [1, 2, 3] for text in (["before"] if item == continue_item else ["before", "after"])
        ]
        assert result.get_outputs() == expected + ["done"]

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("source", [[], [1, 2, 3]])
    async def test_break_loop_as_first_body_action(self, stream: bool, source: list[int]) -> None:
        workflow = WorkflowFactory().create_workflow_from_definition({
            "kind": "Workflow",
            "name": "break_first_action",
            "actions": [
                {"kind": "Foreach", "source": source, "actions": [{"kind": "BreakLoop", "id": "stop"}]},
                {"kind": "SendActivity", "activity": "done"},
            ],
        })
        result = await workflow.run({}, stream=True).get_final_response() if stream else await workflow.run({})
        assert result.get_outputs() == ["done"]
        assert sum(event.type == "executor_completed" and event.executor_id == "stop" for event in result) == bool(
            source
        )

    @pytest.mark.parametrize("stream", [False, True])
    async def test_nested_break_exits_only_inner_loop(self, stream: bool) -> None:
        workflow = WorkflowFactory().create_workflow_from_definition({
            "kind": "Workflow",
            "name": "nested_break",
            "actions": [
                {
                    "kind": "Foreach",
                    "source": [1, 2],
                    "itemName": "outer",
                    "actions": [
                        {"kind": "SendActivity", "activity": "outer-before"},
                        {
                            "kind": "Foreach",
                            "source": [10, 20, 30],
                            "itemName": "inner",
                            "actions": [
                                {"kind": "SendActivity", "activity": "inner"},
                                {"kind": "BreakLoop"},
                            ],
                        },
                        {"kind": "SendActivity", "activity": "outer-after"},
                    ],
                },
                {"kind": "SendActivity", "activity": "done"},
            ],
        })
        result = await workflow.run({}, stream=True).get_final_response() if stream else await workflow.run({})
        assert result.get_outputs() == ["outer-before", "inner", "outer-after"] * 2 + ["done"]

    @pytest.mark.parametrize(
        "control_kind,expected", [("BreakLoop", ["done"]), ("ContinueLoop", ["body", "body", "done"])]
    )
    async def test_loop_control_restored_into_fresh_workflow(self, control_kind: str, expected: list[str]) -> None:
        storage = InMemoryCheckpointStorage()
        definition: dict[str, Any] = {
            "kind": "Workflow",
            "name": "restored_loop_control",
            "actions": [
                {
                    "kind": "Foreach",
                    "id": "loop",
                    "source": [1, 2, 3],
                    "actions": [
                        {"kind": "SendActivity", "activity": "body"},
                        {"kind": control_kind, "id": "control"},
                    ],
                },
                {"kind": "SendActivity", "activity": "done"},
            ],
        }
        workflow = WorkflowFactory(checkpoint_storage=storage).create_workflow_from_definition(definition)
        await workflow.run({})
        checkpoint = next(
            checkpoint
            for checkpoint in await storage.list_checkpoints(workflow_name=workflow.name)
            if any(isinstance(message.data, LoopControl) for message in checkpoint.messages.get("control", []))
        )
        restored = WorkflowFactory(checkpoint_storage=storage).create_workflow_from_definition(definition)
        result = await restored.run(checkpoint_id=checkpoint.checkpoint_id)
        assert result.get_outputs() == expected


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
                    "source": "=Local.items",
                    "itemName": "item",
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
    async def test_foreach_multi_action_body_runs_sequentially(self):
        """Body actions must complete per item before advancing."""
        yaml_def = {
            "name": "loop_sequential_body",
            "actions": [
                {"kind": "SetValue", "id": "set_items", "path": "Local.items", "value": ["A", "B"]},
                {
                    "kind": "Foreach",
                    "id": "loop",
                    "source": "=Local.items",
                    "itemName": "item",
                    "actions": [
                        {"kind": "SendActivity", "id": "step_1", "activity": {"text": '="1-" & Local.item'}},
                        {"kind": "SendActivity", "id": "step_2", "activity": {"text": '="2-" & Local.item'}},
                        {"kind": "SendActivity", "id": "step_3", "activity": {"text": '="3-" & Local.item'}},
                    ],
                },
            ],
        }

        builder = DeclarativeWorkflowBuilder(yaml_def)
        workflow = builder.build()

        events = await workflow.run(ActionTrigger())
        outputs = events.get_outputs()

        assert outputs == ["1-A", "2-A", "3-A", "1-B", "2-B", "3-B"]

    @pytest.mark.asyncio
    async def test_workflow_with_condition_group(self):
        """Test workflow with ConditionGroup."""
        yaml_def = {
            "name": "condition_group_workflow",
            "actions": [
                {"kind": "SetValue", "id": "set_level", "path": "Local.level", "value": 2},
                {
                    "kind": "ConditionGroup",
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
                    "elseActions": [
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

        # Verify multiple executors were created (+ _workflow_entry node)
        assert "step1" in builder._executors
        assert "step2" in builder._executors
        assert "step3" in builder._executors
        assert len(builder._executors) == 4

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

        # Verify all executors exist (+ _workflow_entry node)
        assert len(builder._executors) == 4

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
