# Copyright (c) Microsoft. All rights reserved.

import base64
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field, ValidationError
from pytest import fixture, mark, raises

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Annotation,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReason,
    Role,
    TextSpanRegion,
    ToolMode,
    ToolProtocol,
    UsageDetails,
    detect_media_type_from_base64,
    merge_chat_options,
    prepare_function_call_results,
    tool,
)
from agent_framework._types import (
    _get_data_bytes,
    _get_data_bytes_as_str,
    _parse_content_list,
    _validate_uri,
    add_usage_details,
    validate_tool_mode,
)
from agent_framework.exceptions import ContentError


@fixture
def ai_tool() -> ToolProtocol:
    """Returns a generic ToolProtocol."""

    class GenericTool(BaseModel):
        name: str
        description: str | None = None
        additional_properties: dict[str, Any] | None = None

        def parameters(self) -> dict[str, Any]:
            """Return the parameters of the tool as a JSON schema."""
            return {
                "name": {"type": "string"},
            }

    return GenericTool(name="generic_tool", description="A generic tool")


@fixture
def tool_tool() -> ToolProtocol:
    """Returns a executable ToolProtocol."""

    @tool
    def simple_function(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    return simple_function


# region TextContent


def test_text_content_positional():
    """Test the TextContent class to ensure it initializes correctly and inherits from Content."""
    # Create an instance of TextContent
    content = Content.from_text(
        "Hello, world!", raw_representation="Hello, world!", additional_properties={"version": 1}
    )

    # Check the type and content
    assert content.type == "text"
    assert content.text == "Hello, world!"
    assert content.raw_representation == "Hello, world!"
    assert content.additional_properties["version"] == 1
    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)
    # Note: No longer using Pydantic validation, so type assignment should work
    content.type = "text"  # This should work fine now


def test_text_content_keyword():
    """Test the TextContent class to ensure it initializes correctly and inherits from Content."""
    # Create an instance of TextContent
    content = Content.from_text(
        text="Hello, world!", raw_representation="Hello, world!", additional_properties={"version": 1}
    )

    # Check the type and content
    assert content.type == "text"
    assert content.text == "Hello, world!"
    assert content.raw_representation == "Hello, world!"
    assert content.additional_properties["version"] == 1
    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)
    # Note: No longer using Pydantic validation, so type assignment should work
    content.type = "text"  # This should work fine now


# region DataContent


def test_data_content_bytes():
    """Test the DataContent class to ensure it initializes correctly."""
    # Create an instance of DataContent
    content = Content.from_data(
        data=b"test", media_type="application/octet-stream", additional_properties={"version": 1}
    )

    # Check the type and content
    assert content.type == "data"
    assert content.uri == "data:application/octet-stream;base64,dGVzdA=="
    assert content.media_type.startswith("application/") is True
    assert content.media_type.startswith("image/") is False
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)


def test_data_content_uri():
    """Test the Content.from_uri class to ensure it initializes correctly with a URI."""
    # Create an instance of Content.from_uri with a URI and explicit media_type
    content = Content.from_uri(
        uri="data:application/octet-stream;base64,dGVzdA==",
        media_type="application/octet-stream",
        additional_properties={"version": 1},
    )

    # Check the type and content
    assert content.type == "data"
    assert content.uri == "data:application/octet-stream;base64,dGVzdA=="
    # media_type must be explicitly provided
    assert content.media_type == "application/octet-stream"
    assert content.media_type.startswith("application/") is True
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)


def test_data_content_invalid():
    """Test the DataContent class to ensure it raises an error for invalid initialization."""
    with pytest.raises(ContentError):
        Content.from_uri(uri="invalid_uri", media_type="text/plain")


def test_data_content_empty():
    """Test the DataContent class to ensure it raises an error for empty data."""
    data = Content.from_data(data=b"", media_type="application/octet-stream")
    assert data.uri == "data:application/octet-stream;base64,"
    assert data.media_type == "application/octet-stream"


def test_data_content_detect_image_format_from_base64():
    """Test the detect_image_format_from_base64 static method."""
    # Test each supported format
    png_data = b"\x89PNG\r\n\x1a\n" + b"fake_data"
    assert detect_media_type_from_base64(data_bytes=png_data) == "image/png"
    assert detect_media_type_from_base64(data_str=base64.b64encode(png_data).decode()) == "image/png"

    jpeg_data = b"\xff\xd8\xff\xe0" + b"fake_data"
    assert detect_media_type_from_base64(data_bytes=jpeg_data) == "image/jpeg"
    assert detect_media_type_from_base64(data_str=base64.b64encode(jpeg_data).decode()) == "image/jpeg"

    webp_data = b"RIFF" + b"1234" + b"WEBP" + b"fake_data"
    assert detect_media_type_from_base64(data_str=base64.b64encode(webp_data).decode()) == "image/webp"
    gif_data = b"GIF89a" + b"fake_data"
    assert detect_media_type_from_base64(data_str=base64.b64encode(gif_data).decode()) == "image/gif"

    # Test fallback behavior
    unknown_data = b"UNKNOWN_FORMAT"
    assert detect_media_type_from_base64(data_str=base64.b64encode(unknown_data).decode()) is None
    assert (
        detect_media_type_from_base64(
            data_uri=f"data:application/octet-stream;base64,{base64.b64encode(unknown_data).decode()}"
        )
        is None
    )
    assert detect_media_type_from_base64(data_bytes=unknown_data) is None
    # Test error handling
    with pytest.raises(ValueError, match="Invalid base64 data provided."):
        detect_media_type_from_base64(data_str="invalid_base64!")
        detect_media_type_from_base64(data_str="")

    with pytest.raises(ValueError, match="Provide exactly one of data_bytes, data_str, or data_uri."):
        detect_media_type_from_base64()
        detect_media_type_from_base64(
            data_bytes=b"data", data_str="data", data_uri="data:application/octet-stream;base64,AAA"
        )
        detect_media_type_from_base64(data_bytes=b"data", data_str="data")
        detect_media_type_from_base64(data_bytes=b"data", data_uri="data:application/octet-stream;base64,AAA")
        detect_media_type_from_base64(data_str="data", data_uri="data:application/octet-stream;base64,AAA")


def test_data_content_create_data_uri_from_base64():
    """Test the create_data_uri_from_base64 class method."""
    # Test with PNG data
    png_data = b"\x89PNG\r\n\x1a\n" + b"fake_data"
    content = Content.from_data(png_data, media_type=detect_media_type_from_base64(data_bytes=png_data))

    assert content.uri == f"data:image/png;base64,{base64.b64encode(png_data).decode()}"
    assert content.media_type == "image/png"

    # Test with different format
    jpeg_data = b"\xff\xd8\xff\xe0" + b"fake_data"
    jpeg_base64 = base64.b64encode(jpeg_data).decode()
    content = Content.from_data(jpeg_data, media_type=detect_media_type_from_base64(data_bytes=jpeg_data))

    assert content.uri == f"data:image/jpeg;base64,{jpeg_base64}"
    assert content.media_type == "image/jpeg"


# region UriContent


def test_uri_content():
    """Test the UriContent class to ensure it initializes correctly."""
    content = Content.from_uri(uri="http://example.com", media_type="image/jpg", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "uri"
    assert content.uri == "http://example.com"
    assert content.media_type == "image/jpg"
    assert content.media_type.startswith("image/") is True
    assert content.media_type.startswith("application/") is False
    assert content.additional_properties["version"] == 1
    assert isinstance(content, Content)


# region: HostedFileContent


def test_hosted_file_content():
    """Test the HostedFileContent class to ensure it initializes correctly."""
    content = Content.from_hosted_file(file_id="file-123", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "hosted_file"
    assert content.file_id == "file-123"
    assert content.additional_properties["version"] == 1
    assert isinstance(content, Content)


def test_hosted_file_content_minimal():
    """Test the HostedFileContent class with minimal parameters."""
    content = Content.from_hosted_file(file_id="file-456")

    # Check the type and content
    assert content.type == "hosted_file"
    assert content.file_id == "file-456"
    assert content.additional_properties == {}
    assert content.raw_representation is None
    assert isinstance(content, Content)


def test_hosted_file_content_optional_fields():
    """HostedFileContent should capture optional media type and name."""
    content = Content.from_hosted_file(file_id="file-789", media_type="image/png", name="plot.png")

    assert content.media_type == "image/png"
    assert content.name == "plot.png"
    assert content.media_type.startswith("image/")
    assert content.media_type.startswith("application/") is False


# region: CodeInterpreter content


def test_code_interpreter_tool_call_content_parses_inputs():
    call = Content.from_code_interpreter_tool_call(
        call_id="call-1",
        inputs=[Content.from_text(text="print('hi')")],
    )

    assert call.type == "code_interpreter_tool_call"
    assert call.call_id == "call-1"
    assert call.inputs and call.inputs[0].type == "text"
    assert call.inputs[0].text == "print('hi')"


def test_code_interpreter_tool_result_content_outputs():
    result = Content.from_code_interpreter_tool_result(
        call_id="call-2",
        outputs=[
            Content.from_text(text="log output"),
            Content.from_uri(uri="https://example.com/file.png", media_type="image/png"),
        ],
    )

    assert result.type == "code_interpreter_tool_result"
    assert result.call_id == "call-2"
    assert result.outputs is not None
    assert result.outputs[0].type == "text"
    assert result.outputs[1].type == "uri"


# region: Image generation content


def test_image_generation_tool_contents():
    call = Content.from_image_generation_tool_call(image_id="img-1")
    outputs = [Content.from_data(data=b"1234", media_type="image/png")]
    result = Content.from_image_generation_tool_result(image_id="img-1", outputs=outputs)

    assert call.type == "image_generation_tool_call"
    assert call.image_id == "img-1"
    assert result.type == "image_generation_tool_result"
    assert result.image_id == "img-1"
    assert result.outputs and result.outputs[0].type == "data"


# region: MCP server tool content


def test_mcp_server_tool_call_and_result():
    call = Content.from_mcp_server_tool_call(call_id="c-1", tool_name="tool", server_name="server", arguments={"x": 1})
    assert call.type == "mcp_server_tool_call"
    assert call.arguments == {"x": 1}

    result = Content.from_mcp_server_tool_result(call_id="c-1", output=[{"type": "text", "text": "done"}])
    assert result.type == "mcp_server_tool_result"
    assert result.output

    # Empty call_id is allowed, validation happens elsewhere
    call2 = Content.from_mcp_server_tool_call(call_id="", tool_name="tool", server_name="server")
    assert call2.call_id == ""


# region: HostedVectorStoreContent


def test_hosted_vector_store_content():
    """Test the HostedVectorStoreContent class to ensure it initializes correctly."""
    content = Content.from_hosted_vector_store(vector_store_id="vs-789", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "hosted_vector_store"
    assert content.vector_store_id == "vs-789"
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)
    assert content.type == "hosted_vector_store"
    assert isinstance(content, Content)


def test_hosted_vector_store_content_minimal():
    """Test the HostedVectorStoreContent class with minimal parameters."""
    content = Content.from_hosted_vector_store(vector_store_id="vs-101112")

    # Check the type and content
    assert content.type == "hosted_vector_store"
    assert content.vector_store_id == "vs-101112"
    assert content.additional_properties == {}
    assert content.raw_representation is None


# region FunctionCallContent


def test_function_call_content():
    """Test the FunctionCallContent class to ensure it initializes correctly."""
    content = Content.from_function_call(call_id="1", name="example_function", arguments={"param1": "value1"})

    # Check the type and content
    assert content.type == "function_call"
    assert content.name == "example_function"
    assert content.arguments == {"param1": "value1"}

    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)


def test_function_call_content_parse_arguments():
    c1 = Content.from_function_call(call_id="1", name="f", arguments='{"a": 1, "b": 2}')
    assert c1.parse_arguments() == {"a": 1, "b": 2}
    c2 = Content.from_function_call(call_id="1", name="f", arguments="not json")
    assert c2.parse_arguments() == {"raw": "not json"}
    c3 = Content.from_function_call(call_id="1", name="f", arguments={"x": None})
    assert c3.parse_arguments() == {"x": None}


def test_function_call_content_add_merging_and_errors():
    # str + str concatenation
    a = Content.from_function_call(call_id="1", name="f", arguments="abc")
    b = Content.from_function_call(call_id="1", name="f", arguments="def")
    c = a + b
    assert isinstance(c.arguments, str) and c.arguments == "abcdef"

    # dict + dict merge
    a = Content.from_function_call(call_id="1", name="f", arguments={"x": 1})
    b = Content.from_function_call(call_id="1", name="f", arguments={"y": 2})
    c = a + b
    assert c.arguments == {"x": 1, "y": 2}

    # incompatible argument types
    a = Content.from_function_call(call_id="1", name="f", arguments="abc")
    b = Content.from_function_call(call_id="1", name="f", arguments={"y": 2})
    with raises(TypeError):
        _ = a + b

    # incompatible call ids
    a = Content.from_function_call(call_id="1", name="f", arguments="abc")
    b = Content.from_function_call(call_id="2", name="f", arguments="def")

    with raises(ContentError):
        _ = a + b


# region FunctionResultContent


def test_function_result_content():
    """Test the FunctionResultContent class to ensure it initializes correctly."""
    content = Content.from_function_result(call_id="1", result={"param1": "value1"})

    # Check the type and content
    assert content.type == "function_result"
    assert content.result == {"param1": "value1"}

    # Ensure the instance is of type BaseContent
    assert isinstance(content, Content)


# region UsageDetails


def test_usage_details():
    usage = UsageDetails(input_token_count=5, output_token_count=10, total_token_count=15)
    assert usage["input_token_count"] == 5
    assert usage["output_token_count"] == 10
    assert usage["total_token_count"] == 15
    assert usage.get("additional_counts", {}) == {}


def test_usage_details_addition():
    usage1 = UsageDetails(
        input_token_count=5,
        output_token_count=10,
        total_token_count=15,
        test1=10,
        test2=20,
    )
    usage2 = UsageDetails(
        input_token_count=3,
        output_token_count=6,
        total_token_count=9,
        test1=10,
        test3=30,
    )

    combined_usage = add_usage_details(usage1, usage2)
    assert combined_usage["input_token_count"] == 8
    assert combined_usage["output_token_count"] == 16
    assert combined_usage["total_token_count"] == 24
    assert combined_usage["test1"] == 20
    assert combined_usage["test2"] == 20
    assert combined_usage["test3"] == 30


def test_usage_details_fail():
    # TypedDict doesn't validate types at runtime, so this test no longer applies
    # Creating UsageDetails with wrong types won't raise ValueError
    usage = UsageDetails(input_token_count=5, output_token_count=10, total_token_count=15, wrong_type="42.923")  # type: ignore[typeddict-item]
    assert usage["wrong_type"] == "42.923"  # type: ignore[typeddict-item]


def test_usage_details_additional_counts():
    usage = UsageDetails(input_token_count=5, output_token_count=10, total_token_count=15, **{"test": 1})
    assert usage.get("test") == 1


def test_usage_details_add_with_none_and_type_errors():
    u = UsageDetails(input_token_count=1)
    # add_usage_details with None returns the non-None value
    v = add_usage_details(u, None)
    assert v == u
    # add_usage_details with None on left
    v2 = add_usage_details(None, u)
    assert v2 == u
    # TypedDict doesn't support + operator, use add_usage_details


# region UserInputRequest and Response


def test_function_approval_request_and_response_creation():
    """Test creating a FunctionApprovalRequestContent and producing a response."""
    fc = Content.from_function_call(call_id="call-1", name="do_something", arguments={"a": 1})
    req = Content.from_function_approval_request(id="req-1", function_call=fc)

    assert req.type == "function_approval_request"
    assert req.function_call == fc
    assert req.id == "req-1"
    assert isinstance(req, Content)

    resp = req.to_function_approval_response(True)

    assert isinstance(resp, Content)
    assert resp.type == "function_approval_response"
    assert resp.approved is True
    assert resp.function_call == fc
    assert resp.id == "req-1"


def test_function_approval_serialization_roundtrip():
    fc = Content.from_function_call(call_id="c2", name="f", arguments='{"x":1}')
    req = Content.from_function_approval_request(id="id-2", function_call=fc, additional_properties={"meta": 1})

    dumped = req.to_dict()
    loaded = Content.from_dict(dumped)

    # Test that the basic properties match
    assert loaded.id == req.id
    assert loaded.additional_properties == req.additional_properties
    assert loaded.function_call.call_id == req.function_call.call_id
    assert loaded.function_call.name == req.function_call.name
    assert loaded.function_call.arguments == req.function_call.arguments

    # Skip the BaseModel validation test since we're no longer using Pydantic
    # The Content union will need to be handled differently when we fully migrate


def test_function_approval_accepts_mcp_call():
    """Ensure FunctionApprovalRequestContent supports MCP server tool calls."""
    mcp_call = Content.from_mcp_server_tool_call(
        call_id="c-mcp", tool_name="tool", server_name="srv", arguments={"x": 1}
    )
    req = Content.from_function_approval_request(id="req-mcp", function_call=mcp_call)

    assert isinstance(req.function_call, Content)
    assert req.function_call.call_id == "c-mcp"


# region BaseContent Serialization


@mark.parametrize(
    "args",
    [
        {"type": "text", "text": "Hello, world!"},
        {"type": "uri", "uri": "http://example.com", "media_type": "text/html"},
        {"type": "function_call", "call_id": "1", "name": "example_function", "arguments": {}},
        {"type": "function_result", "call_id": "1", "result": {}},
        {"type": "file", "file_id": "file-123"},
        {"type": "vector_store", "vector_store_id": "vs-789"},
    ],
)
def test_ai_content_serialization(args: dict):
    content = Content(**args)
    serialized = content.to_dict()
    deserialized = Content.from_dict(serialized)
    assert content == deserialized


# region ChatMessage


def test_chat_message_text():
    """Test the ChatMessage class to ensure it initializes correctly with text content."""
    # Create a ChatMessage with a role and text content
    message = ChatMessage(role="user", text="Hello, how are you?")

    # Check the type and content
    assert message.role == Role.USER
    assert len(message.contents) == 1
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "Hello, how are you?"
    assert message.text == "Hello, how are you?"

    # Ensure the instance is of type BaseContent
    assert isinstance(message.contents[0], Content)


def test_chat_message_contents():
    """Test the ChatMessage class to ensure it initializes correctly with contents."""
    # Create a ChatMessage with a role and multiple contents
    content1 = Content.from_text("Hello, how are you?")
    content2 = Content.from_text("I'm fine, thank you!")
    message = ChatMessage(role="user", contents=[content1, content2])

    # Check the type and content
    assert message.role == Role.USER
    assert len(message.contents) == 2
    assert message.contents[0].type == "text"
    assert message.contents[1].type == "text"
    assert message.contents[0].text == "Hello, how are you?"
    assert message.contents[1].text == "I'm fine, thank you!"
    assert message.text == "Hello, how are you? I'm fine, thank you!"


def test_chat_message_with_chatrole_instance():
    m = ChatMessage(role=Role.USER, text="hi")
    assert m.role == Role.USER
    assert m.text == "hi"


# region ChatResponse


def test_chat_response():
    """Test the ChatResponse class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = ChatMessage(role="assistant", text="I'm doing well, thank you!")

    # Create a ChatResponse with the message
    response = ChatResponse(messages=message)

    # Check the type and content
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "I'm doing well, thank you!"
    assert isinstance(response.messages[0], ChatMessage)
    # __str__ returns text
    assert str(response) == response.text


class OutputModel(BaseModel):
    response: str


def test_chat_response_with_format():
    """Test the ChatResponse class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = ChatMessage(role="assistant", text='{"response": "Hello"}')

    # Create a ChatResponse with the message
    response = ChatResponse(messages=message)

    # Check the type and content
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == '{"response": "Hello"}'
    assert isinstance(response.messages[0], ChatMessage)
    assert response.text == '{"response": "Hello"}'
    assert response.value is None
    response.try_parse_value(OutputModel)
    assert response.value is not None
    assert response.value.response == "Hello"


def test_chat_response_with_format_init():
    """Test the ChatResponse class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = ChatMessage(role="assistant", text='{"response": "Hello"}')

    # Create a ChatResponse with the message
    response = ChatResponse(messages=message, response_format=OutputModel)

    # Check the type and content
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == '{"response": "Hello"}'
    assert isinstance(response.messages[0], ChatMessage)
    assert response.text == '{"response": "Hello"}'
    assert response.value is not None
    assert response.value.response == "Hello"


def test_chat_response_value_raises_on_invalid_schema():
    """Test that value property raises ValidationError with field constraint details."""

    class StrictSchema(BaseModel):
        id: Literal[5]
        name: str = Field(min_length=10)
        score: int = Field(gt=0, le=100)

    message = ChatMessage(role="assistant", text='{"id": 1, "name": "test", "score": -5}')
    response = ChatResponse(messages=message, response_format=StrictSchema)

    with raises(ValidationError) as exc_info:
        _ = response.value

    errors = exc_info.value.errors()
    error_fields = {e["loc"][0] for e in errors}
    assert "id" in error_fields, "Expected 'id' Literal constraint error"
    assert "name" in error_fields, "Expected 'name' min_length constraint error"
    assert "score" in error_fields, "Expected 'score' gt constraint error"


def test_chat_response_try_parse_value_returns_none_on_invalid():
    """Test that try_parse_value returns None on validation failure with Field constraints."""

    class StrictSchema(BaseModel):
        id: Literal[5]
        name: str = Field(min_length=10)
        score: int = Field(gt=0, le=100)

    message = ChatMessage(role="assistant", text='{"id": 1, "name": "test", "score": -5}')
    response = ChatResponse(messages=message)

    result = response.try_parse_value(StrictSchema)
    assert result is None


def test_chat_response_try_parse_value_returns_value_on_success():
    """Test that try_parse_value returns parsed value when all constraints pass."""

    class MySchema(BaseModel):
        name: str = Field(min_length=3)
        score: int = Field(ge=0, le=100)

    message = ChatMessage(role="assistant", text='{"name": "test", "score": 85}')
    response = ChatResponse(messages=message)

    result = response.try_parse_value(MySchema)
    assert result is not None
    assert result.name == "test"
    assert result.score == 85


def test_agent_response_value_raises_on_invalid_schema():
    """Test that AgentResponse.value property raises ValidationError with field constraint details."""

    class StrictSchema(BaseModel):
        id: Literal[5]
        name: str = Field(min_length=10)
        score: int = Field(gt=0, le=100)

    message = ChatMessage(role="assistant", text='{"id": 1, "name": "test", "score": -5}')
    response = AgentResponse(messages=message, response_format=StrictSchema)

    with raises(ValidationError) as exc_info:
        _ = response.value

    errors = exc_info.value.errors()
    error_fields = {e["loc"][0] for e in errors}
    assert "id" in error_fields, "Expected 'id' Literal constraint error"
    assert "name" in error_fields, "Expected 'name' min_length constraint error"
    assert "score" in error_fields, "Expected 'score' gt constraint error"


def test_agent_response_try_parse_value_returns_none_on_invalid():
    """Test that AgentResponse.try_parse_value returns None on Field constraint failure."""

    class StrictSchema(BaseModel):
        id: Literal[5]
        name: str = Field(min_length=10)
        score: int = Field(gt=0, le=100)

    message = ChatMessage(role="assistant", text='{"id": 1, "name": "test", "score": -5}')
    response = AgentResponse(messages=message)

    result = response.try_parse_value(StrictSchema)
    assert result is None


def test_agent_response_try_parse_value_returns_value_on_success():
    """Test that AgentResponse.try_parse_value returns parsed value when all constraints pass."""

    class MySchema(BaseModel):
        name: str = Field(min_length=3)
        score: int = Field(ge=0, le=100)

    message = ChatMessage(role="assistant", text='{"name": "test", "score": 85}')
    response = AgentResponse(messages=message)

    result = response.try_parse_value(MySchema)
    assert result is not None
    assert result.name == "test"
    assert result.score == 85


# region ChatResponseUpdate


def test_chat_response_update():
    """Test the ChatResponseUpdate class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = Content.from_text(text="I'm doing well, thank you!")

    # Create a ChatResponseUpdate with the message
    response_update = ChatResponseUpdate(contents=[message])

    # Check the type and content
    assert response_update.contents[0].text == "I'm doing well, thank you!"
    assert response_update.contents[0].type == "text"
    assert response_update.text == "I'm doing well, thank you!"


def test_chat_response_updates_to_chat_response_one():
    """Test converting ChatResponseUpdate to ChatResponse."""
    # Create a ChatMessage
    message1 = Content.from_text("I'm doing well, ")
    message2 = Content.from_text("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [
        ChatResponseUpdate(text=message1, message_id="1"),
        ChatResponseUpdate(text=message2, message_id="1"),
    ]

    # Convert to ChatResponse
    chat_response = ChatResponse.from_chat_response_updates(response_updates)

    # Check the type and content
    assert len(chat_response.messages) == 1
    assert chat_response.text == "I'm doing well, thank you!"
    assert isinstance(chat_response.messages[0], ChatMessage)
    assert len(chat_response.messages[0].contents) == 1
    assert chat_response.messages[0].message_id == "1"


def test_chat_response_updates_to_chat_response_two():
    """Test converting ChatResponseUpdate to ChatResponse."""
    # Create a ChatMessage
    message1 = Content.from_text("I'm doing well, ")
    message2 = Content.from_text("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [
        ChatResponseUpdate(text=message1, message_id="1"),
        ChatResponseUpdate(text=message2, message_id="2"),
    ]

    # Convert to ChatResponse
    chat_response = ChatResponse.from_chat_response_updates(response_updates)

    # Check the type and content
    assert len(chat_response.messages) == 2
    assert chat_response.text == "I'm doing well, \nthank you!"
    assert isinstance(chat_response.messages[0], ChatMessage)
    assert chat_response.messages[0].message_id == "1"
    assert isinstance(chat_response.messages[1], ChatMessage)
    assert chat_response.messages[1].message_id == "2"


def test_chat_response_updates_to_chat_response_multiple():
    """Test converting ChatResponseUpdate to ChatResponse."""
    # Create a ChatMessage
    message1 = Content.from_text("I'm doing well, ")
    message2 = Content.from_text("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [
        ChatResponseUpdate(text=message1, message_id="1"),
        ChatResponseUpdate(contents=[Content.from_text_reasoning(text="Additional context")], message_id="1"),
        ChatResponseUpdate(text=message2, message_id="1"),
    ]

    # Convert to ChatResponse
    chat_response = ChatResponse.from_chat_response_updates(response_updates)

    # Check the type and content
    assert len(chat_response.messages) == 1
    assert chat_response.text == "I'm doing well,  thank you!"
    assert isinstance(chat_response.messages[0], ChatMessage)
    assert len(chat_response.messages[0].contents) == 3
    assert chat_response.messages[0].message_id == "1"


def test_chat_response_updates_to_chat_response_multiple_multiple():
    """Test converting ChatResponseUpdate to ChatResponse."""
    # Create a ChatMessage
    message1 = Content.from_text("I'm doing well, ", raw_representation="I'm doing well, ")
    message2 = Content.from_text("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [
        ChatResponseUpdate(text=message1, message_id="1"),
        ChatResponseUpdate(text=message2, message_id="1"),
        ChatResponseUpdate(contents=[Content.from_text_reasoning(text="Additional context")], message_id="1"),
        ChatResponseUpdate(contents=[Content.from_text(text="More context")], message_id="1"),
        ChatResponseUpdate(text="Final part", message_id="1"),
    ]

    # Convert to ChatResponse
    chat_response = ChatResponse.from_chat_response_updates(response_updates)

    # Check the type and content
    assert len(chat_response.messages) == 1
    assert isinstance(chat_response.messages[0], ChatMessage)
    assert chat_response.messages[0].message_id == "1"
    assert chat_response.messages[0].contents[0].raw_representation is not None

    assert len(chat_response.messages[0].contents) == 3
    assert chat_response.messages[0].contents[0].type == "text"
    assert chat_response.messages[0].contents[0].text == "I'm doing well, thank you!"
    assert chat_response.messages[0].contents[1].type == "text_reasoning"
    assert chat_response.messages[0].contents[1].text == "Additional context"
    assert chat_response.messages[0].contents[2].type == "text"
    assert chat_response.messages[0].contents[2].text == "More contextFinal part"

    assert chat_response.text == "I'm doing well, thank you! More contextFinal part"


async def test_chat_response_from_async_generator():
    async def gen() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(text="Hello", message_id="1")
        yield ChatResponseUpdate(text=" world", message_id="1")

    resp = await ChatResponse.from_chat_response_generator(gen())
    assert resp.text == "Hello world"


async def test_chat_response_from_async_generator_output_format():
    async def gen() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(text='{ "respon', message_id="1")
        yield ChatResponseUpdate(text='se": "Hello" }', message_id="1")

    resp = await ChatResponse.from_chat_response_generator(gen())
    assert resp.text == '{ "response": "Hello" }'
    assert resp.value is None
    resp.try_parse_value(OutputModel)
    assert resp.value is not None
    assert resp.value.response == "Hello"


async def test_chat_response_from_async_generator_output_format_in_method():
    async def gen() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(text='{ "respon', message_id="1")
        yield ChatResponseUpdate(text='se": "Hello" }', message_id="1")

    resp = await ChatResponse.from_chat_response_generator(gen(), output_format_type=OutputModel)
    assert resp.text == '{ "response": "Hello" }'
    assert resp.value is not None
    assert resp.value.response == "Hello"


# region ToolMode


def test_chat_tool_mode():
    """Test the ToolMode class to ensure it initializes correctly."""
    # Create instances of ToolMode
    auto_mode: ToolMode = {"mode": "auto"}
    required_any: ToolMode = {"mode": "required"}
    required_mode: ToolMode = {"mode": "required", "required_function_name": "example_function"}
    none_mode: ToolMode = {"mode": "none"}

    # Check the type and content
    assert auto_mode["mode"] == "auto"
    assert "required_function_name" not in auto_mode
    assert required_any["mode"] == "required"
    assert "required_function_name" not in required_any
    assert required_mode["mode"] == "required"
    assert required_mode["required_function_name"] == "example_function"
    assert none_mode["mode"] == "none"
    assert "required_function_name" not in none_mode

    # equality of dicts
    assert {"mode": "required", "required_function_name": "example_function"} == {
        "mode": "required",
        "required_function_name": "example_function",
    }


def test_chat_tool_mode_from_dict():
    """Test creating ToolMode from a dictionary."""
    mode: ToolMode = {"mode": "required", "required_function_name": "example_function"}

    # Check the type and content
    assert mode["mode"] == "required"
    assert mode["required_function_name"] == "example_function"


# region ChatOptions


def test_chat_options_init() -> None:
    """Test that ChatOptions can be created as a TypedDict."""
    options: ChatOptions = {}
    assert options.get("model_id") is None

    # With values
    options_with_model: ChatOptions = {"model_id": "gpt-4o", "temperature": 0.7}
    assert options_with_model.get("model_id") == "gpt-4o"
    assert options_with_model.get("temperature") == 0.7


def test_chat_options_tool_choice_validation():
    """Test validate_tool_mode utility function."""
    # Valid string values
    assert validate_tool_mode("auto") == {"mode": "auto"}
    assert validate_tool_mode("required") == {"mode": "required"}
    assert validate_tool_mode("none") == {"mode": "none"}

    # Valid ToolMode dict values
    assert validate_tool_mode({"mode": "auto"}) == {"mode": "auto"}
    assert validate_tool_mode({"mode": "required"}) == {"mode": "required"}
    assert validate_tool_mode({"mode": "required", "required_function_name": "example_function"}) == {
        "mode": "required",
        "required_function_name": "example_function",
    }
    assert validate_tool_mode({"mode": "none"}) == {"mode": "none"}

    # None should return mode==none
    assert validate_tool_mode(None) == {"mode": "none"}

    with raises(ContentError):
        validate_tool_mode("invalid_mode")
    with raises(ContentError):
        validate_tool_mode({"mode": "invalid_mode"})
    with raises(ContentError):
        validate_tool_mode({"mode": "auto", "required_function_name": "should_not_be_here"})


def test_chat_options_merge(tool_tool, ai_tool) -> None:
    """Test merge_chat_options utility function."""
    options1: ChatOptions = {
        "model_id": "gpt-4o",
        "tools": [tool_tool],
        "logit_bias": {"x": 1},
        "metadata": {"a": "b"},
    }
    options2: ChatOptions = {"model_id": "gpt-4.1", "tools": [ai_tool]}
    assert options1 != options2

    # Merge options - override takes precedence for non-collection fields
    options3 = merge_chat_options(options1, options2)

    assert options3.get("model_id") == "gpt-4.1"
    assert options3.get("tools") == [tool_tool, ai_tool]  # tools are combined
    assert options3.get("logit_bias") == {"x": 1}  # base value preserved
    assert options3.get("metadata") == {"a": "b"}  # base value preserved


def test_chat_options_and_tool_choice_override() -> None:
    """Test that tool_choice from other takes precedence in ChatOptions merge."""
    # Agent-level defaults to "auto"
    agent_options: ChatOptions = {"model_id": "gpt-4o", "tool_choice": "auto"}
    # Run-level specifies "required"
    run_options: ChatOptions = {"tool_choice": "required"}

    merged = merge_chat_options(agent_options, run_options)

    # Run-level should override agent-level
    assert merged.get("tool_choice") == "required"
    assert merged.get("model_id") == "gpt-4o"  # Other fields preserved


def test_chat_options_and_tool_choice_none_in_other_uses_self() -> None:
    """Test that when other.tool_choice is None, self.tool_choice is used."""
    agent_options: ChatOptions = {"tool_choice": "auto"}
    run_options: ChatOptions = {"model_id": "gpt-4.1"}  # tool_choice is None

    merged = merge_chat_options(agent_options, run_options)

    # Should keep agent-level tool_choice since run-level is None
    assert merged.get("tool_choice") == "auto"
    assert merged.get("model_id") == "gpt-4.1"


def test_chat_options_and_tool_choice_with_tool_mode() -> None:
    """Test ChatOptions merge with ToolMode objects."""
    agent_options: ChatOptions = {"tool_choice": "auto"}
    run_options: ChatOptions = {"tool_choice": "required"}

    merged = merge_chat_options(agent_options, run_options)

    assert merged.get("tool_choice") == "required"
    assert merged.get("tool_choice") == "required"


def test_chat_options_and_tool_choice_required_specific_function() -> None:
    """Test ChatOptions merge with required specific function."""
    agent_options: ChatOptions = {"tool_choice": "auto"}
    run_options: ChatOptions = {"tool_choice": {"mode": "required", "required_function_name": "get_weather"}}

    merged = merge_chat_options(agent_options, run_options)

    tool_choice = merged.get("tool_choice")
    assert tool_choice == {"mode": "required", "required_function_name": "get_weather"}
    assert tool_choice["required_function_name"] == "get_weather"


# region Agent Response Fixtures


@fixture
def chat_message() -> ChatMessage:
    return ChatMessage(role=Role.USER, text="Hello")


@fixture
def text_content() -> Content:
    return Content.from_text(text="Test content")


@fixture
def agent_response(chat_message: ChatMessage) -> AgentResponse:
    return AgentResponse(messages=chat_message)


@fixture
def agent_response_update(text_content: Content) -> AgentResponseUpdate:
    return AgentResponseUpdate(role=Role.ASSISTANT, contents=[text_content])


# region AgentResponse


def test_agent_run_response_init_single_message(chat_message: ChatMessage) -> None:
    response = AgentResponse(messages=chat_message)
    assert response.messages == [chat_message]


def test_agent_run_response_init_list_messages(chat_message: ChatMessage) -> None:
    response = AgentResponse(messages=[chat_message, chat_message])
    assert len(response.messages) == 2
    assert response.messages[0] == chat_message


def test_agent_run_response_init_none_messages() -> None:
    response = AgentResponse()
    assert response.messages == []


def test_agent_run_response_text_property(chat_message: ChatMessage) -> None:
    response = AgentResponse(messages=[chat_message, chat_message])
    assert response.text == "HelloHello"


def test_agent_run_response_text_property_empty() -> None:
    response = AgentResponse()
    assert response.text == ""


def test_agent_run_response_from_updates(agent_response_update: AgentResponseUpdate) -> None:
    updates = [agent_response_update, agent_response_update]
    response = AgentResponse.from_agent_run_response_updates(updates)
    assert len(response.messages) > 0
    assert response.text == "Test contentTest content"


def test_agent_run_response_str_method(chat_message: ChatMessage) -> None:
    response = AgentResponse(messages=chat_message)
    assert str(response) == "Hello"


# region AgentResponseUpdate


def test_agent_run_response_update_init_content_list(text_content: Content) -> None:
    update = AgentResponseUpdate(contents=[text_content, text_content])
    assert len(update.contents) == 2
    assert update.contents[0] == text_content


def test_agent_run_response_update_init_none_content() -> None:
    update = AgentResponseUpdate()
    assert update.contents == []


def test_agent_run_response_update_text_property(text_content: Content) -> None:
    update = AgentResponseUpdate(contents=[text_content, text_content])
    assert update.text == "Test contentTest content"


def test_agent_run_response_update_text_property_empty() -> None:
    update = AgentResponseUpdate()
    assert update.text == ""


def test_agent_run_response_update_str_method(text_content: Content) -> None:
    update = AgentResponseUpdate(contents=[text_content])
    assert str(update) == "Test content"


def test_agent_run_response_update_created_at() -> None:
    """Test that AgentResponseUpdate properly handles created_at timestamps."""
    # Test with a properly formatted UTC timestamp
    utc_timestamp = "2024-12-01T00:31:30.000000Z"
    update = AgentResponseUpdate(
        contents=[Content.from_text(text="test")],
        role=Role.ASSISTANT,
        created_at=utc_timestamp,
    )
    assert update.created_at == utc_timestamp
    assert update.created_at.endswith("Z"), "Timestamp should end with 'Z' for UTC"

    # Verify that we can generate a proper UTC timestamp
    now_utc = datetime.now(tz=timezone.utc)
    formatted_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    update_with_now = AgentResponseUpdate(
        contents=[Content.from_text(text="test")],
        role=Role.ASSISTANT,
        created_at=formatted_utc,
    )
    assert update_with_now.created_at == formatted_utc
    assert update_with_now.created_at.endswith("Z")


def test_agent_run_response_created_at() -> None:
    """Test that AgentResponse properly handles created_at timestamps."""
    # Test with a properly formatted UTC timestamp
    utc_timestamp = "2024-12-01T00:31:30.000000Z"
    response = AgentResponse(
        messages=[ChatMessage(role=Role.ASSISTANT, text="Hello")],
        created_at=utc_timestamp,
    )
    assert response.created_at == utc_timestamp
    assert response.created_at.endswith("Z"), "Timestamp should end with 'Z' for UTC"

    # Verify that we can generate a proper UTC timestamp
    now_utc = datetime.now(tz=timezone.utc)
    formatted_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    response_with_now = AgentResponse(
        messages=[ChatMessage(role=Role.ASSISTANT, text="Hello")],
        created_at=formatted_utc,
    )
    assert response_with_now.created_at == formatted_utc
    assert response_with_now.created_at.endswith("Z")


# region ErrorContent


def test_error_content_str():
    e1 = Content.from_error(message="Oops", error_code="E1")
    assert str(e1) == "Error E1: Oops"
    e2 = Content.from_error(message="Oops")
    assert str(e2) == "Oops"
    e3 = Content.from_error()
    assert str(e3) == "Unknown error"


# region Annotation


def test_annotations_models_and_roundtrip():
    span = TextSpanRegion(type="text_span", start_index=0, end_index=5)
    cit = Annotation(
        type="citation", title="Doc", url="http://example.com", snippet="Snippet", annotated_regions=[span]
    )

    # Attach to content
    content = Content.from_text(text="hello", additional_properties={"v": 1})
    content.annotations = [cit]

    dumped = content.to_dict()
    loaded = Content.from_dict(dumped)
    assert isinstance(loaded.annotations, list)
    assert len(loaded.annotations) == 1
    # After migration from Pydantic, annotations are now TypedDicts (dicts at runtime)
    assert isinstance(loaded.annotations[0], dict)
    # Check the annotation properties
    loaded_cit = loaded.annotations[0]
    assert loaded_cit["type"] == "citation"
    assert loaded_cit["title"] == "Doc"
    assert loaded_cit["url"] == "http://example.com"
    assert loaded_cit["snippet"] == "Snippet"
    # Check the annotated_regions
    assert isinstance(loaded_cit["annotated_regions"], list)
    assert len(loaded_cit["annotated_regions"]) == 1
    assert isinstance(loaded_cit["annotated_regions"][0], dict)
    assert loaded_cit["annotated_regions"][0]["type"] == "text_span"
    assert loaded_cit["annotated_regions"][0]["start_index"] == 0
    assert loaded_cit["annotated_regions"][0]["end_index"] == 5


def test_function_call_merge_in_process_update_and_usage_aggregation():
    # Two function call chunks with same call_id should merge
    u1 = ChatResponseUpdate(
        contents=[Content.from_function_call(call_id="c1", name="f", arguments="{")], message_id="m"
    )
    u2 = ChatResponseUpdate(
        contents=[Content.from_function_call(call_id="c1", name="f", arguments="}")], message_id="m"
    )
    # plus usage
    u3 = ChatResponseUpdate(contents=[Content.from_usage(UsageDetails(input_token_count=1, output_token_count=2))])

    resp = ChatResponse.from_chat_response_updates([u1, u2, u3])
    assert len(resp.messages) == 1
    last_contents = resp.messages[0].contents
    assert any(c.type == "function_call" for c in last_contents)
    fcs = [c for c in last_contents if c.type == "function_call"]
    assert len(fcs) == 1
    assert fcs[0].arguments == "{}"
    assert resp.usage_details is not None
    assert resp.usage_details["input_token_count"] == 1
    assert resp.usage_details["output_token_count"] == 2


def test_function_call_incompatible_ids_are_not_merged():
    u1 = ChatResponseUpdate(contents=[Content.from_function_call(call_id="a", name="f", arguments="x")], message_id="m")
    u2 = ChatResponseUpdate(contents=[Content.from_function_call(call_id="b", name="f", arguments="y")], message_id="m")

    resp = ChatResponse.from_chat_response_updates([u1, u2])
    fcs = [c for c in resp.messages[0].contents if c.type == "function_call"]
    assert len(fcs) == 2


# region Role & FinishReason basics


def test_chat_role_str_and_repr():
    assert str(Role.USER) == "user"
    assert "Role(value=" in repr(Role.USER)


def test_chat_finish_reason_constants():
    assert FinishReason.STOP.value == "stop"


def test_response_update_propagates_fields_and_metadata():
    upd = ChatResponseUpdate(
        text="hello",
        role="assistant",
        author_name="bot",
        response_id="rid",
        message_id="mid",
        conversation_id="cid",
        model_id="model-x",
        created_at="t0",
        finish_reason=FinishReason.STOP,
        additional_properties={"k": "v"},
    )
    resp = ChatResponse.from_chat_response_updates([upd])
    assert resp.response_id == "rid"
    assert resp.created_at == "t0"
    assert resp.conversation_id == "cid"
    assert resp.model_id == "model-x"
    assert resp.finish_reason == FinishReason.STOP
    assert resp.additional_properties and resp.additional_properties["k"] == "v"
    assert resp.messages[0].role == Role.ASSISTANT
    assert resp.messages[0].author_name == "bot"
    assert resp.messages[0].message_id == "mid"


def test_text_coalescing_preserves_first_properties():
    t1 = Content.from_text("A", raw_representation={"r": 1}, additional_properties={"p": 1})
    t2 = Content.from_text("B")
    upd1 = ChatResponseUpdate(text=t1, message_id="x")
    upd2 = ChatResponseUpdate(text=t2, message_id="x")
    resp = ChatResponse.from_chat_response_updates([upd1, upd2])
    # After coalescing there should be a single TextContent with merged text and preserved props from first
    items = [c for c in resp.messages[0].contents if c.type == "text"]
    assert len(items) >= 1
    assert items[0].text == "AB"
    assert items[0].raw_representation == {"r": 1}
    assert items[0].additional_properties == {"p": 1}


def test_function_call_content_parse_numeric_or_list():
    c_num = Content.from_function_call(call_id="1", name="f", arguments="123")
    assert c_num.parse_arguments() == {"raw": 123}
    c_list = Content.from_function_call(call_id="1", name="f", arguments="[1,2]")
    assert c_list.parse_arguments() == {"raw": [1, 2]}


def test_chat_tool_mode_eq_with_string():
    assert {"mode": "auto"} == {"mode": "auto"}


# region AgentResponse


@fixture
def agent_run_response_async() -> AgentResponse:
    return AgentResponse(messages=[ChatMessage(role="user", text="Hello")])


async def test_agent_run_response_from_async_generator():
    async def gen():
        yield AgentResponseUpdate(contents=[Content.from_text("A")])
        yield AgentResponseUpdate(contents=[Content.from_text("B")])

    r = await AgentResponse.from_agent_response_generator(gen())
    assert r.text == "AB"


# region Additional Coverage Tests for Serialization and Arithmetic Methods


def test_text_content_add_comprehensive_coverage():
    """Test TextContent __add__ method with various combinations to improve coverage."""

    # Test with None raw_representation
    t1 = Content.from_text("Hello", raw_representation=None, annotations=None)
    t2 = Content.from_text(" World", raw_representation=None, annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation is None
    assert result.annotations is None

    # Test first has raw_representation, second has None
    t1 = Content.from_text("Hello", raw_representation="raw1", annotations=None)
    t2 = Content.from_text(" World", raw_representation=None, annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == "raw1"

    # Test first has None, second has raw_representation
    t1 = Content.from_text("Hello", raw_representation=None, annotations=None)
    t2 = Content.from_text(" World", raw_representation="raw2", annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == "raw2"

    # Test both have raw_representation (non-list)
    t1 = Content.from_text("Hello", raw_representation="raw1", annotations=None)
    t2 = Content.from_text(" World", raw_representation="raw2", annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2"]

    # Test first has list raw_representation, second has single
    t1 = Content.from_text("Hello", raw_representation=["raw1", "raw2"], annotations=None)
    t2 = Content.from_text(" World", raw_representation="raw3", annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2", "raw3"]

    # Test both have list raw_representation
    t1 = Content.from_text("Hello", raw_representation=["raw1", "raw2"], annotations=None)
    t2 = Content.from_text(" World", raw_representation=["raw3", "raw4"], annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2", "raw3", "raw4"]

    # Test first has single raw_representation, second has list
    t1 = Content.from_text("Hello", raw_representation="raw1", annotations=None)
    t2 = Content.from_text(" World", raw_representation=["raw2", "raw3"], annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2", "raw3"]


def test_text_content_iadd_coverage():
    """Test TextContent += operator for better coverage."""

    t1 = Content.from_text("Hello", raw_representation="raw1", additional_properties={"key1": "val1"})
    t2 = Content.from_text(" World", raw_representation="raw2", additional_properties={"key2": "val2"})

    t1 += t2

    # Content doesn't implement __iadd__, so += creates a new object via __add__
    assert t1.text == "Hello World"
    assert t1.raw_representation == ["raw1", "raw2"]
    assert t1.additional_properties == {"key1": "val1", "key2": "val2"}


def test_text_reasoning_content_add_coverage():
    """Test TextReasoningContent __add__ method for better coverage."""

    t1 = Content.from_text_reasoning(text="Thinking 1")
    t2 = Content.from_text_reasoning(text=" Thinking 2")

    result = t1 + t2
    assert result.text == "Thinking 1 Thinking 2"


def test_text_reasoning_content_iadd_coverage():
    """Test TextReasoningContent += operator for better coverage."""

    t1 = Content.from_text_reasoning(text="Thinking 1")
    t2 = Content.from_text_reasoning(text=" Thinking 2")

    t1 += t2

    # Content doesn't implement __iadd__, so += creates a new object via __add__
    assert t1.text == "Thinking 1 Thinking 2"


def test_comprehensive_to_dict_exclude_options():
    """Test to_dict methods with various exclude options for better coverage."""

    # Test TextContent with exclude_none
    text_content = Content.from_text("Hello", raw_representation=None, additional_properties={"prop": "val"})
    text_dict = text_content.to_dict(exclude_none=True)
    assert "raw_representation" not in text_dict
    assert text_dict["additional_properties"]["prop"] == "val"

    # Test with custom exclude set
    text_dict_exclude = text_content.to_dict(exclude={"additional_properties"})
    assert "additional_properties" not in text_dict_exclude
    assert "text" in text_dict_exclude

    # Test UsageDetails - it's a TypedDict now, not a class with to_dict
    usage = UsageDetails(input_token_count=5, custom_count=10)
    assert usage["input_token_count"] == 5
    assert usage["custom_count"] == 10

    # Test UsageDetails exclude_none behavior isn't applicable to TypedDict
    # TypedDict doesn't have a to_dict method


def test_usage_details_iadd_edge_cases():
    """Test UsageDetails addition with edge cases for better coverage."""
    # Test with None values
    u1 = UsageDetails(input_token_count=None, output_token_count=5, custom1=10)
    u2 = UsageDetails(input_token_count=3, output_token_count=None, custom2=20)

    result = add_usage_details(u1, u2)
    assert result["input_token_count"] == 3
    assert result["output_token_count"] == 5
    assert result.get("custom1") == 10
    assert result.get("custom2") == 20

    # Test merging additional counts
    u3 = UsageDetails(input_token_count=1, shared_count=5)
    u4 = UsageDetails(input_token_count=2, shared_count=15)

    result2 = add_usage_details(u3, u4)
    assert result2["input_token_count"] == 3
    assert result2.get("shared_count") == 20


def test_chat_message_from_dict_with_mixed_content():
    """Test ChatMessage from_dict with mixed content types for better coverage."""

    message_data = {
        "role": "assistant",
        "contents": [
            {"type": "text", "text": "Hello"},
            {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {"arg": "val"}},
            {"type": "function_result", "call_id": "call1", "result": "success"},
        ],
    }

    message = ChatMessage.from_dict(message_data)
    assert len(message.contents) == 3  # Unknown type is ignored
    assert message.contents[0].type == "text"
    assert message.contents[1].type == "function_call"
    assert message.contents[2].type == "function_result"

    # Test round-trip
    message_dict = message.to_dict()
    assert len(message_dict["contents"]) == 3


def test_text_content_add_type_error():
    """Test TextContent __add__ raises TypeError for incompatible types."""
    t1 = Content.from_text("Hello")

    with raises(TypeError, match="Incompatible type"):
        t1 + "not a TextContent"


def test_comprehensive_serialization_methods():
    """Test from_dict and to_dict methods for various content types."""

    # Test TextContent with all fields
    text_data = {
        "type": "text",
        "text": "Hello world",
        "raw_representation": {"key": "value"},
        "additional_properties": {"prop": "val"},
        "annotations": None,
    }
    text_content = Content.from_dict(text_data)
    assert text_content.text == "Hello world"
    assert text_content.raw_representation == {"key": "value"}
    assert text_content.additional_properties == {"prop": "val"}

    # Test round-trip
    text_dict = text_content.to_dict()
    assert text_dict["text"] == "Hello world"
    assert text_dict["additional_properties"] == {"prop": "val"}
    # Note: raw_representation is always excluded from to_dict() output

    # Test with exclude_none
    text_dict_no_none = text_content.to_dict(exclude_none=True)
    assert "annotations" not in text_dict_no_none

    # Test FunctionResultContent
    result_data = {
        "type": "function_result",
        "call_id": "call123",
        "result": "success",
        "additional_properties": {"meta": "data"},
    }
    result_content = Content.from_dict(result_data)
    assert result_content.call_id == "call123"
    assert result_content.result == "success"


def test_chat_message_complex_content_serialization():
    """Test ChatMessage serialization with various content types."""

    # Create a message with multiple content types
    contents = [
        Content.from_text("Hello"),
        Content.from_function_call(call_id="call1", name="func", arguments={"arg": "val"}),
        Content.from_function_result(call_id="call1", result="success"),
    ]

    message = ChatMessage(role=Role.ASSISTANT, contents=contents)

    # Test to_dict
    message_dict = message.to_dict()
    assert len(message_dict["contents"]) == 3
    assert message_dict["contents"][0]["type"] == "text"
    assert message_dict["contents"][1]["type"] == "function_call"
    assert message_dict["contents"][2]["type"] == "function_result"

    # Test from_dict round-trip
    reconstructed = ChatMessage.from_dict(message_dict)
    assert len(reconstructed.contents) == 3
    assert reconstructed.contents[0].type == "text"
    assert reconstructed.contents[1].type == "function_call"
    assert reconstructed.contents[2].type == "function_result"


def test_usage_content_serialization_with_details():
    """Test UsageContent from_dict and to_dict with UsageDetails conversion."""

    # Test from_dict with details as dict
    usage_data = {
        "type": "usage",
        "usage_details": {
            "type": "usage_details",
            "input_token_count": 10,
            "output_token_count": 20,
            "total_token_count": 30,
            "custom_count": 5,
        },
    }
    usage_content = Content(**usage_data)
    assert isinstance(usage_content.usage_details, dict)
    assert usage_content.usage_details["input_token_count"] == 10
    assert usage_content.usage_details["custom_count"] == 5  # Custom fields go directly in UsageDetails

    # Test to_dict with UsageDetails object
    usage_dict = usage_content.to_dict()
    assert isinstance(usage_dict["usage_details"], dict)
    assert usage_dict["usage_details"]["input_token_count"] == 10


def test_function_approval_response_content_serialization():
    """Test FunctionApprovalResponseContent from_dict and to_dict with function_call conversion."""

    # Test from_dict with function_call as dict
    response_data = {
        "type": "function_approval_response",
        "id": "response123",
        "approved": True,
        "function_call": {
            "type": "function_call",
            "call_id": "call123",
            "name": "test_func",
            "arguments": {"param": "value"},
        },
    }
    response_content = Content.from_dict(response_data)
    assert response_content.function_call.type == "function_call"
    assert response_content.function_call.call_id == "call123"

    # Test to_dict with FunctionCallContent object
    response_dict = response_content.to_dict()
    assert isinstance(response_dict["function_call"], dict)
    assert response_dict["function_call"]["call_id"] == "call123"


def test_chat_response_complex_serialization():
    """Test ChatResponse from_dict and to_dict with complex nested objects."""

    # Test from_dict with messages, finish_reason, and usage_details as dicts
    response_data = {
        "messages": [
            {"role": "user", "contents": [{"type": "text", "text": "Hello"}]},
            {"role": "assistant", "contents": [{"type": "text", "text": "Hi there"}]},
        ],
        "finish_reason": {"value": "stop"},
        "usage_details": {
            "type": "usage_details",
            "input_token_count": 5,
            "output_token_count": 8,
            "total_token_count": 13,
        },
        "model_id": "gpt-4",  # Test alias handling
    }

    response = ChatResponse.from_dict(response_data)
    assert len(response.messages) == 2
    assert isinstance(response.messages[0], ChatMessage)
    assert isinstance(response.finish_reason, FinishReason)
    assert isinstance(response.usage_details, dict)
    assert response.model_id == "gpt-4"  # Should be stored as model_id

    # Test to_dict with complex objects
    response_dict = response.to_dict()
    assert len(response_dict["messages"]) == 2
    assert isinstance(response_dict["messages"][0], dict)
    assert isinstance(response_dict["finish_reason"], dict)
    assert isinstance(response_dict["usage_details"], dict)
    assert response_dict["model_id"] == "gpt-4"  # Should serialize as model_id


def test_chat_response_update_all_content_types():
    """Test ChatResponseUpdate from_dict with all supported content types."""

    update_data = {
        "contents": [
            {"type": "text", "text": "Hello"},
            {"type": "data", "data": b"base64data", "media_type": "text/plain"},
            {"type": "uri", "uri": "http://example.com", "media_type": "text/html"},
            {"type": "error", "message": "An error occurred"},
            {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            {"type": "function_result", "call_id": "call1", "result": "success"},
            {"type": "usage", "usage_details": {"input_token_count": 1}},
            {"type": "hosted_file", "file_id": "file123"},
            {"type": "hosted_vector_store", "vector_store_id": "vs123"},
            {
                "type": "function_approval_request",
                "id": "req1",
                "function_call": {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            },
            {
                "type": "function_approval_response",
                "id": "resp1",
                "approved": True,
                "function_call": {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            },
            {"type": "text_reasoning", "text": "reasoning"},
        ]
    }

    update = ChatResponseUpdate.from_dict(update_data)
    assert len(update.contents) == 12  # unknown_type is skipped with warning
    assert update.contents[0].type == "text"
    assert update.contents[1].type == "data"
    assert update.contents[2].type == "uri"
    assert update.contents[3].type == "error"
    assert update.contents[4].type == "function_call"
    assert update.contents[5].type == "function_result"
    assert update.contents[6].type == "usage"
    assert update.contents[7].type == "hosted_file"
    assert update.contents[8].type == "hosted_vector_store"
    assert update.contents[9].type == "function_approval_request"
    assert update.contents[10].type == "function_approval_response"
    assert update.contents[11].type == "text_reasoning"


def test_agent_run_response_complex_serialization():
    """Test AgentResponse from_dict and to_dict with messages and usage_details."""

    response_data = {
        "messages": [
            {"role": "user", "contents": [{"type": "text", "text": "Hello"}]},
            {"role": "assistant", "contents": [{"type": "text", "text": "Hi"}]},
        ],
        "usage_details": {
            "type": "usage_details",
            "input_token_count": 3,
            "output_token_count": 2,
            "total_token_count": 5,
        },
    }

    response = AgentResponse.from_dict(response_data)
    assert len(response.messages) == 2
    assert isinstance(response.messages[0], ChatMessage)
    assert isinstance(response.usage_details, dict)

    # Test to_dict
    response_dict = response.to_dict()
    assert len(response_dict["messages"]) == 2
    assert isinstance(response_dict["messages"][0], dict)
    assert isinstance(response_dict["usage_details"], dict)


def test_agent_run_response_update_all_content_types():
    """Test AgentResponseUpdate from_dict with all content types and role handling."""

    update_data = {
        "contents": [
            {"type": "text", "text": "Hello"},
            {"type": "data", "data": b"base64data", "media_type": "text/plain"},
            {"type": "uri", "uri": "http://example.com", "media_type": "text/html"},
            {"type": "error", "message": "An error occurred"},
            {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            {"type": "function_result", "call_id": "call1", "result": "success"},
            {"type": "usage", "usage_details": {"input_token_count": 1}},
            {"type": "hosted_file", "file_id": "file123"},
            {"type": "hosted_vector_store", "vector_store_id": "vs123"},
            {
                "type": "function_approval_request",
                "id": "req1",
                "function_call": {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            },
            {
                "type": "function_approval_response",
                "id": "resp1",
                "approved": True,
                "function_call": {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            },
            {"type": "text_reasoning", "text": "reasoning"},
        ],
        "role": {"value": "assistant"},  # Test role as dict
    }

    update = AgentResponseUpdate.from_dict(update_data)
    assert len(update.contents) == 12  # unknown_type is logged and ignored
    assert isinstance(update.role, Role)
    assert update.role.value == "assistant"

    # Test to_dict with role conversion
    update_dict = update.to_dict()
    assert len(update_dict["contents"]) == 12  # unknown_type was ignored during from_dict
    assert isinstance(update_dict["role"], dict)

    # Test role as string conversion
    update_data_str_role = update_data.copy()
    update_data_str_role["role"] = "user"
    update_str = AgentResponseUpdate.from_dict(update_data_str_role)
    assert isinstance(update_str.role, Role)
    assert update_str.role.value == "user"


# region Serialization


@mark.parametrize(
    "content_class,init_kwargs",
    [
        pytest.param(
            Content,
            {
                "type": "text",
                "text": "Hello world",
                "raw_representation": "raw",
            },
            id="text_content",
        ),
        pytest.param(
            Content,
            {
                "type": "text_reasoning",
                "text": "Reasoning text",
                "raw_representation": "raw",
            },
            id="text_reasoning_content",
        ),
        pytest.param(
            Content,
            {
                "type": "data",
                "uri": "data:text/plain;base64,dGVzdCBkYXRh",
            },
            id="data_content_with_uri",
        ),
        pytest.param(
            Content,
            {
                "type": "data",
                "data": b"test data",
                "media_type": "text/plain",
            },
            id="data_content_with_bytes",
        ),
        pytest.param(
            Content,
            {
                "type": "uri",
                "uri": "http://example.com",
                "media_type": "text/html",
            },
            id="uri_content",
        ),
        pytest.param(
            Content,
            {"type": "hosted_file", "file_id": "file-123"},
            id="hosted_file_content",
        ),
        pytest.param(
            Content,
            {
                "type": "hosted_vector_store",
                "vector_store_id": "vs-789",
            },
            id="hosted_vector_store_content",
        ),
        pytest.param(
            Content,
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "test_func",
                "arguments": {"arg": "val"},
            },
            id="function_call_content",
        ),
        pytest.param(
            Content,
            {
                "type": "function_result",
                "call_id": "call-1",
                "result": "success",
            },
            id="function_result_content",
        ),
        pytest.param(
            Content,
            {
                "type": "error",
                "message": "Error occurred",
                "error_code": "E001",
            },
            id="error_content",
        ),
        pytest.param(
            Content,
            {
                "type": "usage",
                "usage_details": {
                    "type": "usage_details",
                    "input_token_count": 10,
                    "output_token_count": 20,
                    "reasoning_tokens": 5,
                },
            },
            id="usage_content",
        ),
        pytest.param(
            Content,
            {
                "type": "function_approval_request",
                "id": "req-1",
                "function_call": {"type": "function_call", "call_id": "call-1", "name": "test_func", "arguments": {}},
            },
            id="function_approval_request",
        ),
        pytest.param(
            Content,
            {
                "type": "function_approval_response",
                "id": "resp-1",
                "approved": True,
                "function_call": {"type": "function_call", "call_id": "call-1", "name": "test_func", "arguments": {}},
            },
            id="function_approval_response",
        ),
        pytest.param(
            ChatMessage,
            {
                "role": {"type": "role", "value": "user"},
                "contents": [
                    {"type": "text", "text": "Hello"},
                    {"type": "function_call", "call_id": "call-1", "name": "test_func", "arguments": {}},
                ],
                "message_id": "msg-123",
                "author_name": "User",
            },
            id="chat_message",
        ),
        pytest.param(
            ChatResponse,
            {
                "type": "chat_response",
                "messages": [
                    {
                        "type": "chat_message",
                        "role": {"type": "role", "value": "user"},
                        "contents": [{"type": "text", "text": "Hello"}],
                    },
                    {
                        "type": "chat_message",
                        "role": {"type": "role", "value": "assistant"},
                        "contents": [{"type": "text", "text": "Hi there"}],
                    },
                ],
                "finish_reason": {"type": "finish_reason", "value": "stop"},
                "usage_details": {
                    "type": "usage_details",
                    "input_token_count": 10,
                    "output_token_count": 20,
                    "total_token_count": 30,
                },
                "response_id": "resp-123",
                "model_id": "gpt-4",
            },
            id="chat_response",
        ),
        pytest.param(
            ChatResponseUpdate,
            {
                "contents": [
                    {"type": "text", "text": "Hello"},
                    {"type": "function_call", "call_id": "call-1", "name": "test_func", "arguments": {}},
                ],
                "role": {"type": "role", "value": "assistant"},
                "finish_reason": {"type": "finish_reason", "value": "stop"},
                "message_id": "msg-123",
                "response_id": "resp-123",
            },
            id="chat_response_update",
        ),
        pytest.param(
            AgentResponse,
            {
                "messages": [
                    {
                        "role": {"type": "role", "value": "user"},
                        "contents": [{"type": "text", "text": "Question"}],
                    },
                    {
                        "role": {"type": "role", "value": "assistant"},
                        "contents": [{"type": "text", "text": "Answer"}],
                    },
                ],
                "response_id": "run-123",
                "usage_details": {
                    "type": "usage_details",
                    "input_token_count": 5,
                    "output_token_count": 3,
                    "total_token_count": 8,
                },
            },
            id="agent_response",
        ),
        pytest.param(
            AgentResponseUpdate,
            {
                "contents": [
                    {"type": "text", "text": "Streaming"},
                    {"type": "function_call", "call_id": "call-1", "name": "test_func", "arguments": {}},
                ],
                "role": {"type": "role", "value": "assistant"},
                "message_id": "msg-123",
                "response_id": "run-123",
                "author_name": "Agent",
            },
            id="agent_response_update",
        ),
    ],
)
def test_content_roundtrip_serialization(content_class: type[Content], init_kwargs: dict[str, Any]):
    """Test to_dict/from_dict roundtrip for all content types."""
    # Create instance using from_dict to handle nested dict-to-object conversions
    content = content_class.from_dict(init_kwargs)

    # Serialize to dict
    content_dict = content.to_dict()

    # Verify type key is in serialized dict
    assert "type" in content_dict
    if hasattr(content, "type"):
        assert content_dict["type"] == content.type  # type: ignore[attr-defined]

    # Deserialize from dict
    reconstructed = content_class.from_dict(content_dict)

    # Verify type
    assert isinstance(reconstructed, content_class)
    # Check type attribute dynamically
    if hasattr(content, "type"):
        assert reconstructed.type == content.type  # type: ignore[attr-defined]

    # Verify key attributes (excluding raw_representation which is not serialized)
    for key, value in init_kwargs.items():
        if key == "type":
            continue
        if key == "raw_representation":
            # raw_representation is intentionally excluded from serialization
            continue

        # Special handling for DataContent created with 'data' parameter
        if hasattr(content, "type") and content.type == "data" and key == "data":
            # DataContent converts 'data' to 'uri', so we skip checking 'data' attribute
            # Instead we verify that uri and media_type are set correctly
            assert hasattr(reconstructed, "uri")
            assert hasattr(reconstructed, "media_type")
            assert reconstructed.media_type == init_kwargs.get("media_type")
            # Verify the uri contains the encoded data
            assert reconstructed.uri.startswith(f"data:{init_kwargs.get('media_type')};base64,")
            continue

        reconstructed_value = getattr(reconstructed, key)

        # Special handling for nested SerializationMixin objects
        if hasattr(value, "to_dict"):
            # Compare the serialized forms
            assert reconstructed_value.to_dict() == value.to_dict()
        # Special handling for lists that may contain dicts converted to objects
        elif isinstance(value, list) and value and isinstance(reconstructed_value, list):
            # Check if this is a list of objects that were created from dicts
            if isinstance(value[0], dict) and hasattr(reconstructed_value[0], "to_dict"):
                # Compare each item by serializing the reconstructed object
                assert len(reconstructed_value) == len(value)
                for orig_dict, recon_obj in zip(value, reconstructed_value):
                    recon_dict = recon_obj.to_dict()
                    # Compare all keys from original dict (reconstructed may have extra default fields)
                    for k, v in orig_dict.items():
                        assert k in recon_dict, f"Key '{k}' missing from reconstructed dict"
                        # For nested lists, recursively compare
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            assert len(recon_dict[k]) == len(v)
                            for orig_item, recon_item in zip(v, recon_dict[k]):
                                # Compare essential keys, ignoring fields like additional_properties
                                for item_key, item_val in orig_item.items():
                                    assert item_key in recon_item
                                    assert recon_item[item_key] == item_val
                        else:
                            assert recon_dict[k] == v, f"Value mismatch for key '{k}'"
            else:
                assert reconstructed_value == value
        # Special handling for dicts that get converted to objects (like UsageDetails, FunctionCallContent)
        elif isinstance(value, dict) and hasattr(reconstructed_value, "to_dict"):
            # Compare the dict with the serialized form of the object
            reconstructed_dict = reconstructed_value.to_dict()
            # Verify all keys from the original dict are in the reconstructed dict
            for k, v in value.items():
                assert k in reconstructed_dict, f"Key '{k}' missing from reconstructed dict"
                assert reconstructed_dict[k] == v, f"Value mismatch for key '{k}'"
        else:
            assert reconstructed_value == value


def test_text_content_with_annotations_serialization():
    """Test TextContent with multiple annotations roundtrip serialization."""
    # Create multiple regions
    region1 = TextSpanRegion(type="text_span", start_index=0, end_index=5)
    region2 = TextSpanRegion(type="text_span", start_index=6, end_index=11)

    # Create multiple citations
    citation1 = Annotation(type="citation", title="Citation 1", url="http://example.com/1", annotated_regions=[region1])

    citation2 = Annotation(type="citation", title="Citation 2", url="http://example.com/2", annotated_regions=[region2])

    # Create TextContent with multiple annotations
    content = Content.from_text(text="Hello world", annotations=[citation1, citation2])

    # Serialize
    content_dict = content.to_dict()

    # Verify we have 2 annotations
    assert len(content_dict["annotations"]) == 2
    assert content_dict["annotations"][0]["title"] == "Citation 1"
    assert content_dict["annotations"][1]["title"] == "Citation 2"

    # Deserialize
    reconstructed = Content.from_dict(content_dict)

    # Verify reconstruction
    assert len(reconstructed.annotations) == 2
    # Annotation are TypedDicts (dicts at runtime)
    assert all(isinstance(ann, dict) for ann in reconstructed.annotations)
    assert reconstructed.annotations[0]["title"] == "Citation 1"
    assert reconstructed.annotations[1]["title"] == "Citation 2"
    assert all(isinstance(ann["annotated_regions"][0], dict) for ann in reconstructed.annotations)


# region prepare_function_call_results with Pydantic models


class WeatherResult(BaseModel):
    """A Pydantic model for testing."""

    temperature: float
    condition: str


class NestedModel(BaseModel):
    """A Pydantic model with nested structure."""

    name: str
    weather: WeatherResult


def test_prepare_function_call_results_pydantic_model():
    """Test that Pydantic BaseModel subclasses are properly serialized using model_dump()."""
    result = WeatherResult(temperature=22.5, condition="sunny")
    json_result = prepare_function_call_results(result)

    # The result should be a valid JSON string
    assert isinstance(json_result, str)
    assert '"temperature": 22.5' in json_result or '"temperature":22.5' in json_result
    assert '"condition": "sunny"' in json_result or '"condition":"sunny"' in json_result


def test_prepare_function_call_results_pydantic_model_in_list():
    """Test that lists containing Pydantic models are properly serialized."""
    results = [
        WeatherResult(temperature=20.0, condition="cloudy"),
        WeatherResult(temperature=25.0, condition="sunny"),
    ]
    json_result = prepare_function_call_results(results)

    # The result should be a valid JSON string representing a list
    assert isinstance(json_result, str)
    assert json_result.startswith("[")
    assert json_result.endswith("]")
    assert "cloudy" in json_result
    assert "sunny" in json_result


def test_prepare_function_call_results_pydantic_model_in_dict():
    """Test that dicts containing Pydantic models are properly serialized."""
    results = {
        "current": WeatherResult(temperature=22.0, condition="partly cloudy"),
        "forecast": WeatherResult(temperature=24.0, condition="sunny"),
    }
    json_result = prepare_function_call_results(results)

    # The result should be a valid JSON string representing a dict
    assert isinstance(json_result, str)
    assert "current" in json_result
    assert "forecast" in json_result
    assert "partly cloudy" in json_result
    assert "sunny" in json_result


def test_prepare_function_call_results_nested_pydantic_model():
    """Test that nested Pydantic models are properly serialized."""
    result = NestedModel(name="Seattle", weather=WeatherResult(temperature=18.0, condition="rainy"))
    json_result = prepare_function_call_results(result)

    # The result should be a valid JSON string
    assert isinstance(json_result, str)
    assert "Seattle" in json_result
    assert "rainy" in json_result
    assert "18.0" in json_result or "18" in json_result


# region prepare_function_call_results with MCP TextContent-like objects


def test_prepare_function_call_results_text_content_single():
    """Test that objects with text attribute (like MCP TextContent) are properly handled."""

    @dataclass
    class MockTextContent:
        text: str

    result = [MockTextContent("Hello from MCP tool!")]
    json_result = prepare_function_call_results(result)

    # Should extract text and serialize as JSON array of strings
    assert isinstance(json_result, str)
    assert json_result == '["Hello from MCP tool!"]'


def test_prepare_function_call_results_text_content_multiple():
    """Test that multiple TextContent-like objects are serialized correctly."""

    @dataclass
    class MockTextContent:
        text: str

    result = [MockTextContent("First result"), MockTextContent("Second result")]
    json_result = prepare_function_call_results(result)

    # Should extract text from each and serialize as JSON array
    assert isinstance(json_result, str)
    assert json_result == '["First result", "Second result"]'


def test_prepare_function_call_results_text_content_with_non_string_text():
    """Test that objects with non-string text attribute are not treated as TextContent."""

    class BadTextContent:
        def __init__(self):
            self.text = 12345  # Not a string!

    result = [BadTextContent()]
    json_result = prepare_function_call_results(result)

    # Should not extract text since it's not a string, will serialize the object
    assert isinstance(json_result, str)


# endregion


# region Test Content._add_usage_content


def test_content_add_usage_content():
    """Test adding two usage content instances combines their usage details."""
    usage1 = Content(
        type="usage",
        usage_details={"input_token_count": 100, "output_token_count": 50},
        raw_representation="raw1",
    )
    usage2 = Content(
        type="usage",
        usage_details={"input_token_count": 200, "output_token_count": 100},
        raw_representation="raw2",
    )

    result = usage1 + usage2

    assert result.type == "usage"
    assert result.usage_details["input_token_count"] == 300
    assert result.usage_details["output_token_count"] == 150
    # Raw representations should be combined
    assert isinstance(result.raw_representation, list)
    assert "raw1" in result.raw_representation
    assert "raw2" in result.raw_representation


def test_content_add_usage_content_with_none_raw_representation():
    """Test adding usage content when one has None raw_representation."""
    usage1 = Content(
        type="usage",
        usage_details={"input_token_count": 100},
        raw_representation=None,
    )
    usage2 = Content(
        type="usage",
        usage_details={"output_token_count": 50},
        raw_representation="raw2",
    )

    result = usage1 + usage2

    assert result.raw_representation == "raw2"


def test_content_add_usage_content_non_integer_values():
    """Test adding usage content with non-integer values."""
    usage1 = Content(
        type="usage",
        usage_details={"model": "gpt-4", "count": 10},
    )
    usage2 = Content(
        type="usage",
        usage_details={"model": "gpt-3.5", "count": 20},
    )

    result = usage1 + usage2

    # Non-integer "model" should take first non-None value
    assert result.usage_details["model"] == "gpt-4"
    # Integer "count" should be summed
    assert result.usage_details["count"] == 30


# endregion


# region Test Content.has_top_level_media_type


def test_content_has_top_level_media_type():
    """Test has_top_level_media_type returns correct boolean."""
    image = Content(type="uri", uri="https://example.com/image.png", media_type="image/png")

    assert image.has_top_level_media_type("image") is True
    assert image.has_top_level_media_type("IMAGE") is True  # Case insensitive
    assert image.has_top_level_media_type("audio") is False


def test_content_has_top_level_media_type_no_slash():
    """Test has_top_level_media_type when media_type has no slash."""
    content = Content(type="data", media_type="text")

    assert content.has_top_level_media_type("text") is True


def test_content_has_top_level_media_type_raises_without_media_type():
    """Test has_top_level_media_type raises ContentError when no media_type."""
    content = Content(type="text", text="hello")

    with raises(ContentError, match="no media_type found"):
        content.has_top_level_media_type("text")


# endregion


# region Test Content.parse_arguments


def test_content_parse_arguments_none():
    """Test parse_arguments returns None when arguments is None."""
    content = Content(type="function_call", call_id="1", name="test", arguments=None)

    assert content.parse_arguments() is None


def test_content_parse_arguments_empty_string():
    """Test parse_arguments returns empty dict for empty string."""
    content = Content(type="function_call", call_id="1", name="test", arguments="")

    assert content.parse_arguments() == {}


def test_content_parse_arguments_valid_json():
    """Test parse_arguments parses valid JSON string."""
    content = Content(type="function_call", call_id="1", name="test", arguments='{"key": "value"}')

    result = content.parse_arguments()
    assert result == {"key": "value"}


def test_content_parse_arguments_non_dict_json():
    """Test parse_arguments wraps non-dict JSON in 'raw' key."""
    content = Content(type="function_call", call_id="1", name="test", arguments='"just a string"')

    result = content.parse_arguments()
    # The JSON is parsed, and if it's not a dict, wrapped in 'raw'
    assert result == {"raw": "just a string"}


def test_content_parse_arguments_invalid_json():
    """Test parse_arguments wraps invalid JSON in 'raw' key."""
    content = Content(type="function_call", call_id="1", name="test", arguments="not json at all")

    result = content.parse_arguments()
    assert result == {"raw": "not json at all"}


def test_content_parse_arguments_dict_passthrough():
    """Test parse_arguments passes through dict arguments."""
    args = {"key": "value", "num": 42}
    content = Content(type="function_call", call_id="1", name="test", arguments=args)

    result = content.parse_arguments()
    assert result == args


# endregion


# region Test _get_data_bytes_as_str


def test_get_data_bytes_as_str_non_data_uri():
    """Test _get_data_bytes_as_str returns None for non-data URIs."""
    content = Content(type="uri", uri="https://example.com/image.png")
    assert _get_data_bytes_as_str(content) is None


def test_get_data_bytes_as_str_no_base64():
    """Test _get_data_bytes_as_str raises for non-base64 data URI."""
    content = Content(type="uri", uri="data:text/plain,hello")
    with raises(ContentError, match="base64 encoding"):
        _get_data_bytes_as_str(content)


def test_get_data_bytes_as_str_valid():
    """Test _get_data_bytes_as_str extracts base64 data."""
    data = base64.b64encode(b"hello").decode()
    content = Content(type="uri", uri=f"data:text/plain;base64,{data}")
    result = _get_data_bytes_as_str(content)
    assert result == data


# endregion


# region Test _get_data_bytes


def test_get_data_bytes_decodes_base64():
    """Test _get_data_bytes decodes base64 data correctly."""
    original = b"hello world"
    data = base64.b64encode(original).decode()
    content = Content(type="uri", uri=f"data:text/plain;base64,{data}")

    result = _get_data_bytes(content)
    assert result == original


def test_get_data_bytes_invalid_base64():
    """Test _get_data_bytes raises for invalid base64."""
    content = Content(type="uri", uri="data:text/plain;base64,!!invalid!!")
    with raises(ContentError, match="Failed to decode"):
        _get_data_bytes(content)


# endregion


# region Test _parse_content_list


def test_parse_content_list_with_content_objects():
    """Test _parse_content_list passes through Content objects."""
    content = Content(type="text", text="hello")
    result = _parse_content_list([content])

    assert len(result) == 1
    assert result[0] is content


def test_parse_content_list_with_dicts():
    """Test _parse_content_list converts dicts to Content."""
    result = _parse_content_list([{"type": "text", "text": "hello"}])

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "hello"


def test_parse_content_list_with_mixed_content_and_dict():
    """Test _parse_content_list handles a mix of Content objects and dicts."""
    content = Content(type="text", text="hello")
    # Pass a mix of Content object and dict
    result = _parse_content_list([content, {"type": "text", "text": "world"}])

    assert len(result) == 2
    assert result[0].text == "hello"
    assert result[1].text == "world"


# endregion


# region Test _validate_uri


def test_validate_uri_known_scheme():
    """Test _validate_uri accepts known URI schemes."""
    result = _validate_uri("https://example.com/file.txt", "text/plain")
    assert result.get("uri") == "https://example.com/file.txt"


def test_validate_uri_data_uri():
    """Test _validate_uri handles data URIs."""
    data = base64.b64encode(b"test").decode()
    uri = f"data:text/plain;base64,{data}"
    result = _validate_uri(uri, None)
    assert "uri" in result


# endregion
