# Copyright (c) Microsoft. All rights reserved.
"""Additional tests to improve coverage for the anthropic package."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, AsyncMock

import pytest
from agent_framework import Content, Message, FunctionTool, tool
from anthropic.types.beta import (
    BetaMessage,
    BetaRawContentBlockDeltaEvent,
    BetaRawContentBlockStartEvent,
    BetaRawContentBlockStopEvent,
    BetaRawMessageDeltaEvent,
    BetaRawMessageStartEvent,
    BetaTextBlock,
    BetaThinkingBlock,
    BetaToolUseBlock,
    BetaUsage,
    BetaMessageDeltaUsage,
)
from pydantic import BaseModel, Field

from agent_framework_anthropic import AnthropicClient
from agent_framework_anthropic._chat_client import AnthropicSettings
from agent_framework._settings import load_settings


# Test data constants
VALID_PNG_BASE64 = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def create_test_client(mock_client: MagicMock) -> AnthropicClient:
    """Create a test AnthropicClient with a mock Anthropic client."""
    settings = load_settings(
        AnthropicSettings,
        env_prefix="ANTHROPIC_",
        api_key="test-api-key",
        chat_model_id="claude-3-5-sonnet-20241022",
        env_file_path="test.env",
    )
    
    client = object.__new__(AnthropicClient)
    client.anthropic_client = mock_client
    client.model_id = settings["chat_model_id"]
    client._last_call_id_name = None
    client.additional_properties = {}
    client.middleware = None
    client.additional_beta_flags = []
    
    return client


class TestResponseFormat:
    """Tests for response_format parameter handling."""
    
    def test_prepare_response_format_openai_style(self, mock_anthropic_client: MagicMock) -> None:
        """Test response_format with OpenAI-style json_schema."""
        client = create_test_client(mock_anthropic_client)
        
        response_format = {
            "json_schema": {
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        }
        
        result = client._prepare_response_format(response_format)
        
        assert result["type"] == "json_schema"
        assert result["schema"]["additionalProperties"] is False
        assert result["schema"]["properties"]["name"]["type"] == "string"
    
    def test_prepare_response_format_direct_schema(self, mock_anthropic_client: MagicMock) -> None:
        """Test response_format with direct schema key."""
        client = create_test_client(mock_anthropic_client)
        
        response_format = {
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "number"}},
            }
        }
        
        result = client._prepare_response_format(response_format)
        
        assert result["type"] == "json_schema"
        assert result["schema"]["additionalProperties"] is False
        assert result["schema"]["properties"]["value"]["type"] == "number"
    
    def test_prepare_response_format_raw_schema(self, mock_anthropic_client: MagicMock) -> None:
        """Test response_format with raw schema dict."""
        client = create_test_client(mock_anthropic_client)
        
        response_format = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        
        result = client._prepare_response_format(response_format)
        
        assert result["type"] == "json_schema"
        assert result["schema"]["additionalProperties"] is False
        assert result["schema"]["properties"]["count"]["type"] == "integer"
    
    def test_prepare_response_format_pydantic_model(self, mock_anthropic_client: MagicMock) -> None:
        """Test response_format with Pydantic BaseModel."""
        client = create_test_client(mock_anthropic_client)
        
        class TestModel(BaseModel):
            name: str
            age: int
        
        result = client._prepare_response_format(TestModel)
        
        assert result["type"] == "json_schema"
        assert result["schema"]["additionalProperties"] is False
        assert "properties" in result["schema"]


class TestMessagePreparing:
    """Tests for message preparation with different content types."""
    
    def test_prepare_message_with_image_data(self, mock_anthropic_client: MagicMock) -> None:
        """Test preparing messages with base64-encoded image data."""
        client = create_test_client(mock_anthropic_client)
        
        # Create message with image data content
        message = Message(
            role="user",
            contents=[
                Content.from_data(
                    media_type="image/png",
                    data=VALID_PNG_BASE64
                )
            ]
        )
        
        result = client._prepare_message_for_anthropic(message)
        
        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "image"
        assert result["content"][0]["source"]["type"] == "base64"
        assert result["content"][0]["source"]["media_type"] == "image/png"
    
    def test_prepare_message_with_image_uri(self, mock_anthropic_client: MagicMock) -> None:
        """Test preparing messages with image URI."""
        client = create_test_client(mock_anthropic_client)
        
        message = Message(
            role="user",
            contents=[
                Content.from_uri(
                    uri="https://example.com/image.jpg",
                    media_type="image/jpeg"
                )
            ]
        )
        
        result = client._prepare_message_for_anthropic(message)
        
        assert result["role"] == "user"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "image"
        assert result["content"][0]["source"]["type"] == "url"
        assert result["content"][0]["source"]["url"] == "https://example.com/image.jpg"
    
    def test_prepare_message_with_unsupported_data_type(self, mock_anthropic_client: MagicMock) -> None:
        """Test preparing messages with unsupported data content type."""
        client = create_test_client(mock_anthropic_client)
        
        message = Message(
            role="user",
            contents=[
                Content.from_data(
                    media_type="application/pdf",
                    data=b"PDF data"
                )
            ]
        )
        
        result = client._prepare_message_for_anthropic(message)
        
        # PDF should be ignored
        assert result["role"] == "user"
        assert len(result["content"]) == 0
    
    def test_prepare_message_with_unsupported_uri_type(self, mock_anthropic_client: MagicMock) -> None:
        """Test preparing messages with unsupported URI content type."""
        client = create_test_client(mock_anthropic_client)
        
        message = Message(
            role="user",
            contents=[
                Content.from_uri(
                    uri="https://example.com/video.mp4",
                    media_type="video/mp4"
                )
            ]
        )
        
        result = client._prepare_message_for_anthropic(message)
        
        # Video should be ignored
        assert result["role"] == "user"
        assert len(result["content"]) == 0


class TestMCPTools:
    """Tests for MCP tool configuration."""
    
    def test_get_mcp_tool_with_allowed_tools(self) -> None:
        """Test get_mcp_tool with allowed_tools parameter."""
        result = AnthropicClient.get_mcp_tool(
            name="Test Server",
            url="https://example.com/mcp",
            allowed_tools=["tool1", "tool2"]
        )
        
        assert result["type"] == "mcp"
        assert result["server_label"] == "Test_Server"
        assert result["server_url"] == "https://example.com/mcp"
        assert result["allowed_tools"] == ["tool1", "tool2"]
    
    def test_get_mcp_tool_without_allowed_tools(self) -> None:
        """Test get_mcp_tool without allowed_tools parameter."""
        result = AnthropicClient.get_mcp_tool(
            name="Test Server",
            url="https://example.com/mcp"
        )
        
        assert result["type"] == "mcp"
        assert result["server_label"] == "Test_Server"
        assert result["server_url"] == "https://example.com/mcp"
        assert "allowed_tools" not in result


class TestPrepareOptions:
    """Tests for _prepare_options method."""
    
    def test_prepare_options_with_instructions(self, mock_anthropic_client: MagicMock) -> None:
        """Test prepare_options with instructions parameter."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [
            Message(role="user", contents=[Content.from_text("Hello")])
        ]
        options = {"instructions": "You are a helpful assistant"}
        
        result = client._prepare_options(messages, options)
        
        # Instructions should be prepended as system message
        assert result["model"] == "claude-3-5-sonnet-20241022"
        assert result["max_tokens"] == 1024
    
    def test_prepare_options_missing_model_id(self, mock_anthropic_client: MagicMock) -> None:
        """Test prepare_options raises error when model_id is missing."""
        client = create_test_client(mock_anthropic_client)
        client.model_id = ""  # Set empty model_id
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        options = {}
        
        with pytest.raises(ValueError, match="model_id must be a non-empty string"):
            client._prepare_options(messages, options)
    
    def test_prepare_options_with_user_metadata(self, mock_anthropic_client: MagicMock) -> None:
        """Test prepare_options maps user to metadata.user_id."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        options = {"user": "user123"}
        
        result = client._prepare_options(messages, options)
        
        assert "user" not in result
        assert result["metadata"]["user_id"] == "user123"
    
    def test_prepare_options_user_metadata_no_override(self, mock_anthropic_client: MagicMock) -> None:
        """Test user option doesn't override existing user_id in metadata."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        options = {
            "user": "user123",
            "metadata": {"user_id": "existing_user"}
        }
        
        result = client._prepare_options(messages, options)
        
        # Existing user_id should be preserved
        assert result["metadata"]["user_id"] == "existing_user"


class TestToolChoice:
    """Tests for tool choice configuration."""
    
    def test_tool_choice_auto_with_allow_multiple(self, mock_anthropic_client: MagicMock) -> None:
        """Test tool_choice auto mode with allow_multiple=False."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        @tool(approval_mode="never_require")
        def test_func() -> str:
            """Test function."""
            return "test"
        
        options = {
            "tools": [test_func],
            "tool_choice": "auto",
            "allow_multiple_tool_calls": False
        }
        
        result = client._prepare_options(messages, options)
        
        assert result["tool_choice"]["type"] == "auto"
        assert result["tool_choice"]["disable_parallel_tool_use"] is True
    
    def test_tool_choice_required_any(self, mock_anthropic_client: MagicMock) -> None:
        """Test tool_choice required mode without specific function."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        @tool(approval_mode="never_require")
        def test_func() -> str:
            """Test function."""
            return "test"
        
        options = {
            "tools": [test_func],
            "tool_choice": "required"
        }
        
        result = client._prepare_options(messages, options)
        
        assert result["tool_choice"]["type"] == "any"
    
    def test_tool_choice_required_specific_function(self, mock_anthropic_client: MagicMock) -> None:
        """Test tool_choice required mode with specific function."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        @tool(approval_mode="never_require")
        def test_func() -> str:
            """Test function."""
            return "test"
        
        options = {
            "tools": [test_func],
            "tool_choice": {"mode": "required", "required_function_name": "test_func"}
        }
        
        result = client._prepare_options(messages, options)
        
        assert result["tool_choice"]["type"] == "tool"
        assert result["tool_choice"]["name"] == "test_func"


class TestStreamEvents:
    """Tests for stream event processing."""
    
    def test_process_stream_event_message_stop(self, mock_anthropic_client: MagicMock) -> None:
        """Test processing message_stop event."""
        client = create_test_client(mock_anthropic_client)
        
        # message_stop events don't produce output
        mock_event = MagicMock()
        mock_event.type = "message_stop"
        
        result = client._process_stream_event(mock_event)
        
        assert result is None


@pytest.fixture
def mock_anthropic_client() -> MagicMock:
    """Create a mock Anthropic client."""
    mock = MagicMock()
    mock.beta = MagicMock()
    mock.beta.messages = MagicMock()
    mock.beta.messages.create = AsyncMock()
    return mock


class TestMCPToolConfiguration:
    """Tests for MCP tool configuration with allowed_tools."""
    
    def test_prepare_tools_mcp_with_allowed_tools(self, mock_anthropic_client: MagicMock) -> None:
        """Test MCP tool with allowed_tools configuration."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        mcp_tool = {
            "type": "mcp",
            "server_label": "test_server",
            "server_url": "https://example.com/mcp",
            "allowed_tools": ["tool1", "tool2"]
        }
        
        options = {"tools": [mcp_tool]}
        
        result = client._prepare_options(messages, options)
        
        assert "mcp_servers" in result
        assert len(result["mcp_servers"]) == 1
        assert result["mcp_servers"][0]["tool_configuration"]["allowed_tools"] == ["tool1", "tool2"]


class TestToolChoiceNone:
    """Tests for tool choice none mode."""
    
    def test_tool_choice_none(self, mock_anthropic_client: MagicMock) -> None:
        """Test tool_choice none mode."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        @tool(approval_mode="never_require")
        def test_func() -> str:
            """Test function."""
            return "test"
        
        options = {
            "tools": [test_func],
            "tool_choice": "none"
        }
        
        result = client._prepare_options(messages, options)
        
        assert result["tool_choice"]["type"] == "none"
    
    def test_tool_choice_required_allows_parallel_use(self, mock_anthropic_client: MagicMock) -> None:
        """Test tool choice required mode with allow_multiple=True."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        @tool(approval_mode="never_require")
        def test_func() -> str:
            """Test function."""
            return "test"
        
        options = {
            "tools": [test_func],
            "tool_choice": "required",
            "allow_multiple_tool_calls": True
        }
        
        # This tests line 739: setting disable_parallel_tool_use in required mode
        result = client._prepare_options(messages, options)
        
        assert result["tool_choice"]["type"] == "any"
        assert result["tool_choice"]["disable_parallel_tool_use"] is False


class TestPrepareOptionsFilters:
    """Tests for filtering options."""
    
    def test_prepare_options_filters_internal_kwargs(self, mock_anthropic_client: MagicMock) -> None:
        """Test that internal kwargs are filtered out."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        
        options = {}
        # These should be filtered out
        kwargs = {
            "_function_middleware_pipeline": "some_value",
            "thread": "thread_id",
            "middleware": "middleware_obj",
        }
        
        result = client._prepare_options(messages, options, **kwargs)
        
        assert "_function_middleware_pipeline" not in result
        assert "thread" not in result
        assert "middleware" not in result


class TestParseContentsFromAnthropic:
    """Tests for parsing content blocks from Anthropic."""
    
    def test_parse_contents_mcp_tool_use(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing MCP tool use content."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock MCP tool use block
        mock_block = MagicMock()
        mock_block.type = "mcp_tool_use"
        mock_block.id = "call_123"
        mock_block.name = "test_tool"
        mock_block.input = {"arg": "value"}
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "mcp_server_tool_call"
    
    def test_parse_contents_code_execution_tool(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing code execution tool use."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock code execution tool use block
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.id = "call_456"
        mock_block.name = "code_execution_tool"
        mock_block.input = "print('hello')"
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "code_interpreter_tool_call"
    
    def test_parse_contents_mcp_tool_result_list_content(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing MCP tool result with list content."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_123", "test_tool")
        
        # Create mock MCP tool result with list content
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Result text"
        
        mock_block = MagicMock()
        mock_block.type = "mcp_tool_result"
        mock_block.tool_use_id = "call_123"
        mock_block.content = [mock_text_block]
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "mcp_server_tool_result"
    
    def test_parse_contents_mcp_tool_result_string_content(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing MCP tool result with string content."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_123", "test_tool")
        
        # Create mock MCP tool result with string content
        mock_block = MagicMock()
        mock_block.type = "mcp_tool_result"
        mock_block.tool_use_id = "call_123"
        mock_block.content = "Simple string result"
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "mcp_server_tool_result"
    
    def test_parse_contents_mcp_tool_result_bytes_content(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing MCP tool result with bytes content."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_123", "test_tool")
        
        # Create mock MCP tool result with bytes content
        mock_block = MagicMock()
        mock_block.type = "mcp_tool_result"
        mock_block.tool_use_id = "call_123"
        mock_block.content = b"Binary data"
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "mcp_server_tool_result"
    
    def test_parse_contents_mcp_tool_result_object_content(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing MCP tool result with object content."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_123", "test_tool")
        
        # Create mock MCP tool result with object content
        mock_content_obj = MagicMock()
        mock_content_obj.type = "text"
        mock_content_obj.text = "Object content"
        
        mock_block = MagicMock()
        mock_block.type = "mcp_tool_result"
        mock_block.tool_use_id = "call_123"
        mock_block.content = mock_content_obj
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "mcp_server_tool_result"
    
    def test_parse_contents_web_search_tool_result(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing web search tool result."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_789", "web_search")
        
        # Create mock web search tool result
        mock_block = MagicMock()
        mock_block.type = "web_search_tool_result"
        mock_block.tool_use_id = "call_789"
        mock_block.content = "Search results"
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"
    
    def test_parse_contents_web_fetch_tool_result(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing web fetch tool result."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_101", "web_fetch")
        
        # Create mock web fetch tool result
        mock_block = MagicMock()
        mock_block.type = "web_fetch_tool_result"
        mock_block.tool_use_id = "call_101"
        mock_block.content = "Fetched content"
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"


class TestCodeExecutionResults:
    """Tests for code execution tool result parsing."""
    
    def test_parse_code_execution_result_with_error(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing code execution result with error."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_code1", "code_execution_tool")
        
        # Create mock code execution result with error
        mock_block = MagicMock()
        mock_block.type = "code_execution_tool_result"
        mock_block.tool_use_id = "call_code1"
        mock_block.result = MagicMock()
        mock_block.result.type = "error"
        mock_block.result.error = "Syntax error"
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "code_interpreter_tool_result"
    
    def test_parse_code_execution_result_with_stdout(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing code execution result with stdout."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_code2", "code_execution_tool")
        
        # Create mock code execution result with stdout
        mock_block = MagicMock()
        mock_block.type = "code_execution_tool_result"
        mock_block.tool_use_id = "call_code2"
        mock_block.result = MagicMock()
        mock_block.result.type = "success"
        mock_block.result.stdout = "Hello, world!"
        mock_block.result.stderr = None
        mock_block.result.file_outputs = []
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "code_interpreter_tool_result"
    
    def test_parse_code_execution_result_with_stderr(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing code execution result with stderr."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_code3", "code_execution_tool")
        
        # Create mock code execution result with stderr
        mock_block = MagicMock()
        mock_block.type = "code_execution_tool_result"
        mock_block.tool_use_id = "call_code3"
        mock_block.result = MagicMock()
        mock_block.result.type = "success"
        mock_block.result.stdout = None
        mock_block.result.stderr = "Warning message"
        mock_block.result.file_outputs = []
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "code_interpreter_tool_result"
    
    def test_parse_code_execution_result_with_files(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing code execution result with file outputs."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_code4", "code_execution_tool")
        
        # Create mock file output
        mock_file = MagicMock()
        mock_file.file_id = "file_123"
        
        # Create mock code execution result with files
        mock_block = MagicMock()
        mock_block.type = "code_execution_tool_result"
        mock_block.tool_use_id = "call_code4"
        mock_block.result = MagicMock()
        mock_block.result.type = "success"
        mock_block.result.stdout = None
        mock_block.result.stderr = None
        mock_block.result.file_outputs = [mock_file]
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "code_interpreter_tool_result"





class TestBashExecutionResults:
    """Tests for bash code execution tool result parsing."""
    
    def test_parse_bash_execution_result_with_stdout(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing bash execution result with stdout."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_bash2", "bash_code_execution")
        
        # Create mock bash execution result with stdout
        mock_content = MagicMock()
        mock_content.stdout = "Output text"
        mock_content.stderr = None
        mock_content.content = []
        
        mock_block = MagicMock()
        mock_block.type = "bash_code_execution_tool_result"
        mock_block.tool_use_id = "call_bash2"
        mock_block.content = mock_content
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"
    
    def test_parse_bash_execution_result_with_stderr(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing bash execution result with stderr."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_bash3", "bash_code_execution")
        
        # Create mock bash execution result with stderr
        mock_content = MagicMock()
        mock_content.stdout = None
        mock_content.stderr = "Error output"
        mock_content.content = []
        
        mock_block = MagicMock()
        mock_block.type = "bash_code_execution_tool_result"
        mock_block.tool_use_id = "call_bash3"
        mock_block.content = mock_content
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"


class TestStreamEventParsing:
    """Tests for stream event parsing with usage details."""
    
    def test_parse_usage_with_cache_tokens(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing usage with cache creation and read tokens."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock usage with cache tokens
        mock_usage = MagicMock()
        mock_usage.input_tokens = 100
        mock_usage.output_tokens = 50
        mock_usage.cache_creation_input_tokens = 20
        mock_usage.cache_read_input_tokens = 30
        
        result = client._parse_usage_from_anthropic(mock_usage)
        
        assert result is not None
        assert result["output_token_count"] == 50
        assert result["input_token_count"] == 100
        assert result["anthropic.cache_creation_input_tokens"] == 20
        assert result["anthropic.cache_read_input_tokens"] == 30


class TestTextEditorResults:
    """Tests for text editor code execution tool result parsing."""
    
    def test_parse_text_editor_result_error(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing text editor result with error."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_editor1", "text_editor_code_execution")
        
        # Create mock text editor result with error
        mock_content = MagicMock()
        mock_content.type = "text_editor_code_execution_tool_result_error"
        mock_content.error = "File not found"
        
        mock_block = MagicMock()
        mock_block.type = "text_editor_code_execution_tool_result"
        mock_block.tool_use_id = "call_editor1"
        mock_block.content = mock_content
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"
    
    def test_parse_text_editor_result_view(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing text editor view result."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_editor2", "text_editor_code_execution")
        
        # Create mock text editor view result
        mock_annotation = MagicMock()
        mock_annotation.start_line = 10
        mock_annotation.num_lines = 5
        
        mock_content = MagicMock()
        mock_content.type = "text_editor_code_execution_tool_result_view"
        mock_content.view = "File content"
        mock_content.annotations = [mock_annotation]
        
        mock_block = MagicMock()
        mock_block.type = "text_editor_code_execution_tool_result"
        mock_block.tool_use_id = "call_editor2"
        mock_block.content = mock_content
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"
    
    def test_parse_text_editor_result_str_replace(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing text editor string replace result."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_editor3", "text_editor_code_execution")
        
        # Create mock text editor str_replace result
        mock_content = MagicMock()
        mock_content.type = "text_editor_code_execution_tool_result_str_replace"
        mock_content.old_str = "old text"
        mock_content.new_str = "new text"
        mock_content.old_str_line_range = [5, 10]
        mock_content.new_str_line_range = [5, 11]
        
        mock_block = MagicMock()
        mock_block.type = "text_editor_code_execution_tool_result"
        mock_block.tool_use_id = "call_editor3"
        mock_block.content = mock_content
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"
    
    def test_parse_text_editor_result_file_create(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing text editor file create result."""
        client = create_test_client(mock_anthropic_client)
        client._last_call_id_name = ("call_editor4", "text_editor_code_execution")
        
        # Create mock text editor create/insert result
        mock_content = MagicMock()
        mock_content.type = "text_editor_code_execution_tool_result_create_or_insert"
        mock_content.file_created = True
        
        mock_block = MagicMock()
        mock_block.type = "text_editor_code_execution_tool_result"
        mock_block.tool_use_id = "call_editor4"
        mock_block.content = mock_content
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "function_result"


class TestThinkingBlocks:
    """Tests for thinking block parsing."""
    
    def test_parse_thinking_block(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing thinking content block."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock thinking block
        mock_block = MagicMock()
        mock_block.type = "thinking"
        mock_block.thinking = "Let me think about this..."
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "text_reasoning"
    
    def test_parse_thinking_delta_block(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing thinking delta content block."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock thinking delta block  
        mock_block = MagicMock()
        mock_block.type = "thinking_delta"
        mock_block.thinking = "more thinking..."
        
        result = client._parse_contents_from_anthropic([mock_block])
        
        assert len(result) == 1
        assert result[0].type == "text_reasoning"


class TestCitations:
    """Tests for citation parsing."""
    
    def test_parse_citations_char_location(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing citations with char_location."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock text block with citations
        mock_citation = MagicMock()
        mock_citation.type = "char_location"
        mock_citation.title = "Source Title"
        mock_citation.snippet = "Citation snippet"
        mock_citation.start_char_index = 0
        mock_citation.end_char_index = 10
        mock_citation.file_id = None
        
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Text with citation"
        mock_block.citations = [mock_citation]
        
        result = client._parse_citations_from_anthropic(mock_block)
        
        assert len(result) > 0
    
    def test_parse_citations_page_location(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing citations with page_location."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock citation with page location
        mock_citation = MagicMock()
        mock_citation.type = "page_location"
        mock_citation.document_title = "Document Title"
        mock_citation.start_page_number = 1
        mock_citation.end_page_number = 3
        mock_citation.file_id = None
        
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Text with page citation"
        mock_block.citations = [mock_citation]
        
        result = client._parse_citations_from_anthropic(mock_block)
        
        assert len(result) > 0
    
    def test_parse_citations_content_block_location(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing citations with content_block_location."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock citation with content block location
        mock_citation = MagicMock()
        mock_citation.type = "content_block_location"
        mock_citation.start_content_block_index = 0
        mock_citation.end_content_block_index = 2
        mock_citation.file_id = None
        
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Text with block citation"
        mock_block.citations = [mock_citation]
        
        result = client._parse_citations_from_anthropic(mock_block)
        
        assert len(result) > 0
    
    def test_parse_citations_web_search_location(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing citations with web_search_result_location."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock citation with web search location
        mock_citation = MagicMock()
        mock_citation.type = "web_search_result_location"
        mock_citation.url = "https://example.com"
        mock_citation.file_id = None
        
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Text with web citation"
        mock_block.citations = [mock_citation]
        
        result = client._parse_citations_from_anthropic(mock_block)
        
        assert len(result) > 0
    
    def test_parse_citations_search_result_location(self, mock_anthropic_client: MagicMock) -> None:
        """Test parsing citations with search_result_location."""
        client = create_test_client(mock_anthropic_client)
        
        # Create mock citation with search result location
        mock_citation = MagicMock()
        mock_citation.type = "search_result_location"
        mock_citation.source = "https://source.com"
        mock_citation.start_content_block_index = 0
        mock_citation.end_content_block_index = 1
        mock_citation.file_id = None
        
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Text with search citation"
        mock_block.citations = [mock_citation]
        
        result = client._parse_citations_from_anthropic(mock_block)
        
        assert len(result) > 0
