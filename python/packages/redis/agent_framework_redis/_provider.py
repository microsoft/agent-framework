# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import MutableSequence, Sequence
from typing import Any, Final, Literal, cast

from agent_framework import ChatMessage, Context, ContextProvider, TextContent  # type: ignore[no-any-unimported]
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
from redisvl.query.filter import FilterExpression
from redisvl.utils.token_escaper import TokenEscaper
from redisvl.utils.vectorize import HFTextVectorizer, OpenAITextVectorizer

DEFAULT_CONTEXT_PROMPT: Final[str] = "## Memories\nConsider the following memories when answering user questions:"


class RedisProvider(ContextProvider):
    """Redis-backed context provider with dynamic, filterable schema.

    To-Do: Dynamic Vector/embedding Config in RedisProvider.
    """

    # Connection and indexing
    redis_url: str = "redis://localhost:6379"
    index_name: str = "af_memory"
    prefix: str = "memory"
    key_separator: str = ":"
    storage_type: Literal["hash", "json"] = "hash"

    # Vector configuration (optional)
    vectorizer_api_key: str | None = None
    vectorizer_choice: Literal["openai", "hf"] | None = None
    vectorizer: OpenAITextVectorizer | HFTextVectorizer | None = None
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
    token_escaper: TokenEscaper | None = None

    def __init__(
        self,
        *,
        redis_url: str = "redis://localhost:6379",
        index_name: str = "af_memory",
        prefix: str = "memory",
        key_separator: str = ":",
        storage_type: Literal["hash", "json"] = "hash",
        # Vector: all optional; omit to disable KNN
        vectorizer_api_key: str | None = None,
        vectorizer_choice: Literal["openai", "hf"] | None = None,
        vector_field_name: str | None = None,
        vector_dims: int | None = None,
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
        if vectorizer_choice == "openai":
            vectorizer = OpenAITextVectorizer(
                model="text-embedding-ada-002",
                api_config={"api_key": vectorizer_api_key},
                cache=EmbeddingsCache(name="openai_embeddings_cache"),
            )
            vector_dims = vectorizer.dims
        elif vectorizer_choice == "hf":
            vectorizer = HFTextVectorizer(
                model="sentence-transformers/all-MiniLM-L6-v2", cache=EmbeddingsCache(name="hf_embeddings_cache")
            )
            vector_dims = vectorizer.dims
        else:
            vectorizer = None
            vector_dims = None

        schema_dict = self._build_schema_dict(
            index_name=index_name,
            prefix=prefix,
            key_separator=key_separator,
            storage_type=storage_type,
            vector_field_name=vector_field_name,
            vector_dims=vector_dims,
            vector_datatype=vector_datatype,
            vector_algorithm=vector_algorithm,
            vector_distance_metric=vector_distance_metric,
        )

        redis_index = AsyncSearchIndex.from_dict(schema_dict, redis_url=redis_url, validate_on_load=True)

        token_escaper = TokenEscaper()

        super().__init__(
            redis_url=redis_url,  # type: ignore[reportCallIssue]
            index_name=index_name,  # type: ignore[reportCallIssue]
            prefix=prefix,  # type: ignore[reportCallIssue]
            key_separator=key_separator,  # type: ignore[reportCallIssue]
            storage_type=storage_type,  # type: ignore[reportCallIssue]
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

    def _build_schema_dict(
        self,
        *,
        index_name: str,
        prefix: str,
        key_separator: str,
        storage_type: Literal["hash", "json"],
        vector_field_name: str | None,
        vector_dims: int | None,
        vector_datatype: Literal["float32", "float16", "bfloat16"] | None,
        vector_algorithm: Literal["flat", "hnsw"] | None,
        vector_distance_metric: Literal["cosine", "ip", "l2"] | None,
    ) -> dict[str, Any]:
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
                "key_separator": key_separator,
                "storage_type": storage_type,
            },
            "fields": fields,
        }

    async def create_redis_index(self) -> None:
        await self.redis_index.create(overwrite=self.overwrite_redis_index, drop=self.drop_redis_index)
        return

    async def add(
        self,
        *,
        data: dict[str, Any] | list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert one or many documents with partition fields populated.

        - Accepts either a single dict or a list of dicts.
        - Sets application_id/agent_id/user_id/thread_id from provider defaults if not provided.
        - Requires 'content' field in each doc.
        - If a vector field is configured, enforces presence (defaults to None).
        """
        # Ensure provider has at least one scope set (symmetry with Mem0Provider)
        self._validate_filters()

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
        filter_expression: str | None = None,
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
        """Fulltext search over a text field with optional filters.

        - Applies provider partition filters (application_id/agent_id/user_id/thread_id) when set.
        - Accepts an optional additional filter_expression which is ANDed with partition filters.
        - Minimal, safe defaults; validate inputs and keep output shape simple (list of dicts).
        """
        # Enforce presence of at least one provider-level filter (symmetry with Mem0Provider)
        self._validate_filters()

        q = (text or "").strip()
        if not q:
            raise ServiceInvalidRequestError("text_search() requires non-empty text")
        num_results = max(int(num_results or 10), 1)

        # Build partition scope as a RediSearch filter string (AND by whitespace)
        scope_parts: list[str] = []
        if self.application_id:
            scope_parts.append(f"@application_id:{{{self.application_id}}}")
        if self.agent_id:
            scope_parts.append(f"@agent_id:{{{self.agent_id}}}")
        if self.user_id:
            scope_parts.append(f"@user_id:{{{self.user_id}}}")
        eff_thread = self._effective_thread_id
        if eff_thread:
            scope_parts.append(f"@thread_id:{{{eff_thread}}}")

        scope_str = " ".join(scope_parts) if scope_parts else None

        # Combine user-provided filter with the scope (AND semantics)
        combined_filter_str_parts: list[str] = []
        if scope_str:
            combined_filter_str_parts.append(scope_str)
        if filter_expression is not None:
            combined_filter_str_parts.append(str(filter_expression))
        combined_filter = (
            FilterExpression(" ".join(p for p in combined_filter_str_parts if p)) if combined_filter_str_parts else None
        )

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
                results = await self.redis_index.query(query)
                return cast(list[dict[str, Any]], results)
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
            results2 = await self.redis_index.query(query)
            return cast(list[dict[str, Any]], results2)
        except Exception as exc:  # pragma: no cover - surface as framework error
            raise ServiceInvalidRequestError(f"Redis text search failed: {exc}") from exc

    async def search_all(self, page_size: int = 200) -> list[dict[str, Any]]:
        """Return all docs in the index (paginated under the hood)."""
        out: list[dict[str, Any]] = []
        async for batch in self.redis_index.paginate(
            FilterQuery(FilterExpression("*"), return_fields=[], num_results=page_size),
            page_size=page_size,
        ):
            out.extend(batch)
        return out

    @property
    def _effective_thread_id(self) -> str | None:
        return self._per_operation_thread_id if self.scope_to_per_operation_thread_id else self.thread_id

    async def thread_created(self, thread_id: str | None) -> None:
        """Called when a new thread is created.

        Args:
            thread_id: The ID of the thread or None.
        """
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Called when a new message is being added to the thread.

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
            if message.role.value in {"user", "assistant", "system"} and message.text and message.text.strip()
        ]
        if messages:
            await self.add(data=messages)

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Called before invoking the AI model to provide context.

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
        # Nothing special to do for Redis client; keep for symmetry with Mem0Provider
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        # No-op; indexes/keys remain unless `close()` is called explicitly.
        return None

    def _validate_filters(self) -> None:
        """Ensure at least one provider-level filter is set.

        Symmetry with Mem0Provider: require one of agent_id, user_id, application_id, or thread_id.
        """
        if not self.agent_id and not self.user_id and not self.application_id and not self.thread_id:
            raise ServiceInitializationError(
                "At least one of the filters: agent_id, user_id, application_id, or thread_id is required."
            )

    def _validate_per_operation_thread_id(self, thread_id: str | None) -> None:
        """Validate exclusive per-operation thread id usage when scoping is enabled."""
        if (
            self.scope_to_per_operation_thread_id
            and thread_id
            and self._per_operation_thread_id
            and thread_id != self._per_operation_thread_id
        ):
            raise ValueError(
                "RedisProvider can only be used with one thread,when scope_to_per_operation_thread_id is True."
            )
