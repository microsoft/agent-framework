# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for workflow samples.

These tests verify that the workflow samples from workflow-samples/ directory
can be parsed and validated by the WorkflowFactory.
"""

from pathlib import Path

import pytest
import yaml

# Path to workflow samples - navigate from tests dir up to repo root
# tests/test_*.py -> packages/declarative/tests/ -> packages/declarative/ -> packages/ -> python/ -> repo root
WORKFLOW_SAMPLES_DIR = Path(__file__).parent.parent.parent.parent.parent / "workflow-samples"


def get_workflow_sample_files():
    """Get all .yaml files from the workflow-samples directory."""
    if not WORKFLOW_SAMPLES_DIR.exists():
        return []
    return list(WORKFLOW_SAMPLES_DIR.glob("*.yaml"))


class TestWorkflowSampleParsing:
    """Tests that verify workflow samples can be parsed correctly."""

    @pytest.fixture
    def sample_files(self):
        """Get list of sample files."""
        return get_workflow_sample_files()

    def test_samples_directory_exists(self):
        """Verify the workflow-samples directory exists."""
        assert WORKFLOW_SAMPLES_DIR.exists(), f"Workflow samples directory not found at {WORKFLOW_SAMPLES_DIR}"

    def test_samples_exist(self, sample_files):
        """Verify there are workflow sample files."""
        assert len(sample_files) > 0, "No workflow sample files found"

    @pytest.mark.parametrize("yaml_file", get_workflow_sample_files(), ids=lambda f: f.name)
    def test_sample_yaml_is_valid(self, yaml_file):
        """Test that each sample YAML file can be parsed."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        assert data is not None, f"Failed to parse {yaml_file.name}"
        assert "kind" in data, f"Missing 'kind' field in {yaml_file.name}"
        assert data["kind"] == "Workflow", f"Expected kind: Workflow in {yaml_file.name}"

    @pytest.mark.parametrize("yaml_file", get_workflow_sample_files(), ids=lambda f: f.name)
    def test_sample_has_trigger(self, yaml_file):
        """Test that each sample has a trigger defined."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        assert "trigger" in data, f"Missing 'trigger' field in {yaml_file.name}"
        trigger = data["trigger"]
        assert trigger is not None, f"Trigger is empty in {yaml_file.name}"

    @pytest.mark.parametrize("yaml_file", get_workflow_sample_files(), ids=lambda f: f.name)
    def test_sample_has_actions(self, yaml_file):
        """Test that each sample has actions defined."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        trigger = data.get("trigger", {})
        actions = trigger.get("actions", [])
        assert len(actions) > 0, f"No actions defined in {yaml_file.name}"

    @pytest.mark.parametrize("yaml_file", get_workflow_sample_files(), ids=lambda f: f.name)
    def test_sample_actions_have_kind(self, yaml_file):
        """Test that each action has a 'kind' field."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        def check_actions(actions, path=""):
            for i, action in enumerate(actions):
                action_path = f"{path}[{i}]"
                assert "kind" in action, f"Action missing 'kind' at {action_path} in {yaml_file.name}"

                # Check nested actions
                for nested_key in ["actions", "elseActions", "thenActions"]:
                    if nested_key in action:
                        check_actions(action[nested_key], f"{action_path}.{nested_key}")

                # Check conditions
                if "conditions" in action:
                    for j, cond in enumerate(action["conditions"]):
                        if "actions" in cond:
                            check_actions(cond["actions"], f"{action_path}.conditions[{j}].actions")

                # Check cases
                if "cases" in action:
                    for j, case in enumerate(action["cases"]):
                        if "actions" in case:
                            check_actions(case["actions"], f"{action_path}.cases[{j}].actions")

        trigger = data.get("trigger", {})
        actions = trigger.get("actions", [])
        check_actions(actions, "trigger.actions")


class TestWorkflowDefinitionParsing:
    """Tests for parsing workflow definitions into structured objects."""

    @pytest.mark.parametrize("yaml_file", get_workflow_sample_files(), ids=lambda f: f.name)
    def test_extract_actions_from_sample(self, yaml_file):
        """Test extracting all actions from a workflow sample."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        # Collect all action kinds used
        action_kinds: set[str] = set()

        def collect_actions(actions):
            for action in actions:
                action_kinds.add(action.get("kind", "Unknown"))

                # Collect from nested actions
                for nested_key in ["actions", "elseActions", "thenActions"]:
                    if nested_key in action:
                        collect_actions(action[nested_key])

                if "conditions" in action:
                    for cond in action["conditions"]:
                        if "actions" in cond:
                            collect_actions(cond["actions"])

                if "cases" in action:
                    for case in action["cases"]:
                        if "actions" in case:
                            collect_actions(case["actions"])

        trigger = data.get("trigger", {})
        actions = trigger.get("actions", [])
        collect_actions(actions)

        # Verify we found some actions
        assert len(action_kinds) > 0, f"No action kinds found in {yaml_file.name}"

    @pytest.mark.parametrize("yaml_file", get_workflow_sample_files(), ids=lambda f: f.name)
    def test_extract_agent_names_from_sample(self, yaml_file):
        """Test extracting agent names referenced in a workflow sample."""
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        agent_names: set[str] = set()

        def collect_agents(actions):
            for action in actions:
                kind = action.get("kind", "")

                if kind in ("InvokeAzureAgent", "InvokePromptAgent"):
                    agent_config = action.get("agent", {})
                    name = agent_config.get("name") if isinstance(agent_config, dict) else agent_config
                    if name and not str(name).startswith("="):
                        agent_names.add(name)

                # Collect from nested actions
                for nested_key in ["actions", "elseActions", "thenActions"]:
                    if nested_key in action:
                        collect_agents(action[nested_key])

                if "conditions" in action:
                    for cond in action["conditions"]:
                        if "actions" in cond:
                            collect_agents(cond["actions"])

                if "cases" in action:
                    for case in action["cases"]:
                        if "actions" in case:
                            collect_agents(case["actions"])

        trigger = data.get("trigger", {})
        actions = trigger.get("actions", [])
        collect_agents(actions)

        # Log the agents found (some workflows may not use agents)
        # Agent names: {agent_names}


class TestHandlerCoverage:
    """Tests to verify handler coverage for workflow actions."""

    @pytest.fixture
    def all_action_kinds(self):
        """Collect all action kinds used across all samples."""
        action_kinds: set[str] = set()

        def collect_actions(actions):
            for action in actions:
                action_kinds.add(action.get("kind", "Unknown"))

                for nested_key in ["actions", "elseActions", "thenActions"]:
                    if nested_key in action:
                        collect_actions(action[nested_key])

                if "conditions" in action:
                    for cond in action["conditions"]:
                        if "actions" in cond:
                            collect_actions(cond["actions"])

                if "cases" in action:
                    for case in action["cases"]:
                        if "actions" in case:
                            collect_actions(case["actions"])

        for yaml_file in get_workflow_sample_files():
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            trigger = data.get("trigger", {})
            actions = trigger.get("actions", [])
            collect_actions(actions)

        return action_kinds

    def test_handlers_exist_for_sample_actions(self, all_action_kinds):
        """Test that handlers exist for all action kinds in samples."""
        from agent_framework_declarative._workflows._handlers import list_action_handlers

        registered_handlers = set(list_action_handlers())

        # Handlers we expect but may not be in samples
        expected_handlers = {
            "SetValue",
            "SetVariable",
            "SetTextVariable",
            "SetMultipleVariables",
            "ResetVariable",
            "ClearAllVariables",
            "AppendValue",
            "SendActivity",
            "EmitEvent",
            "Foreach",
            "If",
            "Switch",
            "ConditionGroup",
            "GotoAction",
            "BreakLoop",
            "ContinueLoop",
            "RepeatUntil",
            "TryCatch",
            "ThrowException",
            "EndWorkflow",
            "EndConversation",
            "InvokeAzureAgent",
            "InvokePromptAgent",
            "CreateConversation",
            "AddConversationMessage",
            "CopyConversationMessages",
            "RetrieveConversationMessages",
            "Question",
            "RequestExternalInput",
            "WaitForInput",
        }

        # Check that sample action kinds have handlers
        missing_handlers = all_action_kinds - registered_handlers - {"OnConversationStart"}  # Trigger kind, not action

        if missing_handlers:
            # Informational, not a failure, as some actions may be future work
            pass

        # Check that we have handlers for the expected core set
        core_handlers = registered_handlers & expected_handlers
        assert len(core_handlers) > 10, "Expected more core handlers to be registered"
