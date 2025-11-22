# Copyright (c) Microsoft. All rights reserved.

import base64
from collections.abc import AsyncIterable
from typing import Any

import pytest
from pydantic import BaseModel
from pytest import fixture, mark, raises

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    BaseContent,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CitationAnnotation,
    DataContent,
    ErrorContent,
    FinishReason,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedFileContent,
    HostedVectorStoreContent,
    Role,
    TextContent,
    TextReasoningContent,
    TextSpanRegion,
    ToolMode,
    ToolProtocol,
    UriContent,
    UsageContent,
    UsageDetails,
    ai_function,
)
from agent_framework.exceptions import AdditionItemMismatch, ContentError


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
def ai_function_tool() -> ToolProtocol:
    """Returns a executable ToolProtocol."""

    @ai_function
    def simple_function(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    return simple_function


# region TextContent


def test_text_content_positional():
    """Test the TextContent class to ensure it initializes correctly and inherits from BaseContent."""
    # Create an instance of TextContent
    content = TextContent("Hello, world!", raw_representation="Hello, world!", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "text"
    assert content.text == "Hello, world!"
    assert content.raw_representation == "Hello, world!"
    assert content.additional_properties["version"] == 1
    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)
    # Note: No longer using Pydantic validation, so type assignment should work
    content.type = "text"  # This should work fine now


def test_text_content_keyword():
    """Test the TextContent class to ensure it initializes correctly and inherits from BaseContent."""
    # Create an instance of TextContent
    content = TextContent(
        text="Hello, world!", raw_representation="Hello, world!", additional_properties={"version": 1}
    )

    # Check the type and content
    assert content.type == "text"
    assert content.text == "Hello, world!"
    assert content.raw_representation == "Hello, world!"
    assert content.additional_properties["version"] == 1
    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)
    # Note: No longer using Pydantic validation, so type assignment should work
    content.type = "text"  # This should work fine now


# region DataContent


def test_data_content_bytes():
    """Test the DataContent class to ensure it initializes correctly."""
    # Create an instance of DataContent
    content = DataContent(data=b"test", media_type="application/octet-stream", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "data"
    assert content.uri == "data:application/octet-stream;base64,dGVzdA=="
    assert content.has_top_level_media_type("application") is True
    assert content.has_top_level_media_type("image") is False
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


def test_data_content_uri():
    """Test the DataContent class to ensure it initializes correctly with a URI."""
    # Create an instance of DataContent with a URI
    content = DataContent(uri="data:application/octet-stream;base64,dGVzdA==", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "data"
    assert content.uri == "data:application/octet-stream;base64,dGVzdA=="
    # media_type is extracted from URI now
    assert content.media_type == "application/octet-stream"
    assert content.has_top_level_media_type("application") is True
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


def test_data_content_invalid():
    """Test the DataContent class to ensure it raises an error for invalid initialization."""
    # Attempt to create an instance of DataContent with invalid data
    # not a proper uri
    with raises(ValueError):
        DataContent(uri="invalid_uri")
    # unknown media type
    with raises(ValueError):
        DataContent(uri="data:application/random;base64,dGVzdA==")
    # not valid base64 data would still be accepted by our basic validation
    # but it's not a critical issue for now


def test_data_content_empty():
    """Test the DataContent class to ensure it raises an error for empty data."""
    # Attempt to create an instance of DataContent with empty data
    with raises(ValueError):
        DataContent(data=b"", media_type="application/octet-stream")

    # Attempt to create an instance of DataContent with empty URI
    with raises(ValueError):
        DataContent(uri="")


def test_data_content_detect_image_format_from_base64():
    """Test the detect_image_format_from_base64 static method."""
    # Test each supported format
    png_data = b"\x89PNG\r\n\x1a\n" + b"fake_data"
    assert DataContent.detect_image_format_from_base64(base64.b64encode(png_data).decode()) == "png"

    jpeg_data = b"\xff\xd8\xff\xe0" + b"fake_data"
    assert DataContent.detect_image_format_from_base64(base64.b64encode(jpeg_data).decode()) == "jpeg"

    webp_data = b"RIFF" + b"1234" + b"WEBP" + b"fake_data"
    assert DataContent.detect_image_format_from_base64(base64.b64encode(webp_data).decode()) == "webp"

    gif_data = b"GIF89a" + b"fake_data"
    assert DataContent.detect_image_format_from_base64(base64.b64encode(gif_data).decode()) == "gif"

    # Test fallback behavior
    unknown_data = b"UNKNOWN_FORMAT"
    assert DataContent.detect_image_format_from_base64(base64.b64encode(unknown_data).decode()) == "png"

    # Test error handling
    assert DataContent.detect_image_format_from_base64("invalid_base64!") == "png"
    assert DataContent.detect_image_format_from_base64("") == "png"


def test_data_content_create_data_uri_from_base64():
    """Test the create_data_uri_from_base64 class method."""
    # Test with PNG data
    png_data = b"\x89PNG\r\n\x1a\n" + b"fake_data"
    png_base64 = base64.b64encode(png_data).decode()
    uri, media_type = DataContent.create_data_uri_from_base64(png_base64)

    assert uri == f"data:image/png;base64,{png_base64}"
    assert media_type == "image/png"

    # Test with different format
    jpeg_data = b"\xff\xd8\xff\xe0" + b"fake_data"
    jpeg_base64 = base64.b64encode(jpeg_data).decode()
    uri, media_type = DataContent.create_data_uri_from_base64(jpeg_base64)

    assert uri == f"data:image/jpeg;base64,{jpeg_base64}"
    assert media_type == "image/jpeg"

    # Test fallback for unknown format
    unknown_data = b"UNKNOWN_FORMAT"
    unknown_base64 = base64.b64encode(unknown_data).decode()
    uri, media_type = DataContent.create_data_uri_from_base64(unknown_base64)

    assert uri == f"data:image/png;base64,{unknown_base64}"
    assert media_type == "image/png"


# region UriContent


def test_uri_content():
    """Test the UriContent class to ensure it initializes correctly."""
    content = UriContent(uri="http://example.com", media_type="image/jpg", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "uri"
    assert content.uri == "http://example.com"
    assert content.media_type == "image/jpg"
    assert content.has_top_level_media_type("image") is True
    assert content.has_top_level_media_type("application") is False
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


# region: HostedFileContent


def test_hosted_file_content():
    """Test the HostedFileContent class to ensure it initializes correctly."""
    content = HostedFileContent(file_id="file-123", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "hosted_file"
    assert content.file_id == "file-123"
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


def test_hosted_file_content_minimal():
    """Test the HostedFileContent class with minimal parameters."""
    content = HostedFileContent(file_id="file-456")

    # Check the type and content
    assert content.type == "hosted_file"
    assert content.file_id == "file-456"
    assert content.additional_properties == {}
    assert content.raw_representation is None

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


# region: HostedVectorStoreContent


def test_hosted_vector_store_content():
    """Test the HostedVectorStoreContent class to ensure it initializes correctly."""
    content = HostedVectorStoreContent(vector_store_id="vs-789", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "hosted_vector_store"
    assert content.vector_store_id == "vs-789"
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, HostedVectorStoreContent)
    assert isinstance(content, BaseContent)


def test_hosted_vector_store_content_minimal():
    """Test the HostedVectorStoreContent class with minimal parameters."""
    content = HostedVectorStoreContent(vector_store_id="vs-101112")

    # Check the type and content
    assert content.type == "hosted_vector_store"
    assert content.vector_store_id == "vs-101112"
    assert content.additional_properties == {}
    assert content.raw_representation is None

    # Ensure the instance is of type BaseContent
    assert isinstance(content, HostedVectorStoreContent)
    assert isinstance(content, BaseContent)


# region FunctionCallContent


def test_function_call_content():
    """Test the FunctionCallContent class to ensure it initializes correctly."""
    content = FunctionCallContent(call_id="1", name="example_function", arguments={"param1": "value1"})

    # Check the type and content
    assert content.type == "function_call"
    assert content.name == "example_function"
    assert content.arguments == {"param1": "value1"}

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


def test_function_call_content_parse_arguments():
    c1 = FunctionCallContent(call_id="1", name="f", arguments='{"a": 1, "b": 2}')
    assert c1.parse_arguments() == {"a": 1, "b": 2}
    c2 = FunctionCallContent(call_id="1", name="f", arguments="not json")
    assert c2.parse_arguments() == {"raw": "not json"}
    c3 = FunctionCallContent(call_id="1", name="f", arguments={"x": None})
    assert c3.parse_arguments() == {"x": None}


def test_function_call_content_add_merging_and_errors():
    # str + str concatenation
    a = FunctionCallContent(call_id="1", name="f", arguments="abc")
    b = FunctionCallContent(call_id="1", name="f", arguments="def")
    c = a + b
    assert isinstance(c.arguments, str) and c.arguments == "abcdef"

    # dict + dict merge
    a = FunctionCallContent(call_id="1", name="f", arguments={"x": 1})
    b = FunctionCallContent(call_id="1", name="f", arguments={"y": 2})
    c = a + b
    assert c.arguments == {"x": 1, "y": 2}

    # incompatible argument types
    a = FunctionCallContent(call_id="1", name="f", arguments="abc")
    b = FunctionCallContent(call_id="1", name="f", arguments={"y": 2})
    with raises(TypeError):
        _ = a + b

    # incompatible call ids
    a = FunctionCallContent(call_id="1", name="f", arguments="abc")
    b = FunctionCallContent(call_id="2", name="f", arguments="def")

    with raises(AdditionItemMismatch):
        _ = a + b


# region FunctionResultContent


def test_function_result_content():
    """Test the FunctionResultContent class to ensure it initializes correctly."""
    content = FunctionResultContent(call_id="1", result={"param1": "value1"})

    # Check the type and content
    assert content.type == "function_result"
    assert content.result == {"param1": "value1"}

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


# region UsageDetails


def test_usage_details():
    usage = UsageDetails(input_token_count=5, output_token_count=10, total_token_count=15)
    assert usage.input_token_count == 5
    assert usage.output_token_count == 10
    assert usage.total_token_count == 15
    assert usage.additional_counts == {}


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

    combined_usage = usage1 + usage2
    assert combined_usage.input_token_count == 8
    assert combined_usage.output_token_count == 16
    assert combined_usage.total_token_count == 24
    assert combined_usage.additional_counts["test1"] == 20
    assert combined_usage.additional_counts["test2"] == 20
    assert combined_usage.additional_counts["test3"] == 30


def test_usage_details_fail():
    with raises(ValueError):
        UsageDetails(input_token_count=5, output_token_count=10, total_token_count=15, wrong_type="42.923")


def test_usage_details_additional_counts():
    usage = UsageDetails(input_token_count=5, output_token_count=10, total_token_count=15, **{"test": 1})
    assert usage.additional_counts["test"] == 1


def test_usage_details_add_with_none_and_type_errors():
    u = UsageDetails(input_token_count=1)
    # __add__ with None returns self (no change)
    v = u + None
    assert v is u
    # __iadd__ with None leaves unchanged
    u2 = UsageDetails(input_token_count=2)
    u2 += None
    assert u2.input_token_count == 2
    # wrong type raises
    with raises(ValueError):
        _ = u + 42  # type: ignore[arg-type]
    with raises(ValueError):
        u += 42  # type: ignore[arg-type]


# region UserInputRequest and Response


def test_function_approval_request_and_response_creation():
    """Test creating a FunctionApprovalRequestContent and producing a response."""
    fc = FunctionCallContent(call_id="call-1", name="do_something", arguments={"a": 1})
    req = FunctionApprovalRequestContent(id="req-1", function_call=fc)

    assert req.type == "function_approval_request"
    assert req.function_call == fc
    assert req.id == "req-1"
    assert isinstance(req, BaseContent)

    resp = req.create_response(True)

    assert isinstance(resp, FunctionApprovalResponseContent)
    assert resp.approved is True
    assert resp.function_call == fc
    assert resp.id == "req-1"


def test_function_approval_serialization_roundtrip():
    fc = FunctionCallContent(call_id="c2", name="f", arguments='{"x":1}')
    req = FunctionApprovalRequestContent(id="id-2", function_call=fc, additional_properties={"meta": 1})

    dumped = req.to_dict()
    loaded = FunctionApprovalRequestContent.from_dict(dumped)

    # Test that the basic properties match
    assert loaded.id == req.id
    assert loaded.additional_properties == req.additional_properties
    assert loaded.function_call.call_id == req.function_call.call_id
    assert loaded.function_call.name == req.function_call.name
    assert loaded.function_call.arguments == req.function_call.arguments

    # Skip the BaseModel validation test since we're no longer using Pydantic
    # The Contents union will need to be handled differently when we fully migrate


# region BaseContent Serialization


@mark.parametrize(
    "content_type, args",
    [
        (TextContent, {"text": "Hello, world!"}),
        (DataContent, {"data": b"Hello, world!", "media_type": "text/plain"}),
        (UriContent, {"uri": "http://example.com", "media_type": "text/html"}),
        (FunctionCallContent, {"call_id": "1", "name": "example_function", "arguments": {}}),
        (FunctionResultContent, {"call_id": "1", "result": {}}),
        (HostedFileContent, {"file_id": "file-123"}),
        (HostedVectorStoreContent, {"vector_store_id": "vs-789"}),
    ],
)
def test_ai_content_serialization(content_type: type[BaseContent], args: dict):
    content = content_type(**args)
    serialized = content.to_dict()
    deserialized = content_type.from_dict(serialized)
    # Note: Since we're no longer using Pydantic, we can't do direct equality comparison
    # Instead, let's check that the deserialized object has the same attributes

    # Special handling for DataContent which doesn't expose the original 'data' parameter
    if content_type == DataContent and "data" in args:
        # For DataContent created with data, check uri and media_type instead
        assert hasattr(deserialized, "uri")
        assert hasattr(deserialized, "media_type")
        assert deserialized.media_type == args["media_type"]  # type: ignore
        # Skip checking the 'data' attribute since it's converted to uri
        for key, value in args.items():
            if key != "data":  # Skip the 'data' key for DataContent
                assert getattr(deserialized, key) == value
    else:
        # Normal attribute checking for other content types
        for key, value in args.items():
            if value:
                assert getattr(deserialized, key) == value

    # For now, skip the TestModel validation since it still uses Pydantic
    # This would need to be updated when we migrate more classes
    # class TestModel(BaseModel):
    #     content: Contents
    #
    # test_item = TestModel.model_validate({"content": serialized})
    # assert isinstance(test_item.content, content_type)


# region ChatMessage


def test_chat_message_text():
    """Test the ChatMessage class to ensure it initializes correctly with text content."""
    # Create a ChatMessage with a role and text content
    message = ChatMessage(role="user", text="Hello, how are you?")

    # Check the type and content
    assert message.role == Role.USER
    assert len(message.contents) == 1
    assert isinstance(message.contents[0], TextContent)
    assert message.contents[0].text == "Hello, how are you?"
    assert message.text == "Hello, how are you?"

    # Ensure the instance is of type BaseContent
    assert isinstance(message.contents[0], BaseContent)


def test_chat_message_contents():
    """Test the ChatMessage class to ensure it initializes correctly with contents."""
    # Create a ChatMessage with a role and multiple contents
    content1 = TextContent("Hello, how are you?")
    content2 = TextContent("I'm fine, thank you!")
    message = ChatMessage(role="user", contents=[content1, content2])

    # Check the type and content
    assert message.role == Role.USER
    assert len(message.contents) == 2
    assert isinstance(message.contents[0], TextContent)
    assert isinstance(message.contents[1], TextContent)
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


# region ChatResponseUpdate


def test_chat_response_update():
    """Test the ChatResponseUpdate class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = TextContent(text="I'm doing well, thank you!")

    # Create a ChatResponseUpdate with the message
    response_update = ChatResponseUpdate(contents=[message])

    # Check the type and content
    assert response_update.contents[0].text == "I'm doing well, thank you!"
    assert isinstance(response_update.contents[0], TextContent)
    assert response_update.text == "I'm doing well, thank you!"


def test_chat_response_updates_to_chat_response_one():
    """Test converting ChatResponseUpdate to ChatResponse."""
    # Create a ChatMessage
    message1 = TextContent("I'm doing well, ")
    message2 = TextContent("thank you!")

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
    message1 = TextContent("I'm doing well, ")
    message2 = TextContent("thank you!")

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
    message1 = TextContent("I'm doing well, ")
    message2 = TextContent("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [
        ChatResponseUpdate(text=message1, message_id="1"),
        ChatResponseUpdate(contents=[TextReasoningContent(text="Additional context")], message_id="1"),
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
    message1 = TextContent("I'm doing well, ", raw_representation="I'm doing well, ")
    message2 = TextContent("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [
        ChatResponseUpdate(text=message1, message_id="1"),
        ChatResponseUpdate(text=message2, message_id="1"),
        ChatResponseUpdate(contents=[TextReasoningContent(text="Additional context")], message_id="1"),
        ChatResponseUpdate(contents=[TextContent(text="More context")], message_id="1"),
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
    assert isinstance(chat_response.messages[0].contents[0], TextContent)
    assert chat_response.messages[0].contents[0].text == "I'm doing well, thank you!"
    assert isinstance(chat_response.messages[0].contents[1], TextReasoningContent)
    assert chat_response.messages[0].contents[1].text == "Additional context"
    assert isinstance(chat_response.messages[0].contents[2], TextContent)
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
    auto_mode = ToolMode.AUTO
    required_any = ToolMode.REQUIRED_ANY
    required_mode = ToolMode.REQUIRED("example_function")
    none_mode = ToolMode.NONE

    # Check the type and content
    assert auto_mode.mode == "auto"
    assert auto_mode.required_function_name is None
    assert required_any.mode == "required"
    assert required_any.required_function_name is None
    assert required_mode.mode == "required"
    assert required_mode.required_function_name == "example_function"
    assert none_mode.mode == "none"
    assert none_mode.required_function_name is None

    # Ensure the instances are of type ToolMode
    assert isinstance(auto_mode, ToolMode)
    assert isinstance(required_any, ToolMode)
    assert isinstance(required_mode, ToolMode)
    assert isinstance(none_mode, ToolMode)

    assert ToolMode.REQUIRED("example_function") == ToolMode.REQUIRED("example_function")
    # serializer returns just the mode
    assert ToolMode.REQUIRED_ANY.serialize_model() == "required"


def test_chat_tool_mode_from_dict():
    """Test creating ToolMode from a dictionary."""
    mode_dict = {"mode": "required", "required_function_name": "example_function"}
    mode = ToolMode(**mode_dict)

    # Check the type and content
    assert mode.mode == "required"
    assert mode.required_function_name == "example_function"

    # Ensure the instance is of type ToolMode
    assert isinstance(mode, ToolMode)


# region ChatOptions


def test_chat_options_init() -> None:
    options = ChatOptions()
    assert options.model_id is None


def test_chat_options_tool_choice_validation_errors():
    with raises((ContentError, TypeError)):
        ChatOptions(tool_choice="invalid-choice")


def test_chat_options_and(ai_function_tool, ai_tool) -> None:
    options1 = ChatOptions(model_id="gpt-4o", tools=[ai_function_tool], logit_bias={"x": 1}, metadata={"a": "b"})
    options2 = ChatOptions(model_id="gpt-4.1", tools=[ai_tool], additional_properties={"p": 1})
    assert options1 != options2
    options3 = options1 & options2

    assert options3.model_id == "gpt-4.1"
    assert options3.tools == [ai_function_tool, ai_tool]
    assert options3.logit_bias == {"x": 1}
    assert options3.metadata == {"a": "b"}
    assert options3.additional_properties.get("p") == 1


# region Agent Response Fixtures


@fixture
def chat_message() -> ChatMessage:
    return ChatMessage(role=Role.USER, text="Hello")


@fixture
def text_content() -> TextContent:
    return TextContent(text="Test content")


@fixture
def agent_run_response(chat_message: ChatMessage) -> AgentRunResponse:
    return AgentRunResponse(messages=chat_message)


@fixture
def agent_run_response_update(text_content: TextContent) -> AgentRunResponseUpdate:
    return AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[text_content])


# region AgentRunResponse


def test_agent_run_response_init_single_message(chat_message: ChatMessage) -> None:
    response = AgentRunResponse(messages=chat_message)
    assert response.messages == [chat_message]


def test_agent_run_response_init_list_messages(chat_message: ChatMessage) -> None:
    response = AgentRunResponse(messages=[chat_message, chat_message])
    assert len(response.messages) == 2
    assert response.messages[0] == chat_message


def test_agent_run_response_init_none_messages() -> None:
    response = AgentRunResponse()
    assert response.messages == []


def test_agent_run_response_text_property(chat_message: ChatMessage) -> None:
    response = AgentRunResponse(messages=[chat_message, chat_message])
    assert response.text == "HelloHello"


def test_agent_run_response_text_property_empty() -> None:
    response = AgentRunResponse()
    assert response.text == ""


def test_agent_run_response_from_updates(agent_run_response_update: AgentRunResponseUpdate) -> None:
    updates = [agent_run_response_update, agent_run_response_update]
    response = AgentRunResponse.from_agent_run_response_updates(updates)
    assert len(response.messages) > 0
    assert response.text == "Test contentTest content"


def test_agent_run_response_str_method(chat_message: ChatMessage) -> None:
    response = AgentRunResponse(messages=chat_message)
    assert str(response) == "Hello"


# region AgentRunResponseUpdate


def test_agent_run_response_update_init_content_list(text_content: TextContent) -> None:
    update = AgentRunResponseUpdate(contents=[text_content, text_content])
    assert len(update.contents) == 2
    assert update.contents[0] == text_content


def test_agent_run_response_update_init_none_content() -> None:
    update = AgentRunResponseUpdate()
    assert update.contents == []


def test_agent_run_response_update_text_property(text_content: TextContent) -> None:
    update = AgentRunResponseUpdate(contents=[text_content, text_content])
    assert update.text == "Test contentTest content"


def test_agent_run_response_update_text_property_empty() -> None:
    update = AgentRunResponseUpdate()
    assert update.text == ""


def test_agent_run_response_update_str_method(text_content: TextContent) -> None:
    update = AgentRunResponseUpdate(contents=[text_content])
    assert str(update) == "Test content"


# region ErrorContent


def test_error_content_str():
    e1 = ErrorContent(message="Oops", error_code="E1")
    assert str(e1) == "Error E1: Oops"
    e2 = ErrorContent(message="Oops")
    assert str(e2) == "Oops"
    e3 = ErrorContent()
    assert str(e3) == "Unknown error"


# region Annotations


def test_annotations_models_and_roundtrip():
    span = TextSpanRegion(start_index=0, end_index=5)
    cit = CitationAnnotation(title="Doc", url="http://example.com", snippet="Snippet", annotated_regions=[span])

    # Attach to content
    content = TextContent(text="hello", additional_properties={"v": 1})
    content.annotations = [cit]

    dumped = content.to_dict()
    loaded = TextContent.from_dict(dumped)
    assert isinstance(loaded.annotations, list)
    assert len(loaded.annotations) == 1
    # After migration from Pydantic, annotations should be properly reconstructed as objects
    assert isinstance(loaded.annotations[0], CitationAnnotation)
    # Check the annotation properties
    loaded_cit = loaded.annotations[0]
    assert loaded_cit.type == "citation"
    assert loaded_cit.title == "Doc"
    assert loaded_cit.url == "http://example.com"
    assert loaded_cit.snippet == "Snippet"
    # Check the annotated_regions
    assert isinstance(loaded_cit.annotated_regions, list)
    assert len(loaded_cit.annotated_regions) == 1
    assert isinstance(loaded_cit.annotated_regions[0], TextSpanRegion)
    assert loaded_cit.annotated_regions[0].type == "text_span"
    assert loaded_cit.annotated_regions[0].start_index == 0
    assert loaded_cit.annotated_regions[0].end_index == 5


def test_function_call_merge_in_process_update_and_usage_aggregation():
    # Two function call chunks with same call_id should merge
    u1 = ChatResponseUpdate(contents=[FunctionCallContent(call_id="c1", name="f", arguments="{")], message_id="m")
    u2 = ChatResponseUpdate(contents=[FunctionCallContent(call_id="c1", name="f", arguments="}")], message_id="m")
    # plus usage
    u3 = ChatResponseUpdate(contents=[UsageContent(UsageDetails(input_token_count=1, output_token_count=2))])

    resp = ChatResponse.from_chat_response_updates([u1, u2, u3])
    assert len(resp.messages) == 1
    last_contents = resp.messages[0].contents
    assert any(isinstance(c, FunctionCallContent) for c in last_contents)
    fcs = [c for c in last_contents if isinstance(c, FunctionCallContent)]
    assert len(fcs) == 1
    assert fcs[0].arguments == "{}"
    assert resp.usage_details is not None
    assert resp.usage_details.input_token_count == 1
    assert resp.usage_details.output_token_count == 2


def test_function_call_incompatible_ids_are_not_merged():
    u1 = ChatResponseUpdate(contents=[FunctionCallContent(call_id="a", name="f", arguments="x")], message_id="m")
    u2 = ChatResponseUpdate(contents=[FunctionCallContent(call_id="b", name="f", arguments="y")], message_id="m")

    resp = ChatResponse.from_chat_response_updates([u1, u2])
    fcs = [c for c in resp.messages[0].contents if isinstance(c, FunctionCallContent)]
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
    t1 = TextContent("A", raw_representation={"r": 1}, additional_properties={"p": 1})
    t2 = TextContent("B")
    upd1 = ChatResponseUpdate(text=t1, message_id="x")
    upd2 = ChatResponseUpdate(text=t2, message_id="x")
    resp = ChatResponse.from_chat_response_updates([upd1, upd2])
    # After coalescing there should be a single TextContent with merged text and preserved props from first
    items = [c for c in resp.messages[0].contents if isinstance(c, TextContent)]
    assert len(items) >= 1
    assert items[0].text == "AB"
    assert items[0].raw_representation == {"r": 1}
    assert items[0].additional_properties == {"p": 1}


def test_function_call_content_parse_numeric_or_list():
    c_num = FunctionCallContent(call_id="1", name="f", arguments="123")
    assert c_num.parse_arguments() == {"raw": 123}
    c_list = FunctionCallContent(call_id="1", name="f", arguments="[1,2]")
    assert c_list.parse_arguments() == {"raw": [1, 2]}


def test_chat_tool_mode_eq_with_string():
    assert ToolMode.AUTO == "auto"


# region AgentRunResponse


@fixture
def agent_run_response_async() -> AgentRunResponse:
    return AgentRunResponse(messages=[ChatMessage(role="user", text="Hello")])


async def test_agent_run_response_from_async_generator():
    async def gen():
        yield AgentRunResponseUpdate(contents=[TextContent("A")])
        yield AgentRunResponseUpdate(contents=[TextContent("B")])

    r = await AgentRunResponse.from_agent_response_generator(gen())
    assert r.text == "AB"


# region Additional Coverage Tests for Serialization and Arithmetic Methods


def test_text_content_add_comprehensive_coverage():
    """Test TextContent __add__ method with various combinations to improve coverage."""

    # Test with None raw_representation
    t1 = TextContent("Hello", raw_representation=None, annotations=None)
    t2 = TextContent(" World", raw_representation=None, annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation is None
    assert result.annotations is None

    # Test first has raw_representation, second has None
    t1 = TextContent("Hello", raw_representation="raw1", annotations=None)
    t2 = TextContent(" World", raw_representation=None, annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == "raw1"

    # Test first has None, second has raw_representation
    t1 = TextContent("Hello", raw_representation=None, annotations=None)
    t2 = TextContent(" World", raw_representation="raw2", annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == "raw2"

    # Test both have raw_representation (non-list)
    t1 = TextContent("Hello", raw_representation="raw1", annotations=None)
    t2 = TextContent(" World", raw_representation="raw2", annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2"]

    # Test first has list raw_representation, second has single
    t1 = TextContent("Hello", raw_representation=["raw1", "raw2"], annotations=None)
    t2 = TextContent(" World", raw_representation="raw3", annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2", "raw3"]

    # Test both have list raw_representation
    t1 = TextContent("Hello", raw_representation=["raw1", "raw2"], annotations=None)
    t2 = TextContent(" World", raw_representation=["raw3", "raw4"], annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2", "raw3", "raw4"]

    # Test first has single raw_representation, second has list
    t1 = TextContent("Hello", raw_representation="raw1", annotations=None)
    t2 = TextContent(" World", raw_representation=["raw2", "raw3"], annotations=None)
    result = t1 + t2
    assert result.text == "Hello World"
    assert result.raw_representation == ["raw1", "raw2", "raw3"]


def test_text_content_iadd_coverage():
    """Test TextContent __iadd__ method for better coverage."""

    t1 = TextContent("Hello", raw_representation="raw1", additional_properties={"key1": "val1"})
    t2 = TextContent(" World", raw_representation="raw2", additional_properties={"key2": "val2"})

    original_id = id(t1)
    t1 += t2

    # Should modify in place
    assert id(t1) == original_id
    assert t1.text == "Hello World"
    assert t1.raw_representation == ["raw1", "raw2"]
    assert t1.additional_properties == {"key1": "val1", "key2": "val2"}


def test_text_reasoning_content_add_coverage():
    """Test TextReasoningContent __add__ method for better coverage."""

    t1 = TextReasoningContent("Thinking 1")
    t2 = TextReasoningContent(" Thinking 2")

    result = t1 + t2
    assert result.text == "Thinking 1 Thinking 2"


def test_text_reasoning_content_iadd_coverage():
    """Test TextReasoningContent __iadd__ method for better coverage."""

    t1 = TextReasoningContent("Thinking 1")
    t2 = TextReasoningContent(" Thinking 2")

    original_id = id(t1)
    t1 += t2

    assert id(t1) == original_id
    assert t1.text == "Thinking 1 Thinking 2"


def test_comprehensive_to_dict_exclude_options():
    """Test to_dict methods with various exclude options for better coverage."""

    # Test TextContent with exclude_none
    text_content = TextContent("Hello", raw_representation=None, additional_properties={"prop": "val"})
    text_dict = text_content.to_dict(exclude_none=True)
    assert "raw_representation" not in text_dict
    assert text_dict["prop"] == "val"

    # Test with custom exclude set
    text_dict_exclude = text_content.to_dict(exclude={"additional_properties"})
    assert "additional_properties" not in text_dict_exclude
    assert "text" in text_dict_exclude

    # Test UsageDetails with additional counts
    usage = UsageDetails(input_token_count=5, custom_count=10)
    usage_dict = usage.to_dict()
    assert usage_dict["input_token_count"] == 5
    assert usage_dict["custom_count"] == 10

    # Test UsageDetails exclude_none
    usage_none = UsageDetails(input_token_count=5, output_token_count=None)
    usage_dict_no_none = usage_none.to_dict(exclude_none=True)
    assert "output_token_count" not in usage_dict_no_none
    assert usage_dict_no_none["input_token_count"] == 5


def test_usage_details_iadd_edge_cases():
    """Test UsageDetails __iadd__ with edge cases for better coverage."""

    # Test with None values
    u1 = UsageDetails(input_token_count=None, output_token_count=5, custom1=10)
    u2 = UsageDetails(input_token_count=3, output_token_count=None, custom2=20)

    u1 += u2
    assert u1.input_token_count == 3
    assert u1.output_token_count == 5
    assert u1.additional_counts["custom1"] == 10
    assert u1.additional_counts["custom2"] == 20

    # Test merging additional counts
    u3 = UsageDetails(input_token_count=1, shared_count=5)
    u4 = UsageDetails(input_token_count=2, shared_count=15)

    u3 += u4
    assert u3.input_token_count == 3
    assert u3.additional_counts["shared_count"] == 20


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
    assert isinstance(message.contents[0], TextContent)
    assert isinstance(message.contents[1], FunctionCallContent)
    assert isinstance(message.contents[2], FunctionResultContent)

    # Test round-trip
    message_dict = message.to_dict()
    assert len(message_dict["contents"]) == 3


def test_chat_options_edge_cases():
    """Test ChatOptions with edge cases for better coverage."""

    # Test with tools conversion
    def sample_tool():
        return "test"

    options = ChatOptions(tools=[sample_tool], tool_choice="auto")
    assert options.tool_choice == ToolMode.AUTO

    # Test to_dict with ToolMode
    options_dict = options.to_dict()
    assert "tool_choice" in options_dict

    # Test from_dict with tool_choice dict
    data_with_dict_tool_choice = {
        "model_id": "gpt-4",
        "tool_choice": {"mode": "required", "required_function_name": "test_func"},
    }
    options_from_dict = ChatOptions.from_dict(data_with_dict_tool_choice)
    assert options_from_dict.tool_choice.mode == "required"
    assert options_from_dict.tool_choice.required_function_name == "test_func"


def test_text_content_add_type_error():
    """Test TextContent __add__ raises TypeError for incompatible types."""
    t1 = TextContent("Hello")

    with raises(TypeError, match="Incompatible type"):
        t1 + "not a TextContent"


def test_comprehensive_serialization_methods():
    """Test from_dict and to_dict methods for various content types."""

    # Test TextContent with all fields
    text_data = {
        "text": "Hello world",
        "raw_representation": {"key": "value"},
        "prop": "val",
        "annotations": None,
    }
    text_content = TextContent.from_dict(text_data)
    assert text_content.text == "Hello world"
    assert text_content.raw_representation == {"key": "value"}
    assert text_content.additional_properties == {"prop": "val"}

    # Test round-trip
    text_dict = text_content.to_dict()
    assert text_dict["text"] == "Hello world"
    assert text_dict["prop"] == "val"
    # Note: raw_representation is always excluded from to_dict() output

    # Test with exclude_none
    text_dict_no_none = text_content.to_dict(exclude_none=True)
    assert "annotations" not in text_dict_no_none

    # Test FunctionResultContent
    result_data = {"call_id": "call123", "result": "success", "additional_properties": {"meta": "data"}}
    result_content = FunctionResultContent.from_dict(result_data)
    assert result_content.call_id == "call123"
    assert result_content.result == "success"


def test_chat_options_tool_choice_variations():
    """Test ChatOptions from_dict and to_dict with various tool_choice values."""

    # Test with string tool_choice
    data = {"model_id": "gpt-4", "tool_choice": "auto", "temperature": 0.7}
    options = ChatOptions.from_dict(data)
    assert options.tool_choice == ToolMode.AUTO

    # Test with dict tool_choice
    data_dict = {
        "model_id": "gpt-4",
        "tool_choice": {"mode": "required", "required_function_name": "test_func"},
        "temperature": 0.7,
    }
    options_dict = ChatOptions.from_dict(data_dict)
    assert options_dict.tool_choice.mode == "required"
    assert options_dict.tool_choice.required_function_name == "test_func"

    # Test to_dict with ToolMode
    options_dict_serialized = options_dict.to_dict()
    assert "tool_choice" in options_dict_serialized
    assert isinstance(options_dict_serialized["tool_choice"], dict)


def test_chat_message_complex_content_serialization():
    """Test ChatMessage serialization with various content types."""

    # Create a message with multiple content types
    contents = [
        TextContent("Hello"),
        FunctionCallContent(call_id="call1", name="func", arguments={"arg": "val"}),
        FunctionResultContent(call_id="call1", result="success"),
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
    assert isinstance(reconstructed.contents[0], TextContent)
    assert isinstance(reconstructed.contents[1], FunctionCallContent)
    assert isinstance(reconstructed.contents[2], FunctionResultContent)


def test_usage_content_serialization_with_details():
    """Test UsageContent from_dict and to_dict with UsageDetails conversion."""

    # Test from_dict with details as dict
    usage_data = {
        "type": "usage",
        "details": {
            "type": "usage_details",
            "input_token_count": 10,
            "output_token_count": 20,
            "total_token_count": 30,
            "custom_count": 5,
        },
    }
    usage_content = UsageContent.from_dict(usage_data)
    assert isinstance(usage_content.details, UsageDetails)
    assert usage_content.details.input_token_count == 10
    assert usage_content.details.additional_counts["custom_count"] == 5

    # Test to_dict with UsageDetails object
    usage_dict = usage_content.to_dict()
    assert isinstance(usage_dict["details"], dict)
    assert usage_dict["details"]["input_token_count"] == 10


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
    response_content = FunctionApprovalResponseContent.from_dict(response_data)
    assert isinstance(response_content.function_call, FunctionCallContent)
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
    assert isinstance(response.usage_details, UsageDetails)
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
            {"type": "error", "error": "An error occurred"},
            {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            {"type": "function_result", "call_id": "call1", "result": "success"},
            {"type": "usage", "details": {"type": "usage_details", "input_token_count": 1}},
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
    assert isinstance(update.contents[0], TextContent)
    assert isinstance(update.contents[1], DataContent)
    assert isinstance(update.contents[2], UriContent)
    assert isinstance(update.contents[3], ErrorContent)
    assert isinstance(update.contents[4], FunctionCallContent)
    assert isinstance(update.contents[5], FunctionResultContent)
    assert isinstance(update.contents[6], UsageContent)
    assert isinstance(update.contents[7], HostedFileContent)
    assert isinstance(update.contents[8], HostedVectorStoreContent)
    assert isinstance(update.contents[9], FunctionApprovalRequestContent)
    assert isinstance(update.contents[10], FunctionApprovalResponseContent)
    assert isinstance(update.contents[11], TextReasoningContent)


def test_agent_run_response_complex_serialization():
    """Test AgentRunResponse from_dict and to_dict with messages and usage_details."""

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

    response = AgentRunResponse.from_dict(response_data)
    assert len(response.messages) == 2
    assert isinstance(response.messages[0], ChatMessage)
    assert isinstance(response.usage_details, UsageDetails)

    # Test to_dict
    response_dict = response.to_dict()
    assert len(response_dict["messages"]) == 2
    assert isinstance(response_dict["messages"][0], dict)
    assert isinstance(response_dict["usage_details"], dict)


def test_agent_run_response_update_all_content_types():
    """Test AgentRunResponseUpdate from_dict with all content types and role handling."""

    update_data = {
        "contents": [
            {"type": "text", "text": "Hello"},
            {"type": "data", "data": b"base64data", "media_type": "text/plain"},
            {"type": "uri", "uri": "http://example.com", "media_type": "text/html"},
            {"type": "error", "error": "An error occurred"},
            {"type": "function_call", "call_id": "call1", "name": "func", "arguments": {}},
            {"type": "function_result", "call_id": "call1", "result": "success"},
            {"type": "usage", "details": {"type": "usage_details", "input_token_count": 1}},
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

    update = AgentRunResponseUpdate.from_dict(update_data)
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
    update_str = AgentRunResponseUpdate.from_dict(update_data_str_role)
    assert isinstance(update_str.role, Role)
    assert update_str.role.value == "user"


# region Serialization


@mark.parametrize(
    "content_class,init_kwargs",
    [
        pytest.param(
            TextContent,
            {
                "type": "text",
                "text": "Hello world",
                "raw_representation": "raw",
            },
            id="text_content",
        ),
        pytest.param(
            TextReasoningContent,
            {
                "type": "text_reasoning",
                "text": "Reasoning text",
                "raw_representation": "raw",
            },
            id="text_reasoning_content",
        ),
        pytest.param(
            DataContent,
            {
                "type": "data",
                "uri": "data:text/plain;base64,dGVzdCBkYXRh",
            },
            id="data_content_with_uri",
        ),
        pytest.param(
            DataContent,
            {
                "type": "data",
                "data": b"test data",
                "media_type": "text/plain",
            },
            id="data_content_with_bytes",
        ),
        pytest.param(
            UriContent,
            {
                "type": "uri",
                "uri": "http://example.com",
                "media_type": "text/html",
            },
            id="uri_content",
        ),
        pytest.param(
            HostedFileContent,
            {"type": "hosted_file", "file_id": "file-123"},
            id="hosted_file_content",
        ),
        pytest.param(
            HostedVectorStoreContent,
            {
                "type": "hosted_vector_store",
                "vector_store_id": "vs-789",
            },
            id="hosted_vector_store_content",
        ),
        pytest.param(
            FunctionCallContent,
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "test_func",
                "arguments": {"arg": "val"},
            },
            id="function_call_content",
        ),
        pytest.param(
            FunctionResultContent,
            {
                "type": "function_result",
                "call_id": "call-1",
                "result": "success",
            },
            id="function_result_content",
        ),
        pytest.param(
            ErrorContent,
            {
                "type": "error",
                "message": "Error occurred",
                "error_code": "E001",
            },
            id="error_content",
        ),
        pytest.param(
            UsageContent,
            {
                "type": "usage",
                "details": {
                    "type": "usage_details",
                    "input_token_count": 10,
                    "output_token_count": 20,
                    "reasoning_tokens": 5,
                },
            },
            id="usage_content",
        ),
        pytest.param(
            FunctionApprovalRequestContent,
            {
                "type": "function_approval_request",
                "id": "req-1",
                "function_call": {"type": "function_call", "call_id": "call-1", "name": "test_func", "arguments": {}},
            },
            id="function_approval_request",
        ),
        pytest.param(
            FunctionApprovalResponseContent,
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
            AgentRunResponse,
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
            id="agent_run_response",
        ),
        pytest.param(
            AgentRunResponseUpdate,
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
            id="agent_run_response_update",
        ),
    ],
)
def test_content_roundtrip_serialization(content_class: type[BaseContent], init_kwargs: dict[str, Any]):
    """Test to_dict/from_dict roundtrip for all content types."""
    # Create instance
    content = content_class(**init_kwargs)

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
        if content_class == DataContent and key == "data":
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

            else:
                assert reconstructed_value == value
        # Special handling for dicts that get converted to objects (like UsageDetails, FunctionCallContent)
        elif isinstance(value, dict) and hasattr(reconstructed_value, "to_dict"):
            # Compare the dict with the serialized form of the object, excluding 'type' key
            reconstructed_dict = reconstructed_value.to_dict()
            if value:
                assert len(reconstructed_dict) == len(value)
        else:
            assert reconstructed_value == value


def test_text_content_with_annotations_serialization():
    """Test TextContent with CitationAnnotation and TextSpanRegion roundtrip serialization."""
    # Create TextSpanRegion
    region = TextSpanRegion(start_index=0, end_index=5)

    # Create CitationAnnotation with region
    citation = CitationAnnotation(
        title="Test Citation",
        url="http://example.com/citation",
        file_id="file-123",
        tool_name="test_tool",
        snippet="This is a test snippet",
        annotated_regions=[region],
        additional_properties={"custom": "value"},
    )

    # Create TextContent with annotation
    content = TextContent(
        text="Hello world", annotations=[citation], additional_properties={"content_key": "content_val"}
    )

    # Serialize to dict
    content_dict = content.to_dict()

    # Verify structure
    assert content_dict["type"] == "text"
    assert content_dict["text"] == "Hello world"
    assert content_dict["content_key"] == "content_val"
    assert len(content_dict["annotations"]) == 1

    # Verify annotation structure
    annotation_dict = content_dict["annotations"][0]
    assert annotation_dict["type"] == "citation"
    assert annotation_dict["title"] == "Test Citation"
    assert annotation_dict["url"] == "http://example.com/citation"
    assert annotation_dict["file_id"] == "file-123"
    assert annotation_dict["tool_name"] == "test_tool"
    assert annotation_dict["snippet"] == "This is a test snippet"
    assert annotation_dict["custom"] == "value"

    # Verify region structure
    assert len(annotation_dict["annotated_regions"]) == 1
    region_dict = annotation_dict["annotated_regions"][0]
    assert region_dict["type"] == "text_span"
    assert region_dict["start_index"] == 0
    assert region_dict["end_index"] == 5

    # Deserialize from dict
    reconstructed = TextContent.from_dict(content_dict)

    # Verify reconstructed content
    assert isinstance(reconstructed, TextContent)
    assert reconstructed.text == "Hello world"
    assert reconstructed.type == "text"
    assert reconstructed.additional_properties == {"content_key": "content_val"}

    # Verify reconstructed annotation
    assert len(reconstructed.annotations) == 1  # type: ignore[arg-type]
    recon_annotation = reconstructed.annotations[0]  # type: ignore[index]
    assert isinstance(recon_annotation, CitationAnnotation)
    assert recon_annotation.title == "Test Citation"
    assert recon_annotation.url == "http://example.com/citation"
    assert recon_annotation.file_id == "file-123"
    assert recon_annotation.tool_name == "test_tool"
    assert recon_annotation.snippet == "This is a test snippet"
    assert recon_annotation.additional_properties == {"custom": "value"}

    # Verify reconstructed region
    assert len(recon_annotation.annotated_regions) == 1  # type: ignore[arg-type]
    recon_region = recon_annotation.annotated_regions[0]  # type: ignore[index]
    assert isinstance(recon_region, TextSpanRegion)
    assert recon_region.start_index == 0
    assert recon_region.end_index == 5
    assert recon_region.type == "text_span"


def test_text_content_with_multiple_annotations_serialization():
    """Test TextContent with multiple annotations roundtrip serialization."""
    # Create multiple regions
    region1 = TextSpanRegion(start_index=0, end_index=5)
    region2 = TextSpanRegion(start_index=6, end_index=11)

    # Create multiple citations
    citation1 = CitationAnnotation(title="Citation 1", url="http://example.com/1", annotated_regions=[region1])

    citation2 = CitationAnnotation(title="Citation 2", url="http://example.com/2", annotated_regions=[region2])

    # Create TextContent with multiple annotations
    content = TextContent(text="Hello world", annotations=[citation1, citation2])

    # Serialize
    content_dict = content.to_dict()

    # Verify we have 2 annotations
    assert len(content_dict["annotations"]) == 2
    assert content_dict["annotations"][0]["title"] == "Citation 1"
    assert content_dict["annotations"][1]["title"] == "Citation 2"

    # Deserialize
    reconstructed = TextContent.from_dict(content_dict)

    # Verify reconstruction
    assert len(reconstructed.annotations) == 2
    assert all(isinstance(ann, CitationAnnotation) for ann in reconstructed.annotations)
    assert reconstructed.annotations[0].title == "Citation 1"
    assert reconstructed.annotations[1].title == "Citation 2"
    assert all(isinstance(ann.annotated_regions[0], TextSpanRegion) for ann in reconstructed.annotations)
