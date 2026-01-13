# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for WorkflowFactory."""

import pytest

from agent_framework_declarative._workflows._factory import (
    DeclarativeWorkflowError,
    WorkflowFactory,
)


class TestWorkflowFactoryValidation:
    """Tests for workflow definition validation."""

    def test_missing_actions_raises(self):
        """Test that missing 'actions' field raises an error."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="must have 'actions' field"):
            factory.create_workflow_from_yaml("""
name: test-workflow
description: A test
# Missing 'actions' field
""")

    def test_actions_not_list_raises(self):
        """Test that non-list 'actions' field raises an error."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="'actions' must be a list"):
            factory.create_workflow_from_yaml("""
name: test-workflow
actions: "not a list"
""")

    def test_action_missing_kind_raises(self):
        """Test that actions without 'kind' field raise an error."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="missing 'kind' field"):
            factory.create_workflow_from_yaml("""
name: test-workflow
actions:
  - path: Local.value
    value: test
""")

    def test_valid_minimal_workflow(self):
        """Test creating a valid minimal workflow."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: minimal-workflow
actions:
  - kind: SetValue
    path: Local.result
    value: done
""")

        assert workflow is not None
        assert workflow.name == "minimal-workflow"


class TestWorkflowFactoryExecution:
    """Tests for workflow execution."""

    @pytest.mark.asyncio
    async def test_execute_set_value_workflow(self):
        """Test executing a simple SetValue workflow."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: set-value-test
actions:
  - kind: SetValue
    path: Local.greeting
    value: Hello
  - kind: SendActivity
    activity:
      text: Done
""")

        result = await workflow.run({"input": "test"})
        outputs = result.get_outputs()

        # The workflow should produce output from SendActivity
        assert len(outputs) > 0

    @pytest.mark.asyncio
    async def test_execute_send_activity_workflow(self):
        """Test executing a workflow that sends activities."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: send-activity-test
actions:
  - kind: SendActivity
    activity:
      text: Hello, world!
""")

        result = await workflow.run({"input": "test"})
        outputs = result.get_outputs()

        # Should have a TextOutputEvent
        assert len(outputs) >= 1

    @pytest.mark.asyncio
    async def test_execute_foreach_workflow(self):
        """Test executing a workflow with foreach."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: foreach-test
actions:
  - kind: Foreach
    source:
      - apple
      - banana
      - cherry
    itemName: fruit
    actions:
      - kind: AppendValue
        path: Local.fruits
        value: processed
""")

        _result = await workflow.run({})  # noqa: F841
        # The foreach should have processed 3 items
        # We can check this by examining the workflow outputs

    @pytest.mark.asyncio
    async def test_execute_if_workflow(self):
        """Test executing a workflow with conditional branching."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: if-test
actions:
  - kind: If
    condition: true
    then:
      - kind: SendActivity
        activity:
          text: Condition was true
    else:
      - kind: SendActivity
        activity:
          text: Condition was false
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        # Check for the expected text in WorkflowOutputEvent
        _text_outputs = [str(o) for o in outputs if isinstance(o, str) or hasattr(o, "data")]  # noqa: F841
        assert any("Condition was true" in str(o) for o in outputs)


class TestWorkflowFactoryAgentRegistration:
    """Tests for agent registration."""

    def test_register_agent(self):
        """Test registering an agent with the factory."""

        class MockAgent:
            name = "mock-agent"

        factory = WorkflowFactory()
        factory.register_agent("myAgent", MockAgent())

        assert "myAgent" in factory._agents

    def test_register_binding(self):
        """Test registering a binding with the factory."""

        def my_function(x):
            return x * 2

        factory = WorkflowFactory()
        factory.register_binding("double", my_function)

        assert "double" in factory._bindings
        assert factory._bindings["double"](5) == 10


class TestWorkflowFactoryFromPath:
    """Tests for loading workflows from file paths."""

    def test_nonexistent_file_raises(self, tmp_path):
        """Test that loading from a nonexistent file raises FileNotFoundError."""
        factory = WorkflowFactory()
        with pytest.raises(FileNotFoundError):
            factory.create_workflow_from_yaml_path(tmp_path / "nonexistent.yaml")

    def test_load_from_file(self, tmp_path):
        """Test loading a workflow from a file."""
        workflow_file = tmp_path / "Workflow.yaml"
        workflow_file.write_text("""
name: file-workflow
actions:
  - kind: SetValue
    path: Local.loaded
    value: true
""")

        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml_path(workflow_file)

        assert workflow is not None
        assert workflow.name == "file-workflow"


class TestDisplayNameMetadata:
    """Tests for displayName metadata support."""

    @pytest.mark.asyncio
    async def test_action_with_display_name(self):
        """Test executing an action with displayName metadata."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: display-name-test
actions:
  - kind: SetValue
    id: set_greeting
    displayName: Set the greeting message
    path: Local.greeting
    value: Hello
  - kind: SendActivity
    id: send_greeting
    displayName: Send greeting to user
    activity:
      text: Hello, world!
""")

        result = await workflow.run({"input": "test"})
        outputs = result.get_outputs()

        # Should execute successfully with displayName metadata
        assert len(outputs) >= 1

    def test_action_context_display_name_property(self):
        """Test that ActionContext provides displayName property."""
        from agent_framework_declarative._workflows._handlers import ActionContext
        from agent_framework_declarative._workflows._state import WorkflowState

        state = WorkflowState()
        ctx = ActionContext(
            state=state,
            action={
                "kind": "SetValue",
                "id": "test_action",
                "displayName": "Test Action Display Name",
                "path": "Local.value",
                "value": "test",
            },
            execute_actions=lambda a, s: None,
            agents={},
            bindings={},
        )

        assert ctx.action_id == "test_action"
        assert ctx.display_name == "Test Action Display Name"
        assert ctx.action_kind == "SetValue"

    def test_action_context_without_display_name(self):
        """Test ActionContext when displayName is not provided."""
        from agent_framework_declarative._workflows._handlers import ActionContext
        from agent_framework_declarative._workflows._state import WorkflowState

        state = WorkflowState()
        ctx = ActionContext(
            state=state,
            action={
                "kind": "SetValue",
                "path": "Local.value",
                "value": "test",
            },
            execute_actions=lambda a, s: None,
            agents={},
            bindings={},
        )

        assert ctx.action_id is None
        assert ctx.display_name is None
        assert ctx.action_kind == "SetValue"
