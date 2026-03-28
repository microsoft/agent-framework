# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import os
from functools import wraps
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import Agent, AgentResponse, ChatResponse, Content, Message, SupportsChatGetResponse, tool
from agent_framework.exceptions import SettingNotFoundError
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential
from openai import AsyncAzureOpenAI
from pydantic import BaseModel
from pytest import param

from agent_framework_openai import OpenAIChatClient

pytestmark = pytest.mark.azure

skip_if_azure_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.openai.azure.com")
    or (
        os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "") == ""
        and os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "") == ""
    ),
    reason="No real Azure OpenAI endpoint or responses deployment provided; skipping integration tests.",
)


def _with_azure_openai_debug() -> Any:
    def decorator(func: Any) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                model = os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME") or os.getenv(
                    "AZURE_OPENAI_DEPLOYMENT_NAME", "<unset>"
                )
                api_version = os.getenv("AZURE_OPENAI_API_VERSION") or "preview"
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


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str | None = None


async def create_vector_store(client: OpenAIChatClient) -> tuple[str, Content]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."),
        purpose="assistants",
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store.id,
        file_id=file.id,
        poll_interval_ms=1000,
    )
    if result.last_error is not None:
        raise RuntimeError(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, Content.from_hosted_vector_store(vector_store_id=vector_store.id)


async def delete_vector_store(client: OpenAIChatClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


@tool(approval_mode="never_require")
async def get_weather(location: str) -> str:
    """Get the current weather in a given location."""
    return f"The current weather in {location} is sunny."


def test_init_with_azure_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = OpenAIChatClient(credential=AzureCliCredential())

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(client, SupportsChatGetResponse)
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.OTEL_PROVIDER_NAME == "azure.ai.openai"
    assert client.azure_endpoint.startswith(azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"])


def test_init_auto_detects_azure_env(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = OpenAIChatClient()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]


def test_openai_api_key_wins_over_azure_env(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    client = OpenAIChatClient()

    assert client.model == "gpt-5"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


def test_api_version_alone_does_not_override_openai_api_key(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    client = OpenAIChatClient(api_version="2024-10-21")

    assert client.model == "gpt-5"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


def test_explicit_credential_wins_over_openai_api_key(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    client = OpenAIChatClient(credential=lambda: "token")

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]


def test_init_falls_back_to_generic_azure_deployment_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", raising=False)

    client = OpenAIChatClient()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)


def test_init_does_not_fall_back_to_openai_responses_model_for_azure_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setenv("OPENAI_RESPONSES_MODEL", "test_responses_model")

    with pytest.raises(SettingNotFoundError, match="Azure OpenAI client requires a deployment name"):
        OpenAIChatClient()


def test_init_does_not_fall_back_to_openai_model_for_azure_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("OPENAI_RESPONSES_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    with pytest.raises(SettingNotFoundError, match="Azure OpenAI client requires a deployment name"):
        OpenAIChatClient()


def test_init_with_credential_wraps_async_token_credential(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    class TestAsyncTokenCredential(AsyncTokenCredential):
        async def get_token(self, *scopes: str, **kwargs: object):
            raise NotImplementedError

    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    credential = TestAsyncTokenCredential()
    token_provider = MagicMock()

    with patch("azure.identity.aio.get_bearer_token_provider", return_value=token_provider) as mock_provider:
        client = OpenAIChatClient(credential=credential)

    assert isinstance(client.client, AsyncAzureOpenAI)
    mock_provider.assert_called_once_with(credential, "https://cognitiveservices.azure.com/.default")


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_API_VERSION"]], indirect=True)
def test_init_uses_default_azure_api_version(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = OpenAIChatClient(credential=AzureCliCredential())

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert client.api_version is not None


def test_openai_base_url_wins_over_azure_aliases(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom-openai-endpoint.com/v1")

    client = OpenAIChatClient()

    assert client.model == "gpt-5"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        param("max_tokens", 500, False, id="max_tokens"),
        param("seed", 123, False, id="seed"),
        param("user", "test-user-id", False, id="user"),
        param("metadata", {"test_key": "test_value"}, False, id="metadata"),
        param("frequency_penalty", 0.5, False, id="frequency_penalty"),
        param("presence_penalty", 0.3, False, id="presence_penalty"),
        param("stop", ["END"], False, id="stop"),
        param("allow_multiple_tool_calls", True, False, id="allow_multiple_tool_calls"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        param("safety_identifier", "user-hash-abc123", False, id="safety_identifier"),
        param("truncation", "auto", False, id="truncation"),
        param("prompt_cache_key", "test-cache-key", False, id="prompt_cache_key"),
        param("max_tool_calls", 3, False, id="max_tool_calls"),
        param("tools", [get_weather], True, id="tools_function"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
        param(
            "tool_choice",
            {"mode": "required", "required_function_name": "get_weather"},
            True,
            id="tool_choice_required",
        ),
        param("response_format", OutputStruct, True, id="response_format_pydantic"),
        param(
            "response_format",
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "WeatherDigest",
                    "strict": True,
                    "schema": {
                        "title": "WeatherDigest",
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                            "conditions": {"type": "string"},
                            "temperature_c": {"type": "number"},
                            "advisory": {"type": "string"},
                        },
                        "required": ["location", "conditions", "temperature_c", "advisory"],
                        "additionalProperties": False,
                    },
                },
            },
            True,
            id="response_format_runtime_json_schema",
        ),
    ],
)
@_with_azure_openai_debug()
async def test_integration_options(
    option_name: str,
    option_value: Any,
    needs_validation: bool,
) -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)
        client.function_invocation_configuration["max_iterations"] = 2

        for streaming in [False, True]:
            if option_name in {"tools", "tool_choice"}:
                messages = [Message(role="user", text="What is the weather in Seattle?")]
            elif option_name == "response_format":
                messages = [
                    Message(role="user", text="The weather in Seattle is sunny"),
                    Message(role="user", text="What is the weather in Seattle?"),
                ]
            else:
                messages = [Message(role="user", text="Say 'Hello World' briefly.")]

            options: dict[str, Any] = {option_name: option_value}
            if option_name == "tool_choice":
                options["tools"] = [get_weather]

            if streaming:
                response = await client.get_response(
                    messages=messages,
                    stream=True,
                    options=options,
                ).get_final_response()
            else:
                response = await client.get_response(messages=messages, options=options)

            assert isinstance(response, ChatResponse)
            assert response.text is not None
            assert len(response.text) > 0

            if needs_validation:
                if option_name in {"tools", "tool_choice"}:
                    text = response.text.lower()
                    assert "sunny" in text or "seattle" in text
                elif option_name == "response_format":
                    if option_value == OutputStruct:
                        assert response.value is not None
                        assert isinstance(response.value, OutputStruct)
                        assert "seattle" in response.value.location.lower()
                    else:
                        assert response.value is None
                        response_value = json.loads(response.text)
                        assert isinstance(response_value, dict)
                        assert "location" in response_value
                        assert "seattle" in response_value["location"].lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_web_search() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)

        response = await client.get_response(
            messages=[
                Message(
                    role="user",
                    text="What is the current weather? Do not ask for my current location.",
                )
            ],
            options={
                "tools": [OpenAIChatClient.get_web_search_tool(user_location={"country": "US", "city": "Seattle"})],
            },
            stream=True,
        ).get_final_response()
        assert isinstance(response, ChatResponse)
        assert response.text is not None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_client_file_search() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)
        file_id, vector_store = await create_vector_store(client)
        try:
            response = await client.get_response(
                messages=[Message(role="user", text="What is the weather today? Do a file search to find the answer.")],
                options={
                    "tools": [OpenAIChatClient.get_file_search_tool(vector_store_ids=[vector_store.vector_store_id])],
                    "tool_choice": "auto",
                },
            )

            assert "sunny" in response.text.lower()
            assert "75" in response.text
        finally:
            await delete_vector_store(client, file_id, vector_store.vector_store_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_client_file_search_streaming() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)
        file_id, vector_store = await create_vector_store(client)
        try:
            response_stream = client.get_response(
                messages=[Message(role="user", text="What is the weather today? Do a file search to find the answer.")],
                stream=True,
                options={
                    "tools": [OpenAIChatClient.get_file_search_tool(vector_store_ids=[vector_store.vector_store_id])],
                    "tool_choice": "auto",
                },
            )

            full_response = await response_stream.get_final_response()
            assert "sunny" in full_response.text.lower()
            assert "75" in full_response.text
        finally:
            await delete_vector_store(client, file_id, vector_store.vector_store_id)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_client_agent_hosted_mcp_tool() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)
        response = await client.get_response(
            messages=[Message(role="user", text="How to create an Azure storage account using az cli?")],
            options={
                "max_tokens": 5000,
                "tools": OpenAIChatClient.get_mcp_tool(
                    name="Microsoft Learn MCP",
                    url="https://learn.microsoft.com/api/mcp",
                ),
            },
        )

        assert isinstance(response, ChatResponse)
        if not response.text:
            pytest.skip("MCP server returned empty response - service-side issue")
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_client_agent_hosted_code_interpreter_tool() -> None:
    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)

        response = await client.get_response(
            messages=[Message(role="user", text="Calculate the sum of numbers from 1 to 10 using Python code.")],
            options={"tools": [OpenAIChatClient.get_code_interpreter_tool()]},
        )

        contains_relevant_content = any(
            term in response.text.lower() for term in ["55", "sum", "code", "python", "calculate", "10"]
        )
        assert contains_relevant_content or len(response.text.strip()) > 10


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_integration_client_agent_existing_session() -> None:
    async with AzureCliCredential() as credential:
        preserved_session = None

        async with Agent(
            client=OpenAIChatClient(credential=credential),
            instructions="You are a helpful assistant with good memory.",
        ) as first_agent:
            session = first_agent.create_session()
            first_response = await first_agent.run(
                "My hobby is photography. Remember this.",
                session=session,
                options={"store": True},
            )

            assert isinstance(first_response, AgentResponse)
            preserved_session = session

        if preserved_session:
            async with Agent(
                client=OpenAIChatClient(credential=credential),
                instructions="You are a helpful assistant with good memory.",
            ) as second_agent:
                second_response = await second_agent.run(
                    "What is my hobby?", session=preserved_session, options={"store": True}
                )

                assert isinstance(second_response, AgentResponse)
                assert second_response.text is not None
                assert "photography" in second_response.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_chat_client_tool_rich_content_image() -> None:
    image_path = Path(__file__).parent.parent / "assets" / "sample_image.jpg"
    image_bytes = image_path.read_bytes()

    @tool(approval_mode="never_require")
    def get_test_image() -> Content:
        """Return a test image for analysis."""
        return Content.from_data(data=image_bytes, media_type="image/jpeg")

    async with AzureCliCredential() as credential:
        client = OpenAIChatClient(credential=credential)
        client.function_invocation_configuration["max_iterations"] = 2

        for streaming in [False, True]:
            messages = [Message(role="user", text="Call the get_test_image tool and describe what you see.")]
            options: dict[str, Any] = {"tools": [get_test_image], "tool_choice": "auto"}

            if streaming:
                response = await client.get_response(
                    messages=messages,
                    stream=True,
                    options=options,
                ).get_final_response()
            else:
                response = await client.get_response(messages=messages, options=options)

            assert isinstance(response, ChatResponse)
            assert response.text is not None
            assert "house" in response.text.lower(), (
                f"Model did not describe the house image. Response: {response.text}"
            )
