# Copyright (c) Microsoft. All rights reserved.

"""Azure AI Search Context Provider for Agent Framework.

This module provides context providers for Azure AI Search integration with two modes:
- Semantic: Fast hybrid search (vector + keyword) with semantic ranker
- Agentic: Slower multi-hop reasoning using Knowledge Bases for complex queries

Use semantic mode for most cases. Use agentic mode only when you need multi-hop
reasoning across documents with Knowledge Bases.
"""

import os
import sys
from collections.abc import Awaitable, Callable, MutableSequence
from typing import TYPE_CHECKING, Any, Literal

from agent_framework import ChatMessage, Context, ContextProvider, Role
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeRetrievalOutputMode,
    KnowledgeSourceReference,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
)
from azure.search.documents.models import (
    QueryCaptionType,
    QueryType,
    VectorizableTextQuery,
    VectorizedQuery,
)

# Type checking imports for optional agentic mode dependencies
if TYPE_CHECKING:
    from azure.search.documents.knowledgebases.aio import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseMessage,
        KnowledgeBaseMessageTextContent,
        KnowledgeBaseRetrievalRequest,
    )

# Runtime imports for agentic mode (optional dependency)
try:
    from azure.search.documents.knowledgebases.aio import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseMessage,
        KnowledgeBaseMessageTextContent,
        KnowledgeBaseRetrievalRequest,
    )

    _agentic_retrieval_available = True
except ImportError:
    _agentic_retrieval_available = False

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


class AzureAISearchSettings:
    """Settings for Azure AI Search Context Provider with auto-loading from environment.

    Environment variables:
        AZURE_SEARCH_ENDPOINT: Azure AI Search endpoint URL
        AZURE_SEARCH_INDEX_NAME: Name of the search index
        AZURE_SEARCH_API_KEY: API key for authentication
        AZURE_AI_PROJECT_ENDPOINT: Azure AI Foundry project endpoint (for agentic mode)
        AZURE_OPENAI_RESOURCE_URL: Azure OpenAI resource URL (for agentic mode)
        AZURE_OPENAI_DEPLOYMENT_NAME: Model deployment name (for agentic mode)
        AZURE_OPENAI_API_KEY: Azure OpenAI API key (for agentic mode with API key auth)
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        index_name: str | None = None,
        api_key: str | None = None,
        azure_ai_project_endpoint: str | None = None,
        azure_openai_resource_url: str | None = None,
        model_deployment_name: str | None = None,
        azure_openai_api_key: str | None = None,
    ) -> None:
        """Initialize settings with auto-loading from environment variables.

        Args:
            endpoint: Azure AI Search endpoint URL (or AZURE_SEARCH_ENDPOINT env var)
            index_name: Search index name (or AZURE_SEARCH_INDEX_NAME env var)
            api_key: API key (or AZURE_SEARCH_API_KEY env var)
            azure_ai_project_endpoint: Azure AI Foundry project endpoint (or AZURE_AI_PROJECT_ENDPOINT env var)
            azure_openai_resource_url: Azure OpenAI resource URL (or AZURE_OPENAI_RESOURCE_URL env var)
            model_deployment_name: Model deployment name (or AZURE_OPENAI_DEPLOYMENT_NAME env var)
            azure_openai_api_key: Azure OpenAI API key (or AZURE_OPENAI_API_KEY env var)
        """
        self.endpoint = endpoint or os.getenv("AZURE_SEARCH_ENDPOINT")
        self.index_name = index_name or os.getenv("AZURE_SEARCH_INDEX_NAME")
        self.api_key = api_key or os.getenv("AZURE_SEARCH_API_KEY")
        self.azure_ai_project_endpoint = azure_ai_project_endpoint or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        self.azure_openai_resource_url = azure_openai_resource_url or os.getenv("AZURE_OPENAI_RESOURCE_URL")
        self.model_deployment_name = model_deployment_name or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        self.azure_openai_api_key = azure_openai_api_key or os.getenv("AZURE_OPENAI_API_KEY")

    def validate(self) -> None:
        """Validate required settings are present."""
        if not self.endpoint:
            raise ValueError("endpoint is required (or set AZURE_SEARCH_ENDPOINT)")
        if not self.index_name:
            raise ValueError("index_name is required (or set AZURE_SEARCH_INDEX_NAME)")


class AzureAISearchContextProvider(ContextProvider):
    """Azure AI Search Context Provider with hybrid search and semantic ranking.

    This provider retrieves relevant documents from Azure AI Search to provide context
    to the AI agent. It supports two modes:

    - **semantic** (default): Fast hybrid search combining vector and keyword search
      with semantic reranking. Suitable for most RAG use cases.
    - **agentic**: Slower multi-hop reasoning across documents using Knowledge Bases.
      Use only for complex queries requiring cross-document reasoning.

    Examples:
        Using Settings class with environment variables:

        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework_azure_ai import AzureAIAgentClient
            from agent_framework.azure import AzureAISearchContextProvider, AzureAISearchSettings
            from azure.identity.aio import DefaultAzureCredential

            # Load from environment variables
            settings = AzureAISearchSettings()
            search_provider = AzureAISearchContextProvider(settings=settings, credential=DefaultAzureCredential())

        Semantic hybrid search with API key:

        .. code-block:: python

            # Direct API key string (converted to AzureKeyCredential automatically)
            search_provider = AzureAISearchContextProvider(
                endpoint="https://mysearch.search.windows.net",
                index_name="my-index",
                credential="my-api-key",  # String converted to AzureKeyCredential
                mode="semantic",
            )

        Agentic retrieval for complex queries:

        .. code-block:: python

            # Use agentic mode for multi-hop reasoning (slower)
            search_provider = AzureAISearchContextProvider(
                endpoint="https://mysearch.search.windows.net",
                index_name="my-index",
                credential=DefaultAzureCredential(),
                mode="agentic",  # Multi-hop reasoning
                azure_ai_project_endpoint="https://myproject.services.ai.azure.com",
                model_deployment_name="gpt-4o",
                knowledge_base_name="my-knowledge-base",  # Required for agentic mode
            )
    """

    _DEFAULT_SEARCH_CONTEXT_PROMPT = "Use the following context to answer the question:"

    def __init__(
        self,
        endpoint: str | None = None,
        index_name: str | None = None,
        credential: str | AzureKeyCredential | AsyncTokenCredential | None = None,
        *,
        settings: AzureAISearchSettings | None = None,
        mode: Literal["semantic", "agentic"] = "semantic",
        top_k: int = 5,
        semantic_configuration_name: str | None = None,
        vector_field_name: str | None = None,
        embedding_function: Callable[[str], Awaitable[list[float]]] | None = None,
        context_prompt: str | None = None,
        # Agentic mode parameters (Knowledge Base)
        azure_ai_project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        model_name: str | None = None,
        knowledge_base_name: str | None = None,
        retrieval_instructions: str | None = None,
        azure_openai_api_key: str | None = None,
        azure_openai_resource_url: str | None = None,
        # Deprecated parameters (for backwards compatibility)
        azure_openai_endpoint: str | None = None,
        azure_openai_deployment_name: str | None = None,
        azure_openai_api_version: str | None = None,
    ) -> None:
        """Initialize Azure AI Search Context Provider.

        Args:
            endpoint: Azure AI Search endpoint URL.
            index_name: Name of the search index to query.
            credential: Azure credential (API key string, AzureKeyCredential, or AsyncTokenCredential).
                If a string is provided, it will be converted to AzureKeyCredential.
            settings: Settings object with auto-loaded configuration from environment.
                If provided, endpoint/index_name/api_key from settings will be used as defaults.
            mode: Search mode - "semantic" for hybrid search with semantic ranking (fast)
                or "agentic" for multi-hop reasoning (slower). Default: "semantic".
            top_k: Maximum number of documents to retrieve. Only applies to semantic mode.
                In agentic mode, the server-side Knowledge Base determines retrieval based on
                query complexity and reasoning effort. Default: 5.
            semantic_configuration_name: Name of semantic configuration in the index.
                Required for semantic ranking. If None, uses index default.
            vector_field_name: Name of the vector field in the index for hybrid search.
                Required if using vector search. Default: None (keyword search only).
            embedding_function: Async function to generate embeddings for vector search.
                Signature: async def embed(text: str) -> list[float]
                Required if vector_field_name is specified and no server-side vectorization.
            context_prompt: Custom prompt to prepend to retrieved context.
                Default: "Use the following context to answer the question:"
            azure_ai_project_endpoint: Azure AI Foundry project endpoint URL.
                Required for agentic mode. Example: "https://myproject.services.ai.azure.com"
            model_deployment_name: Model deployment name in the Azure AI project.
                Required for agentic mode.
            model_name: The underlying model name (e.g., "gpt-4o", "gpt-4o-mini").
                If not provided, defaults to model_deployment_name. Used for Knowledge Base configuration.
            knowledge_base_name: Name for the Knowledge Base. Required for agentic mode.
            retrieval_instructions: Custom instructions for the Knowledge Base's
                retrieval planning. Only used in agentic mode.
            azure_openai_api_key: Azure OpenAI API key for Knowledge Base to call the model.
                Only needed when using API key authentication instead of managed identity.
            azure_openai_resource_url: Azure OpenAI resource URL for Knowledge Base model calls.
                Required for agentic mode. Example: "https://myresource.openai.azure.com"
                This is different from azure_ai_project_endpoint (which is Foundry-specific).
            azure_openai_endpoint: (Deprecated) Use azure_ai_project_endpoint instead.
            azure_openai_deployment_name: (Deprecated) Use model_deployment_name instead.
            azure_openai_api_version: (Deprecated) No longer used.
        """
        # Load from settings if provided
        if settings:
            settings.validate()
            endpoint = endpoint or settings.endpoint
            index_name = index_name or settings.index_name
            if not credential and settings.api_key:
                credential = settings.api_key
            azure_ai_project_endpoint = azure_ai_project_endpoint or settings.azure_ai_project_endpoint
            azure_openai_resource_url = azure_openai_resource_url or settings.azure_openai_resource_url
            model_deployment_name = model_deployment_name or settings.model_deployment_name
            azure_openai_api_key = azure_openai_api_key or settings.azure_openai_api_key

        # Validate required parameters
        if not endpoint:
            raise ValueError("endpoint is required")
        if not index_name:
            raise ValueError("index_name is required")
        if not credential:
            raise ValueError("credential is required")

        # Convert string credential to AzureKeyCredential
        if isinstance(credential, str):
            credential = AzureKeyCredential(credential)

        self.endpoint = endpoint
        self.index_name = index_name
        self.credential = credential
        self.mode = mode
        self.top_k = top_k
        self.semantic_configuration_name = semantic_configuration_name
        self.vector_field_name = vector_field_name
        self.embedding_function = embedding_function
        self.context_prompt = context_prompt or self._DEFAULT_SEARCH_CONTEXT_PROMPT

        # Agentic mode parameters (Knowledge Base)
        # azure_openai_resource_url: The actual Azure OpenAI endpoint for model calls
        # azure_openai_endpoint (deprecated): Fall back to this if resource_url not provided
        self.azure_openai_resource_url = azure_openai_resource_url or azure_openai_endpoint

        self.azure_openai_deployment_name = model_deployment_name or azure_openai_deployment_name
        # If model_name not provided, default to deployment name for backwards compatibility
        self.model_name = model_name or self.azure_openai_deployment_name
        self.knowledge_base_name = knowledge_base_name
        self.retrieval_instructions = retrieval_instructions
        self.azure_openai_api_key = azure_openai_api_key
        self.azure_ai_project_endpoint = azure_ai_project_endpoint

        # Auto-discover vector field if not specified
        self._auto_discovered_vector_field = False
        self._use_vectorizable_query = False  # Will be set to True if server-side vectorization detected
        if not vector_field_name and mode == "semantic":
            # Attempt to auto-discover vector field from index schema
            # This will be done lazily on first search to avoid blocking initialization
            pass

        # Validation
        if vector_field_name and not embedding_function:
            raise ValueError("embedding_function is required when vector_field_name is specified")

        if mode == "agentic":
            if not _agentic_retrieval_available:
                raise ImportError(
                    "Agentic retrieval requires azure-search-documents >= 11.7.0b1 with Knowledge Base support. "
                    "Please upgrade: pip install azure-search-documents>=11.7.0b1"
                )
            if not self.azure_openai_resource_url:
                raise ValueError(
                    "azure_openai_resource_url (or deprecated azure_openai_endpoint) is required for agentic mode. "
                    "This should be your Azure OpenAI endpoint (e.g., 'https://myresource.openai.azure.com')"
                )
            if not self.azure_openai_deployment_name:
                raise ValueError(
                    "model_deployment_name (or deprecated azure_openai_deployment_name) is required for agentic mode"
                )
            if not knowledge_base_name:
                raise ValueError("knowledge_base_name is required for agentic mode")

        # Create search client for semantic mode
        self._search_client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
        )

        # Create index client and retrieval client for agentic mode (Knowledge Base)
        self._index_client: SearchIndexClient | None = None
        self._retrieval_client: KnowledgeBaseRetrievalClient | None = None
        if mode == "agentic":
            self._index_client = SearchIndexClient(
                endpoint=endpoint,
                credential=credential,
            )
            # Retrieval client will be created after Knowledge Base initialization

        self._knowledge_base_initialized = False

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit - cleanup clients.

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
        """
        # Close retrieval client if it was created
        if self._retrieval_client is not None:
            await self._retrieval_client.close()
            self._retrieval_client = None

    @override
    async def invoking(
        self,
        messages: ChatMessage | MutableSequence[ChatMessage],
        **kwargs: Any,
    ) -> Context:
        """Retrieve relevant context from Azure AI Search before model invocation.

        Args:
            messages: User messages to use for context retrieval.
            **kwargs: Additional arguments (unused).

        Returns:
            Context object with retrieved documents as messages.
        """
        # Convert to list and filter to USER/ASSISTANT messages with text only
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)

        filtered_messages = [
            msg
            for msg in messages_list
            if msg and msg.text and msg.text.strip() and msg.role in [Role.USER, Role.ASSISTANT]
        ]

        if not filtered_messages:
            return Context()

        # Perform search based on mode
        if self.mode == "semantic":
            # Semantic mode: flatten messages to single query
            query = "\n".join(msg.text for msg in filtered_messages)
            search_results = await self._semantic_search(query)
        else:  # agentic
            # Agentic mode: pass last 10 messages as conversation history
            recent_messages = filtered_messages[-10:]
            search_results = await self._agentic_search(recent_messages)

        # Format results as context
        if not search_results:
            return Context()

        context_text = f"{self.context_prompt}\n\n{search_results}"

        return Context(messages=[ChatMessage(role="system", text=context_text)])

    def _find_vector_fields(self, index: Any) -> list[str]:
        """Find all fields that can store vectors (have dimensions defined).

        Args:
            index: SearchIndex object from Azure Search.

        Returns:
            List of vector field names.
        """
        return [
            field.name
            for field in index.fields
            if field.vector_search_dimensions is not None and field.vector_search_dimensions > 0
        ]

    def _find_vectorizable_fields(self, index: Any, vector_fields: list[str]) -> list[str]:
        """Find vector fields that have auto-vectorization configured.

        These are fields that have a vectorizer in their profile, meaning the index
        can automatically vectorize text queries without needing a client-side embedding function.

        Args:
            index: SearchIndex object from Azure Search.
            vector_fields: List of vector field names.

        Returns:
            List of vectorizable field names (subset of vector_fields).
        """
        vectorizable_fields: list[str] = []

        # Check if index has vector search configuration
        if not index.vector_search or not index.vector_search.profiles:
            return vectorizable_fields

        # For each vector field, check if it has a vectorizer configured
        for field in index.fields:
            if field.name in vector_fields and field.vector_search_profile_name:
                # Find the profile for this field
                profile = next(
                    (p for p in index.vector_search.profiles if p.name == field.vector_search_profile_name), None
                )

                if profile and hasattr(profile, "vectorizer_name") and profile.vectorizer_name:
                    # This field has server-side vectorization configured
                    vectorizable_fields.append(field.name)

        return vectorizable_fields

    async def _auto_discover_vector_field(self) -> None:
        """Auto-discover vector field from index schema.

        Attempts to find vector fields in the index and detect which have server-side
        vectorization configured. Prioritizes vectorizable fields (which can auto-embed text)
        over regular vector fields (which require client-side embedding).
        """
        if self._auto_discovered_vector_field or self.vector_field_name:
            return  # Already discovered or manually specified

        try:
            # Need index client to get schema
            if not self._index_client:
                from azure.search.documents.indexes.aio import SearchIndexClient

                index_client = SearchIndexClient(endpoint=self.endpoint, credential=self.credential)
            else:
                index_client = self._index_client

            # Get index schema
            index = await index_client.get_index(self.index_name)

            # Step 1: Find all vector fields
            vector_fields = self._find_vector_fields(index)

            if not vector_fields:
                # No vector fields found - keyword search only
                import logging

                logging.info(f"No vector fields found in index '{self.index_name}'. Using keyword-only search.")
                self._auto_discovered_vector_field = True
                if not self._index_client:
                    await index_client.close()
                return

            # Step 2: Find which vector fields have server-side vectorization
            vectorizable_fields = self._find_vectorizable_fields(index, vector_fields)

            # Step 3: Decide which field to use
            if vectorizable_fields:
                # Prefer vectorizable fields (server-side embedding)
                if len(vectorizable_fields) == 1:
                    self.vector_field_name = vectorizable_fields[0]
                    self._auto_discovered_vector_field = True
                    self._use_vectorizable_query = True  # Use VectorizableTextQuery
                    import logging

                    logging.info(
                        f"Auto-discovered vectorizable field '{self.vector_field_name}' "
                        f"with server-side vectorization. No embedding_function needed."
                    )
                else:
                    # Multiple vectorizable fields
                    import logging

                    logging.warning(
                        f"Multiple vectorizable fields found: {vectorizable_fields}. "
                        f"Please specify vector_field_name explicitly. Using keyword-only search."
                    )
            elif len(vector_fields) == 1:
                # Single vector field without vectorizer - needs client-side embedding
                self.vector_field_name = vector_fields[0]
                self._auto_discovered_vector_field = True
                self._use_vectorizable_query = False

                if not self.embedding_function:
                    import logging

                    logging.warning(
                        f"Auto-discovered vector field '{self.vector_field_name}' without server-side vectorization. "
                        f"Provide embedding_function for vector search, or it will fall back to keyword-only search."
                    )
                    self.vector_field_name = None
            else:
                # Multiple vector fields without vectorizers
                import logging

                logging.warning(
                    f"Multiple vector fields found: {vector_fields}. "
                    f"Please specify vector_field_name explicitly. Using keyword-only search."
                )

            # Close index client if we created it
            if not self._index_client:
                await index_client.close()

        except Exception as e:
            # Log warning but continue with keyword search
            import logging

            logging.warning(f"Failed to auto-discover vector field: {e}. Using keyword-only search.")

        self._auto_discovered_vector_field = True  # Mark as attempted

    async def _semantic_search(self, query: str) -> str:
        """Perform semantic hybrid search with semantic ranking.

        This is the recommended mode for most use cases. It combines:
        - Vector search (if embedding_function provided)
        - Keyword search (BM25)
        - Semantic reranking (if semantic_configuration_name provided)

        Args:
            query: Search query text.

        Returns:
            Formatted search results as string.
        """
        # Auto-discover vector field if not already done
        await self._auto_discover_vector_field()

        vector_queries: list[VectorizableTextQuery | VectorizedQuery] = []

        # Build vector query based on server-side vectorization or client-side embedding
        if self.vector_field_name:
            # Use larger k for vector query when semantic reranker is enabled for better ranking quality
            vector_k = max(self.top_k, 50) if self.semantic_configuration_name else self.top_k

            if self._use_vectorizable_query:
                # Server-side vectorization: Index will auto-embed the text query
                vector_queries = [
                    VectorizableTextQuery(
                        text=query,
                        k_nearest_neighbors=vector_k,
                        fields=self.vector_field_name,
                    )
                ]
            elif self.embedding_function:
                # Client-side embedding: We provide the vector
                query_vector = await self.embedding_function(query)
                vector_queries = [
                    VectorizedQuery(
                        vector=query_vector,
                        k_nearest_neighbors=vector_k,
                        fields=self.vector_field_name,
                    )
                ]
            # else: vector_field_name is set but no vectorization available - skip vector search

        # Build search parameters
        search_params: dict[str, Any] = {
            "search_text": query,
            "top": self.top_k,
        }

        if vector_queries:
            search_params["vector_queries"] = vector_queries

        # Add semantic ranking if configured
        if self.semantic_configuration_name:
            search_params["query_type"] = QueryType.SEMANTIC
            search_params["semantic_configuration_name"] = self.semantic_configuration_name
            search_params["query_caption"] = QueryCaptionType.EXTRACTIVE

        # Execute search
        results = await self._search_client.search(**search_params)  # type: ignore[reportUnknownVariableType]

        # Format results with citations
        formatted_results: list[str] = []
        async for doc in results:  # type: ignore[reportUnknownVariableType]
            # Extract document ID for citation
            doc_id = doc.get("id") or doc.get("@search.id")  # type: ignore[reportUnknownVariableType]

            # Use full document chunks with citation
            doc_text: str = self._extract_document_text(doc, doc_id=doc_id)  # type: ignore[reportUnknownArgumentType]
            if doc_text:
                formatted_results.append(doc_text)  # type: ignore[reportUnknownArgumentType]

        return "\n\n".join(formatted_results)

    async def _ensure_knowledge_base(self) -> None:
        """Ensure Knowledge Base and knowledge source are created.

        This method is idempotent - it will only create resources if they don't exist.

        Note: Azure SDK uses KnowledgeAgent classes internally, but the feature
        is marketed as "Knowledge Bases" in Azure AI Search.
        """
        if self._knowledge_base_initialized or not self._index_client:
            return

        # Runtime validation for agentic mode parameters
        if not self.knowledge_base_name:
            raise ValueError("knowledge_base_name is required for agentic mode")
        if not self.azure_openai_resource_url:
            raise ValueError("azure_openai_resource_url is required for agentic mode")
        if not self.azure_openai_deployment_name:
            raise ValueError("model_deployment_name is required for agentic mode")

        knowledge_base_name = self.knowledge_base_name

        # Step 1: Create or get knowledge source
        knowledge_source_name = f"{self.index_name}-source"

        try:
            # Try to get existing knowledge source
            await self._index_client.get_knowledge_source(knowledge_source_name)
        except ResourceNotFoundError:
            # Create new knowledge source if it doesn't exist
            knowledge_source = SearchIndexKnowledgeSource(
                name=knowledge_source_name,
                description=f"Knowledge source for {self.index_name} search index",
                search_index_parameters=SearchIndexKnowledgeSourceParameters(
                    search_index_name=self.index_name,
                ),
            )
            await self._index_client.create_knowledge_source(knowledge_source)

        # Step 2: Create or update Knowledge Base
        # Always create/update to ensure configuration is current
        # Note: EXTRACTIVE_DATA mode returns raw chunks without synthesis
        # Model is still needed for query planning and multi-hop reasoning
        aoai_params = AzureOpenAIVectorizerParameters(
            resource_url=self.azure_openai_resource_url,
            deployment_name=self.azure_openai_deployment_name,
            model_name=self.model_name,
            api_key=self.azure_openai_api_key,
        )

        knowledge_base = KnowledgeBase(
            name=knowledge_base_name,
            description=f"Knowledge Base for multi-hop retrieval across {self.index_name}",
            knowledge_sources=[
                KnowledgeSourceReference(
                    name=knowledge_source_name,
                )
            ],
            models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=aoai_params)],
            output_mode=KnowledgeRetrievalOutputMode.EXTRACTIVE_DATA,
        )
        await self._index_client.create_or_update_knowledge_base(knowledge_base)

        self._knowledge_base_initialized = True

        # Create retrieval client now that Knowledge Base is initialized
        if _agentic_retrieval_available and self._retrieval_client is None:
            self._retrieval_client = KnowledgeBaseRetrievalClient(
                endpoint=self.endpoint,
                knowledge_base_name=knowledge_base_name,
                credential=self.credential,
            )

    async def _agentic_search(self, messages: list[ChatMessage]) -> str:
        """Perform agentic retrieval with multi-hop reasoning using Knowledge Bases.

        NOTE: This mode is significantly slower than semantic search and should
        only be used for complex queries requiring cross-document reasoning.

        This method uses Azure AI Search Knowledge Bases which:
        1. Analyze the query and plan sub-queries
        2. Retrieve relevant documents across multiple sources
        3. Perform multi-hop reasoning with an LLM
        4. Synthesize a comprehensive answer with references

        Args:
            messages: Conversation history (last 10 messages) to use for retrieval context.

        Returns:
            Synthesized answer from the Knowledge Base.
        """
        # Ensure Knowledge Base is initialized
        await self._ensure_knowledge_base()

        # Convert ChatMessage list to KnowledgeBase message format
        kb_messages = [
            KnowledgeBaseMessage(
                role=msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                content=[KnowledgeBaseMessageTextContent(text=msg.text)],
            )
            for msg in messages
            if msg.text
        ]

        retrieval_request = KnowledgeBaseRetrievalRequest(messages=kb_messages)

        # Use reusable retrieval client
        if not self._retrieval_client:
            raise RuntimeError("Retrieval client not initialized. Ensure Knowledge Base is set up correctly.")

        # Perform retrieval via Knowledge Base
        retrieval_result = await self._retrieval_client.retrieve(retrieval_request=retrieval_request)

        # Extract synthesized answer from response
        if retrieval_result.response and len(retrieval_result.response) > 0:
            # Get the assistant's response (last message)
            assistant_message = retrieval_result.response[-1]
            if assistant_message.content:
                # Combine all text content
                answer_parts: list[str] = []
                for content_item in assistant_message.content:
                    # Check if this is a text content item
                    if isinstance(content_item, KnowledgeBaseMessageTextContent) and content_item.text:
                        answer_parts.append(content_item.text)

                if answer_parts:
                    return "\n".join(answer_parts)

        # Fallback if no answer generated
        return "No results found from Knowledge Base."

    def _extract_document_text(self, doc: dict[str, Any], doc_id: str | None = None) -> str:
        """Extract readable text from a search document with optional citation.

        Args:
            doc: Search result document.
            doc_id: Optional document ID for citation.

        Returns:
            Formatted document text with citation if doc_id provided.
        """
        # Try common text field names
        text = ""
        for field in ["content", "text", "description", "body", "chunk"]:
            if doc.get(field):
                text = str(doc[field])
                break

        # Fallback: concatenate all string fields
        if not text:
            text_parts: list[str] = []
            for key, value in doc.items():
                if isinstance(value, str) and not key.startswith("@") and key != "id":
                    text_parts.append(f"{key}: {value}")
            text = " | ".join(text_parts) if text_parts else ""

        # Add citation if document ID provided
        if doc_id and text:
            return f"[Source: {doc_id}] {text}"
        return text
