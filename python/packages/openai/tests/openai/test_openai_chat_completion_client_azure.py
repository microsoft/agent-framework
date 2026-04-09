# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from functools import wraps
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    SupportsChatGetResponse,
    tool,
)
from agent_framework.exceptions import SettingNotFoundError
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential
from openai import AsyncAzureOpenAI

from agent_framework_openai import OpenAIChatCompletionClient

pytestmark = pytest.mark.azure

skip_if_azure_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.openai.azure.com")
    or (os.getenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL", "") == "" and os.getenv("AZURE_OPENAI_MODEL", "") == ""),
    reason="No real Azure OpenAI endpoint or chat deployment provided; skipping integration tests.",
)


def _with_azure_openai_debug() -> Any:
    def decorator(func: Any) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                model = os.getenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL") or os.getenv("AZURE_OPENAI_MODEL", "<unset>")
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "<unset>")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "<unset>")
                debug_message = f"Azure OpenAI debug: endpoint={endpoint}, model={model}, api_version={api_version}"
                if hasattr(exc, "add_note"):
                    exc.add_note(debug_message)
                elif exc.args:
                    exc.args = (f"{exc.args[0]}\n{debug_message}", *exc.args[1:])
                else:
                    exc.args = (debug_message,)
                raise

        return wrapper

    return decorator


@tool(approval_mode="never_require")
def get_story_text() -> str:
    """Returns a story about Emily and David."""
    return (
        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
        "of climate change."
    )


@tool(approval_mode="never_require")
async def get_weather(location: str) -> str:
    """Get the current weather in a given location."""
    return f"The current weather in {location} is sunny, 72F."


def test_init_with_azure_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = OpenAIChatCompletionClient(azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"))

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_COMPLETION_MODEL"]
    assert isinstance(client, SupportsChatGetResponse)
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.OTEL_PROVIDER_NAME == "azure.ai.openai"
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]
    assert client.api_version == azure_openai_unit_test_env["AZURE_OPENAI_API_VERSION"]


def test_init_auto_detects_azure_env(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = OpenAIChatCompletionClient()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_COMPLETION_MODEL"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]


def test_openai_api_key_wins_over_azure_env(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    client = OpenAIChatCompletionClient()

    assert client.model == "gpt-5"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


def test_explicit_credential_wins_over_openai_api_key(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    client = OpenAIChatCompletionClient(credential=lambda: "token")

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_CHAT_COMPLETION_MODEL"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]


def test_init_falls_back_to_generic_azure_deployment_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL", raising=False)

    client = OpenAIChatCompletionClient()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_MODEL"]
    assert isinstance(client.client, AsyncAzureOpenAI)


def test_init_does_not_fall_back_to_openai_chat_model_for_azure_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_CHAT_COMPLETION_MODEL", "test_chat_model")

    with pytest.raises(SettingNotFoundError, match="Azure OpenAI client requires a model"):
        OpenAIChatCompletionClient()


def test_init_does_not_fall_back_to_openai_model_for_azure_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_CHAT_COMPLETION_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    with pytest.raises(SettingNotFoundError, match="Azure OpenAI client requires a model"):
        OpenAIChatCompletionClient()


def test_init_with_credential_wraps_async_token_credential(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    class TestAsyncTokenCredential(AsyncTokenCredential):
        async def get_token(self, *scopes: str, **kwargs: object):
            raise NotImplementedError

    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    credential = TestAsyncTokenCredential()
    token_provider = MagicMock()

    with patch("azure.identity.aio.get_bearer_token_provider", return_value=token_provider) as mock_provider:
        client = OpenAIChatCompletionClient(credential=credential)

    assert isinstance(client.client, AsyncAzureOpenAI)
    mock_provider.assert_called_once_with(credential, "https://cognitiveservices.azure.com/.default")


def test_openai_base_url_wins_over_azure_aliases(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom-openai-endpoint.com/v1")

    client = OpenAIChatCompletionClient()

    assert client.model == "gpt-5"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_response() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatCompletionClient(credential=credential)
        assert isinstance(client, SupportsChatGetResponse)

        messages = [
            Message(
                role="user",
                contents=[
                    (
                        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
                        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
                        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
                        "of climate change."
                    )
                ],
            ),
            Message(role="user", contents=["who are Emily and David?"]),
        ]

        response = await client.get_response(messages=messages)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert any(
            word in response.text.lower() for word in ["scientists", "research", "antarctica", "glaciology", "climate"]
        )


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_response_tools() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatCompletionClient(credential=credential)

        response = await client.get_response(
            messages=[Message(role="user", contents=["who are Emily and David?"])],
            options={"tools": [get_story_text], "tool_choice": "auto"},
        )

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert "Emily" in response.text or "David" in response.text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_streaming() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatCompletionClient(credential=credential)

        response = client.get_response(
            messages=[
                Message(
                    role="user",
                    contents=[
                        (
                            "Emily and David, two passionate scientists, met during a research expedition to "
                            "Antarctica. Bonded by their love for the natural world and shared curiosity, they "
                            "uncovered a groundbreaking phenomenon in glaciology that could potentially reshape our "
                            "understanding of climate change."
                        )
                    ],
                ),
                Message(role="user", contents=["who are Emily and David?"]),
            ],
            stream=True,
        )

        full_message = ""
        async for chunk in response:
            assert isinstance(chunk, ChatResponseUpdate)
            assert chunk.message_id is not None
            assert chunk.response_id is not None
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert "Emily" in full_message or "David" in full_message


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_streaming_tools() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatCompletionClient(credential=credential)

        response = client.get_response(
            messages=[Message(role="user", contents=["who are Emily and David?"])],
            stream=True,
            options={"tools": [get_story_text], "tool_choice": "auto"},
        )

        full_message = ""
        async for chunk in response:
            assert isinstance(chunk, ChatResponseUpdate)
            for content in chunk.contents:
                if content.type == "text" and content.text:
                    full_message += content.text

        assert "Emily" in full_message or "David" in full_message


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_agent_basic_run() -> None:
    async with (
        AzureCliCredential() as credential,
        Agent(
            client=OpenAIChatCompletionClient(credential=credential),
        ) as agent,
    ):
        response = await agent.run("Please respond with exactly: 'This is a response test.'")

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert "response test" in response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_agent_basic_run_streaming() -> None:
    async with (
        AzureCliCredential() as credential,
        Agent(client=OpenAIChatCompletionClient(credential=credential)) as agent,
    ):
        full_text = ""
        async for chunk in agent.run("Please respond with exactly: 'This is a streaming response test.'", stream=True):
            assert isinstance(chunk, AgentResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert "streaming response test" in full_text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_agent_session_persistence() -> None:
    async with (
        AzureCliCredential() as credential,
        Agent(
            client=OpenAIChatCompletionClient(credential=credential),
            instructions="You are a helpful assistant with good memory.",
        ) as agent,
    ):
        session = agent.create_session()
        response1 = await agent.run("My name is Alice. Remember this.", session=session)
        response2 = await agent.run("What is my name?", session=session)

        assert isinstance(response1, AgentResponse)
        assert isinstance(response2, AgentResponse)
        assert response2.text is not None
        assert "alice" in response2.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_completion_client_agent_existing_session() -> None:
    async with AzureCliCredential() as credential:
        preserved_session = None

        async with Agent(
            client=OpenAIChatCompletionClient(credential=credential),
            instructions="You are a helpful assistant with good memory.",
        ) as first_agent:
            session = first_agent.create_session()
            first_response = await first_agent.run("My name is Alice. Remember this.", session=session)

            assert isinstance(first_response, AgentResponse)
            preserved_session = session

        if preserved_session:
            async with Agent(
                client=OpenAIChatCompletionClient(credential=credential),
                instructions="You are a helpful assistant with good memory.",
            ) as second_agent:
                second_response = await second_agent.run("What is my name?", session=preserved_session)

                assert isinstance(second_response, AgentResponse)
                assert second_response.text is not None
                assert "alice" in second_response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_chat_completion_client_agent_level_tool_persistence() -> None:
    async with (
        AzureCliCredential() as credential,
        Agent(
            client=OpenAIChatCompletionClient(credential=credential),
            instructions="You are a helpful assistant that uses available tools.",
            tools=[get_weather],
        ) as agent,
    ):
        first_response = await agent.run("What's the weather like in Chicago?")
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(first_response, AgentResponse)
        assert isinstance(second_response, AgentResponse)
        assert first_response.text is not None
        assert second_response.text is not None
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "72"])
