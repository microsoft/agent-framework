# Copyright (c) Microsoft. All rights reserved.

"""WorkflowFactory creates executable Workflow objects from YAML definitions.

This module provides the main entry point for declarative workflow support,
parsing YAML workflow definitions and creating Workflow objects that can be
executed using the core workflow runtime.

Each YAML action becomes a real Executor node in the workflow graph,
enabling checkpointing, visualization, and pause/resume capabilities.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from agent_framework import (
    AgentExecutor,
    AgentProtocol,
    CheckpointStorage,
    Workflow,
    get_logger,
)

from .._loader import AgentFactory
from ._declarative_builder import DeclarativeWorkflowBuilder

logger = get_logger("agent_framework.declarative.workflows")


class DeclarativeWorkflowError(Exception):
    """Exception raised for errors in declarative workflow processing."""

    pass


class WorkflowFactory:
    """Factory for creating executable Workflow objects from YAML definitions.

    WorkflowFactory parses declarative workflow YAML files and creates
    Workflow objects that can be executed using the core workflow runtime.
    Each YAML action becomes a real Executor node in the workflow graph,
    enabling checkpointing at action boundaries, visualization, and pause/resume.

    Examples:
        .. code-block:: python

            from agent_framework.declarative import WorkflowFactory

            # Basic usage: create workflow from YAML file
            factory = WorkflowFactory()
            workflow = factory.create_workflow_from_yaml_path("workflow.yaml")

            async for event in workflow.run_stream({"query": "Hello"}):
                print(event)

        .. code-block:: python

            from agent_framework.declarative import WorkflowFactory
            from agent_framework import FileCheckpointStorage

            # With checkpointing for pause/resume support
            storage = FileCheckpointStorage(path="./checkpoints")
            factory = WorkflowFactory(checkpoint_storage=storage)
            workflow = factory.create_workflow_from_yaml_path("workflow.yaml")

        .. code-block:: python

            from agent_framework.azure import AzureOpenAIChatClient
            from agent_framework.declarative import WorkflowFactory

            # Pre-register agents for InvokeAzureAgent actions
            chat_client = AzureOpenAIChatClient()
            agent = chat_client.as_agent(name="MyAgent", instructions="You are helpful.")

            factory = WorkflowFactory(agents={"MyAgent": agent})
            workflow = factory.create_workflow_from_yaml_path("workflow.yaml")
    """

    _agents: dict[str, AgentProtocol | AgentExecutor]

    def __init__(
        self,
        *,
        agent_factory: AgentFactory | None = None,
        agents: Mapping[str, AgentProtocol | AgentExecutor] | None = None,
        bindings: Mapping[str, Any] | None = None,
        env_file: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> None:
        """Initialize the workflow factory.

        Args:
            agent_factory: Optional AgentFactory for creating agents from inline YAML definitions.
            agents: Optional pre-created agents by name. These are looked up when processing
                InvokeAzureAgent actions in the workflow YAML.
            bindings: Optional function bindings for tool calls within workflow actions.
            env_file: Optional path to .env file for environment variables used in agent creation.
            checkpoint_storage: Optional checkpoint storage enabling pause/resume functionality.

        Examples:
            .. code-block:: python

                from agent_framework.declarative import WorkflowFactory

                # Minimal initialization
                factory = WorkflowFactory()

            .. code-block:: python

                from agent_framework.azure import AzureOpenAIChatClient
                from agent_framework.declarative import WorkflowFactory

                # With pre-registered agents
                client = AzureOpenAIChatClient()
                agents = {
                    "WriterAgent": client.as_agent(name="Writer", instructions="Write content."),
                    "ReviewerAgent": client.as_agent(name="Reviewer", instructions="Review content."),
                }
                factory = WorkflowFactory(agents=agents)

            .. code-block:: python

                from agent_framework import FileCheckpointStorage
                from agent_framework.declarative import WorkflowFactory

                # With checkpoint storage for pause/resume
                factory = WorkflowFactory(
                    checkpoint_storage=FileCheckpointStorage("./checkpoints"),
                    env_file=".env",
                )
        """
        self._agent_factory = agent_factory or AgentFactory(env_file_path=env_file)
        self._agents: dict[str, AgentProtocol | AgentExecutor] = dict(agents) if agents else {}
        self._bindings: dict[str, Any] = dict(bindings) if bindings else {}
        self._checkpoint_storage = checkpoint_storage

    def create_workflow_from_yaml_path(
        self,
        yaml_path: str | Path,
    ) -> Workflow:
        """Create a Workflow from a YAML file path.

        Args:
            yaml_path: Path to the YAML workflow definition file.

        Returns:
            An executable Workflow object with action nodes for each YAML action.

        Raises:
            DeclarativeWorkflowError: If the YAML is invalid or cannot be parsed.
            FileNotFoundError: If the YAML file doesn't exist.

        Examples:
            .. code-block:: python

                from agent_framework.declarative import WorkflowFactory

                factory = WorkflowFactory()
                workflow = factory.create_workflow_from_yaml_path("workflow.yaml")

                # Execute the workflow
                async for event in workflow.run_stream({"input": "Hello"}):
                    print(event)

            .. code-block:: python

                from pathlib import Path
                from agent_framework.declarative import WorkflowFactory

                # Using Path object
                workflow_path = Path(__file__).parent / "workflows" / "customer_support.yaml"
                factory = WorkflowFactory()
                workflow = factory.create_workflow_from_yaml_path(workflow_path)
        """
        if not isinstance(yaml_path, Path):
            yaml_path = Path(yaml_path)

        if not yaml_path.exists():
            raise FileNotFoundError(f"Workflow YAML file not found: {yaml_path}")

        with open(yaml_path) as f:
            yaml_content = f.read()

        return self.create_workflow_from_yaml(yaml_content, base_path=yaml_path.parent)

    def create_workflow_from_yaml(
        self,
        yaml_content: str,
        base_path: Path | None = None,
    ) -> Workflow:
        """Create a Workflow from a YAML string.

        Args:
            yaml_content: The YAML workflow definition as a string.
            base_path: Optional base path for resolving relative file references
                in agent definitions.

        Returns:
            An executable Workflow object with action nodes for each YAML action.

        Raises:
            DeclarativeWorkflowError: If the YAML is invalid or cannot be parsed.

        Examples:
            .. code-block:: python

                from agent_framework.declarative import WorkflowFactory

                yaml_content = '''
                kind: Workflow
                trigger:
                  kind: OnConversationStart
                  id: greeting_workflow
                  actions:
                    - kind: SetVariable
                      id: set_greeting
                      variable: Local.Greeting
                      value: "Hello, World!"
                    - kind: SendActivity
                      id: send_greeting
                      activity: =Local.Greeting
                '''

                factory = WorkflowFactory()
                workflow = factory.create_workflow_from_yaml(yaml_content)

            .. code-block:: python

                from pathlib import Path
                from agent_framework.declarative import WorkflowFactory

                # With base_path for resolving relative agent file references
                yaml_content = '''
                kind: Workflow
                agents:
                  MyAgent:
                    file: ./agents/my_agent.yaml
                trigger:
                  actions:
                    - kind: InvokeAzureAgent
                      agent:
                        name: MyAgent
                '''

                factory = WorkflowFactory()
                workflow = factory.create_workflow_from_yaml(
                    yaml_content,
                    base_path=Path("./workflows"),
                )
        """
        try:
            workflow_def = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise DeclarativeWorkflowError(f"Invalid YAML: {e}") from e

        return self.create_workflow_from_definition(workflow_def, base_path=base_path)

    def create_workflow_from_definition(
        self,
        workflow_def: dict[str, Any],
        base_path: Path | None = None,
    ) -> Workflow:
        """Create a Workflow from a parsed workflow definition dictionary.

        This is the lowest-level creation method, useful when you already have
        a parsed dictionary (e.g., from programmatic construction or custom parsing).

        Args:
            workflow_def: The parsed workflow definition dictionary containing
                'kind', 'trigger', 'actions', and optionally 'agents' keys.
            base_path: Optional base path for resolving relative file references
                in agent definitions.

        Returns:
            An executable Workflow object with action nodes for each YAML action.

        Raises:
            DeclarativeWorkflowError: If the definition is invalid or missing required fields.

        Examples:
            .. code-block:: python

                from agent_framework.declarative import WorkflowFactory

                # Programmatically construct a workflow definition
                workflow_def = {
                    "kind": "Workflow",
                    "name": "my_workflow",
                    "trigger": {
                        "kind": "OnConversationStart",
                        "id": "main_trigger",
                        "actions": [
                            {
                                "kind": "SetVariable",
                                "id": "init",
                                "variable": "Local.Counter",
                                "value": 0,
                            },
                            {
                                "kind": "SendActivity",
                                "id": "output",
                                "activity": "Counter initialized",
                            },
                        ],
                    },
                }

                factory = WorkflowFactory()
                workflow = factory.create_workflow_from_definition(workflow_def)
        """
        # Validate the workflow definition
        self._validate_workflow_def(workflow_def)

        # Extract workflow metadata
        # Support both "name" field and trigger.id for workflow name
        name: str = workflow_def.get("name", "")
        if not name:
            trigger: dict[str, Any] = workflow_def.get("trigger", {})
            trigger_id = trigger.get("id", "declarative_workflow")
            name = str(trigger_id) if trigger_id else "declarative_workflow"
        description = workflow_def.get("description")

        # Create agents from definitions
        agents: dict[str, AgentProtocol | AgentExecutor] = dict(self._agents)
        agent_defs = workflow_def.get("agents", {})

        for agent_name, agent_def in agent_defs.items():
            if agent_name in agents:
                # Already have this agent
                continue

            # Create agent using AgentFactory
            try:
                agent = self._create_agent_from_def(agent_def, base_path)
                agents[agent_name] = agent
                logger.debug(f"Created agent '{agent_name}' from definition")
            except Exception as e:
                logger.error(f"Failed to create agent '{agent_name}': {e}")
                raise DeclarativeWorkflowError(f"Failed to create agent '{agent_name}': {e}") from e

        return self._create_workflow(workflow_def, name, description, agents)

    def _create_workflow(
        self,
        workflow_def: dict[str, Any],
        name: str,
        description: str | None,
        agents: dict[str, AgentProtocol | AgentExecutor],
    ) -> Workflow:
        """Create workflow from definition.

        Each YAML action becomes a real Executor node in the workflow graph.
        This enables checkpointing at action boundaries.

        Args:
            workflow_def: The workflow definition
            name: Workflow name
            description: Workflow description
            agents: Registry of agent instances

        Returns:
            Workflow with individual action executors as nodes
        """
        # Normalize workflow definition to have actions at top level
        normalized_def = self._normalize_workflow_def(workflow_def)
        normalized_def["name"] = name
        if description:
            normalized_def["description"] = description

        # Build the graph-based workflow, passing agents for InvokeAzureAgent executors
        try:
            graph_builder = DeclarativeWorkflowBuilder(
                normalized_def,
                workflow_id=name,
                agents=agents,
                checkpoint_storage=self._checkpoint_storage,
            )
            workflow = graph_builder.build()
        except ValueError as e:
            raise DeclarativeWorkflowError(f"Failed to build graph-based workflow: {e}") from e

        # Store agents and bindings for reference (executors already have them)
        workflow._declarative_agents = agents  # type: ignore[attr-defined]
        workflow._declarative_bindings = self._bindings  # type: ignore[attr-defined]

        # Store input schema if defined in workflow definition
        # This allows DevUI to generate proper input forms
        if "inputs" in workflow_def:
            workflow.input_schema = self._convert_inputs_to_json_schema(workflow_def["inputs"])  # type: ignore[attr-defined]

        logger.debug(
            "Created graph-based workflow '%s' with %d executors",
            name,
            len(graph_builder._executors),  # type: ignore[reportPrivateUsage]
        )

        return workflow

    def _normalize_workflow_def(self, workflow_def: dict[str, Any]) -> dict[str, Any]:
        """Normalize workflow definition to have actions at top level.

        Args:
            workflow_def: The workflow definition

        Returns:
            Normalized definition with actions at top level
        """
        actions = self._get_actions_from_def(workflow_def)
        return {
            **workflow_def,
            "actions": actions,
        }

    def _validate_workflow_def(self, workflow_def: dict[str, Any]) -> None:
        """Validate a workflow definition.

        Args:
            workflow_def: The workflow definition to validate

        Raises:
            DeclarativeWorkflowError: If the definition is invalid
        """
        if not isinstance(workflow_def, dict):
            raise DeclarativeWorkflowError("Workflow definition must be a dictionary")

        # Handle both formats:
        # 1. Direct actions list: {"actions": [...]}
        # 2. Trigger-based: {"kind": "Workflow", "trigger": {"actions": [...]}}
        actions = self._get_actions_from_def(workflow_def)

        if not isinstance(actions, list):
            raise DeclarativeWorkflowError("Workflow 'actions' must be a list")

        # Validate each action has a kind
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                raise DeclarativeWorkflowError(f"Action at index {i} must be a dictionary")
            if "kind" not in action:
                raise DeclarativeWorkflowError(f"Action at index {i} missing 'kind' field")

    def _get_actions_from_def(self, workflow_def: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract actions from a workflow definition.

        Handles both direct actions format and trigger-based format.

        Args:
            workflow_def: The workflow definition

        Returns:
            List of action definitions

        Raises:
            DeclarativeWorkflowError: If no actions can be found
        """
        # Try direct actions first
        if "actions" in workflow_def:
            actions: list[dict[str, Any]] = workflow_def["actions"]
            return actions

        # Try trigger-based format
        if "trigger" in workflow_def:
            trigger = workflow_def["trigger"]
            if isinstance(trigger, dict) and "actions" in trigger:
                trigger_actions: list[dict[str, Any]] = list(trigger["actions"])  # type: ignore[arg-type]
                return trigger_actions

        raise DeclarativeWorkflowError("Workflow definition must have 'actions' field or 'trigger.actions' field")

    def _create_agent_from_def(
        self,
        agent_def: dict[str, Any],
        base_path: Path | None = None,
    ) -> Any:
        """Create an agent from a definition.

        Args:
            agent_def: The agent definition dictionary
            base_path: Optional base path for resolving relative file references

        Returns:
            An agent instance
        """
        # Check if it's a reference to an external file
        if "file" in agent_def:
            file_path = agent_def["file"]
            if base_path and not Path(file_path).is_absolute():
                file_path = base_path / file_path
            return self._agent_factory.create_agent_from_yaml_path(file_path)

        # Check if it's an inline agent definition
        if "kind" in agent_def:
            return self._agent_factory.create_agent_from_dict(agent_def)

        # Handle connection-based agent (like Azure AI agents)
        if "connection" in agent_def:
            # This would create a hosted agent client
            # For now, we'll need the user to provide pre-created agents
            raise DeclarativeWorkflowError(
                "Connection-based agents must be provided via the 'agents' parameter. "
                "Create the agent using the appropriate client and pass it to WorkflowFactory."
            )

        raise DeclarativeWorkflowError(
            f"Invalid agent definition. Expected 'file', 'kind', or 'connection': {agent_def}"
        )

    def register_agent(self, name: str, agent: AgentProtocol | AgentExecutor) -> "WorkflowFactory":
        """Register an agent instance with the factory for use in workflows.

        Registered agents are available to InvokeAzureAgent actions by name.
        This method supports fluent chaining.

        Args:
            name: The name to register the agent under. Must match the agent name
                referenced in InvokeAzureAgent actions.
            agent: The agent instance (typically a ChatAgent or similar).

        Returns:
            Self for method chaining.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureOpenAIChatClient
                from agent_framework.declarative import WorkflowFactory

                client = AzureOpenAIChatClient()

                # Method chaining to register multiple agents
                factory = (
                    WorkflowFactory()
                    .register_agent(
                        "Writer",
                        client.as_agent(
                            name="Writer",
                            instructions="Write content.",
                        ),
                    )
                    .register_agent(
                        "Reviewer",
                        client.as_agent(
                            name="Reviewer",
                            instructions="Review content.",
                        ),
                    )
                )

                workflow = factory.create_workflow_from_yaml_path("workflow.yaml")
        """
        self._agents[name] = agent
        return self

    def register_binding(self, name: str, func: Any) -> "WorkflowFactory":
        """Register a function binding with the factory for use in workflow actions.

        Bindings allow workflow actions to invoke Python functions by name.
        This method supports fluent chaining.

        Args:
            name: The name to register the function under.
            func: The function to bind.

        Returns:
            Self for method chaining.

        Examples:
            .. code-block:: python

                from agent_framework.declarative import WorkflowFactory


                def get_weather(location: str) -> str:
                    return f"Weather in {location}: Sunny, 72F"


                def send_email(to: str, subject: str, body: str) -> bool:
                    # Send email logic
                    return True


                # Register functions for use in workflow
                factory = (
                    WorkflowFactory()
                    .register_binding("get_weather", get_weather)
                    .register_binding("send_email", send_email)
                )

                workflow = factory.create_workflow_from_yaml_path("workflow.yaml")
        """
        self._bindings[name] = func
        return self

    def _convert_inputs_to_json_schema(self, inputs_def: dict[str, Any]) -> dict[str, Any]:
        """Convert a declarative inputs definition to JSON Schema.

        The inputs definition uses a simplified format:
            inputs:
              age:
                type: integer
                description: The user's age
              name:
                type: string

        This is converted to standard JSON Schema format.

        Args:
            inputs_def: The inputs definition from the workflow YAML

        Returns:
            A JSON Schema object
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        for field_name, field_def in inputs_def.items():
            if isinstance(field_def, dict):
                # Field has type and possibly other attributes
                prop: dict[str, Any] = {}
                field_def_dict: dict[str, Any] = cast(dict[str, Any], field_def)
                field_type: str = str(field_def_dict.get("type", "string"))

                # Map declarative types to JSON Schema types
                type_mapping: dict[str, str] = {
                    "string": "string",
                    "str": "string",
                    "integer": "integer",
                    "int": "integer",
                    "number": "number",
                    "float": "number",
                    "boolean": "boolean",
                    "bool": "boolean",
                    "array": "array",
                    "list": "array",
                    "object": "object",
                    "dict": "object",
                }
                prop["type"] = type_mapping.get(field_type, field_type)

                # Copy other attributes
                if "description" in field_def_dict:
                    prop["description"] = field_def_dict["description"]
                if "default" in field_def_dict:
                    prop["default"] = field_def_dict["default"]
                if "enum" in field_def_dict:
                    prop["enum"] = field_def_dict["enum"]

                # Check if required (default: true unless explicitly false)
                if field_def_dict.get("required", True):
                    required.append(field_name)

                properties[field_name] = prop
            else:
                # Simple type definition (e.g., "age: integer")
                type_mapping_simple: dict[str, str] = {
                    "string": "string",
                    "str": "string",
                    "integer": "integer",
                    "int": "integer",
                    "number": "number",
                    "float": "number",
                    "boolean": "boolean",
                    "bool": "boolean",
                }
                properties[field_name] = {"type": type_mapping_simple.get(str(field_def), "string")}
                required.append(field_name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return schema
