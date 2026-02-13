# Copyright (c) Microsoft. All rights reserved.
"""Tests for tool result parsing in the anthropic package."""

from __future__ import annotations

from unittest.mock import MagicMock

from conftest import create_test_client

# Code Execution Result Tests


def test_parse_code_execution_result_with_error(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_code_execution_result_with_stdout(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_code_execution_result_with_stderr(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_code_execution_result_with_files(mock_anthropic_client: MagicMock) -> None:
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


# Bash Execution Result Tests


def test_parse_bash_execution_result_with_stdout(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_bash_execution_result_with_stderr(mock_anthropic_client: MagicMock) -> None:
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


# Text Editor Result Tests


def test_parse_text_editor_result_error(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_text_editor_result_view(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_text_editor_result_str_replace(mock_anthropic_client: MagicMock) -> None:
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


def test_parse_text_editor_result_file_create(mock_anthropic_client: MagicMock) -> None:
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
