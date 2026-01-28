# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock

import pytest
from agent_framework import (
    Content,
    FunctionTool,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedImageGenerationTool,
    HostedMCPTool,
    HostedWebSearchTool,
)
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError
from azure.ai.agents.models import CodeInterpreterToolDefinition
from pydantic import BaseModel

from agent_framework_azure_ai._shared import (
    _convert_response_format,  # type: ignore
    _convert_sdk_tool,  # type: ignore
    _extract_project_connection_id,  # type: ignore
    _prepare_mcp_tool_for_azure_ai,  # type: ignore
    create_text_format_config,
    from_azure_ai_agent_tools,
    from_azure_ai_tools,
    to_azure_ai_agent_tools,
    to_azure_ai_tools,
)


def test_extract_project_connection_id_direct() -> None:
    """Test extracting project_connection_id from direct key."""
    result = _extract_project_connection_id({"project_connection_id": "my-connection"})
    assert result == "my-connection"


def test_extract_project_connection_id_from_connection_name() -> None:
    """Test extracting project_connection_id from connection.name structure."""
    result = _extract_project_connection_id({"connection": {"name": "my-connection"}})
    assert result == "my-connection"


def test_extract_project_connection_id_none() -> None:
    """Test returns None when no connection info."""
    assert _extract_project_connection_id(None) is None
    assert _extract_project_connection_id({}) is None


def test_to_azure_ai_agent_tools_empty() -> None:
    """Test converting empty/None tools list."""
    assert to_azure_ai_agent_tools(None) == []
    assert to_azure_ai_agent_tools([]) == []


def test_to_azure_ai_agent_tools_function_tool() -> None:
    """Test converting FunctionTool to tool definition."""

    def my_func(arg: str) -> str:
        """My function."""
        return arg

    func_tool = FunctionTool(func=my_func, name="my_func", description="My function.")  # type: ignore
    result = to_azure_ai_agent_tools([func_tool])  # type: ignore
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "my_func"


def test_to_azure_ai_agent_tools_code_interpreter() -> None:
    """Test converting HostedCodeInterpreterTool."""
    tool = HostedCodeInterpreterTool()
    result = to_azure_ai_agent_tools([tool])
    assert len(result) == 1
    assert isinstance(result[0], CodeInterpreterToolDefinition)


def test_to_azure_ai_agent_tools_web_search_missing_connection() -> None:
    """Test HostedWebSearchTool raises without connection info."""
    tool = HostedWebSearchTool()
    with pytest.raises(ServiceInitializationError, match="Bing search tool requires"):
        to_azure_ai_agent_tools([tool])


def test_to_azure_ai_agent_tools_dict_passthrough() -> None:
    """Test dict tools pass through unchanged."""
    tool_dict = {"type": "custom", "config": "value"}
    result = to_azure_ai_agent_tools([tool_dict])
    assert result[0] == tool_dict


def test_to_azure_ai_agent_tools_unsupported_type() -> None:
    """Test unsupported tool type raises error."""

    class UnsupportedTool:
        pass

    with pytest.raises(ServiceInitializationError, match="Unsupported tool type"):
        to_azure_ai_agent_tools([UnsupportedTool()])  # type: ignore


def test_from_azure_ai_agent_tools_empty() -> None:
    """Test converting empty/None tools list."""
    assert from_azure_ai_agent_tools(None) == []
    assert from_azure_ai_agent_tools([]) == []


def test_from_azure_ai_agent_tools_code_interpreter() -> None:
    """Test converting CodeInterpreterToolDefinition."""
    tool = CodeInterpreterToolDefinition()
    result = from_azure_ai_agent_tools([tool])
    assert len(result) == 1
    assert isinstance(result[0], HostedCodeInterpreterTool)


def test_convert_sdk_tool_code_interpreter() -> None:
    """Test _convert_sdk_tool with code_interpreter type."""
    tool = MagicMock()
    tool.type = "code_interpreter"
    result = _convert_sdk_tool(tool)
    assert isinstance(result, HostedCodeInterpreterTool)


def test_convert_sdk_tool_function_returns_none() -> None:
    """Test _convert_sdk_tool with function type returns None."""
    tool = MagicMock()
    tool.type = "function"
    result = _convert_sdk_tool(tool)
    assert result is None


def test_convert_sdk_tool_mcp_returns_none() -> None:
    """Test _convert_sdk_tool with mcp type returns None."""
    tool = MagicMock()
    tool.type = "mcp"
    result = _convert_sdk_tool(tool)
    assert result is None


def test_convert_sdk_tool_file_search() -> None:
    """Test _convert_sdk_tool with file_search type."""
    tool = MagicMock()
    tool.type = "file_search"
    tool.file_search = MagicMock()
    tool.file_search.vector_store_ids = ["vs-1", "vs-2"]
    result = _convert_sdk_tool(tool)
    assert isinstance(result, HostedFileSearchTool)
    assert len(result.inputs) == 2  # type: ignore


def test_convert_sdk_tool_bing_grounding() -> None:
    """Test _convert_sdk_tool with bing_grounding type."""
    tool = MagicMock()
    tool.type = "bing_grounding"
    tool.bing_grounding = MagicMock()
    tool.bing_grounding.connection_id = "conn-123"
    result = _convert_sdk_tool(tool)
    assert isinstance(result, HostedWebSearchTool)
    assert result.additional_properties["connection_id"] == "conn-123"  # type: ignore


def test_convert_sdk_tool_bing_custom_search() -> None:
    """Test _convert_sdk_tool with bing_custom_search type."""
    tool = MagicMock()
    tool.type = "bing_custom_search"
    tool.bing_custom_search = MagicMock()
    tool.bing_custom_search.connection_id = "conn-123"
    tool.bing_custom_search.instance_name = "my-instance"
    result = _convert_sdk_tool(tool)
    assert isinstance(result, HostedWebSearchTool)
    assert result.additional_properties["custom_connection_id"] == "conn-123"  # type: ignore
    assert result.additional_properties["custom_instance_name"] == "my-instance"  # type: ignore


def test_to_azure_ai_tools_empty() -> None:
    """Test converting empty/None tools list."""
    assert to_azure_ai_tools(None) == []
    assert to_azure_ai_tools([]) == []


def test_to_azure_ai_tools_code_interpreter_with_file_ids() -> None:
    """Test converting HostedCodeInterpreterTool with file inputs."""
    tool = HostedCodeInterpreterTool(
        inputs=[Content.from_hosted_file(file_id="file-123")]  # type: ignore
    )
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "code_interpreter"
    assert result[0]["container"]["file_ids"] == ["file-123"]


def test_to_azure_ai_tools_function_tool() -> None:
    """Test converting FunctionTool."""

    def my_func(arg: str) -> str:
        """My function."""
        return arg

    func_tool = FunctionTool(func=my_func, name="my_func", description="My function.")  # type: ignore
    result = to_azure_ai_tools([func_tool])  # type: ignore
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["name"] == "my_func"


def test_to_azure_ai_tools_file_search() -> None:
    """Test converting HostedFileSearchTool."""
    tool = HostedFileSearchTool(
        inputs=[Content.from_hosted_vector_store(vector_store_id="vs-123")],  # type: ignore
        max_results=10,
    )
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "file_search"
    assert result[0]["vector_store_ids"] == ["vs-123"]
    assert result[0]["max_num_results"] == 10


def test_to_azure_ai_tools_web_search_with_location() -> None:
    """Test converting HostedWebSearchTool with user location."""
    tool = HostedWebSearchTool(
        additional_properties={
            "user_location": {
                "city": "Seattle",
                "country": "US",
                "region": "WA",
                "timezone": "PST",
            }
        }
    )
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "web_search_preview"


def test_to_azure_ai_tools_image_generation() -> None:
    """Test converting HostedImageGenerationTool."""
    tool = HostedImageGenerationTool(
        options={"model_id": "gpt-image-1", "image_size": "1024x1024"},
        additional_properties={"quality": "high"},
    )
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "image_generation"
    assert result[0]["model"] == "gpt-image-1"


def test_prepare_mcp_tool_basic() -> None:
    """Test basic MCP tool conversion."""
    tool = HostedMCPTool(name="my tool", url="http://localhost:8080")
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["server_label"] == "my_tool"
    assert "http://localhost:8080" in result["server_url"]


def test_prepare_mcp_tool_with_description() -> None:
    """Test MCP tool with description."""
    tool = HostedMCPTool(name="my tool", url="http://localhost:8080", description="My MCP server")
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["server_description"] == "My MCP server"


def test_prepare_mcp_tool_with_headers() -> None:
    """Test MCP tool with headers (no project_connection_id)."""
    tool = HostedMCPTool(name="my tool", url="http://localhost:8080", headers={"X-Api-Key": "secret"})
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["headers"] == {"X-Api-Key": "secret"}


def test_prepare_mcp_tool_project_connection_takes_precedence() -> None:
    """Test project_connection_id takes precedence over headers."""
    tool = HostedMCPTool(
        name="my tool",
        url="http://localhost:8080",
        headers={"X-Api-Key": "secret"},
        additional_properties={"project_connection_id": "my-conn"},
    )
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["project_connection_id"] == "my-conn"
    assert "headers" not in result


def test_prepare_mcp_tool_approval_mode_always() -> None:
    """Test MCP tool with always_require approval mode."""
    tool = HostedMCPTool(name="my tool", url="http://localhost:8080", approval_mode="always_require")
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["require_approval"] == "always"


def test_prepare_mcp_tool_approval_mode_never() -> None:
    """Test MCP tool with never_require approval mode."""
    tool = HostedMCPTool(name="my tool", url="http://localhost:8080", approval_mode="never_require")
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["require_approval"] == "never"


def test_prepare_mcp_tool_approval_mode_dict() -> None:
    """Test MCP tool with dict approval mode."""
    tool = HostedMCPTool(
        name="my tool",
        url="http://localhost:8080",
        approval_mode={
            "always_require_approval": {"sensitive_tool"},
            "never_require_approval": {"safe_tool"},
        },
    )
    result = _prepare_mcp_tool_for_azure_ai(tool)
    # The last assignment wins in the current implementation
    assert "require_approval" in result


def test_create_text_format_config_pydantic_model() -> None:
    """Test creating text format config from Pydantic model."""

    class MySchema(BaseModel):
        name: str
        value: int

    result = create_text_format_config(MySchema)
    assert result["type"] == "json_schema"
    assert result["name"] == "MySchema"
    assert result["strict"] is True


def test_create_text_format_config_json_schema_mapping() -> None:
    """Test creating text format config from json_schema mapping."""
    config = {
        "type": "json_schema",
        "json_schema": {
            "name": "MyResponse",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
    }
    result = create_text_format_config(config)
    assert result["type"] == "json_schema"
    assert result["name"] == "MyResponse"


def test_create_text_format_config_json_object() -> None:
    """Test creating text format config for json_object type."""
    result = create_text_format_config({"type": "json_object"})
    assert result["type"] == "json_object"


def test_create_text_format_config_text() -> None:
    """Test creating text format config for text type."""
    result = create_text_format_config({"type": "text"})
    assert result["type"] == "text"


def test_create_text_format_config_invalid_raises() -> None:
    """Test invalid response_format raises error."""
    with pytest.raises(ServiceInvalidRequestError):
        create_text_format_config({"type": "invalid"})


def test_convert_response_format_with_format_key() -> None:
    """Test _convert_response_format with nested format key."""
    config = {"format": {"type": "json_object"}}
    result = _convert_response_format(config)
    assert result["type"] == "json_object"


def test_convert_response_format_json_schema_missing_schema_raises() -> None:
    """Test json_schema without schema raises error."""
    with pytest.raises(ServiceInvalidRequestError, match="requires a schema"):
        _convert_response_format({"type": "json_schema", "json_schema": {}})


def test_from_azure_ai_tools_mcp_approval_mode_always() -> None:
    """Test from_azure_ai_tools converts MCP require_approval='always' to approval_mode."""
    tools = [
        {
            "type": "mcp",
            "server_label": "my_mcp",
            "server_url": "http://localhost:8080",
            "require_approval": "always",
        }
    ]
    result = from_azure_ai_tools(tools)
    assert len(result) == 1
    assert isinstance(result[0], HostedMCPTool)
    assert result[0].approval_mode == "always_require"


def test_from_azure_ai_tools_mcp_approval_mode_never() -> None:
    """Test from_azure_ai_tools converts MCP require_approval='never' to approval_mode."""
    tools = [
        {
            "type": "mcp",
            "server_label": "my_mcp",
            "server_url": "http://localhost:8080",
            "require_approval": "never",
        }
    ]
    result = from_azure_ai_tools(tools)
    assert len(result) == 1
    assert isinstance(result[0], HostedMCPTool)
    assert result[0].approval_mode == "never_require"


def test_from_azure_ai_tools_mcp_approval_mode_dict_always() -> None:
    """Test from_azure_ai_tools converts MCP dict require_approval with 'always' key."""
    tools = [
        {
            "type": "mcp",
            "server_label": "my_mcp",
            "server_url": "http://localhost:8080",
            "require_approval": {"always": {"tool_names": ["sensitive_tool", "dangerous_tool"]}},
        }
    ]
    result = from_azure_ai_tools(tools)
    assert len(result) == 1
    assert isinstance(result[0], HostedMCPTool)
    assert result[0].approval_mode == {"always_require_approval": {"sensitive_tool", "dangerous_tool"}}


def test_from_azure_ai_tools_mcp_approval_mode_dict_never() -> None:
    """Test from_azure_ai_tools converts MCP dict require_approval with 'never' key."""
    tools = [
        {
            "type": "mcp",
            "server_label": "my_mcp",
            "server_url": "http://localhost:8080",
            "require_approval": {"never": {"tool_names": ["safe_tool"]}},
        }
    ]
    result = from_azure_ai_tools(tools)
    assert len(result) == 1
    assert isinstance(result[0], HostedMCPTool)
    assert result[0].approval_mode == {"never_require_approval": {"safe_tool"}}
