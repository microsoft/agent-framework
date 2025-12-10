# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
from openai import BadRequestError

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    DataContent,
    FunctionResultContent,
    HostedWebSearchTool,
    TextContent,
    ToolProtocol,
    ai_function,
    prepare_function_call_results,
)
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.openai import OpenAIChatClient
from agent_framework.openai._exceptions import OpenAIContentFilterException

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient()

    assert open_ai_chat_completion.model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClientProtocol)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(api_key="34523", model_id={"test": "dict"})  # type: ignore


def test_init_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model_id = "test_model_id"
    open_ai_chat_completion = OpenAIChatClient(model_id=model_id)

    assert open_ai_chat_completion.model_id == model_id
    assert isinstance(open_ai_chat_completion, ChatClientProtocol)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient(
        default_headers=default_headers,
    )

    assert open_ai_chat_completion.model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClientProtocol)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in open_ai_chat_completion.client.default_headers
        assert open_ai_chat_completion.client.default_headers[key] == value


def test_init_base_url(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient(base_url="http://localhost:1234/v1")
    assert str(open_ai_chat_completion.client.base_url) == "http://localhost:1234/v1/"


def test_init_base_url_from_settings_env() -> None:
    """Test that base_url from OpenAISettings environment variable is properly used."""
    # Set environment variable for base_url
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "dummy",
            "OPENAI_CHAT_MODEL_ID": "gpt-5",
            "OPENAI_BASE_URL": "https://custom-openai-endpoint.com/v1",
        },
    ):
        client = OpenAIChatClient()
        assert client.model_id == "gpt-5"
        assert str(client.client.base_url) == "https://custom-openai-endpoint.com/v1/"


@pytest.mark.parametrize("exclude_list", [["OPENAI_CHAT_MODEL_ID"]], indirect=True)
def test_init_with_empty_model_id(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            model_id=model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings.get("default_headers", {})


async def test_content_filter_exception_handling(openai_unit_test_env: dict[str, str]) -> None:
    """Test that content filter errors are properly handled."""
    client = OpenAIChatClient()
    messages = [ChatMessage(role="user", text="test message")]

    # Create a mock BadRequestError with content_filter code
    mock_response = MagicMock()
    mock_error = BadRequestError(
        message="Content filter error", response=mock_response, body={"error": {"code": "content_filter"}}
    )
    mock_error.code = "content_filter"

    # Mock the client to raise the content filter error
    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(OpenAIContentFilterException),
    ):
        await client._inner_get_response(messages=messages, chat_options=ChatOptions())  # type: ignore


def test_unsupported_tool_handling(openai_unit_test_env: dict[str, str]) -> None:
    """Test that unsupported tool types are handled correctly."""
    client = OpenAIChatClient()

    # Create a mock ToolProtocol that's not an AIFunction
    unsupported_tool = MagicMock(spec=ToolProtocol)
    unsupported_tool.__class__.__name__ = "UnsupportedAITool"

    # This should ignore the unsupported ToolProtocol and return empty list
    result = client._chat_to_tool_spec([unsupported_tool])  # type: ignore
    assert result == []

    # Also test with a non-ToolProtocol that should be converted to dict
    dict_tool = {"type": "function", "name": "test"}
    result = client._chat_to_tool_spec([dict_tool])  # type: ignore
    assert result == [dict_tool]


@ai_function
def get_story_text() -> str:
    """Returns a story about Emily and David."""
    return (
        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
        "of climate change."
    )


@ai_function
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny and 72°F."


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_completion_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClientProtocol)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await openai_chat_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_completion_response_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClientProtocol)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await openai_chat_client.get_response(
        messages=messages,
        tools=[get_story_text],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_streaming() -> None:
    """Test Azure OpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClientProtocol)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = openai_chat_client.get_streaming_response(messages=messages)

    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        assert chunk.message_id is not None
        assert chunk.response_id is not None
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_streaming_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClientProtocol)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = openai_chat_client.get_streaming_response(
        messages=messages,
        tools=[get_story_text],
        tool_choice="auto",
    )
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_web_search() -> None:
    # Currently only a select few models support web search tool calls
    openai_chat_client = OpenAIChatClient(model_id="gpt-4o-search-preview")

    assert isinstance(openai_chat_client, ChatClientProtocol)

    # Test that the client will use the web search tool
    response = await openai_chat_client.get_response(
        messages=[
            ChatMessage(
                role="user",
                text="Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
            )
        ],
        tools=[HostedWebSearchTool()],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "Rumi" in response.text
    assert "Mira" in response.text
    assert "Zoey" in response.text

    # Test that the client will use the web search tool with location
    additional_properties = {
        "user_location": {
            "country": "US",
            "city": "Seattle",
        }
    }
    response = await openai_chat_client.get_response(
        messages=[ChatMessage(role="user", text="What is the current weather? Do not ask for my current location.")],
        tools=[HostedWebSearchTool(additional_properties=additional_properties)],
        tool_choice="auto",
    )
    assert response.text is not None


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_web_search_streaming() -> None:
    openai_chat_client = OpenAIChatClient(model_id="gpt-4o-search-preview")

    assert isinstance(openai_chat_client, ChatClientProtocol)

    # Test that the client will use the web search tool
    response = openai_chat_client.get_streaming_response(
        messages=[
            ChatMessage(
                role="user",
                text="Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
            )
        ],
        tools=[HostedWebSearchTool()],
        tool_choice="auto",
    )

    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text
    assert "Rumi" in full_message
    assert "Mira" in full_message
    assert "Zoey" in full_message

    # Test that the client will use the web search tool with location
    additional_properties = {
        "user_location": {
            "country": "US",
            "city": "Seattle",
        }
    }
    response = openai_chat_client.get_streaming_response(
        messages=[ChatMessage(role="user", text="What is the current weather? Do not ask for my current location.")],
        tools=[HostedWebSearchTool(additional_properties=additional_properties)],
        tool_choice="auto",
    )
    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text
    assert full_message is not None


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_agent_basic_run():
    """Test OpenAI chat client agent basic run functionality with OpenAIChatClient."""
    async with ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
    ) as agent:
        # Test basic run
        response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0
        assert "hello world" in response.text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_agent_basic_run_streaming():
    """Test OpenAI chat client agent basic streaming functionality with OpenAIChatClient."""
    async with ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
    ) as agent:
        # Test streaming run
        full_text = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert isinstance(chunk, AgentRunResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert len(full_text) > 0
        assert "streaming response test" in full_text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_agent_thread_persistence():
    """Test OpenAI chat client agent thread persistence across runs with OpenAIChatClient."""
    async with ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First interaction
        response1 = await agent.run("My name is Alice. Remember this.", thread=thread)

        assert isinstance(response1, AgentRunResponse)
        assert response1.text is not None

        # Second interaction - test memory
        response2 = await agent.run("What is my name?", thread=thread)

        assert isinstance(response2, AgentRunResponse)
        assert response2.text is not None
        assert "alice" in response2.text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_agent_existing_thread():
    """Test OpenAI chat client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and capture the thread
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My name is Alice. Remember this.", thread=thread)

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None

        # Preserve the thread for reuse
        preserved_thread = thread

    # Second conversation - reuse the thread in a new agent instance
    if preserved_thread:
        async with ChatAgent(
            chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my name?", thread=preserved_thread)

            assert isinstance(second_response, AgentRunResponse)
            assert second_response.text is not None
            assert "alice" in second_response.text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with OpenAI Chat Client."""

    async with ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4.1"),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],  # Agent-level tool
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "72"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_run_level_tool_isolation():
    """Test that run-level tools are isolated to specific runs and don't persist with OpenAI Chat Client."""
    # Counter to track how many times the weather tool is called
    call_count = 0

    @ai_function
    async def get_weather_with_counter(location: Annotated[str, "The location as a city name"]) -> str:
        """Get the current weather in a given location."""
        nonlocal call_count
        call_count += 1
        return f"The weather in {location} is sunny and 72°F."

    async with ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4.1"),
        instructions="You are a helpful assistant.",
    ) as agent:
        # First run - use run-level tool
        first_response = await agent.run(
            "What's the weather like in Chicago?",
            tools=[get_weather_with_counter],  # Run-level tool
        )

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the run-level weather tool (call count should be 1)
        assert call_count == 1
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - run-level tool should NOT persist (key isolation test)
        second_response = await agent.run("What's the weather like in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should NOT use the weather tool since it was only run-level in previous call
        # Call count should still be 1 (no additional calls)
        assert call_count == 1


async def test_exception_message_includes_original_error_details() -> None:
    """Test that exception messages include original error details in the new format."""
    client = OpenAIChatClient(model_id="test-model", api_key="test-key")
    messages = [ChatMessage(role="user", text="test message")]

    mock_response = MagicMock()
    original_error_message = "Invalid API request format"
    mock_error = BadRequestError(
        message=original_error_message,
        response=mock_response,
        body={"error": {"code": "invalid_request", "message": original_error_message}},
    )
    mock_error.code = "invalid_request"

    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(ServiceResponseException) as exc_info,
    ):
        await client._inner_get_response(messages=messages, chat_options=ChatOptions())  # type: ignore

    exception_message = str(exc_info.value)
    assert "service failed to complete the prompt:" in exception_message
    assert original_error_message in exception_message


def test_chat_response_content_order_text_before_tool_calls(openai_unit_test_env: dict[str, str]):
    """Test that text content appears before tool calls in ChatResponse contents."""
    # Import locally to avoid break other tests when the import changes
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage
    from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function

    # Create a mock OpenAI response with both text and tool calls
    mock_response = ChatCompletion(
        id="test-response",
        object="chat.completion",
        created=1234567890,
        model="gpt-4o-mini",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content="I'll help you with that calculation.",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call-123",
                            type="function",
                            function=Function(name="calculate", arguments='{"x": 5, "y": 3}'),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
    )

    client = OpenAIChatClient()
    response = client._create_chat_response(mock_response, ChatOptions())

    # Verify we have both text and tool call content
    assert len(response.messages) == 1
    message = response.messages[0]
    assert len(message.contents) == 2

    # Verify text content comes first, tool call comes second
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "I'll help you with that calculation."
    assert message.contents[1].type == "function_call"
    assert message.contents[1].name == "calculate"


def test_function_result_falsy_values_handling(openai_unit_test_env: dict[str, str]):
    """Test that falsy values (like empty list) in function result are properly handled."""
    client = OpenAIChatClient()

    # Test with empty list (falsy but not None)
    message_with_empty_list = ChatMessage(role="tool", contents=[FunctionResultContent(call_id="call-123", result=[])])

    openai_messages = client._openai_chat_message_parser(message_with_empty_list)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "[]"  # Empty list should be JSON serialized

    # Test with empty string (falsy but not None)
    message_with_empty_string = ChatMessage(
        role="tool", contents=[FunctionResultContent(call_id="call-456", result="")]
    )

    openai_messages = client._openai_chat_message_parser(message_with_empty_string)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == ""  # Empty string should be preserved

    # Test with False (falsy but not None)
    message_with_false = ChatMessage(role="tool", contents=[FunctionResultContent(call_id="call-789", result=False)])

    openai_messages = client._openai_chat_message_parser(message_with_false)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "false"  # False should be JSON serialized


def test_function_result_exception_handling(openai_unit_test_env: dict[str, str]):
    """Test that exceptions in function result are properly handled.

    Feel free to remove this test in case there's another new behavior.
    """
    client = OpenAIChatClient()

    # Test with exception (no result)
    test_exception = ValueError("Test error message")
    message_with_exception = ChatMessage(
        role="tool",
        contents=[
            FunctionResultContent(call_id="call-123", result="Error: Function failed.", exception=test_exception)
        ],
    )

    openai_messages = client._openai_chat_message_parser(message_with_exception)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "Error: Function failed."
    assert openai_messages[0]["tool_call_id"] == "call-123"


def test_prepare_function_call_results_string_passthrough():
    """Test that string values are passed through directly without JSON encoding."""
    result = prepare_function_call_results("simple string")
    assert result == "simple string"
    assert isinstance(result, str)


def test_openai_content_parser_data_content_image(openai_unit_test_env: dict[str, str]) -> None:
    """Test _openai_content_parser converts DataContent with image media type to OpenAI format."""
    client = OpenAIChatClient()

    # Test DataContent with image media type
    image_data_content = DataContent(
        uri="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
        media_type="image/png",
    )

    result = client._openai_content_parser(image_data_content)  # type: ignore

    # Should convert to OpenAI image_url format
    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == image_data_content.uri

    # Test DataContent with non-image media type should use default model_dump
    text_data_content = DataContent(uri="data:text/plain;base64,SGVsbG8gV29ybGQ=", media_type="text/plain")

    result = client._openai_content_parser(text_data_content)  # type: ignore

    # Should use default model_dump format
    assert result["type"] == "data"
    assert result["uri"] == text_data_content.uri
    assert result["media_type"] == "text/plain"

    # Test DataContent with audio media type
    audio_data_content = DataContent(
        uri="data:audio/wav;base64,UklGRjBEAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQwEAAAAAAAAAAAA",
        media_type="audio/wav",
    )

    result = client._openai_content_parser(audio_data_content)  # type: ignore

    # Should convert to OpenAI input_audio format
    assert result["type"] == "input_audio"
    # Data should contain just the base64 part, not the full data URI
    assert result["input_audio"]["data"] == "UklGRjBEAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQwEAAAAAAAAAAAA"
    assert result["input_audio"]["format"] == "wav"

    # Test DataContent with MP3 audio
    mp3_data_content = DataContent(uri="data:audio/mp3;base64,//uQAAAAWGluZwAAAA8AAAACAAACcQ==", media_type="audio/mp3")

    result = client._openai_content_parser(mp3_data_content)  # type: ignore

    # Should convert to OpenAI input_audio format with mp3
    assert result["type"] == "input_audio"
    # Data should contain just the base64 part, not the full data URI
    assert result["input_audio"]["data"] == "//uQAAAAWGluZwAAAA8AAAACAAACcQ=="
    assert result["input_audio"]["format"] == "mp3"


def test_openai_content_parser_document_file_mapping(openai_unit_test_env: dict[str, str]) -> None:
    """Test _openai_content_parser converts document files (PDF, DOCX, etc.) to OpenAI file format."""
    client = OpenAIChatClient()

    # Test PDF without filename - should omit filename in OpenAI payload
    pdf_data_content = DataContent(
        uri="data:application/pdf;base64,JVBERi0xLjQKJcfsj6IKNSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXS9QYXJlbnQgMiAwIFIvUmVzb3VyY2VzPDwvRm9udDw8L0YxIDQgMCBSPj4+Pi9Db250ZW50cyA1IDAgUj4+CmVuZG9iago0IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYT4+CmVuZG9iago1IDAgb2JqCjw8L0xlbmd0aCA0ND4+CnN0cmVhbQpCVApxCjcwIDUwIFRECi9GMSA4IFRmCihIZWxsbyBXb3JsZCEpIFRqCkVUCmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwNTggMDAwMDAgbiAKMDAwMDAwMDExNSAwMDAwMCBuIAowMDAwMDAwMjQ1IDAwMDAwIG4gCjAwMDAwMDAzMDcgMDAwMDAgbiAKdHJhaWxlcgo8PC9TaXplIDYvUm9vdCAxIDAgUj4+CnN0YXJ0eHJlZgo0MDUKJSVFT0Y=",
        media_type="application/pdf",
    )

    result = client._openai_content_parser(pdf_data_content)  # type: ignore

    # Should convert to OpenAI file format without filename
    assert result["type"] == "file"
    assert "filename" not in result["file"]  # No filename provided, so none should be set
    assert "file_data" in result["file"]
    # Base64 data should be the full data URI (OpenAI requirement)
    assert result["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert result["file"]["file_data"] == pdf_data_content.uri

    # Test PDF with custom filename via additional_properties
    pdf_with_filename = DataContent(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={"filename": "report.pdf"},
    )

    result = client._openai_content_parser(pdf_with_filename)  # type: ignore

    # Should use custom filename
    assert result["type"] == "file"
    assert result["file"]["filename"] == "report.pdf"
    assert result["file"]["file_data"] == "data:application/pdf;base64,JVBERi0xLjQ="

    # Test different application/* media types - all should now be mapped to file format
    test_cases = [
        {
            "media_type": "application/json",
            "filename": "data.json",
            "base64": "eyJrZXkiOiJ2YWx1ZSJ9",
        },
        {
            "media_type": "application/xml",
            "filename": "config.xml",
            "base64": "PD94bWwgdmVyc2lvbj0iMS4wIj8+",
        },
        {
            "media_type": "application/octet-stream",
            "filename": "binary.bin",
            "base64": "AQIDBAUGBwgJCg==",
        },
    ]

    for case in test_cases:
        # Test without filename
        doc_content = DataContent(
            uri=f"data:{case['media_type']};base64,{case['base64']}",
            media_type=case["media_type"],
        )

        result = client._openai_content_parser(doc_content)  # type: ignore

        # All application/* types should now be mapped to file format
        assert result["type"] == "file"
        assert "filename" not in result["file"]  # Should omit filename when not provided
        assert result["file"]["file_data"] == doc_content.uri

        # Test with filename - should now use file format with filename
        doc_with_filename = DataContent(
            uri=f"data:{case['media_type']};base64,{case['base64']}",
            media_type=case["media_type"],
            additional_properties={"filename": case["filename"]},
        )

        result = client._openai_content_parser(doc_with_filename)  # type: ignore

        # Should now use file format with filename
        assert result["type"] == "file"
        assert result["file"]["filename"] == case["filename"]
        assert result["file"]["file_data"] == doc_with_filename.uri

    # Test edge case: empty additional_properties dict
    pdf_empty_props = DataContent(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={},
    )

    result = client._openai_content_parser(pdf_empty_props)  # type: ignore

    assert result["type"] == "file"
    assert "filename" not in result["file"]

    # Test edge case: None filename in additional_properties
    pdf_none_filename = DataContent(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={"filename": None},
    )

    result = client._openai_content_parser(pdf_none_filename)  # type: ignore

    assert result["type"] == "file"
    assert "filename" not in result["file"]  # None filename should be omitted
