# Copyright (c) Microsoft. All rights reserved.

"""New-pattern Redis context provider using BaseContextProvider.

This module provides ``RedisContextProvider``, built on the new
:class:`BaseContextProvider` hooks pattern.
"""

from __future__ import annotations

import json
import sys
from functools import reduce
from operator import and_
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

import numpy as np
from agent_framework import Message
from agent_framework._sessions import AgentSession, BaseContextProvider, SessionContext
from agent_framework.exceptions import (
    AgentException,
    ServiceInitializationError,
    ServiceInvalidRequestError,
)
from redisvl.index import AsyncSearchIndex
from redisvl.query import HybridQuery, TextQuery
from redisvl.query.filter import FilterExpression, Tag
from redisvl.utils.token_escaper import TokenEscaper
from redisvl.utils.vectorize import BaseVectorizer

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun


class RedisContextProvider(BaseContextProvider):
    """Redis context provider using the new BaseContextProvider hooks pattern.

    Stores context in Redis and retrieves scoped context via full-text or
    optional hybrid vector search.
    """

    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"
    DEFAULT_SOURCE_ID: ClassVar[str] = "redis"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        redis_url: str = "redis://localhost:6379",
        index_name: str = "context",
        prefix: str = "context",
        *,
        redis_vectorizer: BaseVectorizer | None = None,
        vector_field_name: str | None = None,
        vector_algorithm: Literal["flat", "hnsw"] | None = None,
        vector_distance_metric: Literal["cosine", "ip", "l2"] | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        context_prompt: str | None = None,
        redis_index: Any = None,
        overwrite_index: bool = False,
    ):
        """Create a Redis Context Provider.

        Args:
            source_id: Unique identifier for this provider instance.
            redis_url: The Redis server URL.
            index_name: The name of the Redis index.
            prefix: The prefix for all keys in the Redis database.
            redis_vectorizer: The vectorizer to use for Redis.
            vector_field_name: The name of the vector field in Redis.
            vector_algorithm: The algorithm to use for vector search.
            vector_distance_metric: The distance metric to use for vector search.
            application_id: The application ID to scope the context.
            agent_id: The agent ID to scope the context.
            user_id: The user ID to scope the context.
            context_prompt: The context prompt to use for the provider.
            redis_index: The Redis index to use for the provider.
            overwrite_index: Whether to overwrite the existing Redis index.
        """
        super().__init__(source_id)
        self.redis_url = redis_url
        self.index_name = index_name
        self.prefix = prefix
        if redis_vectorizer is not None and not isinstance(redis_vectorizer, BaseVectorizer):
            raise AgentException(
                f"The redis vectorizer is not a valid type, got: {type(redis_vectorizer)}, expected: BaseVectorizer."
            )
        self.redis_vectorizer = redis_vectorizer
        self.vector_field_name = vector_field_name
        self.vector_algorithm: Literal["flat", "hnsw"] | None = vector_algorithm
        self.vector_distance_metric: Literal["cosine", "ip", "l2"] | None = vector_distance_metric
        self.application_id = application_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self.overwrite_index = overwrite_index
        self._token_escaper: TokenEscaper = TokenEscaper()
        self._index_initialized: bool = False
        self._schema_dict: dict[str, Any] | None = None
        self.redis_index = redis_index or AsyncSearchIndex.from_dict(
            self.schema_dict, redis_url=self.redis_url, validate_on_load=True
        )

    # -- Hooks pattern ---------------------------------------------------------

    @override
    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Retrieve scoped context from Redis and add to the session context."""
        self._validate_filters()
        input_text = "\n".join(msg.text for msg in context.input_messages if msg and msg.text and msg.text.strip())
        if not input_text.strip():
            return

        memories = await self._redis_search(text=input_text, session_id=context.session_id)
        line_separated_memories = "\n".join(
            str(memory.get("content", "")) for memory in memories if memory.get("content")
        )
        if line_separated_memories:
            context.extend_messages(
                self.source_id,
                [Message(role="user", text=f"{self.context_prompt}\n{line_separated_memories}")],
            )

    @override
    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Store request/response messages to Redis for future retrieval."""
        self._validate_filters()

        messages_to_store: list[Message] = list(context.input_messages)
        if context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)

        messages: list[dict[str, Any]] = []
        for message in messages_to_store:
            if message.role in {"user", "assistant", "system"} and message.text and message.text.strip():
                shaped: dict[str, Any] = {
                    "role": message.role,
                    "content": message.text,
                    "conversation_id": context.session_id,
                    "message_id": message.message_id,
                    "author_name": message.author_name,
                }
                messages.append(shaped)
        if messages:
            await self._add(data=messages, session_id=context.session_id)

    # -- Internal methods (ported from RedisProvider) --------------------------

    @property
    def schema_dict(self) -> dict[str, Any]:
        """Get the Redis schema dictionary, computing and caching it on first access."""
        if self._schema_dict is None:
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
        """Builds a combined filter expression from simple equality tags."""
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
        """Builds the RediSearch schema configuration dictionary."""
        fields: list[dict[str, Any]] = [
            {"name": "role", "type": "tag"},
            {"name": "mime_type", "type": "tag"},
            {"name": "content", "type": "text"},
            {"name": "conversation_id", "type": "tag"},
            {"name": "message_id", "type": "tag"},
            {"name": "author_name", "type": "tag"},
            {"name": "application_id", "type": "tag"},
            {"name": "agent_id", "type": "tag"},
            {"name": "user_id", "type": "tag"},
            {"name": "thread_id", "type": "tag"},
        ]
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
            "index": {"name": index_name, "prefix": prefix, "key_separator": ":", "storage_type": "hash"},
            "fields": fields,
        }

    async def _ensure_index(self) -> None:
        """Initialize the search index."""
        if self._index_initialized:
            return
        index_exists = await self.redis_index.exists()
        if not self.overwrite_index and index_exists:
            await self._validate_schema_compatibility()
        await self.redis_index.create(overwrite=self.overwrite_index, drop=False)
        self._index_initialized = True

    async def _validate_schema_compatibility(self) -> None:
        """Validate that existing index schema matches current configuration."""
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
            return {k: a.get(k) for k in ("algorithm", "dims", "distance_metric", "datatype")}

        def _schema_signature(schema: dict[str, Any]) -> dict[str, Any]:
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
                    sig["fields"][name] = {"type": ftype}
            return sig

        existing_index = await AsyncSearchIndex.from_existing(self.index_name, redis_url=self.redis_url)
        existing_schema = existing_index.schema.to_dict()
        current_schema = self.schema_dict
        existing_sig = _schema_signature(existing_schema)
        current_sig = _schema_signature(current_schema)
        if existing_sig != current_sig:
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
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Inserts one or many documents with partition fields populated."""
        self._validate_filters()
        await self._ensure_index()
        docs = data if isinstance(data, list) else [data]

        prepared: list[dict[str, Any]] = []
        for doc in docs:
            d = dict(doc)
            d.setdefault("application_id", self.application_id)
            d.setdefault("agent_id", self.agent_id)
            d.setdefault("user_id", self.user_id)
            d.setdefault("thread_id", session_id)
            d.setdefault("conversation_id", session_id)
            if "content" not in d:
                raise ServiceInvalidRequestError("add() requires a 'content' field in data")
            if self.vector_field_name:
                d.setdefault(self.vector_field_name, None)
            prepared.append(d)

        if self.redis_vectorizer and self.vector_field_name:
            text_list = [d["content"] for d in prepared]
            embeddings = await self.redis_vectorizer.aembed_many(text_list, batch_size=len(text_list))
            for i, d in enumerate(prepared):
                vec = np.asarray(embeddings[i], dtype=np.float32).tobytes()
                field_name: str = self.vector_field_name
                d[field_name] = vec

        await self.redis_index.load(prepared)

    async def _redis_search(
        self,
        text: str,
        *,
        session_id: str | None = None,
        text_scorer: str = "BM25STD",
        filter_expression: Any | None = None,
        return_fields: list[str] | None = None,
        num_results: int = 10,
        alpha: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Runs a text or hybrid vector-text search with optional filters."""
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
            "thread_id": session_id,
            "conversation_id": session_id,
        })
        if filter_expression is not None:
            combined_filter = (combined_filter & filter_expression) if combined_filter else filter_expression

        return_fields = (
            return_fields
            if return_fields is not None
            else ["content", "role", "application_id", "agent_id", "user_id", "thread_id"]
        )

        try:
            if self.redis_vectorizer and self.vector_field_name:
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
        except Exception as exc:  # pragma: no cover
            raise ServiceInvalidRequestError(f"Redis text search failed: {exc}") from exc

    def _validate_filters(self) -> None:
        """Validates that at least one filter is provided."""
        if not self.agent_id and not self.user_id and not self.application_id:
            raise ServiceInitializationError(
                "At least one of the filters: agent_id, user_id, or application_id is required."
            )

    async def search_all(self, page_size: int = 200) -> list[dict[str, Any]]:
        """Returns all documents in the index."""
        from redisvl.query import FilterQuery

        out: list[dict[str, Any]] = []
        async for batch in self.redis_index.paginate(
            FilterQuery(FilterExpression("*"), return_fields=[], num_results=page_size),
            page_size=page_size,
        ):
            out.extend(batch)
        return out

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""


__all__ = ["RedisContextProvider"]
