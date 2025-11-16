# Copyright (c) Microsoft. All rights reserved.

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_framework_declarative._models import (
    AgentDefinition,
    AgentManifest,
    AnonymousConnection,
    ApiKeyConnection,
    ArrayProperty,
    CodeInterpreterTool,
    Connection,
    CustomTool,
    FileSearchTool,
    FunctionTool,
    McpServerApprovalMode,
    McpServerToolAlwaysRequireApprovalMode,
    McpServerToolNeverRequireApprovalMode,
    McpServerToolSpecifyApprovalMode,
    McpTool,
    ModelResource,
    ObjectProperty,
    OpenApiTool,
    PromptAgent,
    Property,
    PropertySchema,
    ReferenceConnection,
    RemoteConnection,
    Resource,
    ToolResource,
    WebSearchTool,
    agent_schema_dispatch,
)

pytestmark = pytest.mark.skipif(sys.version_info >= (3, 14), reason="Skipping on Python 3.14+")


@pytest.mark.parametrize(
    "yaml_content,expected_type,expected_attributes",
    [
        # Agent Manifest (no kind field)
        (
            """
name: my-manifest
description: A test manifest
""",
            AgentManifest,
            {"name": "my-manifest", "description": "A test manifest"},
        ),
        # PromptAgent
        (
            """
kind: Prompt
name: assistant
description: A helpful assistant
model:
  id: gpt-4
""",
            PromptAgent,
            {"name": "assistant", "description": "A helpful assistant"},
        ),
        # AgentDefinition
        (
            """
kind: Agent
name: base-agent
description: A base agent
""",
            AgentDefinition,
            {"name": "base-agent", "description": "A base agent"},
        ),
        # ModelResource
        (
            """
kind: Model
name: my-model
id: gpt-4
""",
            ModelResource,
            {"name": "my-model", "id": "gpt-4"},
        ),
        # ToolResource
        (
            """
kind: Tool
name: my-tool
id: search-tool
""",
            ToolResource,
            {"name": "my-tool", "id": "search-tool"},
        ),
        # Resource (base)
        (
            """
kind: Resource
name: generic-resource
""",
            Resource,
            {"name": "generic-resource"},
        ),
        # FunctionTool
        (
            """
kind: function
name: get_weather
description: Get the weather
""",
            FunctionTool,
            {"name": "get_weather", "description": "Get the weather"},
        ),
        # CustomTool
        (
            """
kind: custom
name: custom_tool
description: A custom tool
""",
            CustomTool,
            {"name": "custom_tool", "description": "A custom tool"},
        ),
        # WebSearchTool
        (
            """
kind: web_search
name: search
description: Search the web
""",
            WebSearchTool,
            {"name": "search", "description": "Search the web"},
        ),
        # FileSearchTool
        (
            """
kind: file_search
name: file_search
description: Search files
""",
            FileSearchTool,
            {"name": "file_search", "description": "Search files"},
        ),
        # McpTool
        (
            """
kind: mcp
name: mcp_tool
description: An MCP tool
serverName: my-server
""",
            McpTool,
            {"name": "mcp_tool", "serverName": "my-server"},
        ),
        # OpenApiTool
        (
            """
kind: openapi
name: api_tool
description: An OpenAPI tool
specification: https://api.example.com/openapi.json
""",
            OpenApiTool,
            {"name": "api_tool", "specification": "https://api.example.com/openapi.json"},
        ),
        # CodeInterpreterTool
        (
            """
kind: code_interpreter
name: code_tool
description: A code interpreter tool
""",
            CodeInterpreterTool,
            {"name": "code_tool", "description": "A code interpreter tool"},
        ),
        # ReferenceConnection
        (
            """
kind: reference
name: my-connection
target: target-connection
""",
            ReferenceConnection,
            {"name": "my-connection", "target": "target-connection"},
        ),
        # RemoteConnection
        (
            """
kind: remote
endpoint: https://api.example.com
""",
            RemoteConnection,
            {"endpoint": "https://api.example.com"},
        ),
        # ApiKeyConnection
        (
            """
kind: key
apiKey: secret-key
endpoint: https://api.example.com
""",
            ApiKeyConnection,
            {"apiKey": "secret-key", "endpoint": "https://api.example.com"},
        ),
        # AnonymousConnection
        (
            """
kind: anonymous
endpoint: https://api.example.com
""",
            AnonymousConnection,
            {"endpoint": "https://api.example.com"},
        ),
        # Connection (base)
        (
            """
kind: connection
authenticationMode: oauth
""",
            Connection,
            {"authenticationMode": "oauth"},
        ),
        # ArrayProperty
        (
            """
kind: array
name: items
description: An array of items
""",
            ArrayProperty,
            {"name": "items", "description": "An array of items"},
        ),
        # ObjectProperty
        (
            """
kind: object
name: config
description: Configuration object
""",
            ObjectProperty,
            {"name": "config", "description": "Configuration object"},
        ),
        # Property (base)
        (
            """
kind: property
name: field
description: A property field
""",
            Property,
            {"name": "field", "description": "A property field"},
        ),
        # McpServerToolAlwaysRequireApprovalMode
        (
            """
kind: always
""",
            McpServerToolAlwaysRequireApprovalMode,
            {},
        ),
        # McpServerToolNeverRequireApprovalMode
        (
            """
kind: never
""",
            McpServerToolNeverRequireApprovalMode,
            {},
        ),
        # McpServerToolSpecifyApprovalMode
        (
            """
kind: specify
alwaysRequireApprovalTools: []
neverRequireApprovalTools: []
""",
            McpServerToolSpecifyApprovalMode,
            {},
        ),
        # McpServerApprovalMode (base)
        (
            """
kind: approval_mode
""",
            McpServerApprovalMode,
            {},
        ),
    ],
)
def test_agent_schema_dispatch_all_types(yaml_content: str, expected_type: type, expected_attributes: dict[str, Any]):
    """Test that agent_schema_dispatch correctly loads all MAML object types."""
    result = agent_schema_dispatch(yaml.safe_load(yaml_content))

    # Check the type is correct
    assert isinstance(result, expected_type), f"Expected {expected_type.__name__}, got {type(result).__name__}"

    # Check expected attributes
    for attr_name, attr_value in expected_attributes.items():
        assert hasattr(result, attr_name), f"Result missing attribute '{attr_name}'"
        assert getattr(result, attr_name) == attr_value, (
            f"Attribute '{attr_name}' has value {getattr(result, attr_name)}, expected {attr_value}"
        )


def test_agent_schema_dispatch_unknown_kind():
    """Test that agent_schema_dispatch returns None for unknown kind."""
    yaml_content = """
kind: unknown_type
name: test
"""
    result = agent_schema_dispatch(yaml.safe_load(yaml_content))
    assert result is None


def test_agent_schema_dispatch_complex_agent_manifest():
    """Test loading a complex agent manifest with nested objects."""
    yaml_content = """
name: complex-manifest
description: A complete manifest
template:
  kind: Prompt
  name: assistant
  description: A helpful assistant
  model:
    id: gpt-4
    provider: openai
  tools:
    - kind: web_search
      name: search
      description: Search the web
    - kind: function
      name: calculator
      description: Calculate math
resources:
  - kind: model
    name: model1
    id: gpt-4
  - kind: tool
    name: tool1
    id: search
"""
    result = agent_schema_dispatch(yaml.safe_load(yaml_content))

    assert isinstance(result, AgentManifest)
    assert result.name == "complex-manifest"
    assert result.description == "A complete manifest"
    assert isinstance(result.template, PromptAgent)
    assert result.template.name == "assistant"
    assert len(result.resources) == 2
    assert isinstance(result.resources[0], ModelResource)
    assert isinstance(result.resources[1], ToolResource)


def test_agent_schema_dispatch_prompt_agent_with_tools():
    """Test loading a prompt agent with multiple tools."""
    yaml_content = """
kind: Prompt
name: multi-tool-agent
description: Agent with multiple tools
model:
  id: gpt-4
tools:
  - kind: web_search
    name: search
    description: Search the web
  - kind: function
    name: get_weather
    description: Get weather information
  - kind: code_interpreter
    name: code
    description: Execute code
"""
    result = agent_schema_dispatch(yaml.safe_load(yaml_content))

    assert isinstance(result, PromptAgent)
    assert result.name == "multi-tool-agent"
    assert len(result.tools) == 3
    # Tools are polymorphically created based on their kind
    assert result.tools[0].kind == "web_search"
    assert result.tools[1].kind == "function"
    assert result.tools[2].kind == "code_interpreter"


def test_agent_schema_dispatch_model_resource():
    """Test loading a model resource."""
    yaml_content = """
kind: Model
name: my-model
id: gpt-4
"""
    result = agent_schema_dispatch(yaml.safe_load(yaml_content))

    assert isinstance(result, ModelResource)
    assert result.id == "gpt-4"


def test_agent_schema_dispatch_property_schema_with_nested_properties():
    """Test loading a property schema with nested properties."""
    yaml_content = """
kind: property_schema
strict: true
properties:
  - kind: property
    name: name
    description: User name
  - kind: object
    name: address
    description: User address
    properties:
      - kind: property
        name: street
        description: Street address
      - kind: property
        name: city
        description: City name
  - kind: array
    name: tags
    description: User tags
"""
    result = agent_schema_dispatch(yaml.safe_load(yaml_content))

    assert isinstance(result, PropertySchema)
    assert result.strict is True
    assert len(result.properties) == 3
    # Properties are polymorphically created based on their kind
    assert result.properties[0].kind == "property"
    assert result.properties[1].kind == "object"
    assert result.properties[2].kind == "array"


def _get_agent_sample_yaml_files() -> list[tuple[Path, Path]]:
    """Helper function to collect all YAML files from agent-samples directory."""
    current_file = Path(__file__)
    repo_root = current_file.parent.parent.parent.parent  # tests -> declarative -> packages -> python
    agent_samples_dir = repo_root.parent / "agent-samples"

    if not agent_samples_dir.exists():
        return []

    yaml_files = list(agent_samples_dir.rglob("*.yaml")) + list(agent_samples_dir.rglob("*.yml"))
    return [(yaml_file, agent_samples_dir) for yaml_file in yaml_files]


@pytest.mark.parametrize(
    "yaml_file,agent_samples_dir",
    _get_agent_sample_yaml_files(),
    ids=lambda x: x[0].name if isinstance(x, tuple) else str(x),
)
def test_agent_schema_dispatch_agent_samples(yaml_file: Path, agent_samples_dir: Path):
    """Test that agent_schema_dispatch successfully loads a YAML file from agent-samples directory."""
    with open(yaml_file) as f:
        content = f.read()
    result = agent_schema_dispatch(yaml.safe_load(content))
    # Result can be None for unknown kinds, but should not raise exceptions
    assert result is not None, f"agent_schema_dispatch returned None for {yaml_file.relative_to(agent_samples_dir)}"
