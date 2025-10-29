# Copyright (c) Microsoft. All rights reserved.

"""Azure AI Search Context Provider for Agent Framework.

This module provides context providers for Azure AI Search integration with two modes:
- Semantic: Fast hybrid search (vector + keyword) with semantic ranker
- Agentic: Slower multi-hop reasoning using Knowledge Bases for complex queries

Use semantic mode for most cases. Use agentic mode only when you need multi-hop
reasoning across documents with Knowledge Bases.
"""

import sys
from collections.abc import MutableSequence
from typing import TYPE_CHECKING, Any, Literal, cast

from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    KnowledgeAgent,
    KnowledgeAgentAzureOpenAIModel,
    KnowledgeAgentOutputConfiguration,
    KnowledgeAgentOutputConfigurationModality,
    KnowledgeAgentRequestLimits,
    KnowledgeSourceReference,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
)
from azure.search.documents.models import (
    QueryCaptionType,
    QueryType,
    VectorizedQuery,
)

from agent_framework import ChatMessage, Context, ContextProvider

# Type checking imports for optional agentic mode dependencies
if TYPE_CHECKING:
    from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
    from azure.search.documents.agent.models import (
        KnowledgeAgentMessage,
        KnowledgeAgentMessageTextContent,
        KnowledgeAgentRetrievalRequest,
    )

# Runtime imports for agentic mode (optional dependency)
try:
    from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
    from azure.search.documents.agent.models import (
        KnowledgeAgentMessage,
        KnowledgeAgentMessageTextContent,
        KnowledgeAgentRetrievalRequest,
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


class AzureAISearchContextProvider(ContextProvider):
    """Azure AI Search Context Provider with hybrid search and semantic ranking.

    This provider retrieves relevant documents from Azure AI Search to provide context
    to the AI agent. It supports two modes:

    - **semantic** (default): Fast hybrid search combining vector and keyword search
      with semantic reranking. Suitable for most RAG use cases.
    - **agentic**: Slower multi-hop reasoning across documents using Knowledge Bases.
      Use only for complex queries requiring cross-document reasoning.

    Examples:
        Semantic hybrid search (recommended for most cases):

        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework_azure_ai import AzureAIAgentClient, AzureAISearchContextProvider
            from azure.identity.aio import DefaultAzureCredential

            # Create context provider with semantic hybrid search
            search_provider = AzureAISearchContextProvider(
                endpoint="https://mysearch.search.windows.net",
                index_name="my-index",
                credential=DefaultAzureCredential(),
                mode="semantic",  # Fast hybrid + semantic ranker (default)
            )

            # Use with agent
            async with (
                AzureAIAgentClient() as client,
                ChatAgent(
                    chat_client=client,
                    context_providers=[search_provider],
                ) as agent,
            ):
                response = await agent.run("What is in the documents?")

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

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        credential: AzureKeyCredential | AsyncTokenCredential,
        mode: Literal["semantic", "agentic"] = "semantic",
        top_k: int = 5,
        semantic_configuration_name: str | None = None,
        vector_field_name: str | None = None,
        embedding_function: Any | None = None,
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
            credential: Azure credential (API key or DefaultAzureCredential).
            mode: Search mode - "semantic" for hybrid search with semantic ranking (fast)
                or "agentic" for multi-hop reasoning (slower). Default: "semantic".
            top_k: Maximum number of documents to retrieve. Default: 5.
            semantic_configuration_name: Name of semantic configuration in the index.
                Required for semantic ranking. If None, uses index default.
            vector_field_name: Name of the vector field in the index for hybrid search.
                Required if using vector search. Default: None (keyword search only).
            embedding_function: Async function to generate embeddings for vector search.
                Signature: async def embed(text: str) -> list[float]
                Required if vector_field_name is specified.
            context_prompt: Custom prompt to prepend to retrieved context.
                Default: Uses DEFAULT_CONTEXT_PROMPT.
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
        self.endpoint = endpoint
        self.index_name = index_name
        self.credential = credential
        self.mode = mode
        self.top_k = top_k
        self.semantic_configuration_name = semantic_configuration_name
        self.vector_field_name = vector_field_name
        self.embedding_function = embedding_function
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT

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

        # Create index client for agentic mode (Knowledge Base)
        # Note: Retrieval client is created fresh for each query to avoid transport issues
        self._index_client: SearchIndexClient | None = None
        if mode == "agentic":
            self._index_client = SearchIndexClient(
                endpoint=endpoint,
                credential=credential,
            )

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
        """Async context manager exit - cleanup handled by client destructors.

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.

        Note:
            We don't explicitly close the Azure SDK clients here because doing so
            can cause "transport already closed" errors on subsequent uses within
            the same context. The clients will clean up their resources when they
            are garbage collected.
        """
        pass

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
        # Extract query from messages
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)
        query = "\n".join(msg.text for msg in messages_list if msg and msg.text and msg.text.strip())

        if not query:
            return Context()

        # Perform search based on mode
        if self.mode == "semantic":
            search_results = await self._semantic_search(query)
        else:  # agentic
            search_results = await self._agentic_search(query)

        # Format results as context
        if not search_results:
            return Context()

        context_text = f"{self.context_prompt}\n\n{search_results}"

        return Context(messages=[ChatMessage(role="system", text=context_text)])

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
        vector_queries = []

        # Generate vector query if embedding function provided
        if self.embedding_function and self.vector_field_name:
            query_vector = await self.embedding_function(query)
            vector_queries = [
                VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=self.top_k,
                    fields=self.vector_field_name,
                )
            ]

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

        # Format results
        formatted_results: list[str] = []
        async for doc in results:  # type: ignore[reportUnknownVariableType]
            # Extract semantic captions if available
            caption: str | None = None
            if hasattr(doc, "@search.captions"):  # type: ignore[reportUnknownArgumentType]
                captions: Any = doc.get("@search.captions", [])  # type: ignore[reportUnknownVariableType]
                if captions:
                    caption = captions[0].text if hasattr(captions[0], "text") else str(captions[0])  # type: ignore[reportUnknownArgumentType, reportUnknownMemberType]

            # Build document text
            doc_text: str = caption if caption else self._extract_document_text(doc)  # type: ignore[reportUnknownArgumentType]
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

        # Type narrowing: these are validated as non-None in __init__ for agentic mode
        # Using cast() for type checker - actual validation happens in __init__
        knowledge_base_name = cast(str, self.knowledge_base_name)
        azure_openai_resource_url = cast(str, self.azure_openai_resource_url)
        azure_openai_deployment_name = cast(str, self.azure_openai_deployment_name)

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

        # Step 2: Create or get Knowledge Base (using KnowledgeAgent SDK class)
        try:
            # Try to get existing Knowledge Base
            await self._index_client.get_agent(knowledge_base_name)
        except ResourceNotFoundError:
            # Create new Knowledge Base if it doesn't exist
            aoai_params = AzureOpenAIVectorizerParameters(
                resource_url=azure_openai_resource_url,
                deployment_name=azure_openai_deployment_name,
                model_name=self.model_name,  # Underlying model name (e.g., "gpt-4o")
                api_key=self.azure_openai_api_key,  # Optional: for API key auth instead of managed identity
            )

            # Note: SDK uses KnowledgeAgent class name, but this represents a Knowledge Base
            knowledge_base = KnowledgeAgent(
                name=knowledge_base_name,
                description=f"Knowledge Base for multi-hop retrieval across {self.index_name}",
                models=[KnowledgeAgentAzureOpenAIModel(azure_open_ai_parameters=aoai_params)],
                knowledge_sources=[
                    KnowledgeSourceReference(
                        name=knowledge_source_name,
                        include_references=True,
                        include_reference_source_data=True,
                    )
                ],
                output_configuration=KnowledgeAgentOutputConfiguration(
                    modality=KnowledgeAgentOutputConfigurationModality.ANSWER_SYNTHESIS,
                    attempt_fast_path=True,
                ),
                request_limits=KnowledgeAgentRequestLimits(
                    max_output_size=10000,
                    max_runtime_in_seconds=60,
                ),
                retrieval_instructions=self.retrieval_instructions,
            )
            await self._index_client.create_agent(knowledge_base)

        self._knowledge_base_initialized = True

    async def _agentic_search(self, query: str) -> str:
        """Perform agentic retrieval with multi-hop reasoning using Knowledge Bases.

        NOTE: This mode is significantly slower than semantic search and should
        only be used for complex queries requiring cross-document reasoning.

        This method uses Azure AI Search Knowledge Bases which:
        1. Analyze the query and plan sub-queries
        2. Retrieve relevant documents across multiple sources
        3. Perform multi-hop reasoning with an LLM
        4. Synthesize a comprehensive answer with references

        Args:
            query: Search query text.

        Returns:
            Synthesized answer from the Knowledge Base.
        """
        # Ensure Knowledge Base is initialized
        await self._ensure_knowledge_base()

        # Type narrowing: knowledge_base_name is validated in __init__ for agentic mode
        # Using cast() for type checker - actual validation happens in __init__
        knowledge_base_name = cast(str, self.knowledge_base_name)

        # Create retrieval request with query as a conversation message
        # Note: SDK uses KnowledgeAgent class names, but represents Knowledge Base operations
        retrieval_request = KnowledgeAgentRetrievalRequest(
            messages=[
                KnowledgeAgentMessage(
                    role="user",
                    content=[KnowledgeAgentMessageTextContent(text=query)],
                )
            ]
        )

        # Create a fresh retrieval client for each query to avoid transport closure issues
        if not _agentic_retrieval_available:
            raise ImportError("KnowledgeAgentRetrievalClient not available")

        retrieval_client = KnowledgeAgentRetrievalClient(
            endpoint=self.endpoint,
            agent_name=knowledge_base_name,
            credential=self.credential,
        )

        try:
            # Perform retrieval via Knowledge Base
            retrieval_result = await retrieval_client.retrieve(retrieval_request=retrieval_request)
        finally:
            # Ensure client is closed after use
            await retrieval_client.close()

        # Extract synthesized answer from response
        if retrieval_result.response and len(retrieval_result.response) > 0:
            # Get the assistant's response (last message)
            assistant_message = retrieval_result.response[-1]
            if assistant_message.content:
                # Combine all text content
                answer_parts: list[str] = []
                for content_item in assistant_message.content:
                    # Check if this is a text content item
                    if isinstance(content_item, KnowledgeAgentMessageTextContent) and content_item.text:
                        answer_parts.append(content_item.text)

                if answer_parts:
                    return "\n".join(answer_parts)

        # Fallback if no answer generated
        return "No results found from Knowledge Base."

    def _extract_document_text(self, doc: dict[str, Any]) -> str:
        """Extract readable text from a search document.

        Args:
            doc: Search result document.

        Returns:
            Formatted document text.
        """
        # Try common text field names
        for field in ["content", "text", "description", "body", "chunk"]:
            if doc.get(field):
                return str(doc[field])[:500]  # Limit to 500 chars

        # Fallback: concatenate all string fields
        text_parts: list[str] = []
        for key, value in doc.items():
            if isinstance(value, str) and not key.startswith("@") and key != "id":
                text_parts.append(f"{key}: {value}")

        return " | ".join(text_parts)[:500] if text_parts else ""
