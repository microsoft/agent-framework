# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB context provider.

This module provides ``AzureCosmosContextProvider``, built on the new
:class:`BaseContextProvider` hooks pattern.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict, cast

from agent_framework import AGENT_FRAMEWORK_USER_AGENT, Message, SupportsGetEmbeddings
from agent_framework._sessions import AgentSession, BaseContextProvider, SessionContext
from agent_framework._settings import SecretString, load_settings
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun


logger = logging.getLogger(__name__)

AzureCredentialTypes = TokenCredential | AsyncTokenCredential


class CosmosContextSearchMode(str, Enum):
    """Supported Azure Cosmos DB retrieval modes for the context provider."""

    VECTOR = "vector"
    FULL_TEXT = "full_text"
    HYBRID = "hybrid"


class AzureCosmosContextSettings(TypedDict, total=False):
    """Settings for AzureCosmosContextProvider resolved from args and environment."""

    endpoint: str | None
    database_name: str | None
    container_name: str | None
    key: SecretString | None
    top_k: int | None
    scan_limit: int | None


class AzureCosmosContextProvider(BaseContextProvider):
    """Azure Cosmos DB-backed context provider using BaseContextProvider hooks."""

    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_cosmos_context"
    DEFAULT_CONTEXT_PROMPT: ClassVar[str] = "Use the following context to answer the question:"
    _DEFAULT_RESULT_LIMIT: ClassVar[int] = 5
    _DEFAULT_SCAN_LIMIT: ClassVar[int] = 25
    _DEFAULT_SEARCH_MODE: ClassVar[CosmosContextSearchMode] = CosmosContextSearchMode.FULL_TEXT
    _DEFAULT_RRF_WEIGHTS: ClassVar[tuple[float, float]] = (1.0, 1.0)
    _WRITEBACK_DOCUMENT_TYPE: ClassVar[str] = "agent_framework_context_provider_message"
    _TEXT_SCORE_FIELD: ClassVar[str] = "__agent_framework_text_score"
    _VECTOR_SCORE_FIELD: ClassVar[str] = "__agent_framework_vector_score"
    _COMBINED_SCORE_FIELD: ClassVar[str] = "__agent_framework_combined_score"
    _VALID_FIELD_NAME_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    _RETRIEVAL_ROLES: ClassVar[frozenset[str]] = frozenset({"user", "assistant"})

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: str | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        container_client: ContainerProxy | None = None,
        top_k: int | None = None,
        scan_limit: int | None = None,
        default_search_mode: CosmosContextSearchMode = _DEFAULT_SEARCH_MODE,
        id_field_name: str = "id",
        content_field_names: Sequence[str] = ("content", "text"),
        title_field_name: str | None = "title",
        url_field_name: str | None = "url",
        message_field_name: str | None = "message",
        metadata_field_name: str | None = "metadata",
        vector_field_name: str | None = None,
        embedding_function: Callable[[str], Awaitable[list[float]]]
        | SupportsGetEmbeddings[str, list[float], Any]
        | None = None,
        partition_key: str | None = None,
        context_prompt: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the Azure Cosmos DB context provider.

        Args:
            source_id: Unique identifier for this provider instance.
            endpoint: Cosmos DB account endpoint.
                Can be set via ``AZURE_COSMOS_ENDPOINT``.
            database_name: Cosmos DB database name.
                Can be set via ``AZURE_COSMOS_DATABASE_NAME``.
            container_name: Cosmos DB container name.
                Can be set via ``AZURE_COSMOS_CONTAINER_NAME``.
            credential: Credential to authenticate with Cosmos DB.
                Supports key string and Azure credential objects.
                Can be set via ``AZURE_COSMOS_KEY`` when omitted.
            cosmos_client: Pre-created Cosmos async client.
            container_client: Pre-created Cosmos container client for fixed-container usage.
            top_k: Maximum number of context messages to add to the session.
                Can be set via ``AZURE_COSMOS_TOP_K``. This acts as the default
                final result count for normal runs and can be overridden per run
                in ``before_run(...)``.
            scan_limit: Maximum number of candidate Cosmos items to scan per invocation.
                Can be set via ``AZURE_COSMOS_SCAN_LIMIT``. This acts as the default
                candidate scan size for normal runs and can be overridden per run
                in ``before_run(...)``.
            default_search_mode: Default retrieval mode to use when ``before_run``
                does not supply a per-run override through ``search_mode``.
            id_field_name: Field name containing the document identifier.
            content_field_names: Ordered field names to inspect for text content.
            title_field_name: Field name containing the document title.
            url_field_name: Field name containing the source URL.
            message_field_name: Field name containing a serialized Agent Framework message payload.
            metadata_field_name: Field name containing raw metadata to retain on the message.
            vector_field_name: Field name containing vectors for future vector and hybrid retrieval.
            embedding_function: Embedding generator for future vector and hybrid retrieval.
            partition_key: Optional Cosmos partition key value to scope retrieval.
                This acts as the default retrieval scope for normal runs and can be
                overridden per run in ``before_run(...)``.
            context_prompt: Prompt prefix to use when shaping retrieved context.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(source_id)

        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self.top_k = self._validate_positive_int(top_k, default=self._DEFAULT_RESULT_LIMIT, name="top_k")
        self.scan_limit = self._validate_positive_int(scan_limit, default=self._DEFAULT_SCAN_LIMIT, name="scan_limit")
        self.default_search_mode = self._validate_search_mode(
            default_search_mode,
            parameter_name="default_search_mode",
        )
        self.id_field_name = self._validate_field_name(id_field_name, parameter_name="id_field_name")
        self.content_field_names = self._validate_required_field_names(
            content_field_names,
            parameter_name="content_field_names",
        )
        self.title_field_name = self._validate_optional_field_name(title_field_name, parameter_name="title_field_name")
        self.url_field_name = self._validate_optional_field_name(url_field_name, parameter_name="url_field_name")
        self.message_field_name = self._validate_optional_field_name(
            message_field_name,
            parameter_name="message_field_name",
        )
        self.metadata_field_name = self._validate_optional_field_name(
            metadata_field_name,
            parameter_name="metadata_field_name",
        )
        self.vector_field_name = self._validate_optional_field_name(
            vector_field_name,
            parameter_name="vector_field_name",
        )
        self.embedding_function = embedding_function
        self.partition_key = partition_key

        self._cosmos_client: CosmosClient | None = cosmos_client
        self._container_proxy: ContainerProxy | None = container_client
        self._database_client: DatabaseProxy | None = None
        self._owns_client = False

        if self._container_proxy is not None:
            self.database_name = database_name or ""
            self.container_name = container_name or ""
            return

        required_fields: list[str] = ["database_name", "container_name"]
        if cosmos_client is None:
            required_fields.append("endpoint")
            if credential is None:
                required_fields.append("key")

        settings = load_settings(
            AzureCosmosContextSettings,
            env_prefix="AZURE_COSMOS_",
            required_fields=required_fields,
            endpoint=endpoint,
            database_name=database_name,
            container_name=container_name,
            key=credential if isinstance(credential, str) else None,
            top_k=top_k,
            scan_limit=scan_limit,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.database_name = cast(str, settings["database_name"])
        self.container_name = cast(str, settings["container_name"])
        self.top_k = self._validate_positive_int(settings.get("top_k"), default=self.top_k, name="top_k")
        self.scan_limit = self._validate_positive_int(
            settings.get("scan_limit"), default=self.scan_limit, name="scan_limit"
        )

        if self._cosmos_client is None:
            self._cosmos_client = CosmosClient(
                url=settings["endpoint"],  # type: ignore[arg-type]
                credential=credential or settings["key"].get_secret_value(),  # type: ignore[arg-type,union-attr]
                user_agent_suffix=AGENT_FRAMEWORK_USER_AGENT,
            )
            self._owns_client = True

        self._database_client = self._cosmos_client.get_database_client(self.database_name)

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
        search_mode: CosmosContextSearchMode | None = None,
        weights: Sequence[float] | None = None,
        top_k: int | None = None,
        scan_limit: int | None = None,
        partition_key: str | None = None,
    ) -> None:
        """Retrieve relevant context from Cosmos DB before model invocation.

        Args:
            agent: The agent currently being run.
            session: The active agent session.
            context: The session context for the current run.
            state: Mutable per-provider run state storage.
            search_mode: Optional per-run override for the retrieval mode.
                When omitted, ``default_search_mode`` configured on the provider
                instance is used.
            weights: Optional per-run hybrid RRF weights. Only used for hybrid runs.
                When omitted for hybrid search, the provider defaults are used.
            top_k: Optional per-run override for the number of context messages to
                inject into the session. When omitted, the provider's configured
                ``top_k`` value is used.
            scan_limit: Optional per-run override for the number of Cosmos items to
                scan before final selection. When omitted, the provider's configured
                ``scan_limit`` value is used.
            partition_key: Optional per-run override for the Cosmos partition key
                scope used during retrieval. When omitted, the provider's configured
                ``partition_key`` value is used.
        """
        filtered_messages = [
            msg
            for msg in context.input_messages
            if msg and msg.text and msg.text.strip() and msg.role in self._RETRIEVAL_ROLES
        ]
        if not filtered_messages:
            return

        query_text = self._build_query_text(filtered_messages).strip()
        if not query_text:
            return

        resolved_search_mode = (
            self.default_search_mode
            if search_mode is None
            else self._validate_search_mode(
                search_mode,
                parameter_name="search_mode",
            )
        )
        resolved_weights = self._resolve_weights_for_run(resolved_search_mode, weights)
        self._validate_search_configuration(resolved_search_mode, resolved_weights)
        resolved_top_k = self._validate_positive_int(top_k, default=self.top_k, name="top_k")
        resolved_scan_limit = self._validate_positive_int(scan_limit, default=self.scan_limit, name="scan_limit")
        resolved_partition_key = self.partition_key if partition_key is None else partition_key

        query_terms = self._tokenize_query_text(query_text)
        if (
            resolved_search_mode
            in {
                CosmosContextSearchMode.FULL_TEXT,
                CosmosContextSearchMode.HYBRID,
            }
            and not query_terms
        ):
            logger.debug(
                "Skipping Cosmos DB context lookup for provider '%s' because search mode '%s' requires text terms.",
                self.source_id,
                resolved_search_mode.value,
            )
            return

        state["query_text"] = query_text

        candidate_items = await self._get_candidate_items_for_mode(
            query_text=query_text,
            query_terms=query_terms,
            search_mode=resolved_search_mode,
            weights=resolved_weights,
            scan_limit=resolved_scan_limit,
            partition_key=resolved_partition_key,
        )
        result_messages = self._select_context_messages(
            candidate_items,
            query_terms=query_terms,
            top_k=resolved_top_k,
        )

        if not result_messages:
            logger.debug(
                "No Cosmos DB context results found for provider '%s' using mode '%s'.",
                self.source_id,
                resolved_search_mode.value,
            )
            return

        context.extend_messages(
            self.source_id,
            [Message(role="user", contents=[self.context_prompt]), *result_messages],
        )

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Persist input and response messages to Cosmos after each run."""
        messages_to_store: list[Message] = list(context.input_messages)
        if context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)

        writeback_messages = [
            message
            for message in messages_to_store
            if message.role in {"user", "assistant", "system"} and message.text and message.text.strip()
        ]
        if not writeback_messages:
            return

        await self._save_writeback_messages(context.session_id, writeback_messages)

    async def close(self) -> None:
        """Close the underlying Cosmos client when this provider owns it."""
        if self._owns_client and self._cosmos_client is not None:
            await self._cosmos_client.close()

    async def __aenter__(self) -> AzureCosmosContextProvider:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        try:
            await self.close()
        except Exception:
            if exc_type is None:
                raise

    async def _ensure_container_proxy(self) -> ContainerProxy:
        """Get the Cosmos DB container used by the context provider."""
        if self._container_proxy is not None:
            return self._container_proxy
        if self._database_client is None:
            raise RuntimeError("Cosmos database client is not initialized.")

        container = self._database_client.get_container_client(self.container_name)
        try:
            await container.read()
        except CosmosResourceNotFoundError as exc:
            raise RuntimeError(
                f"Cosmos DB container '{self.container_name}' was not found in database "
                f"'{self.database_name}'. The context provider expects an existing container."
            ) from exc

        self._container_proxy = container
        return container

    async def _save_writeback_messages(self, session_id: str | None, messages: Sequence[Message]) -> None:
        """Persist input/response messages back into the configured knowledge container."""
        if not messages:
            return

        container = await self._ensure_container_proxy()
        session_key = self._session_partition_key(session_id)
        base_sort_key = time.time_ns()

        for index, message in enumerate(messages):
            await container.upsert_item(self._build_writeback_document(message, session_key, base_sort_key + index))

    def _build_writeback_document(self, message: Message, session_key: str, sort_key: int) -> dict[str, Any]:
        """Build a Cosmos document for context-provider writeback."""
        role_value = message.role.value if hasattr(message.role, "value") else str(message.role)
        document: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "document_type": self._WRITEBACK_DOCUMENT_TYPE,
            "session_id": session_key,
            "sort_key": sort_key,
            "source_id": self.source_id,
            "role": role_value,
            "content": message.text,
            "message": message.to_dict(),
        }
        if message.author_name:
            document["author_name"] = message.author_name
        return document

    async def _execute_query(
        self,
        *,
        query: str,
        scan_limit: int,
        partition_key: str | None,
        parameters: list[dict[str, object]] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cosmos query with shared query settings."""
        container = await self._ensure_container_proxy()
        query_kwargs: dict[str, Any] = {
            "query": query,
            "max_item_count": scan_limit,
        }
        if parameters is not None:
            query_kwargs["parameters"] = parameters
        if partition_key is not None:
            query_kwargs["partition_key"] = partition_key

        return [item async for item in container.query_items(**query_kwargs)]

    async def _get_candidate_items_for_mode(
        self,
        *,
        query_text: str,
        query_terms: Sequence[str],
        search_mode: CosmosContextSearchMode,
        weights: Sequence[float],
        scan_limit: int,
        partition_key: str | None,
    ) -> list[dict[str, Any]]:
        """Route retrieval to the configured Cosmos search mode."""
        if search_mode is CosmosContextSearchMode.FULL_TEXT:
            return await self._get_full_text_candidate_items(
                query_terms=query_terms,
                scan_limit=scan_limit,
                partition_key=partition_key,
            )
        if search_mode is CosmosContextSearchMode.VECTOR:
            return await self._get_vector_candidate_items(
                query_text=query_text,
                scan_limit=scan_limit,
                partition_key=partition_key,
            )
        if search_mode is CosmosContextSearchMode.HYBRID:
            return await self._get_hybrid_candidate_items(
                query_text=query_text,
                query_terms=query_terms,
                weights=weights,
                scan_limit=scan_limit,
                partition_key=partition_key,
            )
        raise ValueError(f"Unsupported search_mode: {search_mode}")

    async def _get_full_text_candidate_items(
        self,
        *,
        query_terms: Sequence[str],
        scan_limit: int,
        partition_key: str | None,
    ) -> list[dict[str, Any]]:
        """Retrieve candidate items using Cosmos full-text ranking."""
        if not query_terms:
            return []

        query, parameters = self._build_full_text_query(query_terms, scan_limit=scan_limit)
        raw_items = await self._execute_query(
            query=query,
            parameters=parameters,
            scan_limit=scan_limit,
            partition_key=partition_key,
        )
        return self._annotate_rank_scores(raw_items, score_field=self._TEXT_SCORE_FIELD)

    async def _get_vector_candidate_items(
        self,
        *,
        query_text: str,
        scan_limit: int,
        partition_key: str | None,
    ) -> list[dict[str, Any]]:
        """Retrieve candidate items using Cosmos vector distance ranking."""
        query_vector = await self._get_query_vector(query_text)
        query, parameters = self._build_vector_query(query_vector, scan_limit=scan_limit)
        raw_items = await self._execute_query(
            query=query,
            parameters=parameters,
            scan_limit=scan_limit,
            partition_key=partition_key,
        )
        return self._annotate_rank_scores(raw_items, score_field=self._VECTOR_SCORE_FIELD)

    async def _get_hybrid_candidate_items(
        self,
        *,
        query_text: str,
        query_terms: Sequence[str],
        weights: Sequence[float],
        scan_limit: int,
        partition_key: str | None,
    ) -> list[dict[str, Any]]:
        """Retrieve candidate items using Cosmos hybrid reciprocal rank fusion."""
        if not query_terms:
            return []

        query_vector = await self._get_query_vector(query_text)
        query, parameters = self._build_hybrid_query(
            query_terms=query_terms,
            query_vector=query_vector,
            weights=weights,
            scan_limit=scan_limit,
        )
        raw_items = await self._execute_query(
            query=query,
            parameters=parameters,
            scan_limit=scan_limit,
            partition_key=partition_key,
        )
        return self._annotate_rank_scores(raw_items, score_field=self._COMBINED_SCORE_FIELD)

    def _build_full_text_query(
        self,
        query_terms: Sequence[str],
        *,
        scan_limit: int,
    ) -> tuple[str, list[dict[str, object]]]:
        """Build a Cosmos full-text ranking query using FullTextScore/BM25 semantics."""
        score_expression = f"FullTextScore(c.{self._get_primary_search_field_name()}, @query_text)"
        query = (
            f"{self._build_projection_query_base(scan_limit=scan_limit)} "
            f"WHERE {self._build_retrieval_filter_predicate()} "
            f"ORDER BY RANK {score_expression}"
        )
        return (
            query,
            [
                {"name": "@writeback_document_type", "value": self._WRITEBACK_DOCUMENT_TYPE},
                {"name": "@query_text", "value": self._normalize_search_text(query_terms)},
            ],
        )

    def _build_vector_query(
        self,
        query_vector: Sequence[float],
        *,
        scan_limit: int,
    ) -> tuple[str, list[dict[str, object]]]:
        """Build a Cosmos vector distance query using VectorDistance."""
        if self.vector_field_name is None:
            raise ValueError("vector_field_name is required when search_mode='vector'")

        distance_expression = f"VectorDistance(c.{self.vector_field_name}, @query_vector)"
        query = (
            f"{self._build_projection_query_base(scan_limit=scan_limit)} "
            f"WHERE {self._build_retrieval_filter_predicate()} "
            f"ORDER BY {distance_expression} ASC"
        )
        return (
            query,
            [
                {"name": "@writeback_document_type", "value": self._WRITEBACK_DOCUMENT_TYPE},
                {"name": "@query_vector", "value": list(query_vector)},
            ],
        )

    def _build_hybrid_query(
        self,
        *,
        query_terms: Sequence[str],
        query_vector: Sequence[float],
        weights: Sequence[float],
        scan_limit: int,
    ) -> tuple[str, list[dict[str, object]]]:
        """Build a Cosmos hybrid RRF query using full-text and vector components."""
        if self.vector_field_name is None:
            raise ValueError("vector_field_name is required when search_mode='hybrid'")

        full_text_expression = f"FullTextScore(c.{self._get_primary_search_field_name()}, @query_text)"
        vector_expression = f"VectorDistance(c.{self.vector_field_name}, @query_vector)"
        rrf_expression = f"RRF({full_text_expression}, {vector_expression}, {self._build_weights_literal(weights)})"
        query = (
            f"{self._build_projection_query_base(scan_limit=scan_limit)} "
            f"WHERE {self._build_retrieval_filter_predicate()} "
            f"ORDER BY RANK {rrf_expression}"
        )
        return (
            query,
            [
                {"name": "@writeback_document_type", "value": self._WRITEBACK_DOCUMENT_TYPE},
                {"name": "@query_text", "value": self._normalize_search_text(query_terms)},
                {"name": "@query_vector", "value": list(query_vector)},
            ],
        )

    def _shape_context_message(self, item: dict[str, Any]) -> Message | None:
        """Convert a Cosmos item into a context message when possible."""
        message_payload = item.get(self.message_field_name) if self.message_field_name else None
        if isinstance(message_payload, dict):
            try:
                return Message.from_dict(message_payload)  # pyright: ignore[reportUnknownArgumentType]
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping Cosmos DB item with invalid message payload: %s", exc)

        content = next(
            (
                field_value.strip()
                for field_name in self.content_field_names
                if isinstance(field_value := item.get(field_name), str) and field_value.strip()
            ),
            None,
        )
        if not isinstance(content, str) or not content.strip():
            return None

        title = item.get(self.title_field_name) if self.title_field_name else None
        url = item.get(self.url_field_name) if self.url_field_name else None
        message_lines = [
            *([f"Title: {title.strip()}"] if isinstance(title, str) and title.strip() else []),
            *([f"Source: {url.strip()}"] if isinstance(url, str) and url.strip() else []),
            content,
        ]
        additional_properties = {
            key: value
            for key, value in {
                "cosmos_document_id": item.get(self.id_field_name),
                "cosmos_metadata": item.get(self.metadata_field_name) if self.metadata_field_name else None,
            }.items()
            if value is not None
        }
        return Message(role="user", contents=["\n".join(message_lines)], additional_properties=additional_properties)

    def _select_context_messages(
        self,
        candidate_items: Sequence[dict[str, Any]],
        *,
        query_terms: Sequence[str],
        top_k: int,
    ) -> list[Message]:
        """Shape and select the final context messages."""
        ranked_messages: list[tuple[float, float, int, Message]] = []
        for position, item in enumerate(candidate_items):
            message = self._shape_context_message(item)
            if message is None:
                continue

            provider_score = self._get_item_score(item)
            fallback_score = float(self._score_text(message.text, query_terms))
            text_score = self._get_internal_score(item, self._TEXT_SCORE_FIELD)
            vector_score = self._get_internal_score(item, self._VECTOR_SCORE_FIELD)
            combined_score = self._get_internal_score(item, self._COMBINED_SCORE_FIELD)

            if text_score > 0 and vector_score == 0 and combined_score == 0 and fallback_score <= 0:
                continue

            effective_score = provider_score if provider_score > 0 else fallback_score
            if effective_score <= 0:
                continue

            ranked_messages.append((effective_score, fallback_score, -position, message))

        ranked_messages.sort(reverse=True)
        return [message for _, _, _, message in ranked_messages[:top_k]]

    def _annotate_rank_scores(
        self,
        items: Sequence[dict[str, Any]],
        *,
        score_field: str,
    ) -> list[dict[str, Any]]:
        """Attach a monotonic score based on Cosmos result ordering."""
        ranked_items: list[dict[str, Any]] = []
        total = len(items)
        for index, item in enumerate(items):
            ranked_item = dict(item)
            ranked_item[score_field] = float(total - index)
            ranked_items.append(ranked_item)
        return ranked_items

    async def _get_query_vector(self, query_text: str) -> list[float]:
        """Get a query embedding from the configured embedding provider."""
        if self.embedding_function is None:
            raise ValueError("embedding_function is required for vector and hybrid retrieval")

        if isinstance(self.embedding_function, SupportsGetEmbeddings):
            embeddings = await self.embedding_function.get_embeddings([query_text])  # type: ignore[reportUnknownVariableType]
            if not embeddings:
                raise ValueError("embedding_function returned no embeddings")
            resolved_embedding = [float(value) for value in embeddings[0].vector]  # type: ignore[reportUnknownVariableType]
            if not resolved_embedding:
                raise ValueError("embedding_function returned an empty embedding")
            return resolved_embedding

        resolved_embedding = [float(value) for value in await self.embedding_function(query_text)]
        if not resolved_embedding:
            raise ValueError("embedding_function returned an empty embedding")
        return resolved_embedding

    def _get_item_score(self, item: dict[str, Any]) -> float:
        """Get the most relevant provider score present on an item."""
        return max(
            self._get_internal_score(item, self._COMBINED_SCORE_FIELD),
            self._get_internal_score(item, self._VECTOR_SCORE_FIELD),
            self._get_internal_score(item, self._TEXT_SCORE_FIELD),
        )

    @staticmethod
    def _get_internal_score(item: dict[str, Any] | None, score_field: str) -> float:
        """Read an internal provider score from an item."""
        if item is None:
            return 0.0
        value = item.get(score_field)
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    @staticmethod
    def _tokenize_query_text(query_text: str) -> tuple[str, ...]:
        """Normalize query text into de-duplicated casefolded terms."""
        return tuple(dict.fromkeys(match.casefold() for match in re.findall(r"\w+", query_text, flags=re.UNICODE)))

    @staticmethod
    def _score_text(text: str, query_terms: Sequence[str]) -> int:
        """Compute a simple lexical relevance score for a text body."""
        normalized_text = text.casefold()
        return sum(normalized_text.count(term) for term in query_terms)

    def _build_query_text(self, messages: Sequence[Message]) -> str:
        """Build retrieval query text by joining filtered conversation messages."""
        return "\n".join(msg.text.strip() for msg in messages if msg.text and msg.text.strip())

    @staticmethod
    def _normalize_search_text(query_terms: Sequence[str]) -> str:
        """Build a stable full-text search string from normalized terms."""
        return " ".join(term for term in query_terms if term)

    def _get_primary_search_field_name(self) -> str:
        """Return the primary document text field used for Cosmos native search."""
        return self.content_field_names[0]

    def _build_retrieval_filter_predicate(self) -> str:
        """Exclude context-provider writeback documents from retrieval queries."""
        return "(NOT IS_DEFINED(c.document_type) OR c.document_type != @writeback_document_type)"

    def _build_projection_query_base(self, *, scan_limit: int) -> str:
        """Build the base projection clause for Cosmos retrieval queries."""
        projection_fields = [self.id_field_name, *self.content_field_names]
        projection_fields.extend(
            field_name
            for field_name in (
                self.title_field_name,
                self.url_field_name,
                self.message_field_name,
                self.metadata_field_name,
            )
            if field_name is not None and field_name not in projection_fields
        )
        select_clause = ", ".join(f"c.{field_name}" for field_name in projection_fields)
        # Field names and scan_limit are validated during initialization.
        return f"SELECT TOP {scan_limit} {select_clause} FROM c"  # noqa: S608  # nosec B608

    def _validate_search_configuration(
        self,
        search_mode: CosmosContextSearchMode,
        weights: Sequence[float],
    ) -> None:
        """Validate search-mode-specific runtime requirements."""
        if search_mode in {CosmosContextSearchMode.VECTOR, CosmosContextSearchMode.HYBRID}:
            if not self.vector_field_name:
                raise ValueError(f"vector_field_name is required when search_mode='{search_mode.value}'")
            if self.embedding_function is None:
                raise ValueError(f"embedding_function is required when search_mode='{search_mode.value}'")

        if search_mode is CosmosContextSearchMode.HYBRID and len(weights) != 2:
            raise ValueError("weights must contain exactly two values for hybrid RRF search")

    @classmethod
    def _resolve_weights_for_run(
        cls,
        search_mode: CosmosContextSearchMode,
        weights: Sequence[float] | None,
    ) -> tuple[float, ...]:
        """Resolve positional RRF weights for one provider run."""
        if search_mode is not CosmosContextSearchMode.HYBRID:
            return cls._DEFAULT_RRF_WEIGHTS
        return cls._validate_weights(weights)

    @staticmethod
    def _validate_search_mode(value: CosmosContextSearchMode, *, parameter_name: str) -> CosmosContextSearchMode:
        """Validate a Cosmos context search mode value."""
        if not isinstance(value, CosmosContextSearchMode):
            raise TypeError(f"{parameter_name} must be a CosmosContextSearchMode value")
        return value

    @classmethod
    def _validate_weights(cls, value: Sequence[float] | None) -> tuple[float, ...]:
        """Validate hybrid RRF weights used for positional score fusion."""
        resolved = cls._DEFAULT_RRF_WEIGHTS if value is None else tuple(float(weight) for weight in value)
        if len(resolved) != 2:
            raise ValueError("weights must contain exactly two values for hybrid RRF search")
        if any(weight < 0 for weight in resolved):
            raise ValueError("weights values must be greater than or equal to 0")
        if all(weight == 0 for weight in resolved):
            raise ValueError("weights cannot all be 0")
        return resolved

    @staticmethod
    def _build_weights_literal(weights: Sequence[float]) -> str:
        """Build a Cosmos SQL list literal for positional RRF weights."""
        return "[" + ", ".join(f"{float(weight):g}" for weight in weights) + "]"

    @staticmethod
    def _session_partition_key(session_id: str | None) -> str:
        """Resolve a session partition key for writeback documents."""
        if session_id:
            return session_id

        generated_session_id = str(uuid.uuid4())
        logger.warning(
            "Received empty session_id; generated temporary session id '%s' for Cosmos writeback partition key.",
            generated_session_id,
        )
        return generated_session_id

    @classmethod
    def _validate_positive_int(cls, value: int | None, *, default: int, name: str) -> int:
        """Validate a positive integer configuration value."""
        resolved = default if value is None else value
        if resolved <= 0:
            raise ValueError(f"{name} must be greater than 0")
        return resolved

    @classmethod
    def _validate_required_field_names(cls, values: Sequence[str], *, parameter_name: str) -> tuple[str, ...]:
        """Validate a non-empty ordered sequence of Cosmos document field names."""
        normalized = tuple(cls._validate_field_name(value, parameter_name=parameter_name) for value in values)
        if not normalized:
            raise ValueError(f"{parameter_name} must contain at least one field name")
        return normalized

    @classmethod
    def _validate_optional_field_name(cls, value: str | None, *, parameter_name: str) -> str | None:
        """Validate an optional Cosmos document field name."""
        if value is None:
            return None
        return cls._validate_field_name(value, parameter_name=parameter_name)

    @classmethod
    def _validate_field_name(cls, value: str, *, parameter_name: str) -> str:
        """Validate a Cosmos field name used in projection query construction."""
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError(f"{parameter_name} must not be empty")
        if not cls._VALID_FIELD_NAME_PATTERN.fullmatch(stripped_value):
            raise ValueError(
                f"{parameter_name} must contain only letters, numbers, and underscores, and cannot start with a number"
            )
        return stripped_value


__all__ = ["AzureCosmosContextProvider", "CosmosContextSearchMode"]
