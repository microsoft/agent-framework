# Copyright (c) Microsoft. All rights reserved.

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    BaseChatClient,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    TextContent,
    ai_function,
)
from agent_framework._telemetry import USER_AGENT_KEY
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.openai import (
    ContentFilterResultSeverity,
    OpenAIContentFilterException,
)
from azure.identity import AzureCliCredential
from httpx import Request, Response
from openai import AsyncAzureOpenAI, AsyncStream
from openai.resources.chat.completions import AsyncCompletions as AsyncChatCompletions
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta as ChunkChoiceDelta
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from agent_framework_azure import AzureChatClient

# region Service Setup

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com"),
    reason="No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def test_init(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    azure_chat_client = AzureChatClient()

    assert azure_chat_client.client is not None
    assert isinstance(azure_chat_client.client, AsyncAzureOpenAI)
    assert azure_chat_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    assert isinstance(azure_chat_client, BaseChatClient)


def test_init_client(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization with client
    client = MagicMock(spec=AsyncAzureOpenAI)
    azure_chat_client = AzureChatClient(async_client=client)

    assert azure_chat_client.client is not None
    assert isinstance(azure_chat_client.client, AsyncAzureOpenAI)


def test_init_base_url(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Custom header for testing
    default_headers = {"X-Unit-Test": "test-guid"}

    azure_chat_client = AzureChatClient(
        default_headers=default_headers,
    )

    assert azure_chat_client.client is not None
    assert isinstance(azure_chat_client.client, AsyncAzureOpenAI)
    assert azure_chat_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    assert isinstance(azure_chat_client, BaseChatClient)
    for key, value in default_headers.items():
        assert key in azure_chat_client.client.default_headers
        assert azure_chat_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_BASE_URL"]], indirect=True)
def test_init_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    azure_chat_client = AzureChatClient()

    assert azure_chat_client.client is not None
    assert isinstance(azure_chat_client.client, AsyncAzureOpenAI)
    assert azure_chat_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    assert isinstance(azure_chat_client, BaseChatClient)


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]], indirect=True)
def test_init_with_empty_deployment_name(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureChatClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_BASE_URL"]], indirect=True)
def test_init_with_empty_endpoint_and_base_url(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureChatClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("override_env_param_dict", [{"AZURE_OPENAI_ENDPOINT": "http://test.com"}], indirect=True)
def test_init_with_invalid_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureChatClient()


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_BASE_URL"]], indirect=True)
def test_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Test": "test"}

    settings = {
        "deployment_name": azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        "endpoint": azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"],
        "api_key": azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        "api_version": azure_openai_unit_test_env["AZURE_OPENAI_API_VERSION"],
        "default_headers": default_headers,
        "env_file_path": "test.env",
    }

    azure_chat_client = AzureChatClient.from_dict(settings)
    dumped_settings = azure_chat_client.to_dict()
    assert dumped_settings["ai_model_id"] == settings["deployment_name"]
    assert str(settings["endpoint"]) in str(dumped_settings["base_url"])
    assert str(settings["deployment_name"]) in str(dumped_settings["base_url"])
    assert settings["api_key"] == dumped_settings["api_key"]
    assert settings["api_version"] == dumped_settings["api_version"]

    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value

    # Assert that the 'User-agent' header is not present in the dumped_settings default headers
    assert USER_AGENT_KEY not in dumped_settings["default_headers"]


# endregion
# region CMC


@pytest.fixture
def mock_chat_completion_response() -> ChatCompletion:
    return ChatCompletion(
        id="test_id",
        choices=[
            Choice(index=0, message=ChatCompletionMessage(content="test", role="assistant"), finish_reason="stop")
        ],
        created=0,
        model="test",
        object="chat.completion",
    )


@pytest.fixture
def mock_streaming_chat_completion_response() -> AsyncStream[ChatCompletionChunk]:
    content = ChatCompletionChunk(
        id="test_id",
        choices=[ChunkChoice(index=0, delta=ChunkChoiceDelta(content="test", role="assistant"), finish_reason="stop")],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [content]
    return stream


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
) -> None:
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(text="hello world", role="user"))

    azure_chat_client = AzureChatClient()
    await azure_chat_client.get_response(
        messages=chat_history,
    )
    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        stream=False,
        messages=azure_chat_client._prepare_chat_history_for_request(chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc_with_logit_bias(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
) -> None:
    mock_create.return_value = mock_chat_completion_response
    prompt = "hello world"
    chat_history.append(ChatMessage(text=prompt, role="user"))

    token_bias: dict[str | int, float] = {"1": -100}

    azure_chat_client = AzureChatClient()

    await azure_chat_client.get_response(messages=chat_history, logit_bias=token_bias)

    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        messages=azure_chat_client._prepare_chat_history_for_request(chat_history),  # type: ignore
        stream=False,
        logit_bias=token_bias,
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc_with_stop(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
) -> None:
    mock_create.return_value = mock_chat_completion_response
    prompt = "hello world"
    chat_history.append(ChatMessage(text=prompt, role="user"))

    stop = ["!"]

    azure_chat_client = AzureChatClient()

    await azure_chat_client.get_response(messages=chat_history, stop=stop)

    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        messages=azure_chat_client._prepare_chat_history_for_request(chat_history),  # type: ignore
        stream=False,
        stop=stop,
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_azure_on_your_data(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
) -> None:
    mock_chat_completion_response.choices = [
        Choice(
            index=0,
            message=ChatCompletionMessage(
                content="test",
                role="assistant",
                context={  # type: ignore
                    "citations": [
                        {
                            "content": "test content",
                            "title": "test title",
                            "url": "test url",
                            "filepath": "test filepath",
                            "chunk_id": "test chunk_id",
                        }
                    ],
                    "intent": "query used",
                },
            ),
            finish_reason="stop",
        )
    ]
    mock_create.return_value = mock_chat_completion_response
    prompt = "hello world"
    messages_in = chat_history
    chat_history.append(ChatMessage(text=prompt, role="user"))
    messages_out: list[ChatMessage] = []
    messages_out.append(ChatMessage(text=prompt, role="user"))

    expected_data_settings = {
        "data_sources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "indexName": "test_index",
                    "endpoint": "https://test-endpoint-search.com",
                    "key": "test_key",
                },
            }
        ]
    }

    azure_chat_client = AzureChatClient()

    content = await azure_chat_client.get_response(
        messages=messages_in,
        additional_properties={"extra_body": expected_data_settings},
    )
    assert len(content.messages) == 1
    assert len(content.messages[0].contents) == 1
    assert isinstance(content.messages[0].contents[0], TextContent)
    assert len(content.messages[0].contents[0].annotations) == 1
    assert content.messages[0].contents[0].annotations[0].title == "test title"
    assert content.messages[0].contents[0].text == "test"

    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        messages=azure_chat_client._prepare_chat_history_for_request(messages_out),  # type: ignore
        stream=False,
        extra_body=expected_data_settings,
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_azure_on_your_data_string(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
) -> None:
    mock_chat_completion_response.choices = [
        Choice(
            index=0,
            message=ChatCompletionMessage(
                content="test",
                role="assistant",
                context=json.dumps({  # type: ignore
                    "citations": [
                        {
                            "content": "test content",
                            "title": "test title",
                            "url": "test url",
                            "filepath": "test filepath",
                            "chunk_id": "test chunk_id",
                        }
                    ],
                    "intent": "query used",
                }),
            ),
            finish_reason="stop",
        )
    ]
    mock_create.return_value = mock_chat_completion_response
    prompt = "hello world"
    messages_in = chat_history
    messages_in.append(ChatMessage(text=prompt, role="user"))
    messages_out: list[ChatMessage] = []
    messages_out.append(ChatMessage(text=prompt, role="user"))

    expected_data_settings = {
        "data_sources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "indexName": "test_index",
                    "endpoint": "https://test-endpoint-search.com",
                    "key": "test_key",
                },
            }
        ]
    }

    azure_chat_client = AzureChatClient()

    content = await azure_chat_client.get_response(
        messages=messages_in,
        additional_properties={"extra_body": expected_data_settings},
    )
    assert len(content.messages) == 1
    assert len(content.messages[0].contents) == 1
    assert isinstance(content.messages[0].contents[0], TextContent)
    assert len(content.messages[0].contents[0].annotations) == 1
    assert content.messages[0].contents[0].annotations[0].title == "test title"
    assert content.messages[0].contents[0].text == "test"

    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        messages=azure_chat_client._prepare_chat_history_for_request(messages_out),  # type: ignore
        stream=False,
        extra_body=expected_data_settings,
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_azure_on_your_data_fail(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
) -> None:
    mock_chat_completion_response.choices = [
        Choice(
            index=0,
            message=ChatCompletionMessage(
                content="test",
                role="assistant",
                context="not a dictionary",  # type: ignore
            ),
            finish_reason="stop",
        )
    ]
    mock_create.return_value = mock_chat_completion_response
    prompt = "hello world"
    messages_in = chat_history
    messages_in.append(ChatMessage(text=prompt, role="user"))
    messages_out: list[ChatMessage] = []
    messages_out.append(ChatMessage(text=prompt, role="user"))

    expected_data_settings = {
        "data_sources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "indexName": "test_index",
                    "endpoint": "https://test-endpoint-search.com",
                    "key": "test_key",
                },
            }
        ]
    }

    azure_chat_client = AzureChatClient()

    content = await azure_chat_client.get_response(
        messages=messages_in,
        additional_properties={"extra_body": expected_data_settings},
    )
    assert len(content.messages) == 1
    assert len(content.messages[0].contents) == 1
    assert isinstance(content.messages[0].contents[0], TextContent)
    assert content.messages[0].contents[0].text == "test"

    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        messages=azure_chat_client._prepare_chat_history_for_request(messages_out),  # type: ignore
        stream=False,
        extra_body=expected_data_settings,
    )


CONTENT_FILTERED_ERROR_MESSAGE = (
    "The response was filtered due to the prompt triggering Azure OpenAI's content management policy. Please "
    "modify your prompt and retry. To learn more about our content filtering policies please read our "
    "documentation: https://go.microsoft.com/fwlink/?linkid=2198766"
)
CONTENT_FILTERED_ERROR_FULL_MESSAGE = (
    "Error code: 400 - {'error': {'message': \"%s\", 'type': null, 'param': 'prompt', 'code': 'content_filter', "
    "'status': 400, 'innererror': {'code': 'ResponsibleAIPolicyViolation', 'content_filter_result': {'hate': "
    "{'filtered': True, 'severity': 'high'}, 'self_harm': {'filtered': False, 'severity': 'safe'}, 'sexual': "
    "{'filtered': False, 'severity': 'safe'}, 'violence': {'filtered': False, 'severity': 'safe'}}}}}"
) % CONTENT_FILTERED_ERROR_MESSAGE


@patch.object(AsyncChatCompletions, "create")
async def test_content_filtering_raises_correct_exception(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
) -> None:
    prompt = "some prompt that would trigger the content filtering"
    chat_history.append(ChatMessage(text=prompt, role="user"))

    test_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    assert test_endpoint is not None
    mock_create.side_effect = openai.BadRequestError(
        CONTENT_FILTERED_ERROR_FULL_MESSAGE,
        response=Response(400, request=Request("POST", test_endpoint)),
        body={
            "message": CONTENT_FILTERED_ERROR_MESSAGE,
            "type": None,
            "param": "prompt",
            "code": "content_filter",
            "status": 400,
            "innererror": {
                "code": "ResponsibleAIPolicyViolation",
                "content_filter_result": {
                    "hate": {"filtered": True, "severity": "high"},
                    "self_harm": {"filtered": False, "severity": "safe"},
                    "sexual": {"filtered": False, "severity": "safe"},
                    "violence": {"filtered": False, "severity": "safe"},
                },
            },
        },
    )

    azure_chat_client = AzureChatClient()

    with pytest.raises(OpenAIContentFilterException, match="service encountered a content error") as exc_info:
        await azure_chat_client.get_response(
            messages=chat_history,
        )

    content_filter_exc = exc_info.value
    assert content_filter_exc.param == "prompt"
    assert content_filter_exc.content_filter_result["hate"].filtered
    assert content_filter_exc.content_filter_result["hate"].severity == ContentFilterResultSeverity.HIGH


@patch.object(AsyncChatCompletions, "create")
async def test_content_filtering_without_response_code_raises_with_default_code(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
) -> None:
    prompt = "some prompt that would trigger the content filtering"
    chat_history.append(ChatMessage(text=prompt, role="user"))

    test_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    assert test_endpoint is not None
    mock_create.side_effect = openai.BadRequestError(
        CONTENT_FILTERED_ERROR_FULL_MESSAGE,
        response=Response(400, request=Request("POST", test_endpoint)),
        body={
            "message": CONTENT_FILTERED_ERROR_MESSAGE,
            "type": None,
            "param": "prompt",
            "code": "content_filter",
            "status": 400,
            "innererror": {
                "content_filter_result": {
                    "hate": {"filtered": True, "severity": "high"},
                    "self_harm": {"filtered": False, "severity": "safe"},
                    "sexual": {"filtered": False, "severity": "safe"},
                    "violence": {"filtered": False, "severity": "safe"},
                },
            },
        },
    )

    azure_chat_client = AzureChatClient()

    with pytest.raises(OpenAIContentFilterException, match="service encountered a content error"):
        await azure_chat_client.get_response(
            messages=chat_history,
        )


@patch.object(AsyncChatCompletions, "create")
async def test_bad_request_non_content_filter(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
) -> None:
    prompt = "some prompt that would trigger the content filtering"
    chat_history.append(ChatMessage(text=prompt, role="user"))

    test_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    assert test_endpoint is not None
    mock_create.side_effect = openai.BadRequestError(
        "The request was bad.", response=Response(400, request=Request("POST", test_endpoint)), body={}
    )

    azure_chat_client = AzureChatClient()

    with pytest.raises(ServiceResponseException, match="service failed to complete the prompt"):
        await azure_chat_client.get_response(
            messages=chat_history,
        )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_get_streaming(
    mock_create: AsyncMock,
    azure_openai_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_streaming_chat_completion_response: AsyncStream[ChatCompletionChunk],
) -> None:
    mock_create.return_value = mock_streaming_chat_completion_response
    chat_history.append(ChatMessage(text="hello world", role="user"))

    azure_chat_client = AzureChatClient()
    async for msg in azure_chat_client.get_streaming_response(
        messages=chat_history,
    ):
        assert msg is not None
        assert msg.message_id is not None
        assert msg.response_id is not None
    mock_create.assert_awaited_once_with(
        model=azure_openai_unit_test_env["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
        stream=True,
        messages=azure_chat_client._prepare_chat_history_for_request(chat_history),  # type: ignore
        # NOTE: The `stream_options={"include_usage": True}` is explicitly enforced in
        # `OpenAIChatCompletionBase._inner_get_streaming_response`.
        # To ensure consistency, we align the arguments here accordingly.
        stream_options={"include_usage": True},
    )


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


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_response() -> None:
    """Test Azure OpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(credential=AzureCliCredential())
    assert isinstance(azure_chat_client, ChatClientProtocol)

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
    response = await azure_chat_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    # Check for any relevant keywords that indicate the AI understood the context
    assert any(
        word in response.text.lower() for word in ["scientists", "research", "antarctica", "glaciology", "climate"]
    )


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_response_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(credential=AzureCliCredential())
    assert isinstance(azure_chat_client, ChatClientProtocol)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await azure_chat_client.get_response(
        messages=messages,
        tools=[get_story_text],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_streaming() -> None:
    """Test Azure OpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(credential=AzureCliCredential())
    assert isinstance(azure_chat_client, ChatClientProtocol)

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
    response = azure_chat_client.get_streaming_response(messages=messages)

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


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_streaming_tools() -> None:
    """Test AzureOpenAI chat completion responses."""
    azure_chat_client = AzureChatClient(credential=AzureCliCredential())
    assert isinstance(azure_chat_client, ChatClientProtocol)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = azure_chat_client.get_streaming_response(
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


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_agent_basic_run():
    """Test Azure OpenAI chat client agent basic run functionality with AzureChatClient."""
    async with ChatAgent(
        chat_client=AzureChatClient(credential=AzureCliCredential()),
    ) as agent:
        # Test basic run
        response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0
        assert "hello world" in response.text.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_agent_basic_run_streaming():
    """Test Azure OpenAI chat client agent basic streaming functionality with AzureChatClient."""
    async with ChatAgent(
        chat_client=AzureChatClient(credential=AzureCliCredential()),
    ) as agent:
        # Test streaming run
        full_text = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert isinstance(chunk, AgentRunResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert len(full_text) > 0
        assert "streaming response test" in full_text.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_agent_thread_persistence():
    """Test Azure OpenAI chat client agent thread persistence across runs with AzureChatClient."""
    async with ChatAgent(
        chat_client=AzureChatClient(credential=AzureCliCredential()),
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


@skip_if_azure_integration_tests_disabled
async def test_azure_openai_chat_client_agent_existing_thread():
    """Test Azure OpenAI chat client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatAgent(
        chat_client=AzureChatClient(credential=AzureCliCredential()),
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
            chat_client=AzureChatClient(credential=AzureCliCredential()),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my name?", thread=preserved_thread)

            assert isinstance(second_response, AgentRunResponse)
            assert second_response.text is not None
            assert "alice" in second_response.text.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_chat_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with Azure Chat Client."""

    async with ChatAgent(
        chat_client=AzureChatClient(credential=AzureCliCredential()),
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
