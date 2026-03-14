# Copyright (c) Microsoft. All rights reserved.

import os
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    FunctionTool,
)
from agent_framework.exceptions import IntegrationInvalidRequestException
from azure.ai.agents.models import CodeInterpreterToolDefinition
from pydantic import BaseModel

from agent_framework_azure_ai import AzureAIAgentClient
from agent_framework_azure_ai._shared import (
    _convert_response_format,  # type: ignore
    _convert_sdk_tool,  # type: ignore
    _extract_project_connection_id,  # type: ignore
    create_text_format_config,
    from_azure_ai_agent_tools,
    from_azure_ai_tools,
    to_azure_ai_agent_tools,
    to_azure_ai_tools,
)
from agent_framework_azure_ai._shared import (
    _prepare_mcp_tool_dict_for_azure_ai as _prepare_mcp_tool_for_azure_ai,  # type: ignore
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
    """Test converting code_interpreter dict tool."""
    tool = AzureAIAgentClient.get_code_interpreter_tool()
    result = to_azure_ai_agent_tools([tool])
    assert len(result) == 1
    assert isinstance(result[0], CodeInterpreterToolDefinition)


def test_to_azure_ai_agent_tools_web_search_missing_connection() -> None:
    """Test web search tool raises without connection info."""
    # Clear any environment variables that could provide connection info
    with patch.dict(
        os.environ,
        {"BING_CONNECTION_ID": "", "BING_CUSTOM_CONNECTION_ID": "", "BING_CUSTOM_INSTANCE_NAME": ""},
        clear=False,
    ):
        # Also need to unset the keys if they exist
        env_backup = {}
        for key in ["BING_CONNECTION_ID", "BING_CUSTOM_CONNECTION_ID", "BING_CUSTOM_INSTANCE_NAME"]:
            env_backup[key] = os.environ.pop(key, None)
        try:
            # get_web_search_tool now raises ValueError when no connection info is available
            with pytest.raises(ValueError, match="Azure AI Agents requires a Bing connection"):
                AzureAIAgentClient.get_web_search_tool()
        finally:
            # Restore environment
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value


def test_to_azure_ai_agent_tools_dict_passthrough() -> None:
    """Test dict tools pass through unchanged."""
    tool_dict = {"type": "custom", "config": "value"}
    result = to_azure_ai_agent_tools([tool_dict])
    assert result[0] == tool_dict


def test_to_azure_ai_agent_tools_unsupported_type() -> None:
    """Test unsupported tool type passes through unchanged."""

    class UnsupportedTool:
        pass

    unsupported = UnsupportedTool()
    result = to_azure_ai_agent_tools([unsupported])  # type: ignore
    assert len(result) == 1
    assert result[0] is unsupported  # Passed through unchanged


def test_from_azure_ai_agent_tools_empty() -> None:
    """Test converting empty/None tools list."""
    assert from_azure_ai_agent_tools(None) == []
    assert from_azure_ai_agent_tools([]) == []


def test_from_azure_ai_agent_tools_code_interpreter() -> None:
    """Test converting CodeInterpreterToolDefinition."""
    tool = CodeInterpreterToolDefinition()
    result = from_azure_ai_agent_tools([tool])
    assert len(result) == 1
    assert result[0] == {"type": "code_interpreter"}


def test_convert_sdk_tool_code_interpreter() -> None:
    """Test _convert_sdk_tool with code_interpreter type."""
    tool = MagicMock()
    tool.type = "code_interpreter"
    result = _convert_sdk_tool(tool)
    assert result == {"type": "code_interpreter"}


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
    assert result["type"] == "file_search"
    assert result["vector_store_ids"] == ["vs-1", "vs-2"]


def test_convert_sdk_tool_bing_grounding() -> None:
    """Test _convert_sdk_tool with bing_grounding type."""
    tool = MagicMock()
    tool.type = "bing_grounding"
    tool.bing_grounding = MagicMock()
    tool.bing_grounding.connection_id = "conn-123"
    result = _convert_sdk_tool(tool)
    assert result["type"] == "bing_grounding"
    assert result["connection_id"] == "conn-123"


def test_convert_sdk_tool_bing_custom_search() -> None:
    """Test _convert_sdk_tool with bing_custom_search type."""
    tool = MagicMock()
    tool.type = "bing_custom_search"
    tool.bing_custom_search = MagicMock()
    tool.bing_custom_search.connection_id = "conn-123"
    tool.bing_custom_search.instance_name = "my-instance"
    result = _convert_sdk_tool(tool)
    assert result["type"] == "bing_custom_search"
    assert result["connection_id"] == "conn-123"
    assert result["instance_name"] == "my-instance"


def test_to_azure_ai_tools_empty() -> None:
    """Test converting empty/None tools list."""
    assert to_azure_ai_tools(None) == []
    assert to_azure_ai_tools([]) == []


def test_to_azure_ai_tools_code_interpreter_with_file_ids() -> None:
    """Test converting code_interpreter dict tool with file inputs."""
    tool = {
        "type": "code_interpreter",
        "file_ids": ["file-123"],
    }
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "code_interpreter"


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
    """Test converting file_search dict tool."""
    tool = {
        "type": "file_search",
        "vector_store_ids": ["vs-123"],
        "max_num_results": 10,
    }
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "file_search"
    assert result[0]["vector_store_ids"] == ["vs-123"]
    assert result[0]["max_num_results"] == 10


def test_to_azure_ai_tools_web_search_with_location() -> None:
    """Test converting web_search dict tool with user location."""
    tool = {
        "type": "web_search_preview",
        "user_location": {
            "city": "Seattle",
            "country": "US",
            "region": "WA",
            "timezone": "PST",
        },
    }
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "web_search_preview"


def test_to_azure_ai_tools_image_generation() -> None:
    """Test converting image_generation dict tool."""
    tool = {
        "type": "image_generation",
        "model": "gpt-image-1",
        "size": "1024x1024",
        "quality": "high",
    }
    result = to_azure_ai_tools([tool])
    assert len(result) == 1
    assert result[0]["type"] == "image_generation"
    assert result[0]["model"] == "gpt-image-1"


def test_prepare_mcp_tool_basic() -> None:
    """Test basic MCP tool conversion."""
    tool = {"type": "mcp", "server_label": "my_tool", "server_url": "http://localhost:8080"}
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["server_label"] == "my_tool"
    assert "http://localhost:8080" in result["server_url"]


def test_prepare_mcp_tool_with_description() -> None:
    """Test MCP tool with description."""
    tool = {
        "type": "mcp",
        "server_label": "my_tool",
        "server_url": "http://localhost:8080",
        "server_description": "My MCP server",
    }
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["server_description"] == "My MCP server"


def test_prepare_mcp_tool_with_headers() -> None:
    """Test MCP tool with headers (no project_connection_id)."""
    tool = {
        "type": "mcp",
        "server_label": "my_tool",
        "server_url": "http://localhost:8080",
        "headers": {"X-Api-Key": "secret"},
    }
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["headers"] == {"X-Api-Key": "secret"}


def test_prepare_mcp_tool_project_connection_takes_precedence() -> None:
    """Test project_connection_id takes precedence over headers."""
    tool = {
        "type": "mcp",
        "server_label": "my_tool",
        "server_url": "http://localhost:8080",
        "headers": {"X-Api-Key": "secret"},
        "project_connection_id": "my-conn",
    }
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["project_connection_id"] == "my-conn"
    assert "headers" not in result


def test_prepare_mcp_tool_approval_mode_always() -> None:
    """Test MCP tool with always_require approval mode."""
    tool = {
        "type": "mcp",
        "server_label": "my_tool",
        "server_url": "http://localhost:8080",
        "require_approval": "always",
    }
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["require_approval"] == "always"


def test_prepare_mcp_tool_approval_mode_never() -> None:
    """Test MCP tool with never_require approval mode."""
    tool = {
        "type": "mcp",
        "server_label": "my_tool",
        "server_url": "http://localhost:8080",
        "require_approval": "never",
    }
    result = _prepare_mcp_tool_for_azure_ai(tool)
    assert result["require_approval"] == "never"


def test_prepare_mcp_tool_approval_mode_dict() -> None:
    """Test MCP tool with dict approval mode."""
    tool = {
        "type": "mcp",
        "server_label": "my_tool",
        "server_url": "http://localhost:8080",
        "require_approval": {"always": {"tool_names": ["sensitive_tool", "dangerous_tool"]}},
    }
    result = _prepare_mcp_tool_for_azure_ai(tool)
    # The approval mode is passed through
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
    with pytest.raises(IntegrationInvalidRequestException):
        create_text_format_config({"type": "invalid"})


def test_convert_response_format_with_format_key() -> None:
    """Test _convert_response_format with nested format key."""
    config = {"format": {"type": "json_object"}}
    result = _convert_response_format(config)
    assert result["type"] == "json_object"


def test_convert_response_format_json_schema_missing_schema_raises() -> None:
    """Test json_schema without schema raises error."""
    with pytest.raises(IntegrationInvalidRequestException, match="requires a schema"):
        _convert_response_format({"type": "json_schema", "json_schema": {}})


def test_from_azure_ai_tools_mcp_approval_mode_always() -> None:
    """Test from_azure_ai_tools converts MCP require_approval='always' to dict."""
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
    assert result[0]["type"] == "mcp"
    assert result[0]["require_approval"] == "always"


def test_from_azure_ai_tools_mcp_approval_mode_never() -> None:
    """Test from_azure_ai_tools converts MCP require_approval='never' to dict."""
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
    assert result[0]["type"] == "mcp"
    assert result[0]["require_approval"] == "never"


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
    assert result[0]["type"] == "mcp"
    assert result[0]["require_approval"] == {"always": {"tool_names": ["sensitive_tool", "dangerous_tool"]}}


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
    assert result[0]["type"] == "mcp"
    assert result[0]["require_approval"] == {"never": {"tool_names": ["safe_tool"]}}
