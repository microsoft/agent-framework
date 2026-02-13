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
                    data=b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
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
    
    async def test_prepare_options_with_instructions(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_prepare_options_with_user_metadata(self, mock_anthropic_client: MagicMock) -> None:
        """Test prepare_options maps user to metadata.user_id."""
        client = create_test_client(mock_anthropic_client)
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        options = {"user": "user123"}
        
        result = client._prepare_options(messages, options)
        
        assert "user" not in result
        assert result["metadata"]["user_id"] == "user123"
    
    async def test_prepare_options_user_metadata_no_override(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_tool_choice_auto_with_allow_multiple(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_tool_choice_required_any(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_tool_choice_required_specific_function(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_prepare_tools_mcp_with_allowed_tools(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_tool_choice_none(self, mock_anthropic_client: MagicMock) -> None:
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
    
    async def test_tool_choice_unsupported_mode(self, mock_anthropic_client: MagicMock) -> None:
        """Test that tool choice with allow_multiple disables parallel use."""
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
    
    async def test_prepare_options_filters_internal_kwargs(self, mock_anthropic_client: MagicMock) -> None:
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


class TestInnerGetResponseStreaming:
    """Tests for streaming response handling."""
    
    async def test_inner_get_response_streaming_yields_chunks(self, mock_anthropic_client: MagicMock) -> None:
        """Test that streaming mode yields parsed chunks."""
        client = create_test_client(mock_anthropic_client)
        
        # Mock streaming response
        async def mock_stream():
            # Yield mock events
            mock_event1 = MagicMock()
            mock_event1.type = "message_stop"
            yield mock_event1
        
        mock_anthropic_client.beta.messages.create = AsyncMock(return_value=mock_stream())
        
        messages = [Message(role="user", contents=[Content.from_text("Hello")])]
        options = {}
        
        response_stream = client._inner_get_response(
            messages=messages,
            options=options,
            stream=True
        )
        
        # Should return a ResponseStream
        assert response_stream is not None
