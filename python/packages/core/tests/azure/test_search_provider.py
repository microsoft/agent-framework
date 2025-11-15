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


class TestMessageFiltering:
    """Test message filtering functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_filters_non_user_assistant_messages(self, mock_search_class: MagicMock) -> None:
        """Test that only USER and ASSISTANT messages are processed."""
        # Setup mock
        mock_search_client = AsyncMock()
        mock_results = AsyncMock()
        mock_results.__aiter__.return_value = iter([{"content": "Test result"}])
        mock_search_client.search.return_value = mock_results
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        # Mix of message types
        messages = [
            ChatMessage(role=Role.SYSTEM, text="System message"),
            ChatMessage(role=Role.USER, text="User message"),
            ChatMessage(role=Role.ASSISTANT, text="Assistant message"),
            ChatMessage(role=Role.TOOL, text="Tool message"),
        ]

        context = await provider.invoking(messages)

        # Should have processed only USER and ASSISTANT messages
        assert isinstance(context, Context)
        mock_search_client.search.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_filters_empty_messages(self, mock_search_class: MagicMock) -> None:
        """Test that empty/whitespace messages are filtered out."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        # Messages with empty/whitespace text
        messages = [
            ChatMessage(role=Role.USER, text=""),
            ChatMessage(role=Role.USER, text="   "),
            ChatMessage(role=Role.USER, text=None),
        ]

        context = await provider.invoking(messages)

        # Should return empty context
        assert len(context.messages) == 0


class TestCitations:
    """Test citation functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_citations_included_in_semantic_search(self, mock_search_class: MagicMock) -> None:
        """Test that citations are included in semantic search results."""
        # Setup mock with document ID
        mock_search_client = AsyncMock()
        mock_results = AsyncMock()
        mock_doc = {"id": "doc123", "content": "Test document content"}
        mock_results.__aiter__.return_value = iter([mock_doc])
        mock_search_client.search.return_value = mock_results
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        context = await provider.invoking([ChatMessage(role=Role.USER, text="test query")])

        # Check that citation is included
        assert isinstance(context, Context)
        assert len(context.messages) > 0
        assert "[Source: doc123]" in context.messages[0].text
        assert "Test document content" in context.messages[0].text


class TestVectorFieldAutoDiscovery:
    """Test vector field auto-discovery functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_auto_discovers_single_vector_field(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that single vector field is auto-discovered."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index client mock
        mock_index_client = AsyncMock()
        mock_index = MagicMock()

        # Create mock field with vector_search_dimensions attribute
        mock_vector_field = MagicMock()
        mock_vector_field.name = "embedding_vector"
        mock_vector_field.vector_search_dimensions = 1536

        mock_index.fields = [mock_vector_field]
        mock_index_client.get_index.return_value = mock_index
        mock_index_client.close = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Create provider without specifying vector_field_name
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        # Trigger auto-discovery
        await provider._auto_discover_vector_field()

        # Vector field should be auto-discovered but not used without embedding function
        assert provider._auto_discovered_vector_field is True
        # Should be cleared since no embedding function
        assert provider.vector_field_name is None

    @pytest.mark.asyncio
    async def test_vector_detection_accuracy(self) -> None:
        """Test that vector field detection logic correctly identifies vector fields."""
        from azure.search.documents.indexes.models import SearchField

        # Create real SearchField objects to test the detection logic
        vector_field = SearchField(
            name="embedding_vector", type="Collection(Edm.Single)", vector_search_dimensions=1536, searchable=True
        )

        string_field = SearchField(name="content", type="Edm.String", searchable=True)

        number_field = SearchField(name="price", type="Edm.Double", filterable=True)

        # Test detection logic directly
        is_vector_1 = vector_field.vector_search_dimensions is not None and vector_field.vector_search_dimensions > 0
        is_vector_2 = string_field.vector_search_dimensions is not None and string_field.vector_search_dimensions > 0
        is_vector_3 = number_field.vector_search_dimensions is not None and number_field.vector_search_dimensions > 0

        # Only the vector field should be detected
        assert is_vector_1 is True
        assert is_vector_2 is False
        assert is_vector_3 is False

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_no_false_positives_on_string_fields(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that regular string fields are not detected as vector fields."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index with only string fields (no vectors)
        mock_index_client = AsyncMock()
        mock_index = MagicMock()

        # All fields have vector_search_dimensions = None
        mock_fields = []
        for name in ["id", "title", "content", "category"]:
            field = MagicMock()
            field.name = name
            field.vector_search_dimensions = None
            field.vector_search_profile_name = None
            mock_fields.append(field)

        mock_index.fields = mock_fields
        mock_index_client.get_index.return_value = mock_index
        mock_index_client.close = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Create provider
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        # Trigger auto-discovery
        await provider._auto_discover_vector_field()

        # Should NOT detect any vector fields
        assert provider.vector_field_name is None
        assert provider._auto_discovered_vector_field is True


class TestAgenticMode:
    """Test agentic mode functionality with Knowledge Bases."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.KnowledgeAgentRetrievalClient")
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_agentic_mode_end_to_end(
        self,
        mock_search_class: MagicMock,
        mock_index_class: MagicMock,
        mock_retrieval_class: MagicMock,
    ) -> None:
        """Test complete agentic mode flow from invoking to retrieval."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index client mock (Knowledge Base exists)
        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.return_value = MagicMock()
        mock_index_client.get_agent.return_value = MagicMock()
        mock_index_class.return_value = mock_index_client

        # Setup retrieval client mock
        mock_retrieval_client = AsyncMock()

        # Import the models for mocking
        from agent_framework.azure._search_provider import (
            KnowledgeAgentMessageTextContent,
        )

        # Mock retrieval response
        mock_response_message = MagicMock()
        mock_response_message.content = [
            KnowledgeAgentMessageTextContent(text="This is the synthesized answer from the Knowledge Base.")
        ]

        mock_retrieval_result = MagicMock()
        mock_retrieval_result.response = [mock_response_message]
        mock_retrieval_client.retrieve = AsyncMock(return_value=mock_retrieval_result)

        mock_retrieval_class.return_value = mock_retrieval_client

        # Create provider in agentic mode
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

        # Call invoking with a user message
        messages = [ChatMessage(role=Role.USER, text="What information is available?")]
        context = await provider.invoking(messages)

        # Verify context was created with synthesized answer
        assert isinstance(context, Context)
        assert len(context.messages) > 0
        assert "synthesized answer from the Knowledge Base" in context.messages[0].text

        # Verify retrieval was called
        mock_retrieval_client.retrieve.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.KnowledgeAgentRetrievalClient")
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_agentic_mode_empty_response_fallback(
        self,
        mock_search_class: MagicMock,
        mock_index_class: MagicMock,
        mock_retrieval_class: MagicMock,
    ) -> None:
        """Test that agentic mode handles empty responses with fallback message."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index client mock (Knowledge Base exists)
        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.return_value = MagicMock()
        mock_index_client.get_agent.return_value = MagicMock()
        mock_index_class.return_value = mock_index_client

        # Setup retrieval client mock with empty response
        mock_retrieval_client = AsyncMock()
        mock_retrieval_result = MagicMock()
        mock_retrieval_result.response = []  # Empty response
        mock_retrieval_client.retrieve = AsyncMock(return_value=mock_retrieval_result)
        mock_retrieval_class.return_value = mock_retrieval_client

        # Create provider in agentic mode
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

        # Call invoking
        messages = [ChatMessage(role=Role.USER, text="What is this about?")]
        context = await provider.invoking(messages)

        # Should have fallback message
        assert isinstance(context, Context)
        assert len(context.messages) > 0
        assert "No results found from Knowledge Base" in context.messages[0].text


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchIndexClient")
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_auto_discovery_exception_handling(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that auto-discovery gracefully handles exceptions."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index client to raise an exception
        mock_index_client = AsyncMock()
        mock_index_client.get_index.side_effect = Exception("Network error")
        mock_index_client.close = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Create provider
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
        )

        # Should not raise exception, just log warning
        import logging

        with patch.object(logging, "warning") as mock_warning:
            await provider._auto_discover_vector_field()
            # Should log warning about failure
            mock_warning.assert_called_once()

        # Should mark as attempted and continue with keyword search
        assert provider._auto_discovered_vector_field is True
        assert provider.vector_field_name is None

    @pytest.mark.asyncio
    @patch("agent_framework.azure._search_provider.SearchClient")
    async def test_semantic_search_with_semantic_configuration(self, mock_search_class: MagicMock) -> None:
        """Test semantic search with semantic_configuration_name parameter."""
        # Setup mock
        mock_search_client = AsyncMock()
        mock_results = AsyncMock()
        mock_results.__aiter__.return_value = iter([{"content": "Semantic search result"}])
        mock_search_client.search.return_value = mock_results
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            credential=AzureKeyCredential("test-key"),
            mode="semantic",
            semantic_configuration_name="my-semantic-config",
        )

        messages = [ChatMessage(role=Role.USER, text="test query")]
        context = await provider.invoking(messages)

        # Verify search was called with semantic configuration
        assert mock_search_client.search.called
        call_args = mock_search_client.search.call_args
        assert "semantic_configuration_name" in call_args.kwargs
        assert call_args.kwargs["semantic_configuration_name"] == "my-semantic-config"

        # Verify context was created
        assert isinstance(context, Context)
        assert len(context.messages) > 0
