# Copyright (c) Microsoft. All rights reserved.

from collections.abc import MutableSequence

from pydantic import BaseModel, ValidationError
from pytest import fixture, mark, raises

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AIContent,
    AIContents,
    AITool,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    ChatToolMode,
    DataContent,
    FunctionCallContent,
    FunctionResultContent,
    GeneratedEmbeddings,
    StructuredResponse,
    TextContent,
    TextReasoningContent,
    UriContent,
    UsageDetails,
)

# region: TextContent


def test_text_content_positional():
    """Test the TextContent class to ensure it initializes correctly and inherits from AIContent."""
    # Create an instance of TextContent
    content = TextContent("Hello, world!", raw_representation="Hello, world!", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "text"
    assert content.text == "Hello, world!"
    assert content.raw_representation == "Hello, world!"
    assert content.additional_properties["version"] == 1
    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)
    with raises(ValidationError):
        content.type = "ai"


def test_text_content_keyword():
    """Test the TextContent class to ensure it initializes correctly and inherits from AIContent."""
    # Create an instance of TextContent
    content = TextContent(
        text="Hello, world!", raw_representation="Hello, world!", additional_properties={"version": 1}
    )

    # Check the type and content
    assert content.type == "text"
    assert content.text == "Hello, world!"
    assert content.raw_representation == "Hello, world!"
    assert content.additional_properties["version"] == 1
    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)
    with raises(ValidationError):
        content.type = "ai"


# region: DataContent


def test_data_content_bytes():
    """Test the DataContent class to ensure it initializes correctly."""
    # Create an instance of DataContent
    content = DataContent(data=b"test", media_type="application/octet-stream", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "data"
    assert content.uri == "data:application/octet-stream;base64,dGVzdA=="
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)


def test_data_content_uri():
    """Test the DataContent class to ensure it initializes correctly with a URI."""
    # Create an instance of DataContent with a URI
    content = DataContent(uri="data:application/octet-stream;base64,dGVzdA==", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "data"
    assert content.uri == "data:application/octet-stream;base64,dGVzdA=="
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)


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


# region: UriContent


def test_uri_content():
    """Test the UriContent class to ensure it initializes correctly."""
    content = UriContent(uri="http://example.com", media_type="image/jpg", additional_properties={"version": 1})

    # Check the type and content
    assert content.type == "uri"
    assert content.uri == "http://example.com"
    assert content.media_type == "image/jpg"
    assert content.additional_properties["version"] == 1

    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)


# region: FunctionCallContent


def test_function_call_content():
    """Test the FunctionCallContent class to ensure it initializes correctly."""
    content = FunctionCallContent(call_id="1", name="example_function", arguments={"param1": "value1"})

    # Check the type and content
    assert content.type == "function_call"
    assert content.name == "example_function"
    assert content.arguments == {"param1": "value1"}

    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)


# region: FunctionResultContent


def test_function_result_content():
    """Test the FunctionResultContent class to ensure it initializes correctly."""
    content = FunctionResultContent(call_id="1", result={"param1": "value1"})

    # Check the type and content
    assert content.type == "function_result"
    assert content.result == {"param1": "value1"}

    # Ensure the instance is of type AIContent
    assert isinstance(content, AIContent)


# region: UsageDetails


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


# region: AIContent Serialization


@mark.parametrize(
    "content_type, args",
    [
        (TextContent, {"text": "Hello, world!"}),
        (DataContent, {"data": b"Hello, world!", "media_type": "text/plain"}),
        (UriContent, {"uri": "http://example.com", "media_type": "text/html"}),
        (FunctionCallContent, {"call_id": "1", "name": "example_function", "arguments": {}}),
        (FunctionResultContent, {"call_id": "1", "result": {}}),
    ],
)
def test_ai_content_serialization(content_type: type[AIContent], args: dict):
    content = content_type(**args)
    serialized = content.model_dump()
    deserialized = content_type.model_validate(serialized)
    assert deserialized == content

    class TestModel(BaseModel):
        content: AIContents

    test_item = TestModel.model_validate({"content": serialized})

    assert isinstance(test_item.content, content_type)


# region: ChatMessage


def test_chat_message_text():
    """Test the ChatMessage class to ensure it initializes correctly with text content."""
    # Create a ChatMessage with a role and text content
    message = ChatMessage(role="user", text="Hello, how are you?")

    # Check the type and content
    assert message.role == ChatRole.USER
    assert len(message.contents) == 1
    assert isinstance(message.contents[0], TextContent)
    assert message.contents[0].text == "Hello, how are you?"
    assert message.text == "Hello, how are you?"

    # Ensure the instance is of type AIContent
    assert isinstance(message.contents[0], AIContent)


def test_chat_message_contents():
    """Test the ChatMessage class to ensure it initializes correctly with contents."""
    # Create a ChatMessage with a role and multiple contents
    content1 = TextContent("Hello, how are you?")
    content2 = TextContent("I'm fine, thank you!")
    message = ChatMessage(role="user", contents=[content1, content2])

    # Check the type and content
    assert message.role == ChatRole.USER
    assert len(message.contents) == 2
    assert isinstance(message.contents[0], TextContent)
    assert isinstance(message.contents[1], TextContent)
    assert message.contents[0].text == "Hello, how are you?"
    assert message.contents[1].text == "I'm fine, thank you!"
    assert message.text == "Hello, how are you? I'm fine, thank you!"


# region: ChatResponse


def test_chat_response():
    """Test the ChatResponse class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = ChatMessage(role="assistant", text="I'm doing well, thank you!")

    # Create a ChatResponse with the message
    response = ChatResponse(messages=message)

    # Check the type and content
    assert response.messages[0].role == ChatRole.ASSISTANT
    assert response.messages[0].text == "I'm doing well, thank you!"
    assert isinstance(response.messages[0], ChatMessage)


# region: StructuredResponse


def test_structured_response():
    """Test the StructuredResponse class to ensure it initializes correctly with a value."""

    class ResponseModel(BaseModel):
        content: str
        action: str

    # Create a StructuredResponse with a value
    response = StructuredResponse[ResponseModel](
        value=ResponseModel(content="Hello, world!", action="test"),
        text="{'content': 'Hello, world!', 'action': 'test'}",
    )

    # Check the type and content
    assert response.value == ResponseModel(content="Hello, world!", action="test")
    assert isinstance(response, StructuredResponse)


# region: ChatResponseUpdate


def test_chat_response_update():
    """Test the ChatResponseUpdate class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = TextContent(text="I'm doing well, thank you!")

    # Create a ChatResponseUpdate with the message
    response_update = ChatResponseUpdate(contents=[message])

    # Check the type and content
    assert response_update.contents[0].text == "I'm doing well, thank you!"
    assert isinstance(response_update.contents[0], TextContent)


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
    message1 = TextContent("I'm doing well, ")
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

    assert len(chat_response.messages[0].contents) == 3
    assert isinstance(chat_response.messages[0].contents[0], TextContent)
    assert chat_response.messages[0].contents[0].text == "I'm doing well, thank you!"
    assert isinstance(chat_response.messages[0].contents[1], TextReasoningContent)
    assert chat_response.messages[0].contents[1].text == "Additional context"
    assert isinstance(chat_response.messages[0].contents[2], TextContent)
    assert chat_response.messages[0].contents[2].text == "More contextFinal part"

    assert chat_response.text == "I'm doing well, thank you! More contextFinal part"


# region: ChatToolMode


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


# region: ChatOptions


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
    )
    assert options.ai_model_id == "gpt-4"
    assert options.max_tokens == 1024
    assert options.temperature == 0.7
    assert options.top_p == 0.9
    assert options.presence_penalty == 0.0
    assert options.frequency_penalty == 0.0
    assert options.user == "user-123"
    for tool in options._ai_tools:
        assert isinstance(tool, AITool)
        assert tool.name is not None
        assert tool.description is not None
        assert tool.parameters() is not None


def test_chat_options_and(ai_function_tool, ai_tool) -> None:
    options1 = ChatOptions(ai_model_id="gpt-4o", tools=[ai_function_tool])
    options2 = ChatOptions(ai_model_id="gpt-4.1", tools=[ai_tool])
    assert options1 != options2
    options3 = options1 & options2

    assert options3.ai_model_id == "gpt-4.1"
    assert len(options3._ai_tools) == 2
    assert options3._ai_tools == [ai_function_tool, ai_tool]
    assert options3.tools == [ai_function_tool, ai_tool]


# region Agent Response Fixtures


@fixture
def chat_message() -> ChatMessage:
    return ChatMessage(role=ChatRole.USER, text="Hello")


@fixture
def text_content() -> TextContent:
    return TextContent(text="Test content")


@fixture
def agent_run_response(chat_message: ChatMessage) -> AgentRunResponse:
    return AgentRunResponse(messages=chat_message)


@fixture
def agent_run_response_update(text_content: TextContent) -> AgentRunResponseUpdate:
    return AgentRunResponseUpdate(role=ChatRole.ASSISTANT, contents=[text_content])


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
