# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

from agent_framework import AIFunction, AITool, HostedCodeInterpreterTool, ai_function
from agent_framework._tools import _parse_inputs
from agent_framework.telemetry import GenAIAttributes


def test_ai_function_decorator():
    """Test the ai_function decorator."""

    @ai_function(name="test_tool", description="A test tool")
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, AITool)
    assert isinstance(test_tool, AIFunction)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A test tool"
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3


def test_ai_function_decorator_without_args():
    """Test the ai_function decorator."""

    @ai_function
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, AITool)
    assert isinstance(test_tool, AIFunction)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A simple function that adds two numbers."
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3


async def test_ai_function_decorator_with_async():
    """Test the ai_function decorator with an async function."""

    @ai_function(name="async_test_tool", description="An async test tool")
    async def async_test_tool(x: int, y: int) -> int:
        """An async function that adds two numbers."""
        return x + y

    assert isinstance(async_test_tool, AITool)
    assert isinstance(async_test_tool, AIFunction)
    assert async_test_tool.name == "async_test_tool"
    assert async_test_tool.description == "An async test tool"
    assert async_test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "async_test_tool_input",
        "type": "object",
    }
    assert (await async_test_tool(1, 2)) == 3


# Telemetry tests for AIFunction
async def test_ai_function_invoke_telemetry_enabled():
    """Test the ai_function invoke method with telemetry enabled."""

    @ai_function(name="telemetry_test_tool", description="A test tool for telemetry")
    def telemetry_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers for telemetry testing."""
        return x + y

    # Mock the tracer and span
    with (
        patch("agent_framework._tools.tracer") as mock_tracer,
        patch("agent_framework._tools.start_as_current_span") as mock_start_span,
    ):
        mock_span = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_span)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_start_span.return_value = mock_context_manager

        # Mock the histogram
        mock_histogram = Mock()
        telemetry_test_tool._invocation_duration_histogram = mock_histogram

        # Call invoke
        result = await telemetry_test_tool.invoke(x=1, y=2, tool_call_id="test_call_id")

        # Verify result
        assert result == 3

        # Verify telemetry calls
        mock_start_span.assert_called_once_with(
            mock_tracer, telemetry_test_tool, metadata={"tool_call_id": "test_call_id", "kwargs": {"x": 1, "y": 2}}
        )

        # Verify histogram was called with correct attributes
        mock_histogram.record.assert_called_once()
        call_args = mock_histogram.record.call_args
        assert call_args[0][0] > 0  # duration should be positive
        attributes = call_args[1]["attributes"]
        assert attributes[GenAIAttributes.MEASUREMENT_FUNCTION_TAG_NAME.value] == "telemetry_test_tool"
        assert attributes[GenAIAttributes.TOOL_CALL_ID.value] == "test_call_id"


async def test_ai_function_invoke_telemetry_with_pydantic_args():
    """Test the ai_function invoke method with Pydantic model arguments."""

    @ai_function(name="pydantic_test_tool", description="A test tool with Pydantic args")
    def pydantic_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers using Pydantic args."""
        return x + y

    # Create arguments as Pydantic model instance
    args_model = pydantic_test_tool.input_model(x=5, y=10)

    with (
        patch("agent_framework._tools.tracer") as mock_tracer,
        patch("agent_framework._tools.start_as_current_span") as mock_start_span,
    ):
        mock_span = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_span)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_start_span.return_value = mock_context_manager

        mock_histogram = Mock()
        pydantic_test_tool._invocation_duration_histogram = mock_histogram

        # Call invoke with Pydantic model
        result = await pydantic_test_tool.invoke(arguments=args_model, tool_call_id="pydantic_call")

        # Verify result
        assert result == 15

        # Verify telemetry calls
        mock_start_span.assert_called_once_with(
            mock_tracer, pydantic_test_tool, metadata={"tool_call_id": "pydantic_call", "kwargs": {"x": 5, "y": 10}}
        )


async def test_ai_function_invoke_telemetry_with_exception():
    """Test the ai_function invoke method with telemetry when an exception occurs."""

    @ai_function(name="exception_test_tool", description="A test tool that raises an exception")
    def exception_test_tool(x: int, y: int) -> int:
        """A function that raises an exception for telemetry testing."""
        raise ValueError("Test exception for telemetry")

    with (
        patch("agent_framework._tools.tracer"),
        patch("agent_framework._tools.start_as_current_span") as mock_start_span,
    ):
        mock_span = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_span)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_start_span.return_value = mock_context_manager

        mock_histogram = Mock()
        exception_test_tool._invocation_duration_histogram = mock_histogram

        # Call invoke and expect exception
        with pytest.raises(ValueError, match="Test exception for telemetry"):
            await exception_test_tool.invoke(x=1, y=2, tool_call_id="exception_call")

        # Verify telemetry calls
        mock_start_span.assert_called_once()

        # Verify span exception recording
        mock_span.record_exception.assert_called_once()
        mock_span.set_attribute.assert_called()
        mock_span.set_status.assert_called_once()

        # Verify histogram was called with error attributes
        mock_histogram.record.assert_called_once()
        call_args = mock_histogram.record.call_args
        attributes = call_args[1]["attributes"]
        assert attributes[GenAIAttributes.ERROR_TYPE.value] == "ValueError"


async def test_ai_function_invoke_telemetry_async_function():
    """Test the ai_function invoke method with telemetry on async function."""

    @ai_function(name="async_telemetry_test", description="An async test tool for telemetry")
    async def async_telemetry_test(x: int, y: int) -> int:
        """An async function for telemetry testing."""
        return x * y

    with (
        patch("agent_framework._tools.tracer") as mock_tracer,
        patch("agent_framework._tools.start_as_current_span") as mock_start_span,
    ):
        mock_span = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_span)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_start_span.return_value = mock_context_manager

        mock_histogram = Mock()
        async_telemetry_test._invocation_duration_histogram = mock_histogram

        # Call invoke
        result = await async_telemetry_test.invoke(x=3, y=4, tool_call_id="async_call")

        # Verify result
        assert result == 12

        # Verify telemetry calls
        mock_start_span.assert_called_once_with(
            mock_tracer, async_telemetry_test, metadata={"tool_call_id": "async_call", "kwargs": {"x": 3, "y": 4}}
        )

        # Verify histogram recording
        mock_histogram.record.assert_called_once()
        call_args = mock_histogram.record.call_args
        attributes = call_args[1]["attributes"]
        assert attributes[GenAIAttributes.MEASUREMENT_FUNCTION_TAG_NAME.value] == "async_telemetry_test"


async def test_ai_function_invoke_telemetry_no_tool_call_id():
    """Test the ai_function invoke method with telemetry when no tool_call_id is provided."""

    @ai_function(name="no_id_test_tool", description="A test tool without tool_call_id")
    def no_id_test_tool(x: int) -> int:
        """A function for testing without tool_call_id."""
        return x * 2

    with (
        patch("agent_framework._tools.tracer") as mock_tracer,
        patch("agent_framework._tools.start_as_current_span") as mock_start_span,
    ):
        mock_span = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__ = Mock(return_value=mock_span)
        mock_context_manager.__exit__ = Mock(return_value=None)
        mock_start_span.return_value = mock_context_manager

        mock_histogram = Mock()
        no_id_test_tool._invocation_duration_histogram = mock_histogram

        # Call invoke without tool_call_id
        result = await no_id_test_tool.invoke(x=5)

        # Verify result
        assert result == 10

        # Verify telemetry calls
        mock_start_span.assert_called_once_with(
            mock_tracer, no_id_test_tool, metadata={"tool_call_id": None, "kwargs": {"x": 5}}
        )

        # Verify histogram attributes
        mock_histogram.record.assert_called_once()
        call_args = mock_histogram.record.call_args
        attributes = call_args[1]["attributes"]
        assert attributes[GenAIAttributes.TOOL_CALL_ID.value] is None


async def test_ai_function_invoke_invalid_pydantic_args():
    """Test the ai_function invoke method with invalid Pydantic model arguments."""

    @ai_function(name="invalid_args_test", description="A test tool for invalid args")
    def invalid_args_test(x: int, y: int) -> int:
        """A function for testing invalid Pydantic args."""
        return x + y

    # Create a different Pydantic model
    class WrongModel(BaseModel):
        a: str
        b: str

    wrong_args = WrongModel(a="hello", b="world")

    # Call invoke with wrong model type
    with pytest.raises(TypeError, match="Expected invalid_args_test_input, got WrongModel"):
        await invalid_args_test.invoke(arguments=wrong_args)


# Tests for HostedCodeInterpreterTool and _parse_inputs


def test_hosted_code_interpreter_tool_default():
    """Test HostedCodeInterpreterTool with default parameters."""
    tool = HostedCodeInterpreterTool()

    assert tool.name == "code_interpreter"
    assert tool.inputs == []
    assert tool.description == ""
    assert tool.additional_properties is None
    assert str(tool) == "HostedCodeInterpreterTool(name=code_interpreter)"


def test_hosted_code_interpreter_tool_with_description():
    """Test HostedCodeInterpreterTool with description and additional properties."""
    tool = HostedCodeInterpreterTool(
        description="A test code interpreter",
        additional_properties={"version": "1.0", "language": "python"},
    )

    assert tool.name == "code_interpreter"
    assert tool.description == "A test code interpreter"
    assert tool.additional_properties == {"version": "1.0", "language": "python"}


def test_parse_inputs_none():
    """Test _parse_inputs with None input."""
    result = _parse_inputs(None)
    assert result == []


def test_parse_inputs_string():
    """Test _parse_inputs with string input."""
    from agent_framework import UriContent

    result = _parse_inputs("http://example.com")
    assert len(result) == 1
    assert isinstance(result[0], UriContent)
    assert result[0].uri == "http://example.com"
    assert result[0].media_type == "text/plain"


def test_parse_inputs_list_of_strings():
    """Test _parse_inputs with list of strings."""
    from agent_framework import UriContent

    inputs = ["http://example.com", "https://test.org"]
    result = _parse_inputs(inputs)

    assert len(result) == 2
    assert all(isinstance(item, UriContent) for item in result)
    assert result[0].uri == "http://example.com"
    assert result[1].uri == "https://test.org"
    assert all(item.media_type == "text/plain" for item in result)


def test_parse_inputs_uri_dict():
    """Test _parse_inputs with URI dictionary."""
    from agent_framework import UriContent

    input_dict = {"uri": "http://example.com", "media_type": "application/json"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert isinstance(result[0], UriContent)
    assert result[0].uri == "http://example.com"
    assert result[0].media_type == "application/json"


def test_parse_inputs_hosted_file_dict():
    """Test _parse_inputs with hosted file dictionary."""
    from agent_framework import HostedFileContent

    input_dict = {"file_id": "file-123"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert isinstance(result[0], HostedFileContent)
    assert result[0].file_id == "file-123"


def test_parse_inputs_hosted_vector_store_dict():
    """Test _parse_inputs with hosted vector store dictionary."""
    from agent_framework import HostedVectorStoreContent

    input_dict = {"vector_store_id": "vs-789"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert isinstance(result[0], HostedVectorStoreContent)
    assert result[0].vector_store_id == "vs-789"


def test_parse_inputs_data_dict():
    """Test _parse_inputs with data dictionary."""
    from agent_framework import DataContent

    input_dict = {"data": b"test data", "media_type": "application/octet-stream"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert isinstance(result[0], DataContent)
    assert result[0].uri == "data:application/octet-stream;base64,dGVzdCBkYXRh"
    assert result[0].media_type == "application/octet-stream"


def test_parse_inputs_ai_contents_instance():
    """Test _parse_inputs with AIContents instance."""
    from agent_framework import TextContent

    text_content = TextContent(text="Hello, world!")
    result = _parse_inputs(text_content)

    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    assert result[0].text == "Hello, world!"


def test_parse_inputs_mixed_list():
    """Test _parse_inputs with mixed input types."""
    from agent_framework import HostedFileContent, TextContent, UriContent

    inputs = [
        "http://example.com",  # string
        {"uri": "https://test.org", "media_type": "text/html"},  # URI dict
        {"file_id": "file-456"},  # hosted file dict
        TextContent(text="Hello"),  # AIContents instance
    ]

    result = _parse_inputs(inputs)

    assert len(result) == 4
    assert isinstance(result[0], UriContent)
    assert result[0].uri == "http://example.com"
    assert isinstance(result[1], UriContent)
    assert result[1].uri == "https://test.org"
    assert result[1].media_type == "text/html"
    assert isinstance(result[2], HostedFileContent)
    assert result[2].file_id == "file-456"
    assert isinstance(result[3], TextContent)
    assert result[3].text == "Hello"


def test_parse_inputs_unsupported_dict():
    """Test _parse_inputs with unsupported dictionary format."""
    input_dict = {"unsupported_key": "value"}

    with pytest.raises(ValueError, match="Unsupported input type"):
        _parse_inputs(input_dict)


def test_parse_inputs_unsupported_type():
    """Test _parse_inputs with unsupported input type."""
    with pytest.raises(TypeError, match="Unsupported input type: int"):
        _parse_inputs(123)


def test_hosted_code_interpreter_tool_with_string_input():
    """Test HostedCodeInterpreterTool with string input."""
    from agent_framework import UriContent

    tool = HostedCodeInterpreterTool(inputs="http://example.com")

    assert len(tool.inputs) == 1
    assert isinstance(tool.inputs[0], UriContent)
    assert tool.inputs[0].uri == "http://example.com"


def test_hosted_code_interpreter_tool_with_dict_inputs():
    """Test HostedCodeInterpreterTool with dictionary inputs."""
    from agent_framework import HostedFileContent, UriContent

    inputs = [{"uri": "http://example.com", "media_type": "text/html"}, {"file_id": "file-123"}]

    tool = HostedCodeInterpreterTool(inputs=inputs)

    assert len(tool.inputs) == 2
    assert isinstance(tool.inputs[0], UriContent)
    assert tool.inputs[0].uri == "http://example.com"
    assert tool.inputs[0].media_type == "text/html"
    assert isinstance(tool.inputs[1], HostedFileContent)
    assert tool.inputs[1].file_id == "file-123"


def test_hosted_code_interpreter_tool_with_ai_contents():
    """Test HostedCodeInterpreterTool with AIContents instances."""
    from agent_framework import DataContent, TextContent

    inputs = [TextContent(text="Hello, world!"), DataContent(data=b"test", media_type="text/plain")]

    tool = HostedCodeInterpreterTool(inputs=inputs)

    assert len(tool.inputs) == 2
    assert isinstance(tool.inputs[0], TextContent)
    assert tool.inputs[0].text == "Hello, world!"
    assert isinstance(tool.inputs[1], DataContent)
    assert tool.inputs[1].media_type == "text/plain"


def test_hosted_code_interpreter_tool_with_single_input():
    """Test HostedCodeInterpreterTool with single input (not in list)."""
    from agent_framework import HostedFileContent

    input_dict = {"file_id": "file-single"}
    tool = HostedCodeInterpreterTool(inputs=input_dict)

    assert len(tool.inputs) == 1
    assert isinstance(tool.inputs[0], HostedFileContent)
    assert tool.inputs[0].file_id == "file-single"


def test_hosted_code_interpreter_tool_with_unknown_input():
    """Test HostedCodeInterpreterTool with single unknown input."""
    with pytest.raises(ValueError, match="Unsupported input type"):
        HostedCodeInterpreterTool(inputs={"hosted_file": "file-single"})
