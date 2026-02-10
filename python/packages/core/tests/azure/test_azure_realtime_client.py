# Copyright (c) Microsoft. All rights reserved.
"""Tests for AzureOpenAIRealtimeClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework._realtime_client import RealtimeClientProtocol
from agent_framework._realtime_types import RealtimeSessionConfig
from agent_framework.azure._realtime_client import DEFAULT_AZURE_REALTIME_API_VERSION, AzureOpenAIRealtimeClient
from agent_framework.azure._shared import DEFAULT_AZURE_API_VERSION, AzureOpenAIConfigMixin
from agent_framework.exceptions import ServiceInitializationError


def test_azure_realtime_client_implements_protocol():
    """Test AzureOpenAIRealtimeClient satisfies RealtimeClientProtocol."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        api_key="test-key",
    )
    assert isinstance(client, RealtimeClientProtocol)


def test_azure_realtime_client_extends_config_mixin():
    """Test AzureOpenAIRealtimeClient extends AzureOpenAIConfigMixin."""
    assert issubclass(AzureOpenAIRealtimeClient, AzureOpenAIConfigMixin)


def test_azure_realtime_client_with_api_key():
    """Test client can be created with API key."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        api_key="test-key",
    )
    assert client.endpoint == "https://test.openai.azure.com/"
    assert client.deployment_name == "gpt-4o-realtime"


def test_azure_realtime_client_with_credential():
    """Test client can be created with Azure credential."""
    mock_credential = MagicMock()
    # Need to mock get_entra_auth_token since credential path requires token_endpoint
    with patch("agent_framework.azure._shared.get_entra_auth_token", return_value="mock-token"):
        client = AzureOpenAIRealtimeClient(
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4o-realtime",
            credential=mock_credential,
            token_endpoint="https://cognitiveservices.azure.com/.default",
        )
        assert client.deployment_name == "gpt-4o-realtime"


def test_azure_realtime_client_with_ad_token():
    """Test client can be created with AD token."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        ad_token="test-ad-token",
    )
    assert client.deployment_name == "gpt-4o-realtime"


def test_azure_realtime_client_with_ad_token_provider():
    """Test client can be created with AD token provider."""

    def token_provider() -> str:
        return "test-token"

    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        ad_token_provider=token_provider,
    )
    assert client.deployment_name == "gpt-4o-realtime"


def test_azure_realtime_client_requires_deployment_name():
    """Test client requires deployment_name."""
    with pytest.raises(ServiceInitializationError, match="deployment name is required"):
        AzureOpenAIRealtimeClient(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
        )


def test_azure_realtime_client_requires_auth():
    """Test client requires authentication (api_key, ad_token, ad_token_provider, or credential)."""
    with pytest.raises(ServiceInitializationError, match="api_key, ad_token or ad_token_provider"):
        AzureOpenAIRealtimeClient(
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4o-realtime",
        )


def test_azure_realtime_client_settings_fallback():
    """Test client falls back to environment variable for deployment name."""
    with patch.dict("os.environ", {"AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME": "env-deployment"}):
        client = AzureOpenAIRealtimeClient(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
        )
        assert client.deployment_name == "env-deployment"


def test_azure_realtime_client_with_existing_client():
    """Test client can be created with an existing AsyncAzureOpenAI client."""
    mock_client = MagicMock()
    client = AzureOpenAIRealtimeClient(
        deployment_name="gpt-4o-realtime",
        client=mock_client,
    )
    assert client.deployment_name == "gpt-4o-realtime"


@pytest.mark.asyncio
async def test_azure_realtime_client_connect_uses_sdk():
    """Test connect() uses SDK's client.realtime.connect()."""
    mock_sdk_client = MagicMock()
    mock_connection_manager = MagicMock()
    mock_connection = AsyncMock()
    mock_connection.send = AsyncMock()

    mock_connection_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection_manager.__aexit__ = AsyncMock()
    mock_sdk_client.realtime.connect.return_value = mock_connection_manager

    client = AzureOpenAIRealtimeClient(
        deployment_name="gpt-4o-realtime",
        client=mock_sdk_client,
    )

    config = RealtimeSessionConfig(
        instructions="You are helpful.",
        voice="nova",
    )

    await client.connect(config)

    # Verify SDK's realtime.connect() was called
    mock_sdk_client.realtime.connect.assert_called_once()
    call_kwargs = mock_sdk_client.realtime.connect.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-realtime"

    # Verify session.update was sent
    mock_connection.session.update.assert_called_once()
    call_kwargs = mock_connection.session.update.call_args.kwargs
    assert call_kwargs["session"]["instructions"] == "You are helpful."
    assert call_kwargs["session"]["voice"] == "nova"


def test_azure_realtime_client_has_additional_properties():
    """Test AzureOpenAIRealtimeClient has additional_properties."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        api_key="test-key",
    )
    assert hasattr(client, "additional_properties")
    assert isinstance(client.additional_properties, dict)


def test_azure_realtime_client_otel_provider_name():
    """Test AzureOpenAIRealtimeClient has OTEL_PROVIDER_NAME."""
    assert AzureOpenAIRealtimeClient.OTEL_PROVIDER_NAME == "azure.ai.openai"


def test_azure_realtime_client_defaults_to_realtime_api_version():
    """Test client defaults to a realtime-compatible API version, not the general default."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        api_key="test-key",
    )
    assert client.api_version == DEFAULT_AZURE_REALTIME_API_VERSION
    assert client.api_version != DEFAULT_AZURE_API_VERSION


def test_azure_realtime_client_respects_explicit_api_version():
    """Test client uses an explicitly provided API version."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        api_key="test-key",
        api_version="2025-01-01",
    )
    assert client.api_version == "2025-01-01"


async def test_azure_realtime_update_session_not_connected():
    """Test update_session raises RuntimeError when not connected."""
    client = AzureOpenAIRealtimeClient(
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4o-realtime",
        api_key="test-key",
    )
    config = RealtimeSessionConfig(instructions="Updated instructions.")

    with pytest.raises(RuntimeError, match="Not connected"):
        await client.update_session(config)


async def test_azure_realtime_update_session_sends_update():
    """Test update_session calls connection.session.update with correct config."""
    mock_sdk_client = MagicMock()
    mock_connection_manager = MagicMock()
    mock_connection = AsyncMock()

    mock_connection_manager.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection_manager.__aexit__ = AsyncMock()
    mock_sdk_client.realtime.connect.return_value = mock_connection_manager

    client = AzureOpenAIRealtimeClient(
        deployment_name="gpt-4o-realtime",
        client=mock_sdk_client,
    )

    # Connect first
    connect_config = RealtimeSessionConfig(instructions="Initial.", voice="nova")
    await client.connect(connect_config)

    # Reset mock to isolate update_session call
    mock_connection.session.update.reset_mock()

    # Update session with new config
    update_config = RealtimeSessionConfig(instructions="Updated instructions.", voice="alloy")
    await client.update_session(update_config)

    mock_connection.session.update.assert_called_once()
    call_kwargs = mock_connection.session.update.call_args.kwargs
    assert call_kwargs["session"]["instructions"] == "Updated instructions."
    assert call_kwargs["session"]["voice"] == "alloy"
