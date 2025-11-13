# Copyright (c) Microsoft. All rights reserved.

"""Tests for MAML model classes."""

import sys

import pytest

from agent_framework_declarative._models import (
    AgentDefinition,
    AgentManifest,
    AnonymousConnection,
    ApiKeyConnection,
    ArrayProperty,
    Binding,
    CodeInterpreterTool,
    Connection,
    CustomTool,
    EnvironmentVariable,
    FileSearchTool,
    Format,
    FunctionTool,
    McpServerApprovalMode,
    McpServerToolAlwaysRequireApprovalMode,
    McpServerToolNeverRequireApprovalMode,
    McpServerToolSpecifyApprovalMode,
    McpTool,
    Model,
    ModelOptions,
    ModelResource,
    ObjectProperty,
    OpenApiTool,
    Parser,
    PromptAgent,
    Property,
    PropertySchema,
    ProtocolVersionRecord,
    ReferenceConnection,
    RemoteConnection,
    Resource,
    Template,
    ToolResource,
    WebSearchTool,
    _try_powerfx_eval,
)

pytestmark = pytest.mark.skipif(sys.version_info >= (3, 14), reason="Skipping on Python 3.14+")


class TestBinding:
    """Tests for Binding class."""

    def test_binding_creation(self):
        binding = Binding(name="arg1", input="value1")
        assert binding.name == "arg1"
        assert binding.input == "value1"

    def test_binding_from_dict(self):
        data = {"name": "arg1", "input": "value1"}
        binding = Binding.from_dict(data)
        assert binding.name == "arg1"
        assert binding.input == "value1"

    def test_binding_to_dict(self):
        binding = Binding(name="arg1", input="value1")
        result = binding.to_dict()
        assert result["name"] == "arg1"
        assert result["input"] == "value1"


class TestProperty:
    """Tests for Property class."""

    def test_property_creation(self):
        prop = Property(
            name="test_prop",
            kind="string",
            description="A test property",
            required=True,
            default="default_value",
            example="example_value",
            enum=["val1", "val2"],
        )
        assert prop.name == "test_prop"
        assert prop.kind == "string"
        assert prop.description == "A test property"
        assert prop.required is True
        assert prop.default == "default_value"
        assert prop.example == "example_value"
        assert prop.enum == ["val1", "val2"]

    def test_property_from_dict(self):
        data = {
            "name": "test_prop",
            "kind": "string",
            "description": "A test property",
            "required": True,
        }
        prop = Property.from_dict(data)
        assert prop.name == "test_prop"
        assert prop.kind == "string"
        assert prop.description == "A test property"
        assert prop.required is True


class TestArrayProperty:
    """Tests for ArrayProperty class."""

    def test_array_property_creation(self):
        items = Property(name="item", kind="string")
        array_prop = ArrayProperty(name="test_array", kind="array", items=items, required=True)
        assert array_prop.name == "test_array"
        assert array_prop.kind == "array"
        assert array_prop.items.name == "item"
        assert array_prop.required is True

    def test_array_property_from_dict(self):
        data = {
            "name": "test_array",
            "kind": "array",
            "items": {"name": "item", "kind": "string"},
            "required": True,
        }
        array_prop = ArrayProperty.from_dict(data)
        assert array_prop.name == "test_array"
        assert array_prop.kind == "array"
        assert isinstance(array_prop.items, Property)
        assert array_prop.items.name == "item"


class TestObjectProperty:
    """Tests for ObjectProperty class."""

    def test_object_property_creation(self):
        props = [
            Property(name="prop1", kind="string"),
            Property(name="prop2", kind="integer"),
        ]
        obj_prop = ObjectProperty(name="test_object", kind="object", properties=props, required=True)
        assert obj_prop.name == "test_object"
        assert obj_prop.kind == "object"
        assert len(obj_prop.properties) == 2
        assert obj_prop.properties[0].name == "prop1"

    def test_object_property_from_dict(self):
        data = {
            "name": "test_object",
            "kind": "object",
            "properties": [
                {"name": "prop1", "kind": "string"},
                {"name": "prop2", "kind": "integer"},
            ],
            "required": True,
        }
        obj_prop = ObjectProperty.from_dict(data)
        assert obj_prop.name == "test_object"
        assert obj_prop.kind == "object"
        assert len(obj_prop.properties) == 2
        assert all(isinstance(p, Property) for p in obj_prop.properties)

    def test_object_property_with_dict_properties(self):
        """Test ObjectProperty with dict format for properties (MAML YAML dict syntax)."""
        data = {
            "name": "person",
            "kind": "object",
            "properties": {
                "name": {"kind": "string", "required": True},
                "email": {"kind": "string"},
                "age": {"kind": "integer"},
            },
        }
        obj_prop = ObjectProperty.from_dict(data)
        assert obj_prop.name == "person"
        assert obj_prop.kind == "object"
        assert len(obj_prop.properties) == 3

        # Check that all properties were converted correctly
        prop_names = {p.name for p in obj_prop.properties}
        assert prop_names == {"name", "email", "age"}

        # Check specific property
        name_prop = next(p for p in obj_prop.properties if p.name == "name")
        assert name_prop.kind == "string"
        assert name_prop.required is True


class TestPropertySchema:
    """Tests for PropertySchema class."""

    def test_property_schema_creation(self):
        props = [Property(name="prop1", kind="string")]
        schema = PropertySchema(properties=props, strict=True)
        assert schema.strict is True
        assert len(schema.properties) == 1

    def test_property_schema_from_dict(self):
        data = {
            "strict": False,
            "properties": [{"name": "prop1", "kind": "string"}],
        }
        schema = PropertySchema.from_dict(data)
        assert schema.strict is False
        assert len(schema.properties) == 1
        # Properties are properly converted to Property instances
        assert isinstance(schema.properties[0], Property)
        assert schema.properties[0].name == "prop1"
        assert schema.properties[0].kind == "string"

    def test_property_schema_with_dict_properties(self):
        """Test PropertySchema with dict format for properties (MAML YAML dict syntax)."""
        data = {
            "strict": True,
            "properties": {
                "firstName": {"kind": "string", "description": "First name"},
                "lastName": {"kind": "string", "description": "Last name"},
                "age": {"kind": "integer", "required": True},
            },
        }
        schema = PropertySchema.from_dict(data)
        assert schema.strict is True
        assert len(schema.properties) == 3

        # Check that all properties were converted correctly
        prop_names = {p.name for p in schema.properties}
        assert prop_names == {"firstName", "lastName", "age"}

        # Check specific property details
        age_prop = next(p for p in schema.properties if p.name == "age")
        assert age_prop.kind == "integer"
        assert age_prop.required is True


class TestConnection:
    """Tests for Connection base class."""

    def test_connection_creation(self):
        conn = Connection(kind="base")
        assert conn.kind == "base"

    def test_connection_from_dict(self):
        data = {"kind": "base"}
        conn = Connection.from_dict(data)
        assert conn.kind == "base"


class TestReferenceConnection:
    """Tests for ReferenceConnection class."""

    def test_reference_connection_creation(self):
        conn = ReferenceConnection(name="my-connection", target="target-connection")
        assert conn.kind == "reference"
        assert conn.name == "my-connection"
        assert conn.target == "target-connection"

    def test_reference_connection_from_dict(self):
        data = {"kind": "reference", "name": "my-connection", "target": "target-connection"}
        conn = ReferenceConnection.from_dict(data)
        assert conn.kind == "reference"
        assert conn.name == "my-connection"
        assert conn.target == "target-connection"


class TestRemoteConnection:
    """Tests for RemoteConnection class."""

    def test_remote_connection_creation(self):
        conn = RemoteConnection(name="my-remote", endpoint="https://api.example.com")
        assert conn.kind == "remote"
        assert conn.endpoint == "https://api.example.com"

    def test_remote_connection_from_dict(self):
        data = {"kind": "remote", "endpoint": "https://api.example.com"}
        conn = RemoteConnection.from_dict(data)
        assert conn.kind == "remote"
        assert conn.endpoint == "https://api.example.com"


class TestApiKeyConnection:
    """Tests for ApiKeyConnection class."""

    def test_api_key_connection_creation(self):
        conn = ApiKeyConnection(apiKey="secret-key", endpoint="https://api.example.com")
        assert conn.kind == "key"
        assert conn.apiKey == "secret-key"
        assert conn.endpoint == "https://api.example.com"

    def test_api_key_connection_from_dict(self):
        data = {"kind": "key", "apiKey": "secret-key", "endpoint": "https://api.example.com"}
        conn = ApiKeyConnection.from_dict(data)
        assert conn.kind == "key"
        assert conn.apiKey == "secret-key"


class TestAnonymousConnection:
    """Tests for AnonymousConnection class."""

    def test_anonymous_connection_creation(self):
        conn = AnonymousConnection(endpoint="https://api.example.com")
        assert conn.kind == "anonymous"
        assert conn.endpoint == "https://api.example.com"

    def test_anonymous_connection_from_dict(self):
        data = {"kind": "anonymous", "endpoint": "https://api.example.com"}
        conn = AnonymousConnection.from_dict(data)
        assert conn.kind == "anonymous"
        assert conn.endpoint == "https://api.example.com"


class TestModelOptions:
    """Tests for ModelOptions class."""

    def test_model_options_creation(self):
        options = ModelOptions(temperature=0.7, maxOutputTokens=1000, topP=0.9)
        assert options.temperature == 0.7
        assert options.maxOutputTokens == 1000
        assert options.topP == 0.9

    def test_model_options_from_dict(self):
        data = {"temperature": 0.7, "maxOutputTokens": 1000, "topP": 0.9}
        options = ModelOptions.from_dict(data)
        assert options.temperature == 0.7
        assert options.maxOutputTokens == 1000
        assert options.topP == 0.9


class TestModel:
    """Tests for Model class."""

    def test_model_creation(self):
        model = Model(id="gpt-4", provider="openai")
        assert model.id == "gpt-4"
        assert model.provider == "openai"

    def test_model_from_dict(self):
        data = {"id": "gpt-4", "provider": "openai"}
        model = Model.from_dict(data)
        assert model.id == "gpt-4"
        assert model.provider == "openai"

    def test_model_with_connection(self):
        data = {
            "id": "gpt-4",
            "connection": {"kind": "reference", "name": "my-connection"},
        }
        model = Model.from_dict(data)
        assert model.id == "gpt-4"
        assert model.connection.kind == "reference"


class TestFormat:
    """Tests for Format class."""

    def test_format_creation(self):
        fmt = Format(kind="json", strict=True, options={"type": "object"})
        assert fmt.kind == "json"
        assert fmt.strict is True
        assert fmt.options == {"type": "object"}

    def test_format_from_dict(self):
        data = {"kind": "json", "strict": False, "options": {"type": "object"}}
        fmt = Format.from_dict(data)
        assert fmt.kind == "json"
        assert fmt.strict is False


class TestParser:
    """Tests for Parser class."""

    def test_parser_creation(self):
        parser = Parser(kind="json", options={"strict": True})
        assert parser.kind == "json"
        assert parser.options == {"strict": True}

    def test_parser_from_dict(self):
        data = {"kind": "json", "options": {"strict": True}}
        parser = Parser.from_dict(data)
        assert parser.kind == "json"
        assert parser.options == {"strict": True}


class TestTemplate:
    """Tests for Template class."""

    def test_template_creation(self):
        template = Template(
            format=Format(kind="text"),
            parser=Parser(kind="text"),
        )
        assert isinstance(template.format, Format)
        assert isinstance(template.parser, Parser)

    def test_template_from_dict(self):
        data = {
            "format": {"kind": "text"},
            "parser": {"kind": "text"},
        }
        template = Template.from_dict(data)
        assert isinstance(template.format, Format)
        assert isinstance(template.parser, Parser)


class TestAgentDefinition:
    """Tests for AgentDefinition class."""

    def test_agent_definition_creation(self):
        agent = AgentDefinition(
            name="test-agent",
            description="A test agent",
        )
        assert agent.name == "test-agent"
        assert agent.description == "A test agent"

    def test_agent_definition_from_dict(self):
        data = {
            "name": "test-agent",
            "description": "A test agent",
        }
        agent = AgentDefinition.from_dict(data)
        assert agent.name == "test-agent"
        assert agent.description == "A test agent"


class TestFunctionTool:
    """Tests for FunctionTool class."""

    def test_function_tool_creation(self):
        tool = FunctionTool(
            name="my_function",
            description="A test function",
            kind="function",
        )
        assert tool.name == "my_function"
        assert tool.kind == "function"

    def test_function_tool_from_dict(self):
        data = {
            "name": "my_function",
            "description": "A test function",
            "kind": "function",
            "strict": False,
        }
        tool = FunctionTool.from_dict(data)
        assert tool.name == "my_function"
        assert tool.kind == "function"

    def test_function_tool_with_dict_bindings(self):
        """Test FunctionTool with dict format for bindings (MAML YAML dict syntax)."""
        data = {
            "name": "calculate",
            "kind": "function",
            "description": "Calculate something",
            "bindings": {
                "x": "input.x",
                "y": "input.y",
                "operation": "input.op",
            },
        }
        tool = FunctionTool.from_dict(data)
        assert tool.name == "calculate"
        assert len(tool.bindings) == 3

        # Check that all bindings were converted correctly
        binding_names = {b.name for b in tool.bindings}
        assert binding_names == {"x", "y", "operation"}

        # Check specific binding
        x_binding = next(b for b in tool.bindings if b.name == "x")
        assert x_binding.input == "input.x"


class TestCustomTool:
    """Tests for CustomTool class."""

    def test_custom_tool_creation(self):
        tool = CustomTool(
            name="custom_tool",
            description="A custom tool",
            kind="custom",
            options={"endpoint": "https://tool.example.com"},
        )
        assert tool.name == "custom_tool"
        assert tool.kind == "custom"
        assert tool.options == {"endpoint": "https://tool.example.com"}

    def test_custom_tool_from_dict(self):
        data = {
            "name": "custom_tool",
            "description": "A custom tool",
            "kind": "custom",
            "options": {"endpoint": "https://tool.example.com"},
        }
        tool = CustomTool.from_dict(data)
        assert tool.name == "custom_tool"
        assert tool.kind == "custom"


class TestWebSearchTool:
    """Tests for WebSearchTool class."""

    def test_web_search_tool_creation(self):
        tool = WebSearchTool(
            name="web_search",
            description="Search the web",
            kind="web_search",
            options={"maxResults": 10},
        )
        assert tool.name == "web_search"
        assert tool.kind == "web_search"
        assert tool.options == {"maxResults": 10}

    def test_web_search_tool_from_dict(self):
        data = {
            "name": "web_search",
            "description": "Search the web",
            "kind": "web_search",
            "options": {"maxResults": 10},
        }
        tool = WebSearchTool.from_dict(data)
        assert tool.name == "web_search"
        assert tool.kind == "web_search"
        assert tool.options == {"maxResults": 10}


class TestFileSearchTool:
    """Tests for FileSearchTool class."""

    def test_file_search_tool_creation(self):
        tool = FileSearchTool(
            name="file_search",
            description="Search files",
            kind="file_search",
            vectorStoreIds=["vs1", "vs2"],
        )
        assert tool.name == "file_search"
        assert tool.kind == "file_search"
        assert tool.vectorStoreIds == ["vs1", "vs2"]

    def test_file_search_tool_from_dict(self):
        data = {
            "name": "file_search",
            "description": "Search files",
            "kind": "file_search",
            "vectorStoreIds": ["vs1", "vs2"],
        }
        tool = FileSearchTool.from_dict(data)
        assert tool.name == "file_search"
        assert tool.kind == "file_search"
        assert tool.vectorStoreIds == ["vs1", "vs2"]


class TestMcpServerApprovalMode:
    """Tests for MCP Server Approval Mode classes."""

    def test_always_approval_mode(self):
        mode = McpServerToolAlwaysRequireApprovalMode()
        assert mode.kind == "always"

    def test_always_approval_mode_from_dict(self):
        data = {"kind": "always"}
        mode = McpServerToolAlwaysRequireApprovalMode.from_dict(data)
        assert mode.kind == "always"

    def test_never_approval_mode(self):
        mode = McpServerToolNeverRequireApprovalMode()
        assert mode.kind == "never"

    def test_never_approval_mode_from_dict(self):
        data = {"kind": "never"}
        mode = McpServerToolNeverRequireApprovalMode.from_dict(data)
        assert mode.kind == "never"

    def test_specify_approval_mode(self):
        mode = McpServerToolSpecifyApprovalMode(
            alwaysRequireApprovalTools=["tool1"],
            neverRequireApprovalTools=["tool2"],
        )
        assert mode.kind == "specify"
        assert mode.alwaysRequireApprovalTools == ["tool1"]
        assert mode.neverRequireApprovalTools == ["tool2"]

    def test_specify_approval_mode_from_dict(self):
        data = {
            "kind": "specify",
            "alwaysRequireApprovalTools": ["tool1"],
            "neverRequireApprovalTools": ["tool2"],
        }
        mode = McpServerToolSpecifyApprovalMode.from_dict(data)
        assert mode.kind == "specify"
        assert mode.alwaysRequireApprovalTools == ["tool1"]
        assert mode.neverRequireApprovalTools == ["tool2"]


class TestMcpTool:
    """Tests for McpTool class."""

    def test_mcp_tool_creation(self):
        tool = McpTool(
            name="mcp_tool",
            description="An MCP tool",
            kind="mcp",
            serverName="test-server",
        )
        assert tool.name == "mcp_tool"
        assert tool.kind == "mcp"
        assert tool.serverName == "test-server"

    def test_mcp_tool_from_dict(self):
        data = {
            "name": "mcp_tool",
            "description": "An MCP tool",
            "kind": "mcp",
            "serverName": "test-server",
            "approvalMode": {"kind": "always"},
        }
        tool = McpTool.from_dict(data)
        assert tool.name == "mcp_tool"
        assert tool.kind == "mcp"
        assert isinstance(tool.approvalMode, McpServerApprovalMode)

    def test_mcp_tool_with_simplified_approval_mode(self):
        """Test McpTool with simplified string format for approvalMode."""
        # Test simplified string format: approvalMode: "always"
        data = {
            "name": "mcp_tool",
            "description": "An MCP tool",
            "kind": "mcp",
            "serverName": "test-server",
            "approvalMode": "always",
        }
        tool = McpTool.from_dict(data)
        assert tool.name == "mcp_tool"
        assert tool.kind == "mcp"
        assert isinstance(tool.approvalMode, McpServerApprovalMode)
        assert tool.approvalMode.kind == "always"

    def test_mcp_tool_approval_mode_equivalence(self):
        """Test that simplified and full format produce equivalent results."""
        # Simplified format
        data_simplified = {
            "name": "mcp_tool",
            "kind": "mcp",
            "approvalMode": "never",
        }
        tool_simplified = McpTool.from_dict(data_simplified)

        # Full format
        data_full = {
            "name": "mcp_tool",
            "kind": "mcp",
            "approvalMode": {"kind": "never"},
        }
        tool_full = McpTool.from_dict(data_full)

        # Both should produce the same result
        assert tool_simplified.approvalMode.kind == tool_full.approvalMode.kind
        assert tool_simplified.approvalMode.kind == "never"


class TestOpenApiTool:
    """Tests for OpenApiTool class."""

    def test_openapi_tool_creation(self):
        tool = OpenApiTool(
            name="openapi_tool",
            description="An OpenAPI tool",
            kind="openapi",
            specification="https://api.example.com/openapi.json",
        )
        assert tool.name == "openapi_tool"
        assert tool.kind == "openapi"
        assert tool.specification == "https://api.example.com/openapi.json"

    def test_openapi_tool_from_dict(self):
        data = {
            "name": "openapi_tool",
            "description": "An OpenAPI tool",
            "kind": "openapi",
            "specification": "https://api.example.com/openapi.json",
        }
        tool = OpenApiTool.from_dict(data)
        assert tool.name == "openapi_tool"
        assert tool.kind == "openapi"


class TestCodeInterpreterTool:
    """Tests for CodeInterpreterTool class."""

    def test_code_interpreter_tool_creation(self):
        tool = CodeInterpreterTool(
            name="code_interpreter",
            description="Execute code",
            kind="code_interpreter",
            fileIds=["file1", "file2"],
        )
        assert tool.name == "code_interpreter"
        assert tool.kind == "code_interpreter"
        assert tool.fileIds == ["file1", "file2"]

    def test_code_interpreter_tool_from_dict(self):
        data = {
            "name": "code_interpreter",
            "description": "Execute code",
            "kind": "code_interpreter",
            "fileIds": ["file1", "file2"],
        }
        tool = CodeInterpreterTool.from_dict(data)
        assert tool.name == "code_interpreter"
        assert tool.kind == "code_interpreter"
        assert tool.fileIds == ["file1", "file2"]


class TestPromptAgent:
    """Tests for PromptAgent class."""

    def test_prompt_agent_creation(self):
        agent = PromptAgent(
            name="prompt-agent",
            description="A prompt-based agent",
            instructions="You are a helpful assistant",
            kind="Prompt",
        )
        assert agent.name == "prompt-agent"
        assert agent.kind == "Prompt"
        assert agent.instructions == "You are a helpful assistant"

    def test_prompt_agent_from_dict(self):
        data = {
            "name": "prompt-agent",
            "description": "A prompt-based agent",
            "instructions": "You are a helpful assistant",
            "kind": "Prompt",
            "model": {"id": "gpt-4"},
        }
        agent = PromptAgent.from_dict(data)
        assert agent.name == "prompt-agent"
        assert isinstance(agent.model, Model)
        assert isinstance(agent.model, Model)

    def test_prompt_agent_with_tools(self):
        data = {
            "name": "prompt-agent",
            "kind": "Prompt",
            "tools": [
                {"name": "search", "kind": "web_search"},
                {"name": "calc", "kind": "function"},
            ],
        }
        agent = PromptAgent.from_dict(data)
        assert len(agent.tools) == 2
        # Tools are converted via Tool.from_dict, type depends on 'kind'
        assert agent.tools[0].kind == "web_search"
        assert agent.tools[1].kind == "function"


class TestResource:
    """Tests for Resource base class."""

    def test_resource_creation(self):
        resource = Resource(name="test-resource", kind="Resource")
        assert resource.name == "test-resource"
        assert resource.kind == "Resource"

    def test_resource_from_dict(self):
        data = {"name": "test-resource", "kind": "Resource"}
        resource = Resource.from_dict(data)
        assert resource.name == "test-resource"


class TestModelResource:
    """Tests for ModelResource class."""

    def test_model_resource_creation(self):
        resource = ModelResource(name="my-model", kind="model", id="gpt-4")
        assert resource.name == "my-model"
        assert resource.kind == "model"
        assert resource.id == "gpt-4"

    def test_model_resource_from_dict(self):
        data = {
            "name": "my-model",
            "kind": "model",
            "id": "gpt-4",
        }
        resource = ModelResource.from_dict(data)
        assert resource.name == "my-model"
        assert resource.kind == "model"
        assert resource.id == "gpt-4"


class TestToolResource:
    """Tests for ToolResource class."""

    def test_tool_resource_creation(self):
        resource = ToolResource(name="my-tool", kind="tool", id="search-tool")
        assert resource.name == "my-tool"
        assert resource.kind == "tool"
        assert resource.id == "search-tool"

    def test_tool_resource_from_dict(self):
        data = {
            "name": "my-tool",
            "kind": "tool",
            "id": "search-tool",
        }
        resource = ToolResource.from_dict(data)
        assert resource.name == "my-tool"
        assert resource.kind == "tool"
        assert resource.id == "search-tool"


class TestProtocolVersionRecord:
    """Tests for ProtocolVersionRecord class."""

    def test_protocol_version_record_creation(self):
        record = ProtocolVersionRecord(protocol="mcp", version="1.0.0")
        assert record.protocol == "mcp"
        assert record.version == "1.0.0"

    def test_protocol_version_record_from_dict(self):
        data = {"protocol": "mcp", "version": "1.0.0"}
        record = ProtocolVersionRecord.from_dict(data)
        assert record.protocol == "mcp"
        assert record.version == "1.0.0"


class TestEnvironmentVariable:
    """Tests for EnvironmentVariable class."""

    def test_environment_variable_creation(self):
        env_var = EnvironmentVariable(name="API_KEY", value="secret123")
        assert env_var.name == "API_KEY"
        assert env_var.value == "secret123"

    def test_environment_variable_from_dict(self):
        data = {"name": "API_KEY", "value": "secret123"}
        env_var = EnvironmentVariable.from_dict(data)
        assert env_var.name == "API_KEY"
        assert env_var.value == "secret123"


class TestTryPowerfxEval:
    """Tests for _try_powerfx_eval function."""

    def test_no_evaluation_without_equals_prefix(self):
        """Test that strings without '=' prefix are returned as-is."""
        assert _try_powerfx_eval("hello") == "hello"
        assert _try_powerfx_eval("test value") == "test value"
        assert _try_powerfx_eval("123") == "123"

    def test_none_value_returns_none(self):
        """Test that None values are returned as None."""
        assert _try_powerfx_eval(None) is None

    def test_empty_string_returns_empty(self):
        """Test that empty strings are returned as empty."""
        assert _try_powerfx_eval("") == ""

    def test_simple_powerfx_expressions(self):
        """Test simple PowerFx expressions."""
        from decimal import Decimal

        # Simple math - returns Decimal
        assert _try_powerfx_eval("=1 + 2") == Decimal("3")
        assert _try_powerfx_eval("=10 * 5") == Decimal("50")

        # String literals
        assert _try_powerfx_eval('="hello"') == "hello"
        assert _try_powerfx_eval('="test value"') == "test value"

    def test_env_variable_access(self, monkeypatch):
        """Test accessing environment variables using =Env.<name> pattern."""
        # Set up test environment variables
        monkeypatch.setenv("TEST_VAR", "test_value")
        monkeypatch.setenv("API_KEY", "secret123")
        monkeypatch.setenv("PORT", "8080")

        # Test basic env access
        assert _try_powerfx_eval("=Env.TEST_VAR") == "test_value"
        assert _try_powerfx_eval("=Env.API_KEY") == "secret123"
        assert _try_powerfx_eval("=Env.PORT") == "8080"

    def test_env_variable_with_string_concatenation(self, monkeypatch):
        """Test env variables with string concatenation operator."""
        monkeypatch.setenv("BASE_URL", "https://api.example.com")
        monkeypatch.setenv("API_VERSION", "v1")

        # Test concatenation with &
        result = _try_powerfx_eval('=Env.BASE_URL & "/" & Env.API_VERSION')
        assert result == "https://api.example.com/v1"

        # Test concatenation with literals
        result = _try_powerfx_eval('="API Key: " & Env.API_VERSION')
        assert result == "API Key: v1"

    def test_string_comparison_operators(self, monkeypatch):
        """Test PowerFx string comparison operators."""
        monkeypatch.setenv("ENV_MODE", "production")

        # Equal to - returns bool
        assert _try_powerfx_eval('=Env.ENV_MODE = "production"') is True
        assert _try_powerfx_eval('=Env.ENV_MODE = "development"') is False

        # Not equal to - returns bool
        assert _try_powerfx_eval('=Env.ENV_MODE <> "development"') is True
        assert _try_powerfx_eval('=Env.ENV_MODE <> "production"') is False

    def test_string_in_operator(self):
        """Test PowerFx 'in' operator for substring testing (case-insensitive)."""
        # Substring test - case insensitive - returns bool
        assert _try_powerfx_eval('="the" in "The keyboard and the monitor"') is True
        assert _try_powerfx_eval('="THE" in "The keyboard and the monitor"') is True
        assert _try_powerfx_eval('="xyz" in "The keyboard and the monitor"') is False

    def test_string_exactin_operator(self):
        """Test PowerFx 'exactin' operator for substring testing (case-sensitive)."""
        # Substring test - case sensitive - returns bool
        assert _try_powerfx_eval('="Windows" exactin "To display windows in the Windows operating system"') is True
        assert _try_powerfx_eval('="windows" exactin "To display windows in the Windows operating system"') is True
        assert _try_powerfx_eval('="WINDOWS" exactin "To display windows in the Windows operating system"') is False

    def test_logical_operators_with_strings(self):
        """Test PowerFx logical operators (And, Or, Not) with string comparisons."""
        # And operator - returns bool
        assert _try_powerfx_eval('="a" = "a" And "b" = "b"') is True
        assert _try_powerfx_eval('="a" = "a" And "b" = "c"') is False

        # && operator (alternative syntax) - returns bool
        assert _try_powerfx_eval('="a" = "a" && "b" = "b"') is True

        # Or operator - returns bool
        assert _try_powerfx_eval('="a" = "b" Or "c" = "c"') is True
        assert _try_powerfx_eval('="a" = "b" Or "c" = "d"') is False

        # || operator (alternative syntax) - returns bool
        assert _try_powerfx_eval('="a" = "b" || "c" = "c"') is True

        # Not operator - returns bool
        assert _try_powerfx_eval('=Not("a" = "b")') is True
        assert _try_powerfx_eval('=Not("a" = "a")') is False

        # ! operator (alternative syntax) - returns bool
        assert _try_powerfx_eval('=!("a" = "b")') is True

    def test_parentheses_for_precedence(self):
        """Test using parentheses to control operator precedence."""
        from decimal import Decimal

        # Test arithmetic precedence - returns Decimal
        assert _try_powerfx_eval("=(1 + 2) * 3") == Decimal("9")
        assert _try_powerfx_eval("=1 + 2 * 3") == Decimal("7")

        # Test logical precedence - returns bool
        result = _try_powerfx_eval('=("a" = "a" Or "b" = "c") And "d" = "d"')
        assert result is True

    def test_env_with_special_characters(self, monkeypatch):
        """Test env variables containing special characters in values."""
        monkeypatch.setenv("URL_WITH_QUERY", "https://example.com?param=value")
        monkeypatch.setenv("PATH_WITH_SPACES", "C:\\Program Files\\App")

        result = _try_powerfx_eval("=Env.URL_WITH_QUERY")
        assert result == "https://example.com?param=value"

        result = _try_powerfx_eval("=Env.PATH_WITH_SPACES")
        assert result == "C:\\Program Files\\App"


class TestAgentManifest:
    """Tests for AgentManifest class."""

    def test_agent_manifest_creation(self):
        manifest = AgentManifest(name="my-agent-manifest", description="A test manifest")
        assert manifest.name == "my-agent-manifest"
        assert manifest.description == "A test manifest"

    def test_agent_manifest_from_dict(self):
        data = {
            "name": "my-agent-manifest",
            "description": "A test manifest",
        }
        manifest = AgentManifest.from_dict(data)
        assert manifest.name == "my-agent-manifest"

    def test_agent_manifest_with_resources(self):
        data = {
            "name": "my-agent-manifest",
            "resources": [
                {"name": "model1", "kind": "model", "id": "gpt-4"},
                {
                    "name": "tool1",
                    "kind": "tool",
                    "id": "search-tool",
                },
            ],
        }
        manifest = AgentManifest.from_dict(data)
        assert manifest.name == "my-agent-manifest"
        assert len(manifest.resources) == 2
        # Resources are converted via Resource.from_dict based on their 'kind'
        assert isinstance(manifest.resources[0], ModelResource)
        assert isinstance(manifest.resources[1], ToolResource)

    def test_agent_manifest_complete(self):
        """Test a complete agent manifest with all fields."""
        data = {
            "name": "complete-manifest",
            "description": "A complete test manifest",
            "template": {
                "name": "assistant",
                "kind": "Prompt",
                "description": "A helpful assistant",
            },
            "resources": [
                {"name": "model1", "kind": "model", "id": "gpt-4"},
            ],
        }
        manifest = AgentManifest.from_dict(data)
        assert manifest.name == "complete-manifest"
        assert isinstance(manifest.template, AgentDefinition)
        assert len(manifest.resources) == 1
        assert isinstance(manifest.resources[0], ModelResource)

    def test_agent_manifest_with_dict_resources(self):
        """Test AgentManifest with dict format for resources (MAML YAML dict syntax)."""
        data = {
            "name": "manifest-with-dict-resources",
            "description": "Test manifest with dict resources",
            "resources": {
                "gptModelDeployment": {"kind": "model", "id": "gpt-4o"},
                "webSearchInstance": {"kind": "tool", "id": "web-search"},
                "analyticsTool": {"kind": "tool", "id": "analytics"},
            },
        }
        manifest = AgentManifest.from_dict(data)
        assert manifest.name == "manifest-with-dict-resources"
        assert len(manifest.resources) == 3

        # Check that all resources were converted correctly
        resource_names = {r.name for r in manifest.resources}
        assert resource_names == {"gptModelDeployment", "webSearchInstance", "analyticsTool"}

        # Check specific resource
        gpt_resource = next(r for r in manifest.resources if r.name == "gptModelDeployment")
        assert isinstance(gpt_resource, ModelResource)
        assert gpt_resource.id == "gpt-4o"

        web_resource = next(r for r in manifest.resources if r.name == "webSearchInstance")
        assert isinstance(web_resource, ToolResource)
        assert web_resource.id == "web-search"
