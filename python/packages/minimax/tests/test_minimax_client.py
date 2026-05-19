# Copyright (c) Microsoft. All rights reserved.
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    ChatMiddlewareLayer,
    FunctionInvocationLayer,
    Message,
)
from agent_framework._tools import normalize_function_invocation_configuration

USER_MESSAGE = [Message(role="user", contents=["Hello"])]
from agent_framework.observability import ChatTelemetryLayer
from anthropic.types import (
    Message as AnthropicMessage,
    TextBlock,
    Usage,
)

from agent_framework_minimax import MiniMaxClient, RawMiniMaxClient
from agent_framework_minimax._chat_client import (
    MINIMAX_DEFAULT_BASE_URL,
    MINIMAX_MODELS,
    MINIMAX_UNSUPPORTED_PARAMS,
    MiniMaxSettings,
)

skip_if_minimax_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("MINIMAX_API_KEY", "") in ("", "test-minimax-api-key-12345"),
    reason="No real MINIMAX_API_KEY provided; skipping integration tests.",
)


def create_test_minimax_client(
    mock_anthropic_client: MagicMock,
    model: str | None = "MiniMax-M2.7",
) -> MiniMaxClient:
    """Helper function to create MiniMaxClient instances for testing."""
    client = object.__new__(MiniMaxClient)

    client.anthropic_client = mock_anthropic_client
    client.model = model
    client._last_call_id_name = None
    client._last_call_content_type = None
    client._tool_name_aliases = {}
    client.additional_properties = {}
    client.middleware = None
    client.additional_beta_flags = []
    client.chat_middleware = []
    client.function_middleware = []
    client._cached_chat_middleware_pipeline = None
    client._cached_function_middleware_pipeline = None
    client.function_invocation_configuration = normalize_function_invocation_configuration(None)

    return client


def make_anthropic_message(text: str = "Hello from MiniMax!") -> AnthropicMessage:
    """Create a mock Anthropic Message response."""
    return AnthropicMessage(
        id="msg_test123",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
        model="MiniMax-M2.7",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=10, output_tokens=5),
    )


# Settings Tests


def test_minimax_settings_from_env(minimax_unit_test_env: dict[str, str]) -> None:
    """Test that MiniMaxSettings loads correctly from environment variables."""
    from agent_framework._settings import load_settings

    settings = load_settings(
        MiniMaxSettings,
        env_prefix="MINIMAX_",
    )
    assert settings.get("chat_model") == "MiniMax-M2.7"
    assert settings.get("api_key") is not None


def test_minimax_default_base_url() -> None:
    """Test the default base URL constant."""
    assert MINIMAX_DEFAULT_BASE_URL == "https://api.minimax.io/anthropic"


def test_minimax_models_list() -> None:
    """Test that the supported model list contains the expected models."""
    assert "MiniMax-M2.7" in MINIMAX_MODELS
    assert "MiniMax-M2.7-highspeed" in MINIMAX_MODELS


def test_minimax_unsupported_params() -> None:
    """Test that the unsupported params set contains key MiniMax-incompatible params."""
    assert "betas" in MINIMAX_UNSUPPORTED_PARAMS
    assert "top_k" in MINIMAX_UNSUPPORTED_PARAMS
    assert "service_tier" in MINIMAX_UNSUPPORTED_PARAMS
    assert "thinking" in MINIMAX_UNSUPPORTED_PARAMS
    assert "output_format" in MINIMAX_UNSUPPORTED_PARAMS


# Client Initialization Tests


def test_raw_minimax_client_raises_without_api_key(minimax_unit_test_env: dict[str, str], monkeypatch) -> None:  # type: ignore
    """Test that RawMiniMaxClient raises ValueError when no API key is provided."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MiniMax API key is required"):
        RawMiniMaxClient(model="MiniMax-M2.7")


def test_raw_minimax_client_init(minimax_unit_test_env: dict[str, str]) -> None:
    """Test that RawMiniMaxClient initializes correctly with environment variables."""
    client = RawMiniMaxClient()
    assert client.model == "MiniMax-M2.7"
    assert MINIMAX_DEFAULT_BASE_URL in str(client.anthropic_client.base_url)


def test_raw_minimax_client_custom_base_url(minimax_unit_test_env: dict[str, str]) -> None:
    """Test that RawMiniMaxClient respects a custom base_url."""
    custom_url = "https://api.minimaxi.com/anthropic"
    client = RawMiniMaxClient(base_url=custom_url)
    assert custom_url in str(client.anthropic_client.base_url)


def test_raw_minimax_client_with_explicit_anthropic_client(mock_minimax_client: MagicMock) -> None:
    """Test that RawMiniMaxClient accepts a pre-built AsyncAnthropic client."""
    client = RawMiniMaxClient(model="MiniMax-M2.7", anthropic_client=mock_minimax_client)
    assert client.anthropic_client is mock_minimax_client
    assert client.model == "MiniMax-M2.7"


def test_minimax_client_has_middleware_layers(minimax_unit_test_env: dict[str, str]) -> None:
    """Test that MiniMaxClient includes all expected middleware layers."""
    client = MiniMaxClient()
    assert isinstance(client, FunctionInvocationLayer)
    assert isinstance(client, ChatMiddlewareLayer)
    assert isinstance(client, ChatTelemetryLayer)
    assert isinstance(client, RawMiniMaxClient)


# Response Tests


@pytest.mark.asyncio
async def test_minimax_get_response(mock_minimax_client: MagicMock) -> None:
    """Test that MiniMaxClient.get_response returns a valid ChatResponse."""
    mock_minimax_client.messages.create = AsyncMock(
        return_value=make_anthropic_message("Hello!")
    )

    client = create_test_minimax_client(mock_minimax_client)
    response = await client.get_response(USER_MESSAGE)

    assert response is not None
    assert len(response.messages) > 0
    assert response.messages[0].text == "Hello!"


@pytest.mark.asyncio
async def test_minimax_uses_messages_not_beta(mock_minimax_client: MagicMock) -> None:
    """Test that MiniMaxClient uses messages.create (not beta.messages.create)."""
    mock_minimax_client.messages.create = AsyncMock(
        return_value=make_anthropic_message("OK")
    )

    client = create_test_minimax_client(mock_minimax_client)
    await client.get_response(USER_MESSAGE)

    # Should call messages.create, not beta.messages.create
    mock_minimax_client.messages.create.assert_called_once()
    assert not hasattr(mock_minimax_client, "beta") or not mock_minimax_client.beta.messages.create.called


@pytest.mark.asyncio
async def test_minimax_filters_unsupported_params(mock_minimax_client: MagicMock) -> None:
    """Test that unsupported params are filtered out before calling the API."""
    mock_minimax_client.messages.create = AsyncMock(
        return_value=make_anthropic_message("OK")
    )

    client = create_test_minimax_client(mock_minimax_client)
    await client.get_response(USER_MESSAGE)

    call_kwargs = mock_minimax_client.messages.create.call_args[1]
    for param in MINIMAX_UNSUPPORTED_PARAMS:
        assert param not in call_kwargs, f"Unsupported param '{param}' was passed to API"


@pytest.mark.asyncio
async def test_minimax_uses_correct_model(mock_minimax_client: MagicMock) -> None:
    """Test that MiniMaxClient passes the correct model to the API."""
    mock_minimax_client.messages.create = AsyncMock(
        return_value=make_anthropic_message("OK")
    )

    client = create_test_minimax_client(mock_minimax_client, model="MiniMax-M2.7-highspeed")
    await client.get_response(USER_MESSAGE)

    call_kwargs = mock_minimax_client.messages.create.call_args[1]
    assert call_kwargs.get("model") == "MiniMax-M2.7-highspeed"


# Integration Tests (require real MINIMAX_API_KEY)


@skip_if_minimax_integration_tests_disabled
@pytest.mark.integration
@pytest.mark.asyncio
async def test_minimax_integration_basic_chat() -> None:
    """Integration test: basic chat with MiniMax API."""
    client = MiniMaxClient(model="MiniMax-M2.7")
    response = await client.get_response([Message(role="user", contents=["Say 'test passed' in exactly those words."])])
    assert response is not None
    assert len(response.messages) > 0
    text = response.messages[0].text or ""
    assert "test" in text.lower()


@skip_if_minimax_integration_tests_disabled
@pytest.mark.integration
@pytest.mark.asyncio
async def test_minimax_integration_streaming() -> None:
    """Integration test: streaming response from MiniMax API."""
    client = MiniMaxClient(model="MiniMax-M2.7")
    chunks = []
    async for update in await client.get_response([Message(role="user", contents=["Say hello."])], stream=True):
        if update.text:
            chunks.append(update.text)
    assert len(chunks) > 0
