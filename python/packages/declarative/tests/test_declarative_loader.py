# Copyright (c) Microsoft. All rights reserved.

import builtins
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False


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


class TestAgentFactoryCreateFromDict:
    """Tests for AgentFactory.create_agent_from_dict method."""

    def test_create_agent_from_dict_parses_prompt_agent(self):
        """Test that create_agent_from_dict correctly parses a PromptAgent definition."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        agent_def = {
            "kind": "Prompt",
            "name": "TestAgent",
            "description": "A test agent",
            "instructions": "You are a helpful assistant.",
        }

        # Use a pre-configured chat client to avoid needing model
        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_dict(agent_def)

        assert agent is not None

    def test_create_agent_from_dict_matches_yaml(self):
        """Test that create_agent_from_dict produces same result as create_agent_from_yaml."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
description: A test agent
instructions: You are a helpful assistant.
"""

        agent_def = {
            "kind": "Prompt",
            "name": "TestAgent",
            "description": "A test agent",
            "instructions": "You are a helpful assistant.",
        }

        # Use a pre-configured chat client to avoid needing model
        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)

        # Create from YAML string
        agent_from_yaml = factory.create_agent_from_yaml(yaml_content)

        # Create from dict
        agent_from_dict = factory.create_agent_from_dict(agent_def)

        # Both should produce agents with same name
        assert agent_from_yaml.name == agent_from_dict.name
        assert agent_from_yaml.description == agent_from_dict.description

    def test_create_agent_from_dict_invalid_kind_raises(self):
        """Test that non-PromptAgent kind raises DeclarativeLoaderError."""
        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import DeclarativeLoaderError

        # Resource kind (not PromptAgent)
        agent_def = {
            "kind": "Resource",
            "name": "TestResource",
        }

        factory = AgentFactory()
        with pytest.raises(DeclarativeLoaderError, match="Only definitions for a PromptAgent are supported"):
            factory.create_agent_from_dict(agent_def)

    def test_create_agent_from_dict_without_model_or_client_raises(self):
        """Test that missing both model and client raises DeclarativeLoaderError."""
        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import DeclarativeLoaderError

        agent_def = {
            "kind": "Prompt",
            "name": "TestAgent",
            "instructions": "You are helpful.",
        }

        factory = AgentFactory()
        with pytest.raises(DeclarativeLoaderError, match="ChatClient must be provided"):
            factory.create_agent_from_dict(agent_def)

    def test_create_agent_from_dict_output_schema_in_default_options(self):
        """Test that outputSchema is passed as response_format in Agent.default_options."""
        from unittest.mock import MagicMock

        from pydantic import BaseModel

        from agent_framework_declarative import AgentFactory

        agent_def = {
            "kind": "Prompt",
            "name": "TestAgent",
            "instructions": "You are helpful.",
            "outputSchema": {
                "properties": {
                    "answer": {"type": "string", "required": True, "description": "The answer."},
                },
            },
        }

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_dict(agent_def)

        assert "response_format" in agent.default_options
        assert isinstance(agent.default_options["response_format"], type)
        assert issubclass(agent.default_options["response_format"], BaseModel)

    def test_create_agent_from_dict_chat_options_in_default_options(self):
        """Test that chat options (temperature, top_p) are in Agent.default_options."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        agent_def = {
            "kind": "Prompt",
            "name": "TestAgent",
            "instructions": "You are helpful.",
            "model": {
                "options": {
                    "temperature": 0.7,
                    "topP": 0.9,
                },
            },
        }

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_dict(agent_def)

        assert agent.default_options.get("temperature") == 0.7
        assert agent.default_options.get("top_p") == 0.9


class TestAgentFactorySafeMode:
    """Tests for AgentFactory safe_mode parameter."""

    def test_agent_factory_safe_mode_default_is_true(self):
        """Test that safe_mode is True by default."""
        from agent_framework_declarative._loader import AgentFactory

        factory = AgentFactory()
        assert factory.safe_mode is True

    def test_agent_factory_safe_mode_can_be_set_false(self):
        """Test that safe_mode can be explicitly set to False."""
        from agent_framework_declarative._loader import AgentFactory

        factory = AgentFactory(safe_mode=False)
        assert factory.safe_mode is False

    def test_agent_factory_safe_mode_blocks_env_in_yaml(self, monkeypatch):
        """Test that safe_mode=True blocks environment variable access in YAML parsing."""
        from unittest.mock import MagicMock

        from agent_framework_declarative._loader import AgentFactory

        monkeypatch.setenv("TEST_MODEL_ID", "gpt-4-from-env")

        # Create a mock chat client to avoid needing real provider
        mock_client = MagicMock()

        yaml_content = """
kind: Prompt
name: test-agent
description: =Env.TEST_DESCRIPTION
instructions: Hello world
"""
        monkeypatch.setenv("TEST_DESCRIPTION", "Description from env")

        # With safe_mode=True (default), Env access should fail and return original value
        factory = AgentFactory(client=mock_client, safe_mode=True)
        agent = factory.create_agent_from_yaml(yaml_content)

        # The description should NOT be resolved from env (PowerFx fails, returns original)
        assert agent.description == "=Env.TEST_DESCRIPTION"

    @pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")
    def test_agent_factory_safe_mode_false_allows_env_in_yaml(self, monkeypatch):
        """Test that safe_mode=False allows environment variable access in YAML parsing."""
        from unittest.mock import MagicMock

        from agent_framework_declarative._loader import AgentFactory

        monkeypatch.setenv("TEST_DESCRIPTION", "Description from env")

        # Create a mock chat client to avoid needing real provider
        mock_client = MagicMock()

        yaml_content = """
kind: Prompt
name: test-agent
description: =Env.TEST_DESCRIPTION
instructions: Hello world
"""

        # With safe_mode=False, Env access should work
        factory = AgentFactory(client=mock_client, safe_mode=False)
        agent = factory.create_agent_from_yaml(yaml_content)

        # The description should be resolved from env
        assert agent.description == "Description from env"

    def test_agent_factory_safe_mode_with_api_key_connection(self, monkeypatch):
        """Test safe_mode with API key connection containing env variable."""
        from agent_framework_declarative._models import _safe_mode_context

        monkeypatch.setenv("MY_API_KEY", "secret-key-123")

        yaml_content = """
kind: Prompt
name: test-agent
description: Test agent
instructions: Hello
model:
  id: gpt-4
  provider: OpenAI
  apiType: Chat
  connection:
    kind: key
    apiKey: =Env.MY_API_KEY
"""

        # Manually trigger the YAML parsing to check the context is set correctly
        import yaml as yaml_module

        from agent_framework_declarative._models import agent_schema_dispatch

        token = _safe_mode_context.set(True)  # Ensure we're in safe mode
        try:
            result = agent_schema_dispatch(yaml_module.safe_load(yaml_content))

            # The API key should NOT be resolved (still has the PowerFx expression)
            assert result.model.connection.apiKey == "=Env.MY_API_KEY"
        finally:
            _safe_mode_context.reset(token)

    @pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")
    def test_agent_factory_safe_mode_false_resolves_api_key(self, monkeypatch):
        """Test safe_mode=False resolves API key from environment."""
        from agent_framework_declarative._models import _safe_mode_context

        monkeypatch.setenv("MY_API_KEY", "secret-key-123")

        yaml_content = """
kind: Prompt
name: test-agent
description: Test agent
instructions: Hello
model:
  id: gpt-4
  provider: OpenAI
  apiType: Chat
  connection:
    kind: key
    apiKey: =Env.MY_API_KEY
"""

        # With safe_mode=False, the API key should be resolved
        import yaml as yaml_module

        from agent_framework_declarative._models import agent_schema_dispatch

        token = _safe_mode_context.set(False)  # Disable safe mode
        try:
            result = agent_schema_dispatch(yaml_module.safe_load(yaml_content))

            # The API key should be resolved from environment
            assert result.model.connection.apiKey == "secret-key-123"
        finally:
            _safe_mode_context.reset(token)


class TestAgentFactoryMcpToolConnection:
    """Tests for MCP tool connection handling in AgentFactory._parse_tool."""

    def _get_mcp_tools(self, agent):
        """Helper to get MCP dict tools from agent's default_options."""
        tools = agent.default_options.get("tools", [])
        return [t for t in tools if isinstance(t, dict) and t.get("type") == "mcp"]

    def test_mcp_tool_with_api_key_connection_sets_headers(self):
        """Test that MCP tool with ApiKeyConnection sets headers correctly."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: mcp
    name: my-mcp-tool
    url: https://api.example.com/mcp
    connection:
      kind: key
      apiKey: my-secret-api-key
"""

        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Find the MCP tool in the agent's tools
        mcp_tools = self._get_mcp_tools(agent)
        assert len(mcp_tools) == 1
        mcp_tool = mcp_tools[0]

        # Verify headers are set with the API key
        assert mcp_tool.get("headers") is not None
        assert mcp_tool.get("headers") == {"Authorization": "Bearer my-secret-api-key"}

    def test_mcp_tool_with_remote_connection_sets_additional_properties(self):
        """Test that MCP tool with RemoteConnection sets project_connection_id correctly."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: mcp
    name: github-mcp
    url: https://api.githubcopilot.com/mcp
    connection:
      kind: remote
      authenticationMode: oauth
      name: github-mcp-oauth-connection
"""

        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Find the MCP tool in the agent's tools
        mcp_tools = self._get_mcp_tools(agent)
        assert len(mcp_tools) == 1
        mcp_tool = mcp_tools[0]

        # Verify project_connection_id is set from connection name
        assert mcp_tool.get("project_connection_id") == "github-mcp-oauth-connection"

    def test_mcp_tool_with_reference_connection_sets_additional_properties(self):
        """Test that MCP tool with ReferenceConnection sets project_connection_id correctly."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: mcp
    name: ref-mcp-tool
    url: https://api.example.com/mcp
    connection:
      kind: reference
      name: my-connection-ref
      target: /connections/my-connection
"""

        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Find the MCP tool in the agent's tools
        mcp_tools = self._get_mcp_tools(agent)
        assert len(mcp_tools) == 1
        mcp_tool = mcp_tools[0]

        # Verify project_connection_id is set from connection name
        assert mcp_tool.get("project_connection_id") == "my-connection-ref"

    def test_mcp_tool_with_anonymous_connection_no_headers_or_properties(self):
        """Test that MCP tool with AnonymousConnection doesn't set headers or project_connection_id."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: mcp
    name: anon-mcp-tool
    url: https://api.example.com/mcp
    connection:
      kind: anonymous
"""

        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Find the MCP tool in the agent's tools
        mcp_tools = self._get_mcp_tools(agent)
        assert len(mcp_tools) == 1
        mcp_tool = mcp_tools[0]

        # Verify no headers or project_connection_id are set
        assert mcp_tool.get("headers") is None
        assert mcp_tool.get("project_connection_id") is None

    def test_mcp_tool_without_connection_preserves_existing_behavior(self):
        """Test that MCP tool without connection works as before (no headers or additional_properties)."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: mcp
    name: simple-mcp-tool
    url: https://api.example.com/mcp
    approvalMode: never
"""

        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Find the MCP tool in the agent's tools
        mcp_tools = self._get_mcp_tools(agent)
        assert len(mcp_tools) == 1
        mcp_tool = mcp_tools[0]

        # Verify tool is created correctly without connection
        assert mcp_tool["server_label"] == "simple-mcp-tool"
        assert mcp_tool["server_url"] == "https://api.example.com/mcp"
        assert mcp_tool.get("require_approval") == "never"
        assert mcp_tool.get("headers") is None

    def test_mcp_tool_with_remote_connection_with_endpoint(self):
        """Test that MCP tool with RemoteConnection including endpoint sets project_connection_id."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: mcp
    name: endpoint-mcp-tool
    url: https://api.example.com/mcp
    connection:
      kind: remote
      authenticationMode: oauth
      name: my-oauth-connection
      endpoint: https://auth.example.com
"""

        mock_client = MagicMock()
        mock_client.create_agent.return_value = MagicMock()

        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Find the MCP tool in the agent's tools
        mcp_tools = self._get_mcp_tools(agent)
        assert len(mcp_tools) == 1
        mcp_tool = mcp_tools[0]

        # Verify project_connection_id is set from connection name
        assert mcp_tool.get("project_connection_id") == "my-oauth-connection"


class TestAgentFactoryFilePath:
    """Tests for AgentFactory file path operations."""

    def test_create_agent_from_yaml_path_file_not_found(self, tmp_path):
        """Test that nonexistent file raises DeclarativeLoaderError."""
        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import DeclarativeLoaderError

        factory = AgentFactory()
        with pytest.raises(DeclarativeLoaderError, match="YAML file not found"):
            factory.create_agent_from_yaml_path(tmp_path / "nonexistent.yaml")

    def test_create_agent_from_yaml_path_with_string_path(self, tmp_path):
        """Test create_agent_from_yaml_path accepts string path."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("""
kind: Prompt
name: FileAgent
instructions: Test agent from file
""")

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml_path(str(yaml_file))

        assert agent.name == "FileAgent"

    def test_create_agent_from_yaml_path_with_path_object(self, tmp_path):
        """Test create_agent_from_yaml_path accepts Path object."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("""
kind: Prompt
name: PathAgent
instructions: Test agent from Path
""")

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml_path(yaml_file)

        assert agent.name == "PathAgent"


class TestAgentFactoryAsyncMethods:
    """Tests for AgentFactory async methods."""

    @pytest.mark.asyncio
    async def test_create_agent_from_yaml_path_async_file_not_found(self, tmp_path):
        """Test async version raises DeclarativeLoaderError for nonexistent file."""
        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import DeclarativeLoaderError

        factory = AgentFactory()
        with pytest.raises(DeclarativeLoaderError, match="YAML file not found"):
            await factory.create_agent_from_yaml_path_async(tmp_path / "nonexistent.yaml")

    @pytest.mark.asyncio
    async def test_create_agent_from_yaml_async_with_client(self):
        """Test async creation with pre-configured client."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: AsyncAgent
instructions: Test async agent
"""

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = await factory.create_agent_from_yaml_async(yaml_content)

        assert agent.name == "AsyncAgent"

    @pytest.mark.asyncio
    async def test_create_agent_from_dict_async_with_client(self):
        """Test async dict creation with pre-configured client."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        agent_def = {
            "kind": "Prompt",
            "name": "AsyncDictAgent",
            "instructions": "Test async dict agent",
        }

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = await factory.create_agent_from_dict_async(agent_def)

        assert agent.name == "AsyncDictAgent"

    @pytest.mark.asyncio
    async def test_create_agent_from_dict_async_invalid_kind_raises(self):
        """Test that async version also raises for non-PromptAgent."""
        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import DeclarativeLoaderError

        agent_def = {
            "kind": "Resource",
            "name": "NotAnAgent",
        }

        factory = AgentFactory()
        with pytest.raises(DeclarativeLoaderError, match="Only definitions for a PromptAgent are supported"):
            await factory.create_agent_from_dict_async(agent_def)

    @pytest.mark.asyncio
    async def test_create_agent_from_yaml_path_async_with_string_path(self, tmp_path):
        """Test async version accepts string path."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_file = tmp_path / "async_agent.yaml"
        yaml_file.write_text("""
kind: Prompt
name: AsyncPathAgent
instructions: Test async path agent
""")

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = await factory.create_agent_from_yaml_path_async(str(yaml_file))

        assert agent.name == "AsyncPathAgent"


class TestAgentFactoryProviderLookup:
    """Tests for provider configuration lookup."""

    def test_provider_lookup_error_for_unknown_provider(self):
        """Test that unknown provider raises ProviderLookupError."""

        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import ProviderLookupError

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
model:
  id: test-model
  provider: UnknownProvider
  apiType: UnknownApiType
"""

        factory = AgentFactory()
        with pytest.raises(ProviderLookupError, match="Unsupported provider type"):
            factory.create_agent_from_yaml(yaml_content)

    def test_additional_mappings_override_default(self):
        """Test that additional_mappings can extend provider configurations."""
        from agent_framework_declarative import AgentFactory

        # Define a custom provider mapping
        custom_mappings = {
            "CustomProvider.Chat": {
                "package": "agent_framework.openai",
                "name": "OpenAIChatClient",
                "model_id_field": "model_id",
            },
        }

        factory = AgentFactory(additional_mappings=custom_mappings)

        # The custom mapping should be available
        assert "CustomProvider.Chat" in factory.additional_mappings


class TestAgentFactoryConnectionHandling:
    """Tests for connection handling in AgentFactory."""

    def test_reference_connection_requires_connections_dict(self):
        """Test that ReferenceConnection without connections dict raises."""
        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
model:
  id: gpt-4
  provider: OpenAI
  apiType: Chat
  connection:
    kind: reference
    name: my-connection
"""

        factory = AgentFactory()  # No connections provided
        with pytest.raises(ValueError, match="Connections must be provided to resolve ReferenceConnection"):
            factory.create_agent_from_yaml(yaml_content)

    def test_reference_connection_not_found_raises(self):
        """Test that missing ReferenceConnection raises."""
        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
model:
  id: gpt-4
  provider: OpenAI
  apiType: Chat
  connection:
    kind: reference
    name: missing-connection
"""

        factory = AgentFactory(connections={"other-connection": "value"})
        with pytest.raises(ValueError, match="not found in provided connections"):
            factory.create_agent_from_yaml(yaml_content)

    def test_model_without_id_uses_provided_client(self):
        """Test that model without id uses the provided chat_client."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
model:
  provider: OpenAI
"""

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        assert agent is not None

    def test_model_without_id_and_no_client_raises(self):
        """Test that model without id and no client raises."""
        from agent_framework_declarative import AgentFactory
        from agent_framework_declarative._loader import DeclarativeLoaderError

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
model:
  provider: OpenAI
"""

        factory = AgentFactory()  # No chat_client
        with pytest.raises(DeclarativeLoaderError, match="ChatClient must be provided"):
            factory.create_agent_from_yaml(yaml_content)


class TestAgentFactoryChatOptions:
    """Tests for chat options parsing."""

    def test_parse_chat_options_with_all_fields(self):
        """Test parsing all ModelOptions fields into chat options dict."""
        from agent_framework_declarative._loader import AgentFactory
        from agent_framework_declarative._models import Model, ModelOptions

        factory = AgentFactory()

        # Create a Model with all options set
        options = ModelOptions(
            temperature=0.7,
            maxOutputTokens=1000,
            topP=0.9,
            frequencyPenalty=0.5,
            presencePenalty=0.3,
            seed=42,
            stopSequences=["STOP", "END"],
            allowMultipleToolCalls=True,
        )
        options.additionalProperties["chatToolMode"] = "auto"

        model = Model(id="gpt-4", options=options)

        # Parse the options
        chat_options = factory._parse_chat_options(model)

        # Verify all options are parsed correctly
        assert chat_options.get("temperature") == 0.7
        assert chat_options.get("max_tokens") == 1000
        assert chat_options.get("top_p") == 0.9
        assert chat_options.get("frequency_penalty") == 0.5
        assert chat_options.get("presence_penalty") == 0.3
        assert chat_options.get("seed") == 42
        assert chat_options.get("stop") == ["STOP", "END"]
        assert chat_options.get("allow_multiple_tool_calls") is True
        assert chat_options.get("tool_choice") == "auto"

    def test_parse_chat_options_empty_model(self):
        """Test that missing model options returns empty dict."""
        from agent_framework_declarative._loader import AgentFactory

        factory = AgentFactory()
        result = factory._parse_chat_options(None)
        assert result == {}

    def test_parse_chat_options_with_additional_properties(self):
        """Test that additional properties are passed through."""
        from agent_framework_declarative._loader import AgentFactory
        from agent_framework_declarative._models import Model, ModelOptions

        factory = AgentFactory()

        # Create a Model with additional properties
        options = ModelOptions(temperature=0.5)
        options.additionalProperties["customOption"] = "customValue"

        model = Model(id="gpt-4", options=options)

        # Parse the options
        chat_options = factory._parse_chat_options(model)

        # Verify additional properties are preserved
        assert "additional_chat_options" in chat_options
        assert chat_options["additional_chat_options"].get("customOption") == "customValue"


class TestAgentFactoryToolParsing:
    """Tests for tool parsing edge cases."""

    def test_parse_tools_returns_none_for_empty_list(self):
        """Test that empty tools list returns None."""
        from agent_framework_declarative._loader import AgentFactory

        factory = AgentFactory()
        result = factory._parse_tools(None)
        assert result is None

        result = factory._parse_tools([])
        assert result is None

    def test_parse_function_tool_with_bindings(self):
        """Test parsing FunctionTool with bindings."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: function
    name: my_function
    description: A test function
    bindings:
      - name: my_binding
"""

        def my_function():
            return "result"

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client, bindings={"my_binding": my_function})
        agent = factory.create_agent_from_yaml(yaml_content)

        # Should have parsed the tool with binding
        tools = agent.default_options.get("tools", [])
        assert len(tools) == 1

    def test_parse_file_search_tool_with_all_options(self):
        """Test parsing FileSearchTool with ranker and filters."""
        from unittest.mock import MagicMock

        from agent_framework_declarative import AgentFactory

        yaml_content = """
kind: Prompt
name: TestAgent
instructions: Test agent
tools:
  - kind: file_search
    name: search
    description: Search files
    vectorStoreIds:
      - vs_123
    ranker: semantic
    scoreThreshold: 0.8
    maximumResultCount: 10
    filters:
      type: document
"""

        mock_client = MagicMock()
        factory = AgentFactory(client=mock_client)
        agent = factory.create_agent_from_yaml(yaml_content)

        # Verify a file search tool was parsed
        tools = agent.default_options.get("tools", [])
        assert len(tools) == 1

    def test_parse_unsupported_tool_kind_raises(self):
        """Test that unsupported tool kind raises ValueError."""
        from agent_framework_declarative._loader import AgentFactory
        from agent_framework_declarative._models import CustomTool

        factory = AgentFactory()
        custom_tool = CustomTool(kind="custom", name="test")

        with pytest.raises(ValueError, match="Unsupported tool kind"):
            factory._parse_tool(custom_tool)


class TestProviderResponseFormat:
    """response_format from outputSchema must be passed inside default_options."""

    @staticmethod
    def _make_mock_prompt_agent(*, with_output_schema: bool = False) -> MagicMock:
        """Create a mock PromptAgent to avoid serialization complexity."""
        mock_model = MagicMock()
        mock_model.id = "gpt-4"
        mock_model.connection = None

        agent = MagicMock()
        agent.name = "test-agent"
        agent.description = "test"
        agent.instructions = "be helpful"
        agent.model = mock_model
        agent.tools = None

        if with_output_schema:
            mock_schema = MagicMock()
            mock_schema.to_json_schema.return_value = {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
            }
            agent.outputSchema = mock_schema
        else:
            agent.outputSchema = None

        return agent

    @staticmethod
    def _make_mock_provider() -> tuple[MagicMock, AsyncMock]:
        """Create a mock provider class and its instance."""
        mock_agent = MagicMock()
        mock_provider_instance = AsyncMock()
        mock_provider_instance.create_agent = AsyncMock(return_value=mock_agent)
        mock_provider_class = MagicMock(return_value=mock_provider_instance)
        return mock_provider_class, mock_provider_instance

    @pytest.mark.asyncio
    async def test_response_format_in_default_options(self):
        """Provider.create_agent() should receive response_format inside default_options."""
        from agent_framework_declarative._loader import AgentFactory

        prompt_agent = self._make_mock_prompt_agent(with_output_schema=True)
        mock_provider_class, mock_provider_instance = self._make_mock_provider()

        mapping = {"package": "some_module", "name": "SomeProvider"}
        factory = AgentFactory()

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "some_module":
                mod = MagicMock()
                mod.SomeProvider = mock_provider_class
                return mod
            return original_import(name, *args, **kwargs)

        with (
            patch.object(builtins, "__import__", side_effect=mock_import),
            patch.object(factory, "_parse_tools", return_value=None),
        ):
            await factory._create_agent_with_provider(prompt_agent, mapping)

        mock_provider_instance.create_agent.assert_called_once()
        call_kwargs = mock_provider_instance.create_agent.call_args.kwargs

        assert "response_format" not in call_kwargs
        default_options = call_kwargs.get("default_options")
        assert default_options is not None
        assert "response_format" in default_options

    @pytest.mark.asyncio
    async def test_no_default_options_without_output_schema(self):
        """When there's no outputSchema, default_options should be None."""
        from agent_framework_declarative._loader import AgentFactory

        prompt_agent = self._make_mock_prompt_agent(with_output_schema=False)
        mock_provider_class, mock_provider_instance = self._make_mock_provider()

        mapping = {"package": "some_module", "name": "SomeProvider"}
        factory = AgentFactory()

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "some_module":
                mod = MagicMock()
                mod.SomeProvider = mock_provider_class
                return mod
            return original_import(name, *args, **kwargs)

        with (
            patch.object(builtins, "__import__", side_effect=mock_import),
            patch.object(factory, "_parse_tools", return_value=None),
        ):
            await factory._create_agent_with_provider(prompt_agent, mapping)

        call_kwargs = mock_provider_instance.create_agent.call_args.kwargs
        assert call_kwargs.get("default_options") is None
