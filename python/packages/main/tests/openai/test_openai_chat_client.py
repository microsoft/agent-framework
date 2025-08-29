# Copyright (c) Microsoft. All rights reserved.

import os
from unittest.mock import MagicMock, patch

import pytest
from openai import BadRequestError

from agent_framework import (
    AITool,
    ChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    HostedWebSearchTool,
    TextContent,
    ai_function,
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

    assert open_ai_chat_completion.ai_model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClient)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(api_key="34523", ai_model_id={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    open_ai_chat_completion = OpenAIChatClient(ai_model_id=ai_model_id)

    assert open_ai_chat_completion.ai_model_id == ai_model_id
    assert isinstance(open_ai_chat_completion, ChatClient)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient(
        default_headers=default_headers,
    )

    assert open_ai_chat_completion.ai_model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in open_ai_chat_completion.client.default_headers
        assert open_ai_chat_completion.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["OPENAI_CHAT_MODEL_ID"]], indirect=True)
def test_init_with_empty_model_id(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    ai_model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            ai_model_id=ai_model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


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

    # Create a mock AITool that's not an AIFunction
    unsupported_tool = MagicMock(spec=AITool)
    unsupported_tool.__class__.__name__ = "UnsupportedAITool"

    # This should ignore the unsupported AITool and return empty list
    result = client._chat_to_tool_spec([unsupported_tool])  # type: ignore
    assert result == []

    # Also test with a non-AITool that should be converted to dict
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


@skip_if_openai_integration_tests_disabled
async def test_openai_chat_completion_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClient)

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


@skip_if_openai_integration_tests_disabled
async def test_openai_chat_completion_response_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClient)

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


@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_streaming() -> None:
    """Test Azure OpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClient)

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


@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_streaming_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    openai_chat_client = OpenAIChatClient()

    assert isinstance(openai_chat_client, ChatClient)

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


@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_web_search() -> None:
    # Currently only a select few models support web search tool calls
    openai_chat_client = OpenAIChatClient(ai_model_id="gpt-4o-search-preview")

    assert isinstance(openai_chat_client, ChatClient)

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
    assert "Seattle" in response.text


@skip_if_openai_integration_tests_disabled
async def test_openai_chat_client_web_search_streaming() -> None:
    openai_chat_client = OpenAIChatClient(ai_model_id="gpt-4o-search-preview")

    assert isinstance(openai_chat_client, ChatClient)

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
    assert "Seattle" in full_message


async def test_exception_message_includes_original_error_details() -> None:
    """Test that exception messages include original error details in the new format."""
    client = OpenAIChatClient(ai_model_id="test-model", api_key="test-key")
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
