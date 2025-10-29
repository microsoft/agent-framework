# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError

from agent_framework import ChatMessage, Context, Role
from agent_framework.azure import AzureAISearchContextProvider


@pytest.fixture
def mock_search_client() -> AsyncMock:
    """Create a mock SearchClient."""
    mock_client = AsyncMock()
    mock_client.search = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


@pytest.fixture
def mock_index_client() -> AsyncMock:
    """Create a mock SearchIndexClient."""
    mock_client = AsyncMock()
    mock_client.get_knowledge_source = AsyncMock()
    mock_client.create_knowledge_source = AsyncMock()
    mock_client.get_agent = AsyncMock()
    mock_client.create_agent = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    """Create sample chat messages for testing."""
    return [
        ChatMessage(role=Role.USER, text="What is in the documents?"),
    ]


class TestSearchProviderInitialization:
    """Test initialization and configuration of AzureAISearchContextProvider."""

    def test_init_semantic_mode_minimal(self) -> None:
        """Test initialization with minimal semantic mode parameters."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )
        assert provider.endpoint == "https://test.search.windows.net"
        assert provider.index_name == "test-index"
        assert provider.mode == "semantic"
        assert provider.top_k == 5

    def test_init_semantic_mode_with_vector_field_requires_embedding_function(self) -> None:
        """Test that vector_field_name requires embedding_function."""
        with pytest.raises(ValueError, match="embedding_function is required"):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=AzureKeyCredential("test-key"),
                mode="semantic",
                vector_field_name="embedding",
            )

    def test_init_agentic_mode_requires_parameters(self) -> None:
        """Test that agentic mode requires additional parameters."""
        with pytest.raises(ValueError, match="azure_openai_resource_url"):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=AzureKeyCredential("test-key"),
                mode="agentic",
            )

    def test_init_agentic_mode_requires_model_deployment_name(self) -> None:
        """Test that agentic mode requires model_deployment_name."""
        with pytest.raises(ValueError, match="model_deployment_name"):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=AzureKeyCredential("test-key"),
                mode="agentic",
                azure_ai_project_endpoint="https://test.services.ai.azure.com",
                azure_openai_resource_url="https://test.openai.azure.com",
            )

    def test_init_agentic_mode_requires_knowledge_base_name(self) -> None:
        """Test that agentic mode requires knowledge_base_name."""
        with pytest.raises(ValueError, match="knowledge_base_name"):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                credential=AzureKeyCredential("test-key"),
                mode="agentic",
                azure_ai_project_endpoint="https://test.services.ai.azure.com",
                model_deployment_name="gpt-4o",
                azure_openai_resource_url="https://test.openai.azure.com",
            )

    def test_init_agentic_mode_with_all_params(self) -> None:
        """Test initialization with all agentic mode parameters."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="agentic",
            azure_ai_project_endpoint="https://test.services.ai.azure.com",
            model_deployment_name="my-gpt-4o-deployment",
            model_name="gpt-4o",
            knowledge_base_name="test-kb",
            azure_openai_resource_url="https://test.openai.azure.com",
        )
        assert provider.mode == "agentic"
        assert provider.azure_ai_project_endpoint == "https://test.services.ai.azure.com"
        assert provider.azure_openai_resource_url == "https://test.openai.azure.com"
        assert provider.azure_openai_deployment_name == "my-gpt-4o-deployment"
        assert provider.model_name == "gpt-4o"
        assert provider.knowledge_base_name == "test-kb"

    def test_init_model_name_defaults_to_deployment_name(self) -> None:
        """Test that model_name defaults to deployment_name if not provided."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="agentic",
            azure_ai_project_endpoint="https://test.services.ai.azure.com",
            model_deployment_name="gpt-4o",
            knowledge_base_name="test-kb",
            azure_openai_resource_url="https://test.openai.azure.com",
        )
        assert provider.model_name == "gpt-4o"

    def test_init_with_custom_context_prompt(self) -> None:
        """Test initialization with custom context prompt."""
        custom_prompt = "Use the following information:"
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
            context_prompt=custom_prompt,
        )
        assert provider.context_prompt == custom_prompt

    def test_init_uses_default_context_prompt(self) -> None:
        """Test that default context prompt is used when not provided."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )
        assert provider.context_prompt == provider.DEFAULT_CONTEXT_PROMPT


class TestSemanticSearch:
    """Test semantic search functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_semantic_search_basic(
        self, mock_search_class: MagicMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test basic semantic search without vector search."""
        # Setup mock
        mock_search_client = AsyncMock()
        mock_results = AsyncMock()
        mock_results.__aiter__.return_value = iter([{"content": "Test document content"}])
        mock_search_client.search.return_value = mock_results
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        context = await provider.invoking(sample_messages)

        assert isinstance(context, Context)
        assert len(context.messages) > 0
        assert "Test document content" in context.messages[0].text

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_semantic_search_empty_query(self, mock_search_class: MagicMock) -> None:
        """Test that empty queries return empty context."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        # Empty message
        context = await provider.invoking([ChatMessage(role=Role.USER, text="")])

        assert isinstance(context, Context)
        assert len(context.messages) == 0

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_semantic_search_with_vector_query(
        self, mock_search_class: MagicMock, sample_messages: list[ChatMessage]
    ) -> None:
        """Test semantic search with vector query."""
        # Setup mock
        mock_search_client = AsyncMock()
        mock_results = AsyncMock()
        mock_results.__aiter__.return_value = iter([{"content": "Vector search result"}])
        mock_search_client.search.return_value = mock_results
        mock_search_class.return_value = mock_search_client

        # Mock embedding function
        async def mock_embed(text: str) -> list[float]:
            return [0.1, 0.2, 0.3]

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
            vector_field_name="embedding",
            embedding_function=mock_embed,
        )

        context = await provider.invoking(sample_messages)

        assert isinstance(context, Context)
        assert len(context.messages) > 0
        # Verify that search was called
        mock_search_client.search.assert_called_once()


class TestKnowledgeBaseSetup:
    """Test Knowledge Base setup for agentic mode."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_ensure_knowledge_base_creates_when_not_exists(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that Knowledge Base is created when it doesn't exist."""
        # Setup mocks
        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.side_effect = ResourceNotFoundError("Not found")
        mock_index_client.create_knowledge_source = AsyncMock()
        mock_index_client.get_agent.side_effect = ResourceNotFoundError("Not found")
        mock_index_client.create_agent = AsyncMock()
        mock_index_class.return_value = mock_index_client

        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="agentic",
            azure_ai_project_endpoint="https://test.services.ai.azure.com",
            model_deployment_name="gpt-4o",
            model_name="gpt-4o",
            knowledge_base_name="test-kb",
            azure_openai_resource_url="https://test.openai.azure.com",
        )

        await provider._ensure_knowledge_base()

        # Verify knowledge source was created
        mock_index_client.create_knowledge_source.assert_called_once()
        # Verify agent (Knowledge Base) was created
        mock_index_client.create_agent.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_ensure_knowledge_base_skips_when_exists(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that Knowledge Base setup is skipped when already exists."""
        # Setup mocks
        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.return_value = MagicMock()  # Exists
        mock_index_client.get_agent.return_value = MagicMock()  # Exists
        mock_index_class.return_value = mock_index_client

        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="agentic",
            azure_ai_project_endpoint="https://test.services.ai.azure.com",
            model_deployment_name="gpt-4o",
            knowledge_base_name="test-kb",
            azure_openai_resource_url="https://test.openai.azure.com",
        )

        await provider._ensure_knowledge_base()

        # Verify nothing was created
        mock_index_client.create_knowledge_source.assert_not_called()
        mock_index_client.create_agent.assert_not_called()


class TestContextProviderLifecycle:
    """Test context provider lifecycle methods."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_context_manager(self, mock_search_class: MagicMock) -> None:
        """Test that provider can be used as async context manager."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        async with AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        ) as provider:
            assert provider is not None
            assert isinstance(provider, AzureAISearchContextProvider)
