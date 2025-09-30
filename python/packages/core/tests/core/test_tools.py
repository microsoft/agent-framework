# Copyright (c) Microsoft. All rights reserved.
from typing import Any
from unittest.mock import Mock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from agent_framework import (
    AIFunction,
    HostedCodeInterpreterTool,
    HostedMCPTool,
    ToolProtocol,
    ai_function,
)
from agent_framework._tools import _parse_inputs
from agent_framework.exceptions import ToolException
from agent_framework.observability import OtelAttr

# region AIFunction and ai_function decorator tests


def test_ai_function_decorator():
    """Test the ai_function decorator."""

    @ai_function(name="test_tool", description="A test tool")
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, ToolProtocol)
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

    assert isinstance(test_tool, ToolProtocol)
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

    assert isinstance(async_test_tool, ToolProtocol)
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


async def test_ai_function_invoke_telemetry_enabled(span_exporter: InMemorySpanExporter):
    """Test the ai_function invoke method with telemetry enabled."""

    @ai_function(
        name="telemetry_test_tool",
        description="A test tool for telemetry",
    )
    def telemetry_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers for telemetry testing."""
        return x + y

    # Mock the histogram
    mock_histogram = Mock()
    telemetry_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke
    result = await telemetry_test_tool.invoke(x=1, y=2, tool_call_id="test_call_id")

    # Verify result
    assert result == 3

    # Verify telemetry calls
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "telemetry_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "telemetry_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool for telemetry"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 1, "y": 2}'
    assert span.attributes[OtelAttr.TOOL_RESULT] == "3"

    # Verify histogram was called with correct attributes
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    assert call_args[0][0] > 0  # duration should be positive
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] == "telemetry_test_tool"
    assert attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"


@pytest.mark.parametrize("enable_sensitive_data", [False], indirect=True)
async def test_ai_function_invoke_telemetry_sensitive_disabled(span_exporter: InMemorySpanExporter):
    """Test the ai_function invoke method with telemetry enabled."""

    @ai_function(
        name="telemetry_test_tool",
        description="A test tool for telemetry",
    )
    def telemetry_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers for telemetry testing."""
        return x + y

    # Mock the histogram
    mock_histogram = Mock()
    telemetry_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke
    result = await telemetry_test_tool.invoke(x=1, y=2, tool_call_id="test_call_id")

    # Verify result
    assert result == 3

    # Verify telemetry calls
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "telemetry_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "telemetry_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool for telemetry"
    assert OtelAttr.TOOL_ARGUMENTS not in span.attributes
    assert OtelAttr.TOOL_RESULT not in span.attributes

    # Verify histogram was called with correct attributes
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    assert call_args[0][0] > 0  # duration should be positive
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] == "telemetry_test_tool"
    assert attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"


async def test_ai_function_invoke_telemetry_with_pydantic_args(span_exporter: InMemorySpanExporter):
    """Test the ai_function invoke method with Pydantic model arguments."""

    @ai_function(
        name="pydantic_test_tool",
        description="A test tool with Pydantic args",
    )
    def pydantic_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers using Pydantic args."""
        return x + y

    # Create arguments as Pydantic model instance
    args_model = pydantic_test_tool.input_model(x=5, y=10)

    mock_histogram = Mock()
    pydantic_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke with Pydantic model
    result = await pydantic_test_tool.invoke(arguments=args_model, tool_call_id="pydantic_call")

    # Verify result
    assert result == 15
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "pydantic_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "pydantic_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "pydantic_call"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool with Pydantic args"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x":5,"y":10}'


async def test_ai_function_invoke_telemetry_with_exception(span_exporter: InMemorySpanExporter):
    """Test the ai_function invoke method with telemetry when an exception occurs."""

    @ai_function(
        name="exception_test_tool",
        description="A test tool that raises an exception",
    )
    def exception_test_tool(x: int, y: int) -> int:
        """A function that raises an exception for telemetry testing."""
        raise ValueError("Test exception for telemetry")

    mock_histogram = Mock()
    exception_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke and expect exception
    with pytest.raises(ValueError, match="Test exception for telemetry"):
        await exception_test_tool.invoke(x=1, y=2, tool_call_id="exception_call")
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "exception_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "exception_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "exception_call"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool that raises an exception"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 1, "y": 2}'
    assert span.attributes[OtelAttr.ERROR_TYPE] == ValueError.__name__
    assert span.status.status_code == trace.StatusCode.ERROR

    # Verify histogram was called with error attributes
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.ERROR_TYPE] == ValueError.__name__


async def test_ai_function_invoke_telemetry_async_function(span_exporter: InMemorySpanExporter):
    """Test the ai_function invoke method with telemetry on async function."""

    @ai_function(
        name="async_telemetry_test",
        description="An async test tool for telemetry",
    )
    async def async_telemetry_test(x: int, y: int) -> int:
        """An async function for telemetry testing."""
        return x * y

    mock_histogram = Mock()
    async_telemetry_test._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke
    result = await async_telemetry_test.invoke(x=3, y=4, tool_call_id="async_call")

    # Verify result
    assert result == 12
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "async_telemetry_test" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "async_telemetry_test"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "async_call"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "An async test tool for telemetry"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 3, "y": 4}'

    # Verify histogram recording
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] == "async_telemetry_test"


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


# region HostedCodeInterpreterTool and _parse_inputs


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
    """Test _parse_inputs with Contents instance."""
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
        TextContent(text="Hello"),  # Contents instance
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
    """Test HostedCodeInterpreterTool with Contents instances."""
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


# region HostedMCPTool tests


def test_hosted_mcp_tool_with_other_fields():
    """Test creating a HostedMCPTool with a specific approval dict, headers and additional properties."""
    tool = HostedMCPTool(
        name="mcp-tool",
        url="https://mcp.example",
        description="A test MCP tool",
        headers={"x": "y"},
        additional_properties={"p": 1},
    )

    assert tool.name == "mcp-tool"
    # pydantic AnyUrl preserves as string-like
    assert str(tool.url).startswith("https://")
    assert tool.headers == {"x": "y"}
    assert tool.additional_properties == {"p": 1}
    assert tool.description == "A test MCP tool"


@pytest.mark.parametrize(
    "approval_mode",
    [
        "always_require",
        "never_require",
        {
            "always_require_approval": {"toolA"},
            "never_require_approval": {"toolB"},
        },
        {
            "always_require_approval": ["toolA"],
            "never_require_approval": ("toolB",),
        },
    ],
    ids=["always_require", "never_require", "specific", "specific_with_parsing"],
)
def test_hosted_mcp_tool_with_approval_mode(approval_mode: str | dict[str, Any]):
    """Test creating a HostedMCPTool with a specific approval dict, headers and additional properties."""
    tool = HostedMCPTool(name="mcp-tool", url="https://mcp.example", approval_mode=approval_mode)

    assert tool.name == "mcp-tool"
    # pydantic AnyUrl preserves as string-like
    assert str(tool.url).startswith("https://")
    if not isinstance(approval_mode, dict):
        assert tool.approval_mode == approval_mode
    else:
        # approval_mode parsed to sets
        assert isinstance(tool.approval_mode["always_require_approval"], set)
        assert isinstance(tool.approval_mode["never_require_approval"], set)
        assert "toolA" in tool.approval_mode["always_require_approval"]
        assert "toolB" in tool.approval_mode["never_require_approval"]


def test_hosted_mcp_tool_invalid_approval_mode_raises():
    """Invalid approval_mode string should raise ServiceInitializationError."""
    with pytest.raises(ToolException):
        HostedMCPTool(name="bad", url="https://x", approval_mode="invalid_mode")


@pytest.mark.parametrize(
    "tools",
    [
        {"toolA", "toolB"},
        ("toolA", "toolB"),
        ["toolA", "toolB"],
        ["toolA", "toolB", "toolA"],
    ],
    ids=[
        "set",
        "tuple",
        "list",
        "list_with_duplicates",
    ],
)
def test_hosted_mcp_tool_with_allowed_tools(tools: list[str] | tuple[str, ...] | set[str]):
    """Test creating a HostedMCPTool with a list of allowed tools."""
    tool = HostedMCPTool(
        name="mcp-tool",
        url="https://mcp.example",
        allowed_tools=tools,
    )

    assert tool.name == "mcp-tool"
    # pydantic AnyUrl preserves as string-like
    assert str(tool.url).startswith("https://")
    # approval_mode parsed to set
    assert isinstance(tool.allowed_tools, set)
    assert tool.allowed_tools == {"toolA", "toolB"}


def test_hosted_mcp_tool_with_dict_of_allowed_tools():
    """Test creating a HostedMCPTool with a dict of allowed tools."""
    with pytest.raises(ToolException):
        HostedMCPTool(
            name="mcp-tool",
            url="https://mcp.example",
            allowed_tools={"toolA": "Tool A", "toolC": "Tool C"},
        )
