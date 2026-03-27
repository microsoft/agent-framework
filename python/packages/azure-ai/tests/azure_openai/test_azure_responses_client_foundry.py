# Copyright (c) Microsoft. All rights reserved.

import os
import warnings
from unittest.mock import MagicMock

import pytest
from agent_framework import Agent, SupportsChatGetResponse, tool

warnings.filterwarnings(
    "ignore",
    message=r"RawAzureAIClient is deprecated\..*",
    category=DeprecationWarning,
)

from agent_framework.azure import AzureOpenAIResponsesClient  # noqa: E402
from azure.identity import AzureCliCredential  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore:AzureOpenAIResponsesClient is deprecated\\..*:DeprecationWarning")

skip_if_foundry_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") == "" or os.getenv("FOUNDRY_MODEL", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL provided; skipping integration tests.",
)


def test_init_with_project_client(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test initialization with an existing AIProjectClient."""
    from unittest.mock import patch

    from openai import AsyncOpenAI

    # Create a mock AIProjectClient that returns a mock AsyncOpenAI client
    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_openai_client.default_headers = {}

    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    with patch(
        "agent_framework_azure_ai._deprecated_azure_openai.AzureOpenAIResponsesClient._create_client_from_project",
        return_value=mock_openai_client,
    ):
        azure_responses_client = AzureOpenAIResponsesClient(
            project_client=mock_project_client,
            deployment_name="gpt-4o",
        )

    assert azure_responses_client.model == "gpt-4o"
    assert azure_responses_client.client is mock_openai_client
    assert isinstance(azure_responses_client, SupportsChatGetResponse)


def test_init_with_project_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    """Test initialization with a project endpoint and credential."""
    from unittest.mock import patch

    from openai import AsyncOpenAI

    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_openai_client.default_headers = {}

    with patch(
        "agent_framework_azure_ai._deprecated_azure_openai.AzureOpenAIResponsesClient._create_client_from_project",
        return_value=mock_openai_client,
    ):
        azure_responses_client = AzureOpenAIResponsesClient(
            project_endpoint="https://test-project.services.ai.azure.com",
            deployment_name="gpt-4o",
            credential=AzureCliCredential(),
        )

    assert azure_responses_client.model == "gpt-4o"
    assert azure_responses_client.client is mock_openai_client
    assert isinstance(azure_responses_client, SupportsChatGetResponse)


def test_create_client_from_project_with_project_client() -> None:
    """Test _create_client_from_project with an existing project client."""
    from openai import AsyncOpenAI

    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai_client

    result = AzureOpenAIResponsesClient._create_client_from_project(
        project_client=mock_project_client,
        project_endpoint=None,
        credential=None,
    )

    assert result is mock_openai_client
    mock_project_client.get_openai_client.assert_called_once()


def test_create_client_from_project_with_endpoint() -> None:
    """Test _create_client_from_project with a project endpoint."""
    from unittest.mock import patch

    from openai import AsyncOpenAI

    mock_openai_client = MagicMock(spec=AsyncOpenAI)
    mock_credential = MagicMock()

    with patch("agent_framework_azure_ai._deprecated_azure_openai.AIProjectClient") as MockAIProjectClient:
        mock_instance = MockAIProjectClient.return_value
        mock_instance.get_openai_client.return_value = mock_openai_client

        result = AzureOpenAIResponsesClient._create_client_from_project(
            project_client=None,
            project_endpoint="https://test-project.services.ai.azure.com",
            credential=mock_credential,
        )

    assert result is mock_openai_client
    MockAIProjectClient.assert_called_once()
    mock_instance.get_openai_client.assert_called_once()


def test_create_client_from_project_missing_endpoint() -> None:
    """Test _create_client_from_project raises error when endpoint is missing."""
    with pytest.raises(ValueError, match="project endpoint is required"):
        AzureOpenAIResponsesClient._create_client_from_project(
            project_client=None,
            project_endpoint=None,
            credential=MagicMock(),
        )


def test_create_client_from_project_missing_credential() -> None:
    """Test _create_client_from_project raises error when credential is missing."""
    with pytest.raises(ValueError, match="credential is required"):
        AzureOpenAIResponsesClient._create_client_from_project(
            project_client=None,
            project_endpoint="https://test-project.services.ai.azure.com",
            credential=None,
        )


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_foundry_integration_tests_disabled
async def test_integration_function_call_roundtrip_preserves_fidelity() -> None:
    """Test that function calls roundtrip correctly with full fidelity preserved."""
    call_count = 0

    @tool(name="get_weather", approval_mode="never_require")
    async def get_weather_tool(location: str) -> str:
        """Get weather for a location."""
        nonlocal call_count
        call_count += 1
        return f"Weather in {location} is sunny, 72F"

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        deployment_name=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    async with Agent(
        client=client,
        name="WeatherAgent",
        instructions="You help check weather. Use get_weather when asked about weather.",
        tools=[get_weather_tool],
        default_options={"store": False},
    ) as agent:
        session = agent.create_session()

        response1 = await agent.run("What is the weather in Seattle?", session=session)

        assert response1 is not None
        assert response1.text is not None
        assert call_count >= 1

        response_text = response1.text.lower()
        assert "seattle" in response_text or "sunny" in response_text or "72" in response_text

        response2 = await agent.run("And how about in Portland?", session=session)

        assert response2 is not None
        assert response2.text is not None
        assert call_count >= 2
