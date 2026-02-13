# Copyright (c) Microsoft. All rights reserved.
"""Tests for message content preparation and parsing in the anthropic package."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_framework import Content, Message
from agent_framework._settings import load_settings

from agent_framework_anthropic import AnthropicClient
from agent_framework_anthropic._chat_client import AnthropicSettings

# Test constants
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


# Message Preparation Tests


def test_prepare_message_with_image_data(mock_anthropic_client: MagicMock) -> None:
    """Test preparing messages with base64-encoded image data."""
    client = create_test_client(mock_anthropic_client)

    # Create message with image data content
    message = Message(
        role="user",
        contents=[Content.from_data(media_type="image/png", data=VALID_PNG_BASE64)],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["source"]["type"] == "base64"
    assert result["content"][0]["source"]["media_type"] == "image/png"


def test_prepare_message_with_image_uri(mock_anthropic_client: MagicMock) -> None:
    """Test preparing messages with image URI."""
    client = create_test_client(mock_anthropic_client)

    message = Message(
        role="user",
        contents=[Content.from_uri(uri="https://example.com/image.jpg", media_type="image/jpeg")],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["source"]["type"] == "url"
    assert result["content"][0]["source"]["url"] == "https://example.com/image.jpg"


def test_prepare_message_with_unsupported_data_type(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test preparing messages with unsupported data content type."""
    client = create_test_client(mock_anthropic_client)

    message = Message(
        role="user",
        contents=[Content.from_data(media_type="application/pdf", data=b"PDF data")],
    )

    result = client._prepare_message_for_anthropic(message)

    # PDF should be ignored
    assert result["role"] == "user"
    assert len(result["content"]) == 0


def test_prepare_message_with_unsupported_uri_type(mock_anthropic_client: MagicMock) -> None:
    """Test preparing messages with unsupported URI content type."""
    client = create_test_client(mock_anthropic_client)

    message = Message(
        role="user",
        contents=[Content.from_uri(uri="https://example.com/video.mp4", media_type="video/mp4")],
    )

    result = client._prepare_message_for_anthropic(message)

    # Video should be ignored
    assert result["role"] == "user"
    assert len(result["content"]) == 0


# Content Parsing Tests


def test_parse_contents_mcp_tool_use(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_contents_code_execution_tool(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_contents_mcp_tool_result_list_content(
    mock_anthropic_client: MagicMock,
) -> None:
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


def test_parse_contents_mcp_tool_result_string_content(
    mock_anthropic_client: MagicMock,
) -> None:
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


def test_parse_contents_mcp_tool_result_bytes_content(
    mock_anthropic_client: MagicMock,
) -> None:
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


def test_parse_contents_mcp_tool_result_object_content(
    mock_anthropic_client: MagicMock,
) -> None:
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


def test_parse_contents_web_search_tool_result(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_contents_web_fetch_tool_result(mock_anthropic_client: MagicMock) -> None:
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
