# Copyright (c) Microsoft. All rights reserved.
# pyright: reportPrivateUsage=false

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatMessage, Context, Role
from agent_framework.azure import AzureAISearchContextProvider, AzureAISearchSettings
from agent_framework.exceptions import ServiceInitializationError
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError


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


class TestAzureAISearchSettings:
    """Test AzureAISearchSettings configuration."""

    def test_settings_with_direct_values(self) -> None:
        """Test settings with direct values."""
        settings = AzureAISearchSettings(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
        )
        assert settings.endpoint == "https://test.search.windows.net"
        assert settings.index_name == "test-index"
        # api_key is now SecretStr
        assert settings.api_key.get_secret_value() == "test-key"

    def test_settings_with_env_file_path(self) -> None:
        """Test settings with env_file_path parameter."""
        settings = AzureAISearchSettings(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            env_file_path="test.env",
        )
        assert settings.endpoint == "https://test.search.windows.net"
        assert settings.index_name == "test-index"

    def test_provider_uses_settings_from_env(self) -> None:
        """Test that provider creates settings internally from env."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
        )
        assert provider.endpoint == "https://test.search.windows.net"
        assert provider.index_name == "test-index"

    def test_provider_missing_endpoint_raises_error(self) -> None:
        """Test that provider raises ServiceInitializationError without endpoint."""
        # Use patch.dict to clear environment and pass env_file_path="" to prevent .env file loading
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with (
            patch.dict(os.environ, clean_env, clear=True),
            pytest.raises(ServiceInitializationError, match="endpoint is required"),
        ):
            AzureAISearchContextProvider(
                index_name="test-index",
                api_key="test-key",
                env_file_path="",  # Disable .env file loading
            )

    def test_provider_missing_index_name_raises_error(self) -> None:
        """Test that provider raises ServiceInitializationError without index_name."""
        # Use patch.dict to clear environment and pass env_file_path="" to prevent .env file loading
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with (
            patch.dict(os.environ, clean_env, clear=True),
            pytest.raises(ServiceInitializationError, match="index name is required"),
        ):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                env_file_path="",  # Disable .env file loading
            )

    def test_provider_missing_credential_raises_error(self) -> None:
        """Test that provider raises ServiceInitializationError without credential."""
        # Use patch.dict to clear environment and pass env_file_path="" to prevent .env file loading
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with (
            patch.dict(os.environ, clean_env, clear=True),
            pytest.raises(ServiceInitializationError, match="credential is required"),
        ):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                env_file_path="",  # Disable .env file loading
            )


class TestSearchProviderInitialization:
    """Test initialization and configuration of AzureAISearchContextProvider."""

    def test_init_semantic_mode_minimal(self) -> None:
        """Test initialization with minimal semantic mode parameters."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
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
                api_key="test-key",
                mode="semantic",
                vector_field_name="embedding",
            )

    def test_init_agentic_mode_with_kb_only(self) -> None:
        """Test agentic mode with existing knowledge_base_name (simplest path)."""
        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                env_file_path="",  # Disable .env file loading
            )
            assert provider.mode == "agentic"
            assert provider.knowledge_base_name == "test-kb"
            assert provider._use_existing_knowledge_base is True

    def test_init_agentic_mode_with_index_requires_model(self) -> None:
        """Test that agentic mode with index_name requires model_deployment_name."""
        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with (
            patch.dict(os.environ, clean_env, clear=True),
            pytest.raises(ServiceInitializationError, match="model_deployment_name"),
        ):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                api_key="test-key",
                mode="agentic",
                env_file_path="",  # Disable .env file loading
            )

    def test_init_agentic_mode_with_index_and_model(self) -> None:
        """Test agentic mode with index_name (auto-create KB path)."""
        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                api_key="test-key",
                mode="agentic",
                model_deployment_name="gpt-4o",
                azure_openai_resource_url="https://test.openai.azure.com",
                env_file_path="",  # Disable .env file loading
            )
            assert provider.mode == "agentic"
            assert provider.index_name == "test-index"
            assert provider.knowledge_base_name == "test-index-kb"  # Auto-generated
            assert provider._use_existing_knowledge_base is False

    def test_init_agentic_mode_rejects_both_index_and_kb(self) -> None:
        """Test that agentic mode rejects both index_name AND knowledge_base_name."""
        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with (
            patch.dict(os.environ, clean_env, clear=True),
            pytest.raises(ServiceInitializationError, match="either 'index_name' OR 'knowledge_base_name', not both"),
        ):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                model_deployment_name="gpt-4o",
                azure_openai_resource_url="https://test.openai.azure.com",
                env_file_path="",  # Disable .env file loading
            )

    def test_init_agentic_mode_requires_index_or_kb(self) -> None:
        """Test that agentic mode requires either index_name or knowledge_base_name."""
        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with (
            patch.dict(os.environ, clean_env, clear=True),
            pytest.raises(ServiceInitializationError, match="provide either 'index_name'.*or 'knowledge_base_name'"),
        ):
            AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                env_file_path="",  # Disable .env file loading
            )

    def test_init_model_name_defaults_to_deployment_name(self) -> None:
        """Test that model_name defaults to deployment_name if not provided."""
        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                model_deployment_name="gpt-4o",
                env_file_path="",  # Disable .env file loading
            )
            assert provider.model_name == "gpt-4o"

    def test_init_with_custom_context_prompt(self) -> None:
        """Test initialization with custom context prompt."""
        custom_prompt = "Use the following information:"
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
            context_prompt=custom_prompt,
        )
        assert provider.context_prompt == custom_prompt

    def test_init_uses_default_context_prompt(self) -> None:
        """Test that default context prompt is used when not provided."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
        )
        assert provider.context_prompt == provider._DEFAULT_SEARCH_CONTEXT_PROMPT


class TestSemanticSearch:
    """Test semantic search functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
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
            api_key="test-key",
            mode="semantic",
        )

        context = await provider.invoking(sample_messages)

        assert isinstance(context, Context)
        assert len(context.messages) > 1  # First message is prompt, rest are results
        # First message should be the context prompt
        assert "Use the following context" in context.messages[0].text
        # Second message should contain the search result
        assert "Test document content" in context.messages[1].text

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_semantic_search_empty_query(self, mock_search_class: MagicMock) -> None:
        """Test that empty queries return empty context."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
        )

        # Empty message
        context = await provider.invoking([ChatMessage(role=Role.USER, text="")])

        assert isinstance(context, Context)
        assert len(context.messages) == 0

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
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
            api_key="test-key",
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
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_ensure_knowledge_base_creates_when_not_exists(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that Knowledge Base is created when it doesn't exist (index_name path)."""
        # Setup mocks
        mock_index_client = AsyncMock()
        mock_index_client.get_knowledge_source.side_effect = ResourceNotFoundError("Not found")
        mock_index_client.create_knowledge_source = AsyncMock()
        mock_index_client.get_knowledge_base.side_effect = ResourceNotFoundError("Not found")
        mock_index_client.create_or_update_knowledge_base = AsyncMock()
        mock_index_class.return_value = mock_index_client

        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            # Use index_name path (auto-create KB)
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                index_name="test-index",
                api_key="test-key",
                mode="agentic",
                model_deployment_name="gpt-4o",
                azure_openai_resource_url="https://test.openai.azure.com",
                env_file_path="",  # Disable .env file loading
            )

            await provider._ensure_knowledge_base()

            # Verify knowledge source was created
            mock_index_client.create_knowledge_source.assert_called_once()
            # Verify Knowledge Base was created
            mock_index_client.create_or_update_knowledge_base.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_ensure_knowledge_base_skips_when_using_existing_kb(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that KB setup is skipped when using existing knowledge_base_name."""
        # Setup mocks
        mock_index_client = AsyncMock()
        mock_index_class.return_value = mock_index_client

        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            # Use knowledge_base_name path (existing KB)
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                env_file_path="",  # Disable .env file loading
            )

            await provider._ensure_knowledge_base()

            # Verify nothing was created (using existing KB)
            mock_index_client.create_knowledge_source.assert_not_called()
            mock_index_client.create_or_update_knowledge_base.assert_not_called()


class TestContextProviderLifecycle:
    """Test context provider lifecycle methods."""

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_context_manager(self, mock_search_class: MagicMock) -> None:
        """Test that provider can be used as async context manager."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        async with AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
        ) as provider:
            assert provider is not None
            assert isinstance(provider, AzureAISearchContextProvider)

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.KnowledgeBaseRetrievalClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_context_manager_agentic_cleanup(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock, mock_retrieval_class: MagicMock
    ) -> None:
        """Test that agentic mode provider cleans up retrieval client."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        mock_index_client = AsyncMock()
        mock_index_class.return_value = mock_index_client

        mock_retrieval_client = AsyncMock()
        mock_retrieval_client.close = AsyncMock()
        mock_retrieval_class.return_value = mock_retrieval_client

        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            # Use knowledge_base_name path (existing KB)
            async with AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                env_file_path="",  # Disable .env file loading
            ) as provider:
                # Simulate retrieval client being created
                provider._retrieval_client = mock_retrieval_client

            # Verify cleanup was called
            mock_retrieval_client.close.assert_called_once()

    def test_string_api_key_conversion(self) -> None:
        """Test that string api_key is converted to AzureKeyCredential."""
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="my-api-key",  # String api_key
            mode="semantic",
        )
        assert isinstance(provider.credential, AzureKeyCredential)


class TestMessageFiltering:
    """Test message filtering functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
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
            api_key="test-key",
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
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_filters_empty_messages(self, mock_search_class: MagicMock) -> None:
        """Test that empty/whitespace messages are filtered out."""
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
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
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
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
            api_key="test-key",
            mode="semantic",
        )

        context = await provider.invoking([ChatMessage(role=Role.USER, text="test query")])

        # Check that citation is included
        assert isinstance(context, Context)
        assert len(context.messages) > 1  # First message is prompt, rest are results
        # Citation should be in the result message (second message)
        assert "[Source: doc123]" in context.messages[1].text
        assert "Test document content" in context.messages[1].text


class TestAgenticSearch:
    """Test agentic search functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.KnowledgeBaseRetrievalClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_agentic_search_basic(
        self,
        mock_search_class: MagicMock,
        mock_index_class: MagicMock,
        mock_retrieval_class: MagicMock,
        sample_messages: list[ChatMessage],
    ) -> None:
        """Test basic agentic search with Knowledge Base retrieval."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index client mock
        mock_index_client = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Setup retrieval client mock with response
        mock_retrieval_client = AsyncMock()
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Agentic search result"
        # Make it pass isinstance check
        from agent_framework_azure_ai_search._search_provider import _agentic_retrieval_available

        if _agentic_retrieval_available:
            from azure.search.documents.knowledgebases.models import KnowledgeBaseMessageTextContent

            mock_content.__class__ = KnowledgeBaseMessageTextContent
        mock_message.content = [mock_content]
        mock_response.response = [mock_message]
        mock_retrieval_client.retrieve.return_value = mock_response
        mock_retrieval_client.close = AsyncMock()
        mock_retrieval_class.return_value = mock_retrieval_client

        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            # Use knowledge_base_name path (existing KB)
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                env_file_path="",  # Disable .env file loading
            )

            context = await provider.invoking(sample_messages)

            assert isinstance(context, Context)
            # Should have at least the prompt message
            assert len(context.messages) >= 1

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.KnowledgeBaseRetrievalClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_agentic_search_no_results(
        self,
        mock_search_class: MagicMock,
        mock_index_class: MagicMock,
        mock_retrieval_class: MagicMock,
        sample_messages: list[ChatMessage],
    ) -> None:
        """Test agentic search when no results are returned."""
        # Setup mocks
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        mock_index_client = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Empty response
        mock_retrieval_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.response = []
        mock_retrieval_client.retrieve.return_value = mock_response
        mock_retrieval_client.close = AsyncMock()
        mock_retrieval_class.return_value = mock_retrieval_client

        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            # Use knowledge_base_name path (existing KB)
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                env_file_path="",  # Disable .env file loading
            )

            context = await provider.invoking(sample_messages)

            assert isinstance(context, Context)
            # Should have fallback message
            assert len(context.messages) >= 1

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.KnowledgeBaseRetrievalClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_agentic_search_with_medium_reasoning(
        self,
        mock_search_class: MagicMock,
        mock_index_class: MagicMock,
        mock_retrieval_class: MagicMock,
        sample_messages: list[ChatMessage],
    ) -> None:
        """Test agentic search with medium reasoning effort."""
        # Setup mocks
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        mock_index_client = AsyncMock()
        mock_index_class.return_value = mock_index_client

        mock_retrieval_client = AsyncMock()
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Medium reasoning result"
        from agent_framework_azure_ai_search._search_provider import _agentic_retrieval_available

        if _agentic_retrieval_available:
            from azure.search.documents.knowledgebases.models import KnowledgeBaseMessageTextContent

            mock_content.__class__ = KnowledgeBaseMessageTextContent
        mock_message.content = [mock_content]
        mock_response.response = [mock_message]
        mock_retrieval_client.retrieve.return_value = mock_response
        mock_retrieval_client.close = AsyncMock()
        mock_retrieval_class.return_value = mock_retrieval_client

        # Clear environment to ensure no env vars interfere
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith("AZURE_SEARCH_")}
        with patch.dict(os.environ, clean_env, clear=True):
            # Use knowledge_base_name path (existing KB)
            provider = AzureAISearchContextProvider(
                endpoint="https://test.search.windows.net",
                api_key="test-key",
                mode="agentic",
                knowledge_base_name="test-kb",
                retrieval_reasoning_effort="medium",  # Test medium reasoning
                env_file_path="",  # Disable .env file loading
            )

            context = await provider.invoking(sample_messages)

            assert isinstance(context, Context)
            assert len(context.messages) >= 1


class TestVectorFieldAutoDiscovery:
    """Test vector field auto-discovery functionality."""

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
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
            api_key="test-key",
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
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
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
            api_key="test-key",
            mode="semantic",
        )

        # Trigger auto-discovery
        await provider._auto_discover_vector_field()

        # Should NOT detect any vector fields
        assert provider.vector_field_name is None
        assert provider._auto_discovered_vector_field is True

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_multiple_vector_fields_without_vectorizer(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that multiple vector fields without vectorizer logs warning and uses keyword search."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index with multiple vector fields (no vectorizers)
        mock_index_client = AsyncMock()
        mock_index = MagicMock()

        # Multiple vector fields
        mock_fields = []
        for name in ["embedding1", "embedding2"]:
            field = MagicMock()
            field.name = name
            field.vector_search_dimensions = 1536
            field.vector_search_profile_name = None  # No vectorizer
            mock_fields.append(field)

        mock_index.fields = mock_fields
        mock_index.vector_search = None  # No vector search config
        mock_index_client.get_index.return_value = mock_index
        mock_index_client.close = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Create provider
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
        )

        # Trigger auto-discovery
        await provider._auto_discover_vector_field()

        # Should NOT use any vector field (multiple fields, can't choose)
        assert provider.vector_field_name is None
        assert provider._auto_discovered_vector_field is True

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_multiple_vectorizable_fields(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that multiple vectorizable fields logs warning and uses keyword search."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index with multiple vectorizable fields
        mock_index_client = AsyncMock()
        mock_index = MagicMock()

        # Multiple vector fields with vectorizers
        mock_fields = []
        for name in ["embedding1", "embedding2"]:
            field = MagicMock()
            field.name = name
            field.vector_search_dimensions = 1536
            field.vector_search_profile_name = f"{name}-profile"
            mock_fields.append(field)

        mock_index.fields = mock_fields

        # Setup vector search config with profiles that have vectorizers
        mock_profile1 = MagicMock()
        mock_profile1.name = "embedding1-profile"
        mock_profile1.vectorizer_name = "vectorizer1"

        mock_profile2 = MagicMock()
        mock_profile2.name = "embedding2-profile"
        mock_profile2.vectorizer_name = "vectorizer2"

        mock_index.vector_search = MagicMock()
        mock_index.vector_search.profiles = [mock_profile1, mock_profile2]

        mock_index_client.get_index.return_value = mock_index
        mock_index_client.close = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Create provider
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
        )

        # Trigger auto-discovery
        await provider._auto_discover_vector_field()

        # Should NOT use any vector field (multiple vectorizable fields, can't choose)
        assert provider.vector_field_name is None
        assert provider._auto_discovered_vector_field is True

    @pytest.mark.asyncio
    @patch("agent_framework_azure_ai_search._search_provider.SearchIndexClient")
    @patch("agent_framework_azure_ai_search._search_provider.SearchClient")
    async def test_single_vectorizable_field_detected(
        self, mock_search_class: MagicMock, mock_index_class: MagicMock
    ) -> None:
        """Test that single vectorizable field is auto-detected for server-side vectorization."""
        # Setup search client mock
        mock_search_client = AsyncMock()
        mock_search_class.return_value = mock_search_client

        # Setup index with single vectorizable field
        mock_index_client = AsyncMock()
        mock_index = MagicMock()

        # Single vector field with vectorizer
        mock_field = MagicMock()
        mock_field.name = "embedding"
        mock_field.vector_search_dimensions = 1536
        mock_field.vector_search_profile_name = "embedding-profile"

        mock_index.fields = [mock_field]

        # Setup vector search config with profile that has vectorizer
        mock_profile = MagicMock()
        mock_profile.name = "embedding-profile"
        mock_profile.vectorizer_name = "openai-vectorizer"

        mock_index.vector_search = MagicMock()
        mock_index.vector_search.profiles = [mock_profile]

        mock_index_client.get_index.return_value = mock_index
        mock_index_client.close = AsyncMock()
        mock_index_class.return_value = mock_index_client

        # Create provider
        provider = AzureAISearchContextProvider(
            endpoint="https://test.search.windows.net",
            index_name="test-index",
            api_key="test-key",
            mode="semantic",
        )

        # Trigger auto-discovery
        await provider._auto_discover_vector_field()

        # Should detect the vectorizable field
        assert provider.vector_field_name == "embedding"
        assert provider._auto_discovered_vector_field is True
        assert provider._use_vectorizable_query is True  # Server-side vectorization
