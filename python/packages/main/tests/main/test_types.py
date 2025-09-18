# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, MutableSequence
from typing import Any

from pydantic import BaseModel, ValidationError
from pytest import fixture, mark, raises

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AIFunction,
    BaseContent,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatToolMode,
    CitationAnnotation,
    Contents,
    DataContent,
    ErrorContent,
    FinishReason,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    GeneratedEmbeddings,
    HostedFileContent,
    HostedVectorStoreContent,
    Role,
    SpeechToTextOptions,
    TextContent,
    TextReasoningContent,
    TextSpanRegion,
    TextToSpeechOptions,
    ToolProtocol,
    UriContent,
    UsageContent,
    UsageDetails,
    ai_function,
)
from agent_framework.exceptions import AdditionItemMismatch


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
    with raises(ValidationError):
        content.type = "ai"


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
    with raises(ValidationError):
        content.type = "ai"


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
    # media_type attribute is None when created from uri-only
    assert content.has_top_level_media_type("application") is False
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type BaseContent
    assert isinstance(content, BaseContent)


def test_data_content_invalid():
    """Test the DataContent class to ensure it raises an error for invalid initialization."""
    # Attempt to create an instance of DataContent with invalid data
    # not a proper uri
    with raises(ValidationError):
        DataContent(uri="invalid_uri")
    # unknown media type
    with raises(ValidationError):
        DataContent(uri="data:application/random;base64,dGVzdA==")
    # not valid base64 data

    with raises(ValidationError):
        DataContent(uri="data:application/json;base64,dGVzdA&")


def test_data_content_empty():
    """Test the DataContent class to ensure it raises an error for empty data."""
    # Attempt to create an instance of DataContent with empty data
    with raises(ValidationError):
        DataContent(data=b"", media_type="application/octet-stream")

    # Attempt to create an instance of DataContent with empty URI
    with raises(ValidationError):
        DataContent(uri="")


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
    assert content.additional_properties is None
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
    assert content.additional_properties is None
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
    with raises(ValidationError):
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

    dumped = req.model_dump()
    loaded = FunctionApprovalRequestContent.model_validate(dumped)
    assert loaded == req

    class TestModel(BaseModel):
        content: Contents

    test_item = TestModel.model_validate({"content": dumped})
    assert isinstance(test_item.content, FunctionApprovalRequestContent)


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
    serialized = content.model_dump()
    deserialized = content_type.model_validate(serialized)
    assert deserialized == content

    class TestModel(BaseModel):
        content: Contents

    test_item = TestModel.model_validate({"content": serialized})

    assert isinstance(test_item.content, content_type)


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


def test_chat_response_update_with_method():
    u = ChatResponseUpdate(text="Hello", message_id="1")
    v = u.with_(contents=[TextContent(" world")])
    assert v is not u
    assert v.text == "Hello world"
    assert v.message_id == "1"


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


@mark.asyncio
async def test_chat_response_from_async_generator():
    async def gen() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(text="Hello", message_id="1")
        yield ChatResponseUpdate(text=" world", message_id="1")

    resp = await ChatResponse.from_chat_response_generator(gen())
    assert resp.text == "Hello world"


@mark.asyncio
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


@mark.asyncio
async def test_chat_response_from_async_generator_output_format_in_method():
    async def gen() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(text='{ "respon', message_id="1")
        yield ChatResponseUpdate(text='se": "Hello" }', message_id="1")

    resp = await ChatResponse.from_chat_response_generator(gen(), output_format_type=OutputModel)
    assert resp.text == '{ "response": "Hello" }'
    assert resp.value is not None
    assert resp.value.response == "Hello"


# region ChatToolMode


def test_chat_tool_mode():
    """Test the ChatToolMode class to ensure it initializes correctly."""
    # Create instances of ChatToolMode
    auto_mode = ChatToolMode.AUTO
    required_any = ChatToolMode.REQUIRED_ANY
    required_mode = ChatToolMode.REQUIRED("example_function")
    none_mode = ChatToolMode.NONE

    # Check the type and content
    assert auto_mode.mode == "auto"
    assert auto_mode.required_function_name is None
    assert required_any.mode == "required"
    assert required_any.required_function_name is None
    assert required_mode.mode == "required"
    assert required_mode.required_function_name == "example_function"
    assert none_mode.mode == "none"
    assert none_mode.required_function_name is None

    # Ensure the instances are of type ChatToolMode
    assert isinstance(auto_mode, ChatToolMode)
    assert isinstance(required_any, ChatToolMode)
    assert isinstance(required_mode, ChatToolMode)
    assert isinstance(none_mode, ChatToolMode)

    assert ChatToolMode.REQUIRED("example_function") == ChatToolMode.REQUIRED("example_function")
    # serializer returns just the mode
    assert ChatToolMode.REQUIRED_ANY.model_dump() == "required"


def test_chat_tool_mode_from_dict():
    """Test creating ChatToolMode from a dictionary."""
    mode_dict = {"mode": "required", "required_function_name": "example_function"}
    mode = ChatToolMode(**mode_dict)

    # Check the type and content
    assert mode.mode == "required"
    assert mode.required_function_name == "example_function"

    # Ensure the instance is of type ChatToolMode
    assert isinstance(mode, ChatToolMode)


def test_generated_embeddings():
    """Test the GeneratedEmbeddings class to ensure it initializes correctly."""
    # Create an instance of GeneratedEmbeddings
    embeddings = GeneratedEmbeddings(embeddings=[[0.1, 0.2, 0.3]])

    # Check the type and content
    assert embeddings.embeddings == [[0.1, 0.2, 0.3]]

    # Ensure the instance is of type GeneratedEmbeddings
    assert isinstance(embeddings, GeneratedEmbeddings)
    assert issubclass(GeneratedEmbeddings, MutableSequence)


# region ChatOptions


def test_chat_options_init() -> None:
    options = ChatOptions()
    assert options.ai_model_id is None


def test_chat_options_init_with_args(ai_function_tool, ai_tool) -> None:
    options = ChatOptions(
        ai_model_id="gpt-4",
        max_tokens=1024,
        temperature=0.7,
        top_p=0.9,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        user="user-123",
        tools=[ai_function_tool, ai_tool],
        tool_choice="required",
        additional_properties={"custom": True},
        logit_bias={"a": 1},
        metadata={"m": "v"},
    )
    assert options.ai_model_id == "gpt-4"
    assert options.max_tokens == 1024
    assert options.temperature == 0.7
    assert options.top_p == 0.9
    assert options.presence_penalty == 0.0
    assert options.frequency_penalty == 0.0
    assert options.user == "user-123"
    for tool in options.tools:
        assert isinstance(tool, ToolProtocol)
        assert tool.name is not None
        assert tool.description is not None
        if isinstance(tool, AIFunction):
            assert tool.parameters() is not None

    settings = options.to_provider_settings()
    assert settings["model"] == "gpt-4"  # uses alias
    assert settings["tool_choice"] == "required"  # serialized via model_serializer
    assert settings["custom"] is True  # from additional_properties
    assert "additional_properties" not in settings


def test_chat_options_tool_choice_validation_errors():
    with raises((ValidationError, TypeError)):
        ChatOptions(tool_choice="invalid-choice")


def test_chat_options_tool_choice_excluded_when_no_tools():
    options = ChatOptions(tool_choice="auto")
    settings = options.to_provider_settings()
    assert "tool_choice" not in settings


def test_chat_options_and(ai_function_tool, ai_tool) -> None:
    options1 = ChatOptions(ai_model_id="gpt-4o", tools=[ai_function_tool], logit_bias={"x": 1}, metadata={"a": "b"})
    options2 = ChatOptions(ai_model_id="gpt-4.1", tools=[ai_tool], additional_properties={"p": 1})
    assert options1 != options2
    options3 = options1 & options2

    assert options3.ai_model_id == "gpt-4.1"
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

    dumped = content.model_dump()
    loaded = TextContent.model_validate(dumped)
    assert isinstance(loaded.annotations, list)
    assert len(loaded.annotations) == 1
    assert isinstance(loaded.annotations[0], dict) is False  # pydantic parsed into models
    # discriminators preserved
    assert any(getattr(a, "type", None) == "citation" for a in loaded.annotations)


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


# region Speech/Text To Speech options


def test_speech_to_text_options_provider_settings():
    o = SpeechToTextOptions(ai_model_id="stt", additional_properties={"x": 1})
    settings = o.to_provider_settings()
    assert settings["model"] == "stt"
    assert settings["x"] == 1
    assert "additional_properties" not in settings


def test_text_to_speech_options_provider_settings():
    o = TextToSpeechOptions(ai_model_id="tts", response_format="wav", speed=1.2, additional_properties={"x": 2})
    settings = o.to_provider_settings()
    assert settings["model"] == "tts"
    assert settings["response_format"] == "wav"
    assert settings["x"] == 2


# region GeneratedEmbeddings operations


def test_generated_embeddings_operations():
    g = GeneratedEmbeddings[int](embeddings=[1, 2, 3])
    assert 2 in g
    assert list(iter(g)) == [1, 2, 3]
    assert len(g) == 3
    assert list(reversed(g)) == [3, 2, 1]
    assert g.index(2) == 1
    assert g.count(2) == 1
    assert g[0] == 1
    assert g[0:2] == [1, 2]

    g[1] = 5
    assert g[1] == 5
    g[1:3] = [7, 8]
    assert g[1:] == [7, 8]

    with raises(TypeError):
        g[0] = [9]  # int index cannot be set with iterable
    with raises(TypeError):
        g[0:1] = 9  # slice requires iterable

    del g[0]
    assert g.embeddings == [7, 8]
    del g[0:1]
    assert g.embeddings == [8]

    g.insert(0, 1)
    g.append(2)
    g.extend([3, 4])
    assert g.embeddings == [1, 8, 2, 3, 4]
    g.reverse()
    assert g.embeddings == [4, 3, 2, 8, 1]
    assert g.pop() == 1
    g.remove(8)
    assert g.embeddings == [4, 3, 2]

    # iadd with another GeneratedEmbeddings, including usage merge
    g2 = GeneratedEmbeddings[int](embeddings=[5], usage=UsageDetails(input_token_count=1))
    g.usage = UsageDetails(input_token_count=2)
    g += g2
    assert g.embeddings[-1] == 5
    assert g.usage.input_token_count == 3

    # clear
    g.additional_properties = {"a": 1}
    g.clear()
    assert g.embeddings == []
    assert g.usage is None
    assert g.additional_properties == {}


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
        ai_model_id="model-x",
        created_at="t0",
        finish_reason=FinishReason.STOP,
        additional_properties={"k": "v"},
    )
    resp = ChatResponse.from_chat_response_updates([upd])
    assert resp.response_id == "rid"
    assert resp.created_at == "t0"
    assert resp.conversation_id == "cid"
    assert resp.ai_model_id == "model-x"
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
    assert ChatToolMode.AUTO == "auto"


def test_chat_options_tool_choice_dict_mapping(ai_tool):
    opts = ChatOptions(tool_choice={"mode": "required", "required_function_name": "fn"}, tools=[ai_tool])
    assert isinstance(opts.tool_choice, ChatToolMode)
    assert opts.tool_choice.mode == "required"
    assert opts.tool_choice.required_function_name == "fn"
    # provider settings serialize to just the mode
    settings = opts.to_provider_settings()
    assert settings["tool_choice"] == "required"


def test_chat_options_to_provider_settings_with_falsy_values():
    """Test that falsy values (except None) are included in provider settings."""
    options = ChatOptions(
        temperature=0.0,  # falsy but not None
        top_p=0.0,  # falsy but not None
        presence_penalty=False,  # falsy but not None
        frequency_penalty=None,  # None - should be excluded
        additional_properties={"empty_string": "", "zero": 0, "false_flag": False, "none_value": None},
    )

    settings = options.to_provider_settings()

    # Falsy values that are not None should be included
    assert "temperature" in settings
    assert isinstance(settings["temperature"], float)
    assert settings["temperature"] == 0.0
    assert "top_p" in settings
    assert isinstance(settings["top_p"], float)
    assert settings["top_p"] == 0.0
    assert "presence_penalty" in settings
    assert isinstance(settings["presence_penalty"], float)  # converted to float
    assert settings["presence_penalty"] == 0.0

    # None values should be excluded
    assert "frequency_penalty" not in settings

    # Additional properties - falsy values should always be included
    assert "empty_string" in settings
    assert settings["empty_string"] == ""
    assert "zero" in settings
    assert settings["zero"] == 0
    assert "false_flag" in settings
    assert settings["false_flag"] is False
    assert "none_value" in settings
    assert settings["none_value"] is None


def test_chat_options_empty_logit_bias_and_metadata_excluded():
    """Test that empty logit_bias and metadata are excluded from provider settings."""
    options = ChatOptions(
        ai_model_id="gpt-4o",
        logit_bias={},  # empty dict should be excluded
        metadata={},  # empty dict should be excluded
    )

    settings = options.to_provider_settings()

    # Empty logit_bias and metadata should be excluded
    assert "logit_bias" not in settings
    assert "metadata" not in settings
    assert settings["model"] == "gpt-4o"


# region AgentRunResponse


@fixture
def agent_run_response_async() -> AgentRunResponse:
    return AgentRunResponse(messages=[ChatMessage(role="user", text="Hello")])


@mark.asyncio
async def test_agent_run_response_from_async_generator():
    async def gen():
        yield AgentRunResponseUpdate(contents=[TextContent("A")])
        yield AgentRunResponseUpdate(contents=[TextContent("B")])

    r = await AgentRunResponse.from_agent_response_generator(gen())
    assert r.text == "AB"
