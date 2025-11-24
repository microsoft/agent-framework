import pytest
from agent_framework import (
    ChatMessage,
    TextContent,
    FunctionCallContent,
    Role,
)
from agent_framework.openai import OpenAIChatClient


class TestOpenAIChatMessageParser:
    """Test cases for _openai_chat_message_parser method."""

    def test_chat_message_with_text_and_tool_calls_combined(self):
        """
        Test that a ChatMessage containing both text content and tool calls
        is correctly parsed into a SINGLE message with both 'content' and 'tool_calls' fields.
        
        This verifies the fix for issue #2410 where messages were incorrectly split.
        """
        # Arrange
        client = OpenAIChatClient(
            model_id="gpt-4",
            api_key="test-key"
        )
        
        message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                TextContent(text="I'll help you with that calculation."),
                FunctionCallContent(
                    call_id="call-123",
                    name="calculate",
                    arguments={"x": 5, "y": 3}
                )
            ]
        )
        
        # Act
        result = client._openai_chat_message_parser(message)
        
        # Assert
        assert len(result) == 1, "Should return exactly one message, not split into multiple"
        
        parsed_message = result[0]
        
        # Verify the message has the correct role
        assert parsed_message["role"] == "assistant"
        
        # Verify both content and tool_calls are present in the SAME message
        assert "content" in parsed_message, "Message should contain 'content' field"
        assert "tool_calls" in parsed_message, "Message should contain 'tool_calls' field"
        
        # Verify content is correctly formatted
        assert isinstance(parsed_message["content"], list)
        assert len(parsed_message["content"]) == 1
        assert parsed_message["content"][0]["type"] == "text"
        assert parsed_message["content"][0]["text"] == "I'll help you with that calculation."
        
        # Verify tool_calls is correctly formatted
        assert isinstance(parsed_message["tool_calls"], list)
        assert len(parsed_message["tool_calls"]) == 1
        assert parsed_message["tool_calls"][0]["id"] == "call-123"
        assert parsed_message["tool_calls"][0]["type"] == "function"
        assert parsed_message["tool_calls"][0]["function"]["name"] == "calculate"


    def test_chat_message_with_multiple_tool_calls_and_text(self):
        """
        Test that a ChatMessage with text and multiple tool calls
        keeps everything in a single message.
        """
        # Arrange
        client = OpenAIChatClient(
            model_id="gpt-4",
            api_key="test-key"
        )
        
        message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                TextContent(text="Let me check both databases for you."),
                FunctionCallContent(
                    call_id="call-456",
                    name="query_database_a",
                    arguments={"query": "SELECT * FROM users"}
                ),
                FunctionCallContent(
                    call_id="call-789",
                    name="query_database_b",
                    arguments={"query": "SELECT * FROM products"}
                )
            ]
        )
        
        # Act
        result = client._openai_chat_message_parser(message)
        
        # Assert
        assert len(result) == 1, "Should return exactly one message with all tool calls"
        
        parsed_message = result[0]
        assert parsed_message["role"] == "assistant"
        assert "content" in parsed_message
        assert "tool_calls" in parsed_message
        
        # Verify multiple tool calls are in the same message
        assert len(parsed_message["tool_calls"]) == 2
        assert parsed_message["tool_calls"][0]["id"] == "call-456"
        assert parsed_message["tool_calls"][1]["id"] == "call-789"


    def test_chat_message_with_only_text(self):
        """
        Test that a ChatMessage with only text content works correctly.
        """
        # Arrange
        client = OpenAIChatClient(
            model_id="gpt-4",
            api_key="test-key"
        )
        
        message = ChatMessage(
            role=Role.USER,
            contents=[TextContent(text="Hello, how are you?")]
        )
        
        # Act
        result = client._openai_chat_message_parser(message)
        
        # Assert
        assert len(result) == 1
        parsed_message = result[0]
        assert parsed_message["role"] == "user"
        assert "content" in parsed_message
        assert "tool_calls" not in parsed_message


    def test_chat_message_with_only_tool_calls(self):
        """
        Test that a ChatMessage with only tool calls (no text) works correctly.
        """
        # Arrange
        client = OpenAIChatClient(
            model_id="gpt-4",
            api_key="test-key"
        )
        
        message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                FunctionCallContent(
                    call_id="call-999",
                    name="get_weather",
                    arguments={"location": "San Francisco"}
                )
            ]
        )
        
        # Act
        result = client._openai_chat_message_parser(message)
        
        # Assert
        assert len(result) == 1
        parsed_message = result[0]
        assert parsed_message["role"] == "assistant"
        assert "tool_calls" in parsed_message
        assert "content" not in parsed_message


    def test_openai_api_compatibility(self):
        """
        Test that the message format matches OpenAI API specification.
        According to OpenAI docs, a single assistant message can have both
        'content' and 'tool_calls' in the same message object.
        """
        # Arrange
        client = OpenAIChatClient(
            model_id="gpt-4",
            api_key="test-key"
        )
        
        message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                TextContent(text="I found the weather information."),
                FunctionCallContent(
                    call_id="call_abc123",
                    name="get_weather",
                    arguments='{"location": "New York", "unit": "celsius"}'
                )
            ]
        )
        
        # Act
        result = client._openai_chat_message_parser(message)
        
        # Assert - Verify OpenAI API compatible structure
        assert len(result) == 1
        api_message = result[0]
        
        # Structure should match OpenAI API expectations
        assert "role" in api_message
        assert "content" in api_message
        assert "tool_calls" in api_message
        
        # Verify tool_call structure matches OpenAI spec
        tool_call = api_message["tool_calls"][0]
        assert "id" in tool_call
        assert "type" in tool_call
        assert tool_call["type"] == "function"
        assert "function" in tool_call
        assert "name" in tool_call["function"]
        assert "arguments" in tool_call["function"]
