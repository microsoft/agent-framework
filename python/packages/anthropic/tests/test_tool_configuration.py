# Copyright (c) Microsoft. All rights reserved.
"""Tests for tool configuration and tool choice in the anthropic package."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_framework import Content, Message, tool
from conftest import create_test_client

from agent_framework_anthropic import AnthropicClient

# MCP Tool Configuration Tests


def test_get_mcp_tool_with_allowed_tools() -> None:
    """Test get_mcp_tool with allowed_tools parameter."""
    result = AnthropicClient.get_mcp_tool(
        name="Test Server",
        url="https://example.com/mcp",
        allowed_tools=["tool1", "tool2"],
    )

    assert result["type"] == "mcp"
    assert result["server_label"] == "Test_Server"
    assert result["server_url"] == "https://example.com/mcp"
    assert result["allowed_tools"] == ["tool1", "tool2"]


def test_get_mcp_tool_without_allowed_tools() -> None:
    """Test get_mcp_tool without allowed_tools parameter."""
    result = AnthropicClient.get_mcp_tool(name="Test Server", url="https://example.com/mcp")

    assert result["type"] == "mcp"
    assert result["server_label"] == "Test_Server"
    assert result["server_url"] == "https://example.com/mcp"
    assert "allowed_tools" not in result


def test_prepare_tools_mcp_with_allowed_tools(mock_anthropic_client: MagicMock) -> None:
    """Test MCP tool with allowed_tools configuration."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    mcp_tool = {
        "type": "mcp",
        "server_label": "test_server",
        "server_url": "https://example.com/mcp",
        "allowed_tools": ["tool1", "tool2"],
    }

    options = {"tools": [mcp_tool]}

    result = client._prepare_options(messages, options)

    assert "mcp_servers" in result
    assert len(result["mcp_servers"]) == 1
    assert result["mcp_servers"][0]["tool_configuration"]["allowed_tools"] == [
        "tool1",
        "tool2",
    ]


# Tool Choice Mode Tests


def test_tool_choice_auto_with_allow_multiple(mock_anthropic_client: MagicMock) -> None:
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
        "allow_multiple_tool_calls": False,
    }

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "auto"
    assert result["tool_choice"]["disable_parallel_tool_use"] is True


def test_tool_choice_required_any(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice required mode without specific function."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {"tools": [test_func], "tool_choice": "required"}

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "any"


def test_tool_choice_required_specific_function(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice required mode with specific function."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {
        "tools": [test_func],
        "tool_choice": {"mode": "required", "required_function_name": "test_func"},
    }

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "tool"
    assert result["tool_choice"]["name"] == "test_func"


def test_tool_choice_none(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice none mode."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {"tools": [test_func], "tool_choice": "none"}

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "none"


def test_tool_choice_required_allows_parallel_use(mock_anthropic_client: MagicMock) -> None:
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
        "allow_multiple_tool_calls": True,
    }

    # This tests line 739: setting disable_parallel_tool_use in required mode
    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "any"
    assert result["tool_choice"]["disable_parallel_tool_use"] is False


# Options Preparation Tests


def test_prepare_options_with_instructions(mock_anthropic_client: MagicMock) -> None:
    """Test prepare_options with instructions parameter."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {"instructions": "You are a helpful assistant"}

    result = client._prepare_options(messages, options)

    # Instructions should be prepended as system message
    assert result["model"] == "claude-3-5-sonnet-20241022"
    assert result["max_tokens"] == 1024


def test_prepare_options_missing_model_id(mock_anthropic_client: MagicMock) -> None:
    """Test prepare_options raises error when model_id is missing."""
    client = create_test_client(mock_anthropic_client)
    client.model_id = ""  # Set empty model_id

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {}

    try:
        client._prepare_options(messages, options)
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "model_id must be a non-empty string" in str(e)


def test_prepare_options_with_user_metadata(mock_anthropic_client: MagicMock) -> None:
    """Test prepare_options maps user to metadata.user_id."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {"user": "user123"}

    result = client._prepare_options(messages, options)

    assert "user" not in result
    assert result["metadata"]["user_id"] == "user123"


def test_prepare_options_user_metadata_no_override(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test user option doesn't override existing user_id in metadata."""
    client = create_test_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {"user": "user123", "metadata": {"user_id": "existing_user"}}

    result = client._prepare_options(messages, options)

    # Existing user_id should be preserved
    assert result["metadata"]["user_id"] == "existing_user"


def test_prepare_options_filters_internal_kwargs(mock_anthropic_client: MagicMock) -> None:
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


# Stream Event Tests


def test_process_stream_event_message_stop(mock_anthropic_client: MagicMock) -> None:
    """Test processing message_stop event."""
    client = create_test_client(mock_anthropic_client)

    # message_stop events don't produce output
    mock_event = MagicMock()
    mock_event.type = "message_stop"

    result = client._process_stream_event(mock_event)

    assert result is None


def test_parse_usage_with_cache_tokens(mock_anthropic_client: MagicMock) -> None:
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
