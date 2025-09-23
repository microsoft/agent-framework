# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import MutableSequence, Sequence
from functools import reduce
from operator import and_
from typing import Any, Literal, cast

from agent_framework import ChatMessage, Context, ContextProvider, Role, TextContent
from agent_framework.exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
)

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

import json

import numpy as np
from redisvl.index import AsyncSearchIndex
from redisvl.query import FilterQuery, HybridQuery, TextQuery
from redisvl.query.filter import FilterExpression, Tag
from redisvl.utils.token_escaper import TokenEscaper
from redisvl.utils.vectorize import BaseVectorizer


class RedisProvider(ContextProvider):
    """Redis context provider with dynamic, filterable schema.

    Stores context in Redis and retrieves scoped context.
    Uses full-text or optional hybrid vector search to ground model responses.
    """

    # Connection and indexing
    redis_url: str = "redis://localhost:6379"
    index_name: str = "context"
    prefix: str = "context"

    # Redis vectorizer configuration (optional, injected by client)
    redis_vectorizer: BaseVectorizer | None = None
    vector_field_name: str | None = None
    vector_algorithm: Literal["flat", "hnsw"] | None = None
    vector_distance_metric: Literal["cosine", "ip", "l2"] | None = None

    # Partition fields (indexed for filtering)
    application_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    scope_to_per_operation_thread_id: bool = False

    # Prompt and runtime
    context_prompt: str = ContextProvider.DEFAULT_CONTEXT_PROMPT
    redis_index: Any = None
    overwrite_index: bool = False
    _per_operation_thread_id: str | None = None
    _token_escaper: TokenEscaper = TokenEscaper()
    _conversation_id: str | None = None
    _index_initialized: bool = False
    _schema_dict: dict[str, Any] | None = None

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization hook to set up computed fields after Pydantic initialization.

        This is called automatically by Pydantic after the model is initialized.
        """
        # Create Redis index using the cached schema_dict property
        self.redis_index = AsyncSearchIndex.from_dict(self.schema_dict, redis_url=self.redis_url, validate_on_load=True)

    @property
    def schema_dict(self) -> dict[str, Any]:
        """Get the Redis schema dictionary, computing and caching it on first access."""
        if self._schema_dict is None:
            # Get vector configuration from vectorizer if available
            vector_dims = self.redis_vectorizer.dims if self.redis_vectorizer is not None else None
            vector_datatype = self.redis_vectorizer.dtype if self.redis_vectorizer is not None else None

            self._schema_dict = self._build_schema_dict(
                index_name=self.index_name,
                prefix=self.prefix,
                vector_field_name=self.vector_field_name,
                vector_dims=vector_dims,
                vector_datatype=vector_datatype,
                vector_algorithm=self.vector_algorithm,
                vector_distance_metric=self.vector_distance_metric,
            )
        return self._schema_dict

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
        vector_datatype: str | None,
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
            # Conversation tracking
            {"name": "conversation_id", "type": "tag"},
            {"name": "message_id", "type": "tag"},
            {"name": "author_name", "type": "tag"},
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
        """Initialize the search index.

        - Connect to existing index if it exists and schema matches
        - Create new index if it doesn't exist
        - Overwrite if requested via overwrite_index=True
        - Validate schema compatibility to prevent accidental data loss
        """
        if self._index_initialized:
            return

        # Check if index already exists
        index_exists = await self.redis_index.exists()

        if not self.overwrite_index and index_exists:
            # Validate schema compatibility before connecting
            await self._validate_schema_compatibility()

        # Create the index (will connect to existing or create new)
        await self.redis_index.create(overwrite=self.overwrite_index, drop=False)

        self._index_initialized = True

    async def _validate_schema_compatibility(self) -> None:
        """Validate that existing index schema matches current configuration.

        Raises ServiceInitializationError if schemas don't match, with helpful guidance.

        self._build_schema_dict returns a minimal schema while Redis returns an expanded
        schema with all defaults filled in. To compare for incompatibilities, compare
        significant parts of the schema by creating signatures with normalized default values.
        """
        # Defaults for attr normalization
        TAG_DEFAULTS = {"separator": ",", "case_sensitive": False, "withsuffixtrie": False}
        TEXT_DEFAULTS = {"weight": 1.0, "no_stem": False}

        def _significant_index(i: dict[str, Any]) -> dict[str, Any]:
            return {k: i.get(k) for k in ("name", "prefix", "key_separator", "storage_type")}

        def _sig_tag(attrs: dict[str, Any] | None) -> dict[str, Any]:
            a = {**TAG_DEFAULTS, **(attrs or {})}
            return {k: a[k] for k in ("separator", "case_sensitive", "withsuffixtrie")}

        def _sig_text(attrs: dict[str, Any] | None) -> dict[str, Any]:
            a = {**TEXT_DEFAULTS, **(attrs or {})}
            return {k: a[k] for k in ("weight", "no_stem")}

        def _sig_vector(attrs: dict[str, Any] | None) -> dict[str, Any]:
            a = {**(attrs or {})}
            # Require these to exist if vector field is present
            return {k: a.get(k) for k in ("algorithm", "dims", "distance_metric", "datatype")}

        def _schema_signature(schema: dict[str, Any]) -> dict[str, Any]:
            # Order-independent, minimal signature
            sig: dict[str, Any] = {"index": _significant_index(schema.get("index", {})), "fields": {}}
            for f in schema.get("fields", []):
                name, ftype = f.get("name"), f.get("type")
                if not name:
                    continue
                if ftype == "tag":
                    sig["fields"][name] = {"type": "tag", "attrs": _sig_tag(f.get("attrs"))}
                elif ftype == "text":
                    sig["fields"][name] = {"type": "text", "attrs": _sig_text(f.get("attrs"))}
                elif ftype == "vector":
                    sig["fields"][name] = {"type": "vector", "attrs": _sig_vector(f.get("attrs"))}
                else:
                    # Unknown field types: compare by type only
                    sig["fields"][name] = {"type": ftype}
            return sig

        existing_index = await AsyncSearchIndex.from_existing(self.index_name, redis_url=self.redis_url)
        existing_schema = existing_index.schema.to_dict()
        current_schema = self.schema_dict

        existing_sig = _schema_signature(existing_schema)
        current_sig = _schema_signature(current_schema)

        if existing_sig != current_sig:
            # Add sigs to error message
            raise ServiceInitializationError(
                "Existing Redis index schema is incompatible with the current configuration.\n"
                f"Existing (significant): {json.dumps(existing_sig, indent=2, sort_keys=True)}\n"
                f"Current  (significant): {json.dumps(current_sig, indent=2, sort_keys=True)}\n"
                "Set overwrite_index=True to rebuild if this change is intentional."
            )

    async def _add(
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
            # Conversation defaults
            d.setdefault("conversation_id", self._conversation_id)

            # Logical requirement
            if "content" not in d:
                raise ServiceInvalidRequestError("add() requires a 'content' field in data")

            # Vector field requirement (only if schema has one)
            if self.vector_field_name:
                d.setdefault(self.vector_field_name, None)

            prepared.append(d)

        # Batch embed contents for every message
        if self.redis_vectorizer and self.vector_field_name:
            text_list = [d["content"] for d in prepared]
            embeddings = await self.redis_vectorizer.aembed_many(text_list, batch_size=len(text_list))
            for i, d in enumerate(prepared):
                vec = np.asarray(embeddings[i], dtype=np.float32).tobytes()
                field_name: str = self.vector_field_name
                d[field_name] = vec

        # Load all at once if supported
        await self.redis_index.load(prepared)
        return

    async def _redis_search(
        self,
        text: str,
        *,
        text_scorer: str = "BM25STD",
        filter_expression: Any | None = None,
        return_fields: list[str] | None = None,
        num_results: int = 10,
        alpha: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Runs a text or hybrid vector-text search with optional filters.

        Builds a TextQuery or HybridQuery and automatically ANDs partition filters to keep results scoped and safe.

        Args:
            text: Query text.
            text_scorer: Scorer to use for text ranking.
            filter_expression: Additional filter expression to AND with partition filters.
            return_fields: Fields to return in results.
            num_results: Maximum number of results.
            alpha: Hybrid balancing parameter when vectors are enabled.

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
            "conversation_id": self._conversation_id,
        })

        if filter_expression is not None:
            combined_filter = (combined_filter & filter_expression) if combined_filter else filter_expression

        # Choose return fields
        return_fields = (
            return_fields
            if return_fields is not None
            else ["content", "role", "application_id", "agent_id", "user_id", "thread_id"]
        )

        try:
            if self.redis_vectorizer and self.vector_field_name:
                # Build hybrid query: combine full-text and vector similarity
                vector = await self.redis_vectorizer.aembed(q)
                query = HybridQuery(
                    text=q,
                    text_field_name="content",
                    vector=vector,
                    vector_field_name=self.vector_field_name,
                    text_scorer=text_scorer,
                    filter_expression=combined_filter,
                    alpha=alpha,
                    dtype=self.redis_vectorizer.dtype,
                    num_results=num_results,
                    return_fields=return_fields,
                    stopwords=None,
                )
                hybrid_results = await self.redis_index.query(query)
                return cast(list[dict[str, Any]], hybrid_results)
            # Text-only search
            query = TextQuery(
                text=q,
                text_field_name="content",
                text_scorer=text_scorer,
                filter_expression=combined_filter,
                num_results=num_results,
                return_fields=return_fields,
                stopwords=None,
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
        # Track current conversation id (Agent passes conversation_id here)
        self._conversation_id = thread_id or self._conversation_id

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

        messages: list[dict[str, Any]] = []
        for message in messages_list:
            if (
                message.role.value in {Role.USER.value, Role.ASSISTANT.value, Role.SYSTEM.value}
                and message.text
                and message.text.strip()
            ):
                shaped: dict[str, Any] = {
                    "role": message.role.value,
                    "content": message.text,
                    "conversation_id": self._conversation_id,
                    "message_id": message.message_id,
                    "author_name": message.author_name,
                }
                messages.append(shaped)
        if messages:
            await self._add(data=messages)

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

        memories = await self._redis_search(text=input_text)
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
                "RedisProvider can only be used with one thread, when scope_to_per_operation_thread_id is True."
            )
