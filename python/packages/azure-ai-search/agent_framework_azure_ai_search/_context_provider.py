# Copyright (c) Microsoft. All rights reserved.

"""New-pattern Azure AI Search context provider using BaseContextProvider.

This module provides ``AzureAISearchContextProvider``, built on the new
:class:`BaseContextProvider` hooks pattern.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypedDict

from agent_framework import AGENT_FRAMEWORK_USER_AGENT, Annotation, Content, Message, SupportsGetEmbeddings
from agent_framework._sessions import AgentSession, BaseContextProvider, SessionContext
from agent_framework._settings import SecretString, load_settings
from agent_framework.azure._entra_id_authentication import AzureCredentialTypes
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalMediumReasoningEffort,
    KnowledgeRetrievalMinimalReasoningEffort,
    KnowledgeRetrievalOutputMode,
    KnowledgeRetrievalReasoningEffort,
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

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun
    from azure.search.documents.knowledgebases.aio import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseMessage,
        KnowledgeBaseMessageImageContent,
        KnowledgeBaseMessageImageContentImage,
        KnowledgeBaseMessageTextContent,
        KnowledgeBaseReference,
        KnowledgeBaseRetrievalRequest,
        KnowledgeBaseRetrievalResponse,
        KnowledgeRetrievalIntent,
        KnowledgeRetrievalSemanticIntent,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalLowReasoningEffort as KBRetrievalLowReasoningEffort,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalMediumReasoningEffort as KBRetrievalMediumReasoningEffort,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalMinimalReasoningEffort as KBRetrievalMinimalReasoningEffort,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalOutputMode as KBRetrievalOutputMode,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalReasoningEffort as KBRetrievalReasoningEffort,
    )

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

# Runtime imports for agentic mode (optional dependency)
try:
    from azure.search.documents.knowledgebases.aio import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseMessage,
        KnowledgeBaseMessageImageContent,
        KnowledgeBaseMessageImageContentImage,
        KnowledgeBaseMessageTextContent,
        KnowledgeBaseReference,
        KnowledgeBaseRetrievalRequest,
        KnowledgeBaseRetrievalResponse,
        KnowledgeRetrievalIntent,
        KnowledgeRetrievalSemanticIntent,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalLowReasoningEffort as KBRetrievalLowReasoningEffort,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalMediumReasoningEffort as KBRetrievalMediumReasoningEffort,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalMinimalReasoningEffort as KBRetrievalMinimalReasoningEffort,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalOutputMode as KBRetrievalOutputMode,
    )
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalReasoningEffort as KBRetrievalReasoningEffort,
    )

    _agentic_retrieval_available = True
except ImportError:
    _agentic_retrieval_available = False

logger = logging.getLogger("agent_framework.azure_ai_search")

_DEFAULT_AGENTIC_MESSAGE_HISTORY_COUNT = 10


class AzureAISearchSettings(TypedDict, total=False):
    """Settings for Azure AI Search Context Provider with auto-loading from environment.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'AZURE_SEARCH_'.

    Keys:
        endpoint: Azure AI Search endpoint URL.
            Can be set via environment variable AZURE_SEARCH_ENDPOINT.
        index_name: Name of the search index.
            Can be set via environment variable AZURE_SEARCH_INDEX_NAME.
        knowledge_base_name: Name of an existing Knowledge Base (for agentic mode).
            Can be set via environment variable AZURE_SEARCH_KNOWLEDGE_BASE_NAME.
        api_key: API key for authentication (optional, use managed identity if not provided).
            Can be set via environment variable AZURE_SEARCH_API_KEY.
    """

    endpoint: str | None
    index_name: str | None
    knowledge_base_name: str | None
    api_key: SecretString | None


class AzureAISearchContextProvider(BaseContextProvider):
    """Azure AI Search context provider using the new BaseContextProvider hooks pattern.

    Retrieves relevant context from Azure AI Search using semantic or agentic search
    modes.
    """

    _DEFAULT_SEARCH_CONTEXT_PROMPT: ClassVar[str] = "Use the following context to answer the question:"
    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_ai_search"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        endpoint: str | None = None,
        index_name: str | None = None,
        api_key: str | AzureKeyCredential | None = None,
        credential: AzureCredentialTypes | None = None,
        *,
        mode: Literal["semantic", "agentic"] = "semantic",
        top_k: int = 5,
        semantic_configuration_name: str | None = None,
        vector_field_name: str | None = None,
        embedding_function: Callable[[str], Awaitable[list[float]]]
        | SupportsGetEmbeddings[str, list[float], Any]
        | None = None,
        context_prompt: str | None = None,
        azure_openai_resource_url: str | None = None,
        model_deployment_name: str | None = None,
        model_name: str | None = None,
        knowledge_base_name: str | None = None,
        retrieval_instructions: str | None = None,
        azure_openai_api_key: str | None = None,
        knowledge_base_output_mode: Literal["extractive_data", "answer_synthesis"] = "extractive_data",
        retrieval_reasoning_effort: Literal["minimal", "medium", "low"] = "minimal",
        agentic_message_history_count: int = _DEFAULT_AGENTIC_MESSAGE_HISTORY_COUNT,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize Azure AI Search Context Provider.

        Args:
            source_id: Unique identifier for this provider instance.
            endpoint: Azure AI Search endpoint URL.
            index_name: Name of the search index to query.
            api_key: API key for authentication.
            credential: Azure credential for managed identity authentication.
                Accepts a TokenCredential, AsyncTokenCredential, or a callable token provider.
            mode: Search mode - "semantic" or "agentic". Default: "semantic".
            top_k: Maximum number of documents to retrieve. Default: 5.
            semantic_configuration_name: Name of semantic configuration in the index.
            vector_field_name: Name of the vector field in the index.
            embedding_function: Async function to generate embeddings or a SupportsGetEmbeddings instance.
            context_prompt: Custom prompt to prepend to retrieved context.
            azure_openai_resource_url: Azure OpenAI resource URL for Knowledge Base.
            model_deployment_name: Model deployment name in Azure OpenAI.
            model_name: The underlying model name.
            knowledge_base_name: Name of an existing Knowledge Base to use.
            retrieval_instructions: Custom instructions for Knowledge Base retrieval.
            azure_openai_api_key: Azure OpenAI API key.
            knowledge_base_output_mode: Output mode for Knowledge Base retrieval.
            retrieval_reasoning_effort: Reasoning effort for Knowledge Base query planning.
            agentic_message_history_count: Number of recent messages for agentic mode.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(source_id)

        # Determine which fields are required based on mode
        required: list[str | tuple[str, ...]] = ["endpoint"]
        if mode == "semantic":
            required.append("index_name")
        elif mode == "agentic":
            required.append(("index_name", "knowledge_base_name"))

        # Load settings from environment/file
        settings = load_settings(
            AzureAISearchSettings,
            env_prefix="AZURE_SEARCH_",
            required_fields=required,
            endpoint=endpoint,
            index_name=index_name,
            knowledge_base_name=knowledge_base_name,
            api_key=api_key if isinstance(api_key, str) else None,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        if mode == "agentic" and settings.get("index_name") and not model_deployment_name:
            raise ValueError(
                "model_deployment_name is required for agentic mode when creating Knowledge Base from index."
            )

        resolved_credential: AzureKeyCredential | AsyncTokenCredential
        if credential:
            resolved_credential = credential  # type: ignore[assignment]
        elif isinstance(api_key, AzureKeyCredential):
            resolved_credential = api_key
        elif settings.get("api_key"):
            resolved_credential = AzureKeyCredential(settings["api_key"].get_secret_value())  # type: ignore[union-attr]
        else:
            raise ValueError(
                "Azure credential is required. Provide 'api_key' or 'credential' parameter "
                "or set 'AZURE_SEARCH_API_KEY' environment variable."
            )

        self.endpoint: str = settings["endpoint"]  # type: ignore[assignment]  # validated above
        self.index_name = settings.get("index_name")
        self.credential = resolved_credential
        self.mode = mode
        self.top_k = top_k
        self.semantic_configuration_name = semantic_configuration_name
        self.vector_field_name = vector_field_name
        self.embedding_function = embedding_function
        self.context_prompt = context_prompt or self._DEFAULT_SEARCH_CONTEXT_PROMPT

        self.azure_openai_resource_url = azure_openai_resource_url
        self.azure_openai_deployment_name = model_deployment_name
        self.model_name = model_name or model_deployment_name
        self.knowledge_base_name = settings.get("knowledge_base_name")
        self.retrieval_instructions = retrieval_instructions
        self.azure_openai_api_key = azure_openai_api_key
        self.knowledge_base_output_mode = knowledge_base_output_mode
        self.retrieval_reasoning_effort = retrieval_reasoning_effort
        self.agentic_message_history_count = agentic_message_history_count

        self._use_existing_knowledge_base = False
        if mode == "agentic":
            if settings.get("knowledge_base_name"):
                self._use_existing_knowledge_base = True
            else:
                self.knowledge_base_name = f"{settings.get('index_name', '')}-kb"

        self._auto_discovered_vector_field = False
        self._use_vectorizable_query = False

        if vector_field_name and not embedding_function:
            raise ValueError("embedding_function is required when vector_field_name is specified")

        if mode == "agentic":
            if not _agentic_retrieval_available:
                raise ImportError(
                    "Agentic retrieval requires azure-search-documents >= 11.7.0b1 with Knowledge Base support."
                )
            if not self._use_existing_knowledge_base and not self.azure_openai_resource_url:
                raise ValueError(
                    "azure_openai_resource_url is required for agentic mode when creating Knowledge Base from index."
                )

        self._search_client: SearchClient | None = None
        if self.index_name:
            self._search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.index_name,
                credential=self.credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )

        self._index_client: SearchIndexClient | None = None
        self._retrieval_client: KnowledgeBaseRetrievalClient | None = None
        if mode == "agentic":
            self._index_client = SearchIndexClient(
                endpoint=self.endpoint,
                credential=self.credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
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
        """Async context manager exit - cleanup clients."""
        await self.close()

    async def close(self) -> None:
        """Close all the open clients."""
        if self._retrieval_client is not None:
            await self._retrieval_client.close()
            self._retrieval_client = None
            self._knowledge_base_initialized = False
        if self._search_client is not None:
            await self._search_client.close()
            self._search_client = None
        if self._index_client is not None:
            await self._index_client.close()
            self._index_client = None

    # -- Hooks pattern ---------------------------------------------------------

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Retrieve relevant context from Azure AI Search and add to session context."""
        messages_list = list(context.input_messages)

        filtered_messages = [
            msg for msg in messages_list if msg and msg.text and msg.text.strip() and msg.role in ["user", "assistant"]
        ]
        if not filtered_messages:
            return

        if self.mode == "semantic":
            query = "\n".join(msg.text for msg in filtered_messages)
            result_messages = await self._semantic_search(query)
        else:
            recent_messages = filtered_messages[-self.agentic_message_history_count :]
            result_messages = await self._agentic_search(recent_messages)

        if not result_messages:
            return

        context.extend_messages(self.source_id, [Message(role="user", text=self.context_prompt), *result_messages])

    def _find_vector_fields(self, index: Any) -> list[str]:
        """Find all fields that can store vectors."""
        return [
            field.name
            for field in index.fields
            if field.vector_search_dimensions is not None and field.vector_search_dimensions > 0
        ]

    def _find_vectorizable_fields(self, index: Any, vector_fields: list[str]) -> list[str]:
        """Find vector fields that have auto-vectorization configured."""
        vectorizable_fields: list[str] = []
        if not index.vector_search or not index.vector_search.profiles:
            return vectorizable_fields
        for field in index.fields:
            if field.name in vector_fields and field.vector_search_profile_name:
                profile = next(
                    (p for p in index.vector_search.profiles if p.name == field.vector_search_profile_name), None
                )
                if profile and hasattr(profile, "vectorizer_name") and profile.vectorizer_name:
                    vectorizable_fields.append(field.name)
        return vectorizable_fields

    async def _auto_discover_vector_field(self) -> None:
        """Auto-discover vector field from index schema."""
        if self._auto_discovered_vector_field or self.vector_field_name:
            return

        try:
            if not self._index_client:
                self._index_client = SearchIndexClient(
                    endpoint=self.endpoint,
                    credential=self.credential,
                    user_agent=AGENT_FRAMEWORK_USER_AGENT,
                )
            if not self.index_name:
                logger.warning("Cannot auto-discover vector field: index_name is not set.")
                self._auto_discovered_vector_field = True
                return

            index = await self._index_client.get_index(self.index_name)
            vector_fields = self._find_vector_fields(index)
            if not vector_fields:
                logger.info(f"No vector fields found in index '{self.index_name}'. Using keyword-only search.")
                self._auto_discovered_vector_field = True
                return

            vectorizable_fields = self._find_vectorizable_fields(index, vector_fields)
            if vectorizable_fields:
                if len(vectorizable_fields) == 1:
                    self.vector_field_name = vectorizable_fields[0]
                    self._auto_discovered_vector_field = True
                    self._use_vectorizable_query = True
                    logger.info(
                        f"Auto-discovered vectorizable field '{self.vector_field_name}' with server-side vectorization."
                    )
                else:
                    logger.warning(
                        f"Multiple vectorizable fields found: {vectorizable_fields}. "
                        f"Please specify vector_field_name explicitly."
                    )
            elif len(vector_fields) == 1:
                self.vector_field_name = vector_fields[0]
                self._auto_discovered_vector_field = True
                self._use_vectorizable_query = False
                if not self.embedding_function:
                    logger.warning(
                        f"Auto-discovered vector field '{self.vector_field_name}' without server-side vectorization. "
                        f"Provide embedding_function for vector search."
                    )
                    self.vector_field_name = None
            else:
                logger.warning(
                    f"Multiple vector fields found: {vector_fields}. Please specify vector_field_name explicitly."
                )
        except Exception as e:
            logger.warning(f"Failed to auto-discover vector field: {e}. Using keyword-only search.")

        self._auto_discovered_vector_field = True

    async def _semantic_search(self, query: str) -> list[Message]:
        """Perform semantic hybrid search."""
        await self._auto_discover_vector_field()

        vector_queries: list[VectorizableTextQuery | VectorizedQuery] = []
        if self.vector_field_name:
            vector_k = max(self.top_k, 50) if self.semantic_configuration_name else self.top_k
            if self._use_vectorizable_query:
                vector_queries = [VectorizableTextQuery(text=query, k=vector_k, fields=self.vector_field_name)]
            elif self.embedding_function:
                if isinstance(self.embedding_function, SupportsGetEmbeddings):
                    embeddings = await self.embedding_function.get_embeddings([query])  # type: ignore[reportUnknownVariableType]
                    query_vector: list[float] = embeddings[0].vector  # type: ignore[reportUnknownVariableType]
                else:
                    query_vector = await self.embedding_function(query)
                vector_queries = [VectorizedQuery(vector=query_vector, k=vector_k, fields=self.vector_field_name)]

        search_params: dict[str, Any] = {"search_text": query, "top": self.top_k}
        if vector_queries:
            search_params["vector_queries"] = vector_queries
        if self.semantic_configuration_name:
            search_params["query_type"] = QueryType.SEMANTIC
            search_params["semantic_configuration_name"] = self.semantic_configuration_name
            search_params["query_caption"] = QueryCaptionType.EXTRACTIVE

        if not self._search_client:
            raise RuntimeError("Search client is not initialized.")
        results = await self._search_client.search(**search_params)  # type: ignore[reportUnknownVariableType]

        result_messages: list[Message] = []
        async for doc in results:  # type: ignore[reportUnknownVariableType]
            doc_id = doc.get("id") or doc.get("@search.id")  # type: ignore[reportUnknownVariableType]
            doc_text: str = self._extract_document_text(doc, doc_id=doc_id)  # type: ignore[reportUnknownArgumentType]
            if doc_text:
                result_messages.append(Message(role="user", text=doc_text))  # type: ignore[reportUnknownArgumentType]
        return result_messages

    async def _ensure_knowledge_base(self) -> None:
        """Ensure Knowledge Base and knowledge source are created or use existing KB."""
        if self._knowledge_base_initialized:
            return

        if not self.knowledge_base_name:
            raise ValueError("knowledge_base_name is required for agentic mode")

        knowledge_base_name = self.knowledge_base_name

        if self._use_existing_knowledge_base:
            if _agentic_retrieval_available and self._retrieval_client is None:
                self._retrieval_client = KnowledgeBaseRetrievalClient(
                    endpoint=self.endpoint,
                    knowledge_base_name=knowledge_base_name,
                    credential=self.credential,
                    user_agent=AGENT_FRAMEWORK_USER_AGENT,
                )
            self._knowledge_base_initialized = True
            return

        if not self._index_client:
            raise ValueError("Index client is required when creating Knowledge Base from index")
        if not self.azure_openai_resource_url:
            raise ValueError("azure_openai_resource_url is required when creating Knowledge Base from index")
        if not self.azure_openai_deployment_name:
            raise ValueError("model_deployment_name is required when creating Knowledge Base from index")
        if not self.index_name:
            raise ValueError("index_name is required when creating Knowledge Base from index")

        knowledge_source_name = f"{self.index_name}-source"
        try:
            await self._index_client.get_knowledge_source(knowledge_source_name)
        except ResourceNotFoundError:
            knowledge_source = SearchIndexKnowledgeSource(
                name=knowledge_source_name,
                description=f"Knowledge source for {self.index_name} search index",
                search_index_parameters=SearchIndexKnowledgeSourceParameters(
                    search_index_name=self.index_name,
                ),
            )
            await self._index_client.create_knowledge_source(knowledge_source)

        aoai_params = AzureOpenAIVectorizerParameters(
            resource_url=self.azure_openai_resource_url,
            deployment_name=self.azure_openai_deployment_name,
            model_name=self.model_name,
            api_key=self.azure_openai_api_key,
        )

        output_mode = (
            KnowledgeRetrievalOutputMode.EXTRACTIVE_DATA
            if self.knowledge_base_output_mode == "extractive_data"
            else KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS
        )
        reasoning_effort_map: dict[str, KnowledgeRetrievalReasoningEffort] = {
            "minimal": KnowledgeRetrievalMinimalReasoningEffort(),
            "medium": KnowledgeRetrievalMediumReasoningEffort(),
            "low": KnowledgeRetrievalLowReasoningEffort(),
        }
        reasoning_effort = reasoning_effort_map[self.retrieval_reasoning_effort]

        knowledge_base = KnowledgeBase(
            name=knowledge_base_name,
            description=f"Knowledge Base for multi-hop retrieval across {self.index_name}",
            knowledge_sources=[KnowledgeSourceReference(name=knowledge_source_name)],
            models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=aoai_params)],
            output_mode=output_mode,
            retrieval_reasoning_effort=reasoning_effort,
        )
        await self._index_client.create_or_update_knowledge_base(knowledge_base)
        self._knowledge_base_initialized = True

        if _agentic_retrieval_available and self._retrieval_client is None:
            self._retrieval_client = KnowledgeBaseRetrievalClient(
                endpoint=self.endpoint,
                knowledge_base_name=knowledge_base_name,
                credential=self.credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )

    async def _agentic_search(self, messages: list[Message]) -> list[Message]:
        """Perform agentic retrieval with multi-hop reasoning."""
        await self._ensure_knowledge_base()

        reasoning_effort_map: dict[str, KBRetrievalReasoningEffort] = {
            "minimal": KBRetrievalMinimalReasoningEffort(),
            "medium": KBRetrievalMediumReasoningEffort(),
            "low": KBRetrievalLowReasoningEffort(),
        }
        reasoning_effort = reasoning_effort_map[self.retrieval_reasoning_effort]

        output_mode = (
            KBRetrievalOutputMode.EXTRACTIVE_DATA
            if self.knowledge_base_output_mode == "extractive_data"
            else KBRetrievalOutputMode.ANSWER_SYNTHESIS
        )

        if self.retrieval_reasoning_effort == "minimal":
            query = "\n".join(msg.text for msg in messages if msg.text)
            intents: list[KnowledgeRetrievalIntent] = [KnowledgeRetrievalSemanticIntent(search=query)]
            retrieval_request = KnowledgeBaseRetrievalRequest(
                intents=intents,
                retrieval_reasoning_effort=reasoning_effort,
                output_mode=output_mode,
                include_activity=True,
            )
        else:
            kb_messages = self._prepare_messages_for_kb_search(messages)
            retrieval_request = KnowledgeBaseRetrievalRequest(
                messages=kb_messages,
                retrieval_reasoning_effort=reasoning_effort,
                output_mode=output_mode,
                include_activity=True,
            )

        if not self._retrieval_client:
            raise RuntimeError("Retrieval client not initialized.")
        retrieval_result = await self._retrieval_client.retrieve(retrieval_request=retrieval_request)

        return self._parse_messages_from_kb_response(retrieval_result)

    @staticmethod
    def _prepare_messages_for_kb_search(messages: list[Message]) -> list[KnowledgeBaseMessage]:
        """Convert framework Messages to KnowledgeBaseMessages for agentic retrieval.

        Handles text and image content types. Other content types (function calls,
        errors, etc.) are skipped.

        Args:
            messages: Framework messages to convert.

        Returns:
            List of KnowledgeBaseMessage objects suitable for retrieval requests.
        """
        kb_messages: list[KnowledgeBaseMessage] = []
        for msg in messages:
            kb_content: list[KnowledgeBaseMessageTextContent | KnowledgeBaseMessageImageContent] = []
            if msg.contents:
                for content in msg.contents:
                    match content.type:
                        case "text" if content.text:
                            kb_content.append(KnowledgeBaseMessageTextContent(text=content.text))
                        case "uri" | "data" if (
                            content.uri and content.media_type and content.media_type.startswith("image/")
                        ):
                            kb_content.append(
                                KnowledgeBaseMessageImageContent(
                                    image=KnowledgeBaseMessageImageContentImage(url=content.uri),
                                )
                            )
            elif msg.text:
                kb_content.append(KnowledgeBaseMessageTextContent(text=msg.text))
            if kb_content:
                kb_messages.append(KnowledgeBaseMessage(role=msg.role, content=kb_content))  # type: ignore[arg-type]
        return kb_messages

    @staticmethod
    def _parse_references_to_annotations(references: list[KnowledgeBaseReference] | None) -> list[Annotation]:
        """Convert Knowledge Base references to framework Annotations.

        Captures all available fields from each reference subtype: URLs, doc keys,
        reranker scores, source data, and the raw reference object itself.

        Args:
            references: The references from a Knowledge Base retrieval response.

        Returns:
            List of citation Annotations.
        """
        if not references:
            return []
        annotations: list[Annotation] = []
        for ref in references:
            url: str | None = None
            for attr in ("url", "blob_url", "doc_url", "web_url"):
                url = getattr(ref, attr, None)
                if url:
                    break

            annotation = Annotation(
                type="citation",
                url=url or "",
                title=getattr(ref, "title", None) or ref.id,
            )

            extra: dict[str, Any] = {
                "reference_id": ref.id,
                "reference_type": getattr(ref, "type", None),
                "activity_source": ref.activity_source,
            }
            if ref.reranker_score is not None:
                extra["reranker_score"] = ref.reranker_score
            if ref.source_data:
                extra["source_data"] = ref.source_data
            doc_key = getattr(ref, "doc_key", None)
            if doc_key:
                extra["doc_key"] = doc_key
            if ref.additional_properties:
                extra["sdk_additional_properties"] = ref.additional_properties
            sensitivity_info = getattr(ref, "search_sensitivity_label_info", None)
            if sensitivity_info:
                extra["sensitivity_label"] = {
                    "display_name": sensitivity_info.display_name,
                    "sensitivity_label_id": sensitivity_info.sensitivity_label_id,
                    "is_encrypted": sensitivity_info.is_encrypted,
                }

            annotation["additional_properties"] = extra
            annotation["raw_representation"] = ref
            annotations.append(annotation)
        return annotations

    @staticmethod
    def _parse_messages_from_kb_response(retrieval_result: KnowledgeBaseRetrievalResponse) -> list[Message]:
        """Convert a Knowledge Base retrieval response to framework Messages.

        Each KnowledgeBaseMessage becomes a Message. References from the response
        are converted to Annotations and attached to content items.

        Args:
            retrieval_result: The full retrieval response including messages and references.

        Returns:
            List of Messages, or a single default Message if no results found.
        """
        if not retrieval_result.response:
            return [Message(role="assistant", text="No results found from Knowledge Base.")]

        annotations = AzureAISearchContextProvider._parse_references_to_annotations(retrieval_result.references)

        result_messages: list[Message] = []
        for kb_msg in retrieval_result.response:
            if not kb_msg.content:
                continue
            contents: list[Content] = []
            for item in kb_msg.content:
                if isinstance(item, KnowledgeBaseMessageTextContent) and item.text:
                    contents.append(Content.from_text(item.text))
                elif isinstance(item, KnowledgeBaseMessageImageContent) and item.image and item.image.url:
                    contents.append(Content.from_uri(uri=item.image.url, media_type="image/png"))
            if contents:
                if annotations:
                    for c in contents:
                        c.annotations = annotations
                result_messages.append(Message(role=kb_msg.role or "assistant", contents=contents))

        if not result_messages:
            return [Message(role="assistant", text="No results found from Knowledge Base.")]
        return result_messages

    def _extract_document_text(self, doc: dict[str, Any], doc_id: str | None = None) -> str:
        """Extract readable text from a search document with optional citation."""
        text = ""
        for field in ["content", "text", "description", "body", "chunk"]:
            if doc.get(field):
                text = str(doc[field])
                break
        if not text:
            text_parts: list[str] = []
            for key, value in doc.items():
                if isinstance(value, str) and not key.startswith("@") and key != "id":
                    text_parts.append(f"{key}: {value}")
            text = " | ".join(text_parts) if text_parts else ""
        if doc_id and text:
            return f"[Source: {doc_id}] {text}"
        return text


__all__ = ["AzureAISearchContextProvider"]
