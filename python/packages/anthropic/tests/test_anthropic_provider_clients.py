# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AGENT_FRAMEWORK_USER_AGENT, ChatMiddlewareLayer, FunctionInvocationLayer
from agent_framework.observability import ChatTelemetryLayer

from agent_framework_anthropic import (
    AnthropicBedrockClient,
    AnthropicFoundryClient,
    AnthropicVertexClient,
    RawAnthropicBedrockClient,
    RawAnthropicFoundryClient,
    RawAnthropicVertexClient,
)


def _create_mock_transport(base_url: str) -> MagicMock:
    transport = MagicMock()
    transport.base_url = base_url
    transport.beta = MagicMock()
    transport.beta.messages = MagicMock()
    transport.beta.messages.create = AsyncMock()
    return transport


@pytest.mark.parametrize(
    ("public_client", "raw_client"),
    [
        (AnthropicFoundryClient, RawAnthropicFoundryClient),
        (AnthropicBedrockClient, RawAnthropicBedrockClient),
        (AnthropicVertexClient, RawAnthropicVertexClient),
    ],
)
def test_provider_client_wraps_raw_client_with_standard_layer_order(public_client, raw_client) -> None:
    assert issubclass(public_client, raw_client)
    mro = public_client.__mro__
    assert mro.index(FunctionInvocationLayer) < mro.index(ChatMiddlewareLayer)
    assert mro.index(ChatMiddlewareLayer) < mro.index(ChatTelemetryLayer)
    assert mro.index(ChatTelemetryLayer) < mro.index(raw_client)


def test_raw_anthropic_foundry_client_creates_sdk_client_from_settings(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_CHAT_MODEL=claude-foundry-test\n"
        "ANTHROPIC_FOUNDRY_API_KEY=test-key\n"
        "ANTHROPIC_FOUNDRY_RESOURCE=test-resource\n"
    )
    mock_transport = _create_mock_transport("https://test-resource.services.ai.azure.com/anthropic/")

    with patch(
        "agent_framework_anthropic._foundry_client.AsyncAnthropicFoundry", return_value=mock_transport
    ) as factory:
        client = RawAnthropicFoundryClient(env_file_path=str(env_file))

    assert client.model == "claude-foundry-test"
    assert client.anthropic_client is mock_transport
    factory.assert_called_once_with(
        resource="test-resource",
        api_key="test-key",
        azure_ad_token_provider=None,
        default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
    )


def test_raw_anthropic_foundry_client_creates_sdk_client_from_base_url_settings(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_CHAT_MODEL=claude-foundry-test\n"
        "ANTHROPIC_FOUNDRY_API_KEY=test-key\n"
        "ANTHROPIC_FOUNDRY_BASE_URL=https://test-resource.services.ai.azure.com/anthropic/\n"
    )
    mock_transport = _create_mock_transport("https://test-resource.services.ai.azure.com/anthropic/")

    with patch(
        "agent_framework_anthropic._foundry_client.AsyncAnthropicFoundry", return_value=mock_transport
    ) as factory:
        client = RawAnthropicFoundryClient(env_file_path=str(env_file))

    assert client.model == "claude-foundry-test"
    assert client.anthropic_client is mock_transport
    factory.assert_called_once_with(
        base_url="https://test-resource.services.ai.azure.com/anthropic/",
        api_key="test-key",
        azure_ad_token_provider=None,
        default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
    )


def test_raw_anthropic_foundry_client_requires_resource_or_base_url() -> None:
    with patch("agent_framework_anthropic._foundry_client.load_settings") as mock_load:
        mock_load.return_value = {
            "anthropic_foundry_api_key": None,
            "anthropic_foundry_resource": None,
            "anthropic_foundry_base_url": None,
            "anthropic_chat_model": None,
        }

        with pytest.raises(
            ValueError,
            match=(
                "Anthropic Foundry requires either `resource`/`ANTHROPIC_FOUNDRY_RESOURCE` "
                "or `base_url`/`ANTHROPIC_FOUNDRY_BASE_URL`\\."
            ),
        ):
            RawAnthropicFoundryClient()


def test_raw_anthropic_bedrock_client_creates_sdk_client_from_arguments() -> None:
    mock_transport = _create_mock_transport("https://bedrock-runtime.us-east-1.amazonaws.com")

    with patch(
        "agent_framework_anthropic._bedrock_client.AsyncAnthropicBedrock", return_value=mock_transport
    ) as factory:
        client = RawAnthropicBedrockClient(
            model="claude-bedrock-test",
            aws_access_key="access-key",
            aws_secret_key="secret-key",
            aws_region="us-east-1",
        )

    assert client.model == "claude-bedrock-test"
    assert client.anthropic_client is mock_transport
    factory.assert_called_once_with(
        aws_secret_key="secret-key",
        aws_access_key="access-key",
        aws_region="us-east-1",
        aws_profile=None,
        aws_session_token=None,
        base_url=None,
        default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
    )


def test_raw_anthropic_vertex_client_creates_sdk_client_from_arguments() -> None:
    mock_transport = _create_mock_transport("https://us-central1-aiplatform.googleapis.com/v1")

    with patch("agent_framework_anthropic._vertex_client.AsyncAnthropicVertex", return_value=mock_transport) as factory:
        client = RawAnthropicVertexClient(
            model="claude-vertex-test",
            region="us-central1",
            project_id="test-project",
        )

    assert client.model == "claude-vertex-test"
    assert client.anthropic_client is mock_transport
    factory.assert_called_once_with(
        region="us-central1",
        project_id="test-project",
        access_token=None,
        credentials=None,
        base_url=None,
        default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
    )
