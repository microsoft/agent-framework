# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import MutableSequence, Sequence
from typing import Any, Literal

from agent_framework import ChatMessage, Context, ContextProvider, TextContent
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from redis import Redis
    from redisvl.extensions.message_history import MessageHistory, SemanticMessageHistory
    from redisvl.utils.utils import deserialize, serialize
    from redisvl.utils.vectorize import HFTextVectorizer
except ImportError as e:
    raise ImportError("To use Redis Memory RedisVL must be installed. Run `pip install ***`") from e


class RedisMemoryConfig(BaseModel):
    """Configuration for Redis-based vector memory.

    This class defines the configuration options for using Redis as a vector memory store,
    supporting semantic memory. It allows customization of the Redis connection, index settings,
    similarity search parameters, and embedding model.
    """

    redis_url: str = Field(default="redis://localhost:6379", description="url of the Redis instance")
    index_name: str = Field(default="chat_history", description="Name of the Redis collection")
    prefix: str = Field(default="memory", description="prefix of the Redis collection")
    sequential: bool = Field(
        default=False, description="ignore semantic similarity and simply return memories in sequential order"
    )
    distance_metric: Literal["cosine", "ip", "l2"] = "cosine"
    algorithm: Literal["flat", "hnsw"] = "flat"
    top_k: int = Field(default=10, description="Number of results to return in queries")
    datatype: Literal["uint8", "int8", "float16", "float32", "float64", "bfloat16"] = "float32"
    distance_threshold: float = Field(default=0.7, description="Minimum similarity score threshold")
    model_name: str = Field(default="sentence-transformers/all-mpnet-base-v2", description="Embedding model name")


DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"


class RedisMemory(ContextProvider):
    context_prompt: str = DEFAULT_CONTEXT_PROMPT

    def __init__(self, config: RedisMemoryConfig | None = None, *, context_prompt: str | None = None) -> None:
        """Initialize Redis-backed memory provider.

        Args:
            config: Configuration for Redis memory.
            context_prompt: Optional prompt header to prepend to retrieved memories.
        """
        super().__init__(context_prompt=context_prompt or DEFAULT_CONTEXT_PROMPT)  # type: ignore[reportCallIssue]
        self.config = config or RedisMemoryConfig()

        client = Redis.from_url(url=self.config.redis_url)  # type: ignore[reportUnknownMemberType]
        if self.config.sequential:
            self._message_history = MessageHistory(
                name=self.config.index_name, prefix=self.config.prefix, redis_client=client
            )
        else:
            vectorizer = HFTextVectorizer(model=self.config.model_name, dtype=self.config.datatype)
            self._message_history = SemanticMessageHistory(
                name=self.config.index_name,
                prefix=self.config.prefix,
                vectorizer=vectorizer,
                distance_threshold=self.config.distance_threshold,
                redis_client=client,
            )

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Store recent user/system/assistant messages into Redis."""
        messages_list = [new_messages] if isinstance(new_messages, ChatMessage) else list(new_messages)

        # Persist only textual messages for now
        for message in messages_list:
            role = str(message.role)
            if role in {"user", "assistant", "system"}:
                text = message.text
                if text and text.strip():
                    self._message_history.add_message({
                        "role": role,
                        "content": text,
                        "metadata": serialize({"mime_type": "text/plain"}),
                    })

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Query Redis for relevant memories and return them as an additional system instruction."""
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)
        input_text = "\n".join(msg.text for msg in messages_list if msg and msg.text and msg.text.strip())

        results = (
            self._get_recent(self.config.top_k)
            if self.config.sequential
            else self._get_relevant(
                prompt=input_text, top_k=self.config.top_k, distance_threshold=self.config.distance_threshold
            )
        )

        # Deserialize message contents and render as plain text lines
        lines: list[str] = []
        for r in results:  # type: ignore[reportUnknownVariableType]
            metadata = deserialize(r.get("metadata", {}))  # type: ignore[reportArgumentType]

            mime = metadata.get("mime_type", "text/plain")
            if mime in {"text/plain", "text/markdown"}:
                lines.append(str(r.get("content", "")))
            elif mime == "application/json":
                lines.append(str(deserialize(r.get("content", "{}"))))  # type: ignore[reportArgumentType]

        if not lines:
            return Context(contents=None)

        content = TextContent(f"{self.context_prompt}\n" + "\n".join(lines))
        return Context(contents=[content])

    # region Optional convenience API (not required by ContextProvider)
    async def add(self, *, text: str, metadata: dict[str, Any] | None = None) -> None:
        metadata = {"mime_type": "text/plain", **(metadata or {})}
        self._message_history.add_message(
            {"role": "user", "content": text, "metadata": serialize(metadata)}  # type: ignore[reportArgumentType]
        )

    async def query(
        self,
        query: str,
        *,
        top_k: int | None = None,
        distance_threshold: float | None = None,
        sequential: bool | None = None,
    ) -> list[dict[str, Any]]:
        if sequential or (sequential is None and self.config.sequential):
            return list(self._get_recent(top_k or self.config.top_k))
        return list(
            self._get_relevant(
                prompt=query,
                top_k=top_k or self.config.top_k,
                distance_threshold=distance_threshold or self.config.distance_threshold,
            )
        )

    async def clear(self) -> None:
        self._message_history.clear()

    async def close(self) -> None:
        self._message_history.delete()

    # region Internal helpers
    def _get_recent(self, top_k: int) -> list[dict[str, Any]]:
        return self._message_history.get_recent(top_k=top_k, raw=False)  # type: ignore[no-any-return]

    def _get_relevant(self, *, prompt: str, top_k: int, distance_threshold: float) -> list[dict[str, Any]]:
        return self._message_history.get_relevant(  # type: ignore[no-any-return]
            prompt=prompt,
            top_k=top_k,
            distance_threshold=distance_threshold,
            raw=False,
        )
