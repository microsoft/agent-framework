# Copyright (c) Microsoft. All rights reserved.

import pytest
from pydantic import ValidationError

from agent_framework import (
    AIContent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    ChatToolMode,
    DataContent,
    TextContent,
)


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
    with pytest.raises(ValidationError):
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
    with pytest.raises(ValidationError):
        content.type = "ai"


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
    assert message.text == "Hello, how are you?\nI'm fine, thank you!"


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


def test_chat_response_update():
    """Test the ChatResponseUpdate class to ensure it initializes correctly with a message."""
    # Create a ChatMessage
    message = TextContent(text="I'm doing well, thank you!")

    # Create a ChatResponseUpdate with the message
    response_update = ChatResponseUpdate(contents=[message])

    # Check the type and content
    assert response_update.contents[0].text == "I'm doing well, thank you!"
    assert isinstance(response_update.contents[0], TextContent)


def test_chat_response_updates_to_chat_response():
    """Test converting ChatResponseUpdate to ChatResponse."""
    # Create a ChatMessage
    message1 = TextContent("I'm doing well, ")
    message2 = TextContent("thank you!")

    # Create a ChatResponseUpdate with the message
    response_updates = [ChatResponseUpdate(text=message1), ChatResponseUpdate(text=message2)]

    # Convert to ChatResponse
    chat_response = ChatResponseUpdate.to_chat_response(response_updates)

    # Check the type and content
    assert len(chat_response.messages) == 2
    assert chat_response.text == "I'm doing well, \nthank you!"
    assert isinstance(chat_response.messages[0], ChatMessage)


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
    with pytest.raises(ValidationError):
        DataContent(uri="invalid_uri")
    # unknown media type
    with pytest.raises(ValidationError):
        DataContent(uri="data:application/random;base64,dGVzdA==")
    # not valid base64 data

    with pytest.raises(ValidationError):
        DataContent(uri="data:application/json;base64,dGVzdA&")


def test_data_content_empty():
    """Test the DataContent class to ensure it raises an error for empty data."""
    # Attempt to create an instance of DataContent with empty data
    with pytest.raises(ValidationError):
        DataContent(data=b"", media_type="application/octet-stream")

    # Attempt to create an instance of DataContent with empty URI
    with pytest.raises(ValidationError):
        DataContent(uri="")
