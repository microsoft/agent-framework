# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
import sys
from collections.abc import MutableSequence, Sequence
from functools import reduce
from operator import and_
from typing import Any, Final, Literal, cast

from agent_framework import ChatMessage, Context, ContextProvider, Role, TextContent  # type: ignore[no-any-unimported]
from agent_framework.exceptions import (  # type: ignore[no-any-unimported]
    ServiceInitializationError,
    ServiceInvalidRequestError,
)

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


import numpy as np
from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.index import AsyncSearchIndex
from redisvl.query import FilterQuery, HybridQuery, TextQuery
from redisvl.query.filter import FilterExpression, Tag
from redisvl.utils.token_escaper import TokenEscaper
from redisvl.utils.vectorize import HFTextVectorizer, OpenAITextVectorizer

DEFAULT_CONTEXT_PROMPT: Final[str] = "## Memories\nConsider the following memories when answering user questions:"


class RedisProvider(ContextProvider):
    """Redis-backed context provider with dynamic, filterable schema.

    Stores chat messages in RediSearch and retrieves scoped context.
    Uses full-text or optional hybrid vector search to ground model responses.
    """

    # Connection and indexing
    redis_url: str = "redis://localhost:6379"
    index_name: str = "af_memory"
    prefix: str = "memory"
    fresh_initialization: bool = False

    # Vector configuration (optional)
    vectorizer_api_key: str | None = None
    vectorizer_choice: Literal["openai", "hf"] | None = None
    vectorizer: Any | None = None
    vector_field_name: str | None = None
    vector_datatype: Literal["float32", "float16", "bfloat16"] | None = None
    vector_algorithm: Literal["flat", "hnsw"] | None = None
    vector_distance_metric: Literal["cosine", "ip", "l2"] | None = None

    # Partition fields (indexed for filtering)
    application_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    scope_to_per_operation_thread_id: bool = False

    # Prompt and runtime
    context_prompt: str = DEFAULT_CONTEXT_PROMPT
    redis_index: Any = None
    overwrite_redis_index: bool = True
    drop_redis_index: bool = True
    _per_operation_thread_id: str | None = None
    token_escaper: Any | None = None

    def __init__(
        self,
        *,
        redis_url: str = "redis://localhost:6379",
        index_name: str = "af_memory",
        prefix: str = "memory",
        fresh_initialization: bool = False,
        # Vector: all optional; omit to disable KNN
        vectorizer_api_key: str | None = None,
        vectorizer_choice: Literal["openai", "hf"] | None = None,
        vector_field_name: str | None = None,
        vector_datatype: Literal["float32", "float16", "bfloat16"] | None = None,
        vector_algorithm: Literal["flat", "hnsw"] | None = None,
        vector_distance_metric: Literal["cosine", "ip", "l2"] | None = None,
        # Partition fields
        application_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        thread_id: str | None = None,
        scope_to_per_operation_thread_id: bool = False,
        context_prompt: str = DEFAULT_CONTEXT_PROMPT,
        overwrite_redis_index: bool = True,
        drop_redis_index: bool = True,
    ):
        """Initializes a new instance of the RedisProvider class.

        Builds the index schema and optional vectorizer.
        Wires default partition filters used to scope reads and writes.

        Args:
            redis_url: Redis connection URL.
            index_name: RediSearch index name.
            prefix: Key prefix for stored documents.
            fresh_initialization: Whether this is a fresh setup run.
            vectorizer_api_key: API key for the chosen vectorizer or None.
            vectorizer_choice: Vectorizer backend to use ("openai" or "hf") or None.
            vector_field_name: Name of the vector field in the schema or None.
            vector_datatype: Vector datatype if vectors are enabled.
            vector_algorithm: Vector index algorithm if vectors are enabled.
            vector_distance_metric: Vector distance metric if vectors are enabled.
            application_id: Application scope filter or None.
            agent_id: Agent scope filter or None.
            user_id: User scope filter or None.
            thread_id: Thread scope filter or None.
            scope_to_per_operation_thread_id: Whether to scope to per-operation thread ID.
            context_prompt: Prompt to prepend to retrieved memories.
            overwrite_redis_index: Whether to overwrite the index on create.
            drop_redis_index: Whether to drop the index before create.
        """
        # Avoid mypy inferring unfollowed-import types for local variables
        vectorizer: Any | None = None
        if vectorizer_choice == "openai":
            # Will try to retrieve from environment variable if not provided
            if vectorizer_api_key is None:
                vectorizer_api_key = os.getenv("OPENAI_API_KEY")
                if vectorizer_api_key is None:
                    raise ServiceInvalidRequestError(
                        "OpenAI API key is required."
                        "Set 'vectorizer_api_key' parameter"
                        "Or 'OPENAI_API_KEY' environment variable."
                    )
            vectorizer = OpenAITextVectorizer(
                model="text-embedding-ada-002",
                api_config={"api_key": vectorizer_api_key},
                cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url=redis_url),
            )
            vector_dims = vectorizer.dims
        elif vectorizer_choice == "hf":
            vectorizer = HFTextVectorizer(
                model="sentence-transformers/all-MiniLM-L6-v2",
                cache=EmbeddingsCache(name="hf_embeddings_cache", redis_url=redis_url),
            )
            vector_dims = vectorizer.dims
        else:
            vectorizer = None
            vector_dims = None

        schema_dict = self._build_schema_dict(
            index_name=index_name,
            prefix=prefix,
            vector_field_name=vector_field_name,
            vector_dims=vector_dims,
            vector_datatype=vector_datatype,
            vector_algorithm=vector_algorithm,
            vector_distance_metric=vector_distance_metric,
        )

        redis_index = AsyncSearchIndex.from_dict(schema_dict, redis_url=redis_url, validate_on_load=True)

        token_escaper: Any = TokenEscaper()

        super().__init__(
            redis_url=redis_url,  # type: ignore[reportCallIssue]
            index_name=index_name,  # type: ignore[reportCallIssue]
            prefix=prefix,  # type: ignore[reportCallIssue]
            fresh_initialization=fresh_initialization,  # type: ignore[reportCallIssue]
            vectorizer_api_key=vectorizer_api_key,  # type: ignore[reportCallIssue]
            vectorizer_choice=vectorizer_choice,  # type: ignore[reportCallIssue]
            vectorizer=vectorizer,  # type: ignore[reportCallIssue]
            vector_field_name=vector_field_name,  # type: ignore[reportCallIssue]
            vector_dims=vector_dims,  # type: ignore[reportCallIssue]
            vector_datatype=vector_datatype,  # type: ignore[reportCallIssue]
            vector_algorithm=vector_algorithm,  # type: ignore[reportCallIssue]
            vector_distance_metric=vector_distance_metric,  # type: ignore[reportCallIssue]
            application_id=application_id,  # type: ignore[reportCallIssue]
            agent_id=agent_id,  # type: ignore[reportCallIssue]
            user_id=user_id,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            scope_to_per_operation_thread_id=scope_to_per_operation_thread_id,  # type: ignore[reportCallIssue]
            context_prompt=context_prompt,  # type: ignore[reportCallIssue]
            redis_index=redis_index,  # type: ignore[reportCallIssue]
            overwrite_redis_index=overwrite_redis_index,  # type: ignore[reportCallIssue]
            drop_redis_index=drop_redis_index,  # type: ignore[reportCallIssue]
            token_escaper=token_escaper,  # type: ignore[reportCallIssue]
        )

    def _build_filter_from_dict(self, filters: dict[str, str | None]) -> Any | None:
        """Builds a combined filter expression from simple equality tags.

        This ANDs non-empty tag filters and is used to scope all operations to app/agent/user/thread partitions.

        Args:
            filters: Mapping of field name to value; falsy values are ignored.

        Returns:
            A combined filter expression or None if no filters are provided.
        """
        parts = [Tag(k) == v for k, v in filters.items() if v]
        return reduce(and_, parts) if parts else None

    def _build_schema_dict(
        self,
        *,
        index_name: str,
        prefix: str,
        vector_field_name: str | None,
        vector_dims: int | None,
        vector_datatype: Literal["float32", "float16", "bfloat16"] | None,
        vector_algorithm: Literal["flat", "hnsw"] | None,
        vector_distance_metric: Literal["cosine", "ip", "l2"] | None,
    ) -> dict[str, Any]:
        """Builds the RediSearch schema configuration dictionary.

        Defines text and tag fields for messages plus an optional vector field enabling KNN/hybrid search.

        Args:
            index_name: Index name.
            prefix: Key prefix.
            vector_field_name: Vector field name or None.
            vector_dims: Vector dimensionality or None.
            vector_datatype: Vector datatype or None.
            vector_algorithm: Vector index algorithm or None.
            vector_distance_metric: Vector distance metric or None.

        Returns:
            Dict representing the index and fields configuration.
        """
        fields: list[dict[str, Any]] = [
            {"name": "role", "type": "tag"},
            {"name": "mime_type", "type": "tag"},
            {"name": "content", "type": "text"},
            # Partition fields (TAG for fast filtering)
            {"name": "application_id", "type": "tag"},
            {"name": "agent_id", "type": "tag"},
            {"name": "user_id", "type": "tag"},
            {"name": "thread_id", "type": "tag"},
        ]

        # Add vector field only if configured (keeps provider runnable with no params)
        if vector_field_name is not None and vector_dims is not None:
            fields.append({
                "name": vector_field_name,
                "type": "vector",
                "attrs": {
                    "algorithm": (vector_algorithm or "hnsw"),
                    "dims": int(vector_dims),
                    "distance_metric": (vector_distance_metric or "cosine"),
                    "datatype": (vector_datatype or "float32"),
                },
            })

        return {
            "index": {
                "name": index_name,
                "prefix": prefix,
                "key_separator": ":",
                "storage_type": "hash",
            },
            "fields": fields,
        }

    async def _ensure_index(self) -> None:
        """Ensures the index exists, creating or dropping as configured.

        Called before reads/writes so queries are safe and the schema is applied deterministically.
        """
        if self.drop_redis_index:
            if not self.fresh_initialization:
                await self.redis_index.create(overwrite=self.overwrite_redis_index, drop=self.drop_redis_index)
                self.fresh_initialization = True
        else:
            if not await self.redis_index.exists():
                await self.redis_index.create(overwrite=self.overwrite_redis_index, drop=self.drop_redis_index)
        return

    async def add(
        self,
        *,
        data: dict[str, Any] | list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Inserts one or many documents with partition fields populated.

        Fills default partition fields, optionally embeds content when configured, and loads documents in a batch.

        Args:
            data: Single document or list of documents to insert.
            metadata: Optional metadata dictionary (unused placeholder).

        Raises:
            ServiceInvalidRequestError: If required fields are missing or invalid.
        """
        # Ensure provider has at least one scope set (symmetry with Mem0Provider)
        self._validate_filters()
        await self._ensure_index()
        docs = data if isinstance(data, list) else [data]

        prepared: list[dict[str, Any]] = []
        for doc in docs:
            d = dict(doc)  # shallow copy

            # Partition defaults
            d.setdefault("application_id", self.application_id)
            d.setdefault("agent_id", self.agent_id)
            d.setdefault("user_id", self.user_id)
            d.setdefault("thread_id", self._effective_thread_id)

            # Logical requirement
            if "content" not in d:
                raise ServiceInvalidRequestError("add() requires a 'content' field in data")

            # Vector field requirement (only if schema has one)
            if self.vector_field_name:
                d.setdefault(self.vector_field_name, None)

            prepared.append(d)

        # Batch embed contents for every message
        if self.vectorizer and self.vector_field_name:
            text_list = [d["content"] for d in prepared]
            embeddings = await self.vectorizer.aembed_many(text_list, batch_size=len(text_list))
            for i, d in enumerate(prepared):
                vec = np.asarray(embeddings[i], dtype=np.float32).tobytes()
                field_name: str = self.vector_field_name
                d[field_name] = vec

        # Load all at once if supported
        await self.redis_index.load(prepared)
        return

    async def redis_search(
        self,
        text: str,
        *,
        text_field_name: str = "content",
        text_scorer: str = "BM25STD",
        filter_expression: Any | None = None,
        return_fields: list[str] | None = None,
        num_results: int = 10,
        return_score: bool = True,
        dialect: int = 2,
        sort_by: str | None = None,
        in_order: bool = False,
        params: dict[str, Any] | None = None,
        stopwords: str | set[str] | None = "english",
        alpha: float = 0.7,
        dtype: Literal["float32", "float16", "bfloat16"] = "float32",
    ) -> list[dict[str, Any]]:
        """Runs a text or hybrid vector-text search with optional filters.

        Builds a TextQuery or HybridQuery and automatically ANDs partition filters to keep results scoped and safe.

        Args:
            text: Query text.
            text_field_name: Text field to search.
            text_scorer: Scorer to use for text ranking.
            filter_expression: Additional filter expression to AND with partition filters.
            return_fields: Fields to return in results.
            num_results: Maximum number of results.
            return_score: Whether to include scores for text-only search.
            dialect: RediSearch dialect version.
            sort_by: Field to sort by (text-only search).
            in_order: Whether to preserve field order (text-only search).
            params: Additional query params.
            stopwords: Stopwords to apply.
            alpha: Hybrid balancing parameter when vectors are enabled.
            dtype: Vector dtype when vectors are enabled.

        Returns:
            List of result dictionaries.

        Raises:
            ServiceInvalidRequestError: If input is invalid or the query fails.
        """
        # Enforce presence of at least one provider-level filter (symmetry with Mem0Provider)
        await self._ensure_index()
        self._validate_filters()

        q = (text or "").strip()
        if not q:
            raise ServiceInvalidRequestError("text_search() requires non-empty text")
        num_results = max(int(num_results or 10), 1)

        combined_filter = self._build_filter_from_dict({
            "application_id": self.application_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "thread_id": self._effective_thread_id,
        })

        if filter_expression is not None:
            combined_filter = (combined_filter & filter_expression) if combined_filter else filter_expression

        # Choose return fields
        return_fields = (
            return_fields
            if return_fields is not None
            else ["content", "role", "application_id", "agent_id", "user_id", "thread_id"]
        )

        # Normalize stopwords to match TextQuery's expected types
        normalized_stopwords: str | set[str] | None = stopwords
        if isinstance(stopwords, list):
            normalized_stopwords = set(stopwords)
        try:
            if self.vectorizer and self.vector_field_name:
                # Build hybrid query: combine full-text and vector similarity
                embed_list = await self.vectorizer.aembed_many([q], batch_size=1)
                vector: list[float] = [float(x) for x in (embed_list[0] or [])]
                query = HybridQuery(
                    text=q,
                    text_field_name=text_field_name,
                    vector=vector,
                    vector_field_name=self.vector_field_name,
                    text_scorer=text_scorer,
                    filter_expression=combined_filter,
                    alpha=alpha,
                    dtype=dtype,
                    num_results=num_results,
                    return_fields=return_fields,
                    stopwords=normalized_stopwords,
                    dialect=dialect,
                )
                hybrid_results = await self.redis_index.query(query)
                return cast(list[dict[str, Any]], hybrid_results)
            # Text-only search
            query = TextQuery(
                text=q,
                text_field_name=text_field_name,
                text_scorer=text_scorer,
                filter_expression=combined_filter,
                num_results=num_results,
                return_fields=return_fields,
                stopwords=normalized_stopwords,
                dialect=dialect,
                # return_score supported on TextQuery; omit on HybridQuery for compatibility
                return_score=return_score,
                sort_by=sort_by,
                in_order=in_order,
                params=params,
            )
            text_results = await self.redis_index.query(query)
            return cast(list[dict[str, Any]], text_results)
        except Exception as exc:  # pragma: no cover - surface as framework error
            raise ServiceInvalidRequestError(f"Redis text search failed: {exc}") from exc

    async def search_all(self, page_size: int = 200) -> list[dict[str, Any]]:
        """Returns all documents in the index.

        Streams results via pagination to avoid excessive memory and response sizes.

        Args:
            page_size: Page size used for pagination under the hood.

        Returns:
            List of all documents.
        """
        out: list[dict[str, Any]] = []
        async for batch in self.redis_index.paginate(
            FilterQuery(FilterExpression("*"), return_fields=[], num_results=page_size),
            page_size=page_size,
        ):
            out.extend(batch)
        return out

    @property
    def _effective_thread_id(self) -> str | None:
        """Resolves the active thread id.

        Returns per-operation thread id when scoping is enabled; otherwise the provider's thread id.
        """
        return self._per_operation_thread_id if self.scope_to_per_operation_thread_id else self.thread_id

    async def thread_created(self, thread_id: str | None) -> None:
        """Called when a new thread is created.

        Captures the per-operation thread id when scoping is enabled to enforce single-thread usage.

        Args:
            thread_id: The ID of the thread or None.
        """
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Called when a new message is being added to the thread.

        Validates scope, normalizes allowed roles, and persists messages to Redis via add().

        Args:
            thread_id: The ID of the thread or None.
            new_messages: New messages to add.
        """
        self._validate_filters()
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

        messages_list = [new_messages] if isinstance(new_messages, ChatMessage) else list(new_messages)

        messages: list[dict[str, str]] = [
            {"role": message.role.value, "content": message.text}
            for message in messages_list
            if message.role.value in {Role.USER.value, Role.ASSISTANT.value, Role.SYSTEM.value}
            and message.text
            and message.text.strip()
        ]
        if messages:
            await self.add(data=messages)

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Called before invoking the model to provide scoped context.

        Concatenates recent messages into a query, fetches matching memories from Redis.
        Prepends them as instructions.

        Args:
            messages: List of new messages in the thread.

        Returns:
            Context: Context object containing instructions with memories.
        """
        self._validate_filters()
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)
        input_text = "\n".join(msg.text for msg in messages_list if msg and msg.text and msg.text.strip())

        memories = await self.redis_search(text=input_text)
        line_separated_memories = "\n".join(
            str(memory.get("content", "")) for memory in memories if memory.get("content")
        )
        content = TextContent(f"{self.context_prompt}\n{line_separated_memories}") if line_separated_memories else None
        return Context(contents=[content] if content else None)

    async def __aenter__(self) -> Self:
        """Async context manager entry.

        No special setup is required; provided for symmetry with the Mem0 provider.
        """
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit.

        No cleanup is required; indexes/keys remain unless explicitly cleared.
        """
        return

    def _validate_filters(self) -> None:
        """Validates that at least one filter is provided.

        Prevents unbounded operations by requiring a partition filter before reads or writes.

        Raises:
            ServiceInitializationError: If no filters are provided.
        """
        if not self.agent_id and not self.user_id and not self.application_id and not self.thread_id:
            raise ServiceInitializationError(
                "At least one of the filters: agent_id, user_id, application_id, or thread_id is required."
            )

    def _validate_per_operation_thread_id(self, thread_id: str | None) -> None:
        """Validates that a new thread ID doesn't conflict when scoped.

        Prevents cross-thread data leakage by enforcing single-thread usage when per-operation scoping is enabled.

        Args:
            thread_id: The new thread ID or None.

        Raises:
            ValueError: If a new thread ID conflicts with the existing one.
        """
        if (
            self.scope_to_per_operation_thread_id
            and thread_id
            and self._per_operation_thread_id
            and thread_id != self._per_operation_thread_id
        ):
            raise ValueError(
                "RedisProvider can only be used with one thread,when scope_to_per_operation_thread_id is True."
            )
