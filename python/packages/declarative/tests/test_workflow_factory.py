# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for WorkflowFactory."""

import pytest

from agent_framework_declarative._workflows._factory import (
    DeclarativeWorkflowError,
    WorkflowFactory,
)

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

_requires_powerfx = pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")


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


@_requires_powerfx
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

        # Check for the expected text in output event (type='output')
        _text_outputs = [str(o) for o in outputs if isinstance(o, str) or hasattr(o, "data")]  # noqa: F841
        assert any("Condition was true" in str(o) for o in outputs)

    @pytest.mark.asyncio
    async def test_entry_join_executor_initializes_workflow_inputs(self):
        """Regression test for #3948: Entry JoinExecutor must initialize Workflow.Inputs.

        When workflow.run() is called with a dict input, the Entry node (JoinExecutor
        with kind: 'Entry') must call _ensure_state_initialized so that Workflow.Inputs
        is populated. Without this, expressions like =inputs.age resolve to blank and
        conditions like =Local.age < 13 always evaluate as true (blank treated as 0).
        """
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: entry-inputs-test
actions:
  - kind: SetValue
    id: get_age
    path: Local.age
    value: =inputs.age
  - kind: If
    id: check_age
    condition: =Local.age < 13
    then:
      - kind: SendActivity
        activity:
          text: child
    else:
      - kind: SendActivity
        activity:
          text: adult
""")

        # age=8 -> child branch
        result_child = await workflow.run({"age": 8})
        outputs_child = result_child.get_outputs()
        assert any("child" in str(o) for o in outputs_child), f"Expected 'child' for age=8 but got: {outputs_child}"
        assert not any("adult" in str(o) for o in outputs_child), (
            f"Did not expect 'adult' for age=8 but got: {outputs_child}"
        )

        # age=25 -> adult branch (bug: blank treated as 0 made this always go to child)
        result_adult = await workflow.run({"age": 25})
        outputs_adult = result_adult.get_outputs()
        assert any("adult" in str(o) for o in outputs_adult), f"Expected 'adult' for age=25 but got: {outputs_adult}"
        assert not any("child" in str(o) for o in outputs_adult), (
            f"Did not expect 'child' for age=25 but got: {outputs_adult}"
        )

    @pytest.mark.asyncio
    async def test_entry_join_executor_initializes_workflow_inputs_string(self):
        """Regression test for #3948: Entry JoinExecutor must initialize Workflow.Inputs for string input.

        When workflow.run() is called with a string input, Workflow.Inputs.input and
        System.LastMessage.Text should be set correctly.
        """
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: entry-string-inputs-test
actions:
  - kind: SetValue
    path: Local.msg
    value: =inputs.input
  - kind: SendActivity
    activity:
      text: =Local.msg
""")

        result = await workflow.run("hello-world")
        outputs = result.get_outputs()
        assert any("hello-world" in str(o) for o in outputs), f"Expected 'hello-world' in outputs but got: {outputs}"

    async def test_as_agent_round_trip_with_last_message_text(self):
        """Regression test: a declarative workflow built via WorkflowFactory must be
        consumable as an AIAgent via Workflow.as_agent().

        Specifically, the declarative start executor must accept list[Message]
        (the input passed by WorkflowAgent) and populate System.LastMessageText
        so =System.LastMessageText is resolvable in the YAML.
        """
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: as-agent-roundtrip-test
actions:
  - kind: SetVariable
    variable: Local.echo
    value: =System.LastMessageText
  - kind: SendActivity
    activity:
      text: =Local.echo
""")

        agent = workflow.as_agent(name="echo-agent")
        response = await agent.run("Hello there")

        assert "Hello there" in response.text, (
            f"Expected 'Hello there' in agent response text but got: {response.text!r}"
        )

    async def test_as_agent_continuation_preserves_prior_state(self):
        """Regression test for the ``is_continuation`` branch in
        ``DeclarativeWorkflowExecutor._ensure_state_initialized``.

        Verifies, end-to-end via ``Workflow.as_agent()``:
          * Turn 1 initializes the declarative state via ``state.initialize``.
          * Turn 2 takes the *continuation* branch (skips ``state.initialize``),
            so any non-Inputs/non-System state stamped on turn 1 survives.
          * Turn 2 still refreshes ``Inputs.input`` and
            ``System.LastMessage*`` to the new user message.

        Without state preservation, ``Workflow.run`` would clear shared state
        on entry and ``state.initialize`` would re-run on every turn,
        wiping the marker we stamped between calls.
        """
        from agent_framework_declarative._workflows._declarative_base import DECLARATIVE_STATE_KEY

        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: as-agent-continuation-test
actions:
  - kind: SendActivity
    activity:
      text: =System.LastMessageText
""")

        agent = workflow.as_agent(name="continuation-agent")

        first = await agent.run("turn-1-msg")
        assert first.text == "turn-1-msg", f"Expected turn-1 echo 'turn-1-msg', got: {first.text!r}"

        # Stamp a marker into the declarative state between turns. The
        # continuation branch must preserve it; a state-clearing run would
        # wipe ``DECLARATIVE_STATE_KEY`` and force re-initialization.
        state_data = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert isinstance(state_data, dict), "Expected declarative state to be initialized after turn 1"
        state_data["Local"] = {"persisted_marker": "kept-from-turn-1"}
        workflow._state.set(DECLARATIVE_STATE_KEY, state_data)
        workflow._state.commit()

        second = await agent.run("turn-2-msg")
        assert second.text == "turn-2-msg", (
            f"Expected System.LastMessageText to refresh to 'turn-2-msg', got: {second.text!r}"
        )

        # The continuation branch in ``_ensure_state_initialized`` must:
        # 1. preserve the cross-turn marker we stamped above
        # 2. refresh Inputs.input and System.LastMessage* to the new turn
        post_state = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert isinstance(post_state, dict), "declarative state vanished between turns"
        local = post_state.get("Local", {})
        assert local.get("persisted_marker") == "kept-from-turn-1", (
            f"Cross-turn marker was wiped (state was reset). post_state Local={local!r}"
        )
        assert post_state.get("Inputs", {}).get("input") == "turn-2-msg", (
            f"Inputs.input not refreshed on turn 2: {post_state.get('Inputs')!r}"
        )
        assert post_state.get("System", {}).get("LastMessageText") == "turn-2-msg", (
            f"System.LastMessageText not refreshed on turn 2: {post_state.get('System')!r}"
        )


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


@_requires_powerfx
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


class TestWorkflowFactoryToolRegistration:
    """Tests for tool registration."""

    def test_register_tool_basic(self):
        """Test registering a tool."""

        def my_tool(x: int) -> int:
            return x * 2

        factory = WorkflowFactory()
        result = factory.register_tool("my_tool", my_tool)

        # Should return self for fluent chaining
        assert result is factory
        assert "my_tool" in factory._tools
        assert factory._tools["my_tool"](5) == 10

    def test_register_multiple_tools(self):
        """Test registering multiple tools with fluent chaining."""

        def add(a: int, b: int) -> int:
            return a + b

        def multiply(a: int, b: int) -> int:
            return a * b

        factory = WorkflowFactory().register_tool("add", add).register_tool("multiply", multiply)

        assert "add" in factory._tools
        assert "multiply" in factory._tools
        assert factory._tools["add"](2, 3) == 5
        assert factory._tools["multiply"](2, 3) == 6

    def test_register_tool_non_callable_raises(self):
        """Test that register_tool raises TypeError for non-callable."""
        factory = WorkflowFactory()

        with pytest.raises(TypeError, match="Expected a callable for tool"):
            factory.register_tool("bad_tool", "not_a_function")

    def test_register_binding_non_callable_raises(self):
        """Test that register_binding raises TypeError for non-callable."""
        factory = WorkflowFactory()

        with pytest.raises(TypeError, match="Expected a callable for binding"):
            factory.register_binding("bad_binding", 42)


class TestWorkflowFactoryEdgeCases:
    """Tests for edge cases in workflow factory."""

    def test_empty_actions_list(self):
        """Test workflow with empty actions list."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="actions"):
            factory.create_workflow_from_yaml("""
name: empty-actions
actions: []
""")

    def test_unknown_action_kind(self):
        """Test workflow with unknown action kind."""
        factory = WorkflowFactory()
        with pytest.raises((DeclarativeWorkflowError, ValueError)):
            factory.create_workflow_from_yaml("""
name: unknown-action
actions:
  - kind: UnknownActionType
    value: test
""")

    def test_workflow_with_description(self):
        """Test workflow with description field."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: described-workflow
description: This is a test workflow
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        assert workflow is not None
        assert workflow.name == "described-workflow"

    @_requires_powerfx
    @pytest.mark.asyncio
    async def test_workflow_with_expression_value(self):
        """Test workflow with expression-based value."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: expression-test
actions:
  - kind: SetValue
    path: Local.x
    value: 5
  - kind: SetValue
    path: Local.y
    value: =Local.x
  - kind: SendActivity
    activity:
      text: =Local.y
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        assert any("5" in str(o) for o in outputs)

    @_requires_powerfx
    @pytest.mark.asyncio
    async def test_workflow_with_nested_if(self):
        """Test workflow with nested If statements."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: nested-if-test
actions:
  - kind: SetValue
    path: Local.level
    value: 2
  - kind: If
    condition: true
    then:
      - kind: If
        condition: true
        then:
          - kind: SendActivity
            activity:
              text: Nested condition passed
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        assert any("Nested condition passed" in str(o) for o in outputs)

    def test_load_from_string_path(self, tmp_path):
        """Test loading a workflow from a string file path."""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text("""
name: string-path-workflow
actions:
  - kind: SetValue
    path: Local.loaded
    value: true
""")

        factory = WorkflowFactory()
        # Pass as string instead of Path object
        workflow = factory.create_workflow_from_yaml_path(str(workflow_file))

        assert workflow is not None
        assert workflow.name == "string-path-workflow"


@_requires_powerfx
class TestWorkflowFactorySwitch:
    """Tests for Switch/Case action."""

    @pytest.mark.asyncio
    async def test_switch_with_matching_case(self):
        """Test Switch with a matching case."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: switch-test
actions:
  - kind: SetValue
    path: Local.color
    value: red
  - kind: Switch
    value: =Local.color
    cases:
      - match: red
        actions:
          - kind: SendActivity
            activity:
              text: Color is red
      - match: blue
        actions:
          - kind: SendActivity
            activity:
              text: Color is blue
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        assert any("Color is red" in str(o) for o in outputs)

    @pytest.mark.asyncio
    async def test_switch_with_default(self):
        """Test Switch falling through to default."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: switch-default-test
actions:
  - kind: SetValue
    path: Local.color
    value: green
  - kind: Switch
    value: =Local.color
    cases:
      - match: red
        actions:
          - kind: SendActivity
            activity:
              text: Red
      - match: blue
        actions:
          - kind: SendActivity
            activity:
              text: Blue
    default:
      - kind: SendActivity
        activity:
          text: Unknown color
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        assert any("Unknown color" in str(o) for o in outputs)


@_requires_powerfx
class TestWorkflowFactoryMultipleActionTypes:
    """Tests for workflows with multiple action types."""

    @pytest.mark.asyncio
    async def test_set_multiple_variables(self):
        """Test SetMultipleVariables action."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: multi-set-test
actions:
  - kind: SetMultipleVariables
    variables:
      - path: Local.a
        value: 1
      - path: Local.b
        value: 2
      - path: Local.c
        value: 3
  - kind: SendActivity
    activity:
      text: Done
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        assert any("Done" in str(o) for o in outputs)

    @pytest.mark.asyncio
    async def test_append_value(self):
        """Test AppendValue action."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: append-test
actions:
  - kind: SetValue
    path: Local.list
    value: []
  - kind: AppendValue
    path: Local.list
    value: first
  - kind: AppendValue
    path: Local.list
    value: second
  - kind: SendActivity
    activity:
      text: Done
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        assert any("Done" in str(o) for o in outputs)

    @pytest.mark.asyncio
    async def test_emit_event(self):
        """Test EmitEvent action."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: emit-event-test
actions:
  - kind: EmitEvent
    event:
      name: test_event
      data:
        message: Hello
  - kind: SendActivity
    activity:
      text: Event emitted
""")

        result = await workflow.run({})
        outputs = result.get_outputs()

        # Workflow should complete
        assert any("Event emitted" in str(o) for o in outputs)


class TestWorkflowFactoryYamlErrors:
    """Tests for YAML parsing error handling."""

    def test_invalid_yaml_raises(self):
        """Test that invalid YAML raises DeclarativeWorkflowError."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="Invalid YAML"):
            factory.create_workflow_from_yaml("""
name: broken-yaml
actions:
  - kind: SetValue
    path: Local.x
    value: [unclosed bracket
""")

    def test_non_dict_workflow_raises(self):
        """Test that non-dict workflow definition raises error."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="must be a dictionary"):
            factory.create_workflow_from_yaml("- just a list item")


class TestWorkflowFactoryTriggerFormat:
    """Tests for trigger-based workflow format."""

    def test_trigger_based_workflow(self):
        """Test workflow with trigger-based format."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
kind: Workflow
trigger:
  kind: OnConversationStart
  id: my_trigger
  actions:
    - kind: SetValue
      path: Local.x
      value: 1
""")

        assert workflow is not None
        assert workflow.name == "my_trigger"

    def test_trigger_workflow_without_id(self):
        """Test trigger workflow without id uses default name."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
kind: Workflow
trigger:
  kind: OnConversationStart
  actions:
    - kind: SetValue
      path: Local.x
      value: 1
""")

        assert workflow is not None
        assert workflow.name == "declarative_workflow"


class TestWorkflowFactoryAgentCreation:
    """Tests for agent creation from definitions."""

    def test_agent_creation_with_file_reference(self, tmp_path):
        """Test creating agent from file reference."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        # Create a minimal agent YAML file (using Prompt kind)
        agent_file = tmp_path / "test_agent.yaml"
        agent_file.write_text("""
kind: Prompt
name: TestAgent
description: A test agent
instructions: You are a test agent.
""")

        # Create a mock client and agent factory
        mock_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_client.create_agent.return_value = mock_agent

        agent_factory = AgentFactory(client=mock_client)

        # Create workflow that references the agent
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(f"""
kind: Workflow
agents:
  TestAgent:
    file: {agent_file.name}
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        factory = WorkflowFactory(agent_factory=agent_factory)
        workflow = factory.create_workflow_from_yaml_path(workflow_file)

        assert workflow is not None
        assert "TestAgent" in workflow._declarative_agents

    def test_agent_connection_definition_raises(self):
        """Test that connection-based agent definition raises error."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="Connection-based agents"):
            factory.create_workflow_from_yaml("""
kind: Workflow
agents:
  MyAgent:
    connection: azure-connection
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

    def test_invalid_agent_definition_raises(self):
        """Test that invalid agent definition raises error."""
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError, match="Invalid agent definition"):
            factory.create_workflow_from_yaml("""
kind: Workflow
agents:
  MyAgent:
    unknown_field: value
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

    def test_preregistered_agent_not_overwritten(self):
        """Test that pre-registered agents are not overwritten by definitions."""

        class MockAgent:
            name = "PreregisteredAgent"

        factory = WorkflowFactory(agents={"TestAgent": MockAgent()})
        workflow = factory.create_workflow_from_yaml("""
kind: Workflow
agents:
  TestAgent:
    kind: Agent
    name: OverrideAttempt
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        assert workflow._declarative_agents["TestAgent"].name == "PreregisteredAgent"


class TestWorkflowFactoryInputSchema:
    """Tests for input schema conversion."""

    def test_inputs_to_json_schema_basic(self):
        """Test basic input schema conversion."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: input-schema-test
inputs:
  name:
    type: string
    description: The user's name
  age:
    type: integer
    description: The user's age
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        schema = workflow.input_schema
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["age"]["type"] == "integer"
        assert "name" in schema["required"]
        assert "age" in schema["required"]

    def test_inputs_schema_with_optional_field(self):
        """Test input schema with optional field."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: optional-input-test
inputs:
  required_field:
    type: string
    required: true
  optional_field:
    type: string
    required: false
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        schema = workflow.input_schema
        assert "required_field" in schema["required"]
        assert "optional_field" not in schema["required"]

    def test_inputs_schema_with_default_value(self):
        """Test input schema with default value."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: default-input-test
inputs:
  greeting:
    type: string
    default: Hello
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        schema = workflow.input_schema
        assert schema["properties"]["greeting"]["default"] == "Hello"

    def test_inputs_schema_with_enum(self):
        """Test input schema with enum values."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: enum-input-test
inputs:
  color:
    type: string
    enum:
      - red
      - green
      - blue
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        schema = workflow.input_schema
        assert schema["properties"]["color"]["enum"] == ["red", "green", "blue"]

    def test_inputs_schema_type_mappings(self):
        """Test various type mappings in input schema."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: type-mapping-test
inputs:
  str_field:
    type: str
  int_field:
    type: int
  float_field:
    type: float
  bool_field:
    type: bool
  list_field:
    type: list
  dict_field:
    type: dict
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        schema = workflow.input_schema
        assert schema["properties"]["str_field"]["type"] == "string"
        assert schema["properties"]["int_field"]["type"] == "integer"
        assert schema["properties"]["float_field"]["type"] == "number"
        assert schema["properties"]["bool_field"]["type"] == "boolean"
        assert schema["properties"]["list_field"]["type"] == "array"
        assert schema["properties"]["dict_field"]["type"] == "object"

    def test_inputs_schema_simple_format(self):
        """Test simple input format (field: type)."""
        factory = WorkflowFactory()
        workflow = factory.create_workflow_from_yaml("""
name: simple-input-test
inputs:
  name: string
  count: integer
actions:
  - kind: SetValue
    path: Local.x
    value: 1
""")

        schema = workflow.input_schema
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert "name" in schema["required"]
        assert "count" in schema["required"]


class TestWorkflowFactoryChaining:
    """Tests for fluent method chaining."""

    def test_fluent_agent_registration(self):
        """Test fluent agent registration."""

        class MockAgent1:
            name = "Agent1"

        class MockAgent2:
            name = "Agent2"

        factory = WorkflowFactory().register_agent("agent1", MockAgent1()).register_agent("agent2", MockAgent2())

        assert "agent1" in factory._agents
        assert "agent2" in factory._agents

    def test_fluent_binding_registration(self):
        """Test fluent binding registration."""

        def func1():
            return 1

        def func2():
            return 2

        factory = WorkflowFactory().register_binding("func1", func1).register_binding("func2", func2)

        assert "func1" in factory._bindings
        assert "func2" in factory._bindings

    def test_fluent_mixed_registration(self):
        """Test mixed fluent registration."""

        class MockAgent:
            name = "Agent"

        def my_tool():
            return "tool"

        def my_binding():
            return "binding"

        factory = (
            WorkflowFactory()
            .register_agent("agent", MockAgent())
            .register_tool("tool", my_tool)
            .register_binding("binding", my_binding)
        )

        assert "agent" in factory._agents
        assert "tool" in factory._tools
        assert "binding" in factory._bindings
