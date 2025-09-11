# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import MutableSequence, Sequence
from typing import Any, Final, Literal

from agent_framework import ChatMessage, Context, ContextProvider, TextContent
from agent_framework.exceptions import ServiceInitializationError

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


from redis import Redis
from redisvl.extensions.message_history import MessageHistory, SemanticMessageHistory
from redisvl.utils.utils import deserialize, serialize
from redisvl.utils.vectorize import HFTextVectorizer

DEFAULT_CONTEXT_PROMPT: Final[str] = "## Memories\nConsider the following memories when answering user questions:"


class RedisProvider(ContextProvider):
    """RedisProvider Class."""

    # ---- Configuration / public attrs (validated upstream by AFBaseModel) ----
    redis_url: str = "redis://localhost:6379"
    index_name: str = "chat_history"
    prefix: str = "memory"

    # Partitioning / filters (mirrors Mem0 provider semantics)
    application_id: str | None = None
    agent_id: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    scope_to_per_operation_thread_id: bool = False

    # Retrieval modes / knobs
    sequential: bool = False
    top_k: int = 10
    distance_threshold: float = 0.7

    # Embedding + index config
    model_name: str = "sentence-transformers/all-mpnet-base-v2"
    datatype: Literal["uint8", "int8", "float16", "float32", "float64", "bfloat16"] = "float32"

    # (Present for parity; not currently wired into SemanticMessageHistory creation)
    distance_metric: Literal["cosine", "ip", "l2"] = "cosine"
    algorithm: Literal["flat", "hnsw"] = "flat"

    # Prompt header
    context_prompt: str = DEFAULT_CONTEXT_PROMPT

    # ---- Internal state ----
    _message_history: Any = None  # MessageHistory | SemanticMessageHistory
    _redis_client: Any = None
    _per_operation_thread_id: str | None = None
    _current_prefix: str | None = None

    def __init__(
        self,
        *,
        redis_url: str = "redis://localhost:6379",
        index_name: str = "chat_history",
        prefix: str = "memory",
        application_id: str | None = None,
        agent_id: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        scope_to_per_operation_thread_id: bool = False,
        sequential: bool = False,
        top_k: int = 10,
        distance_threshold: float = 0.7,
        model_name: str = "sentence-transformers/all-mpnet-base-v2",
        datatype: Literal["uint8", "int8", "float16", "float32", "float64", "bfloat16"] = "float32",
        distance_metric: Literal["cosine", "ip", "l2"] = "cosine",
        algorithm: Literal["flat", "hnsw"] = "flat",
        context_prompt: str = DEFAULT_CONTEXT_PROMPT,
    ) -> None:
        super().__init__(
            redis_url=redis_url,  # type: ignore[reportCallIssue]
            index_name=index_name,  # type: ignore[reportCallIssue]
            prefix=prefix,  # type: ignore[reportCallIssue]
            application_id=application_id,  # type: ignore[reportCallIssue]
            agent_id=agent_id,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            user_id=user_id,  # type: ignore[reportCallIssue]
            scope_to_per_operation_thread_id=scope_to_per_operation_thread_id,  # type: ignore[reportCallIssue]
            sequential=sequential,  # type: ignore[reportCallIssue]
            top_k=top_k,  # type: ignore[reportCallIssue]
            distance_threshold=distance_threshold,  # type: ignore[reportCallIssue]
            model_name=model_name,  # type: ignore[reportCallIssue]
            datatype=datatype,  # type: ignore[reportCallIssue]
            distance_metric=distance_metric,  # type: ignore[reportCallIssue]
            algorithm=algorithm,  # type: ignore[reportCallIssue]
            context_prompt=context_prompt,  # type: ignore[reportCallIssue]
        )

        # Initialize Redis client and history implementation
        self._redis_client = Redis.from_url(url=self.redis_url)  # type: ignore[reportUnknownMemberType]
        # initialize per-operation thread id holder
        self._per_operation_thread_id = None
        # Create history with partition-aware prefix
        self._ensure_history()

    # ---------- Lifecycle ----------

    async def __aenter__(self) -> Self:
        # Nothing special to do for Redis client; keep for symmetry with Mem0Provider
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        # No-op; indexes/keys remain unless `close()` is called explicitly.
        return None

    async def thread_created(self, thread_id: str | None = None) -> None:
        # Track per-operation thread id when requested and adjust partition
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id
        self._ensure_history()
        return

    # ---------- Ingestion ----------

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Ingest messages into the partitioned Redis history."""
        self._validate_filters()
        self._validate_per_operation_thread_id(thread_id)
        self._per_operation_thread_id = self._per_operation_thread_id or thread_id
        self._ensure_history()

        messages_list = [new_messages] if isinstance(new_messages, ChatMessage) else list(new_messages)

        for message in messages_list:
            role = str(message.role)
            if role in {"user", "assistant", "system"}:
                text = message.text
                if text and text.strip():
                    # Store MIME in metadata for round-trip compatibility and include partition info
                    meta = {
                        "mime_type": "text/plain",
                        "role": role,
                        "application_id": self.application_id,
                        "agent_id": self.agent_id,
                        "user_id": self.user_id,
                        "thread_id": self._effective_thread_id,
                    }
                    self._message_history.add_message(
                        {"role": role, "content": text, "metadata": serialize(meta)}  # type: ignore[reportArgumentType]
                    )

    # ---------- Recall ----------

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Recall relevant or recent memories and return as a single instruction block."""
        self._validate_filters()
        self._ensure_history()
        messages_list = [messages] if isinstance(messages, ChatMessage) else list(messages)
        input_text = "\n".join(m.text for m in messages_list if m and m.text and m.text.strip())

        results = (
            self._get_recent(self.top_k)
            if self.sequential
            else self._get_relevant(prompt=input_text, top_k=self.top_k, distance_threshold=self.distance_threshold)
        )

        lines: list[str] = []
        for r in results:  # type: ignore[reportUnknownVariableType]
            # Best-effort metadata decode
            try:
                metadata = deserialize(r.get("metadata", {}))  # type: ignore[reportArgumentType]
            except Exception:
                metadata = {}

            mime = metadata.get("mime_type", "text/plain")
            if mime in {"text/plain", "text/markdown"}:
                lines.append(str(r.get("content", "")))
            elif mime == "application/json":
                try:
                    lines.append(str(deserialize(r.get("content", "{}"))))  # type: ignore[reportArgumentType]
                except Exception:
                    lines.append(str(r.get("content", "")))
            else:
                # Unknown MIME → stringify content
                lines.append(str(r.get("content", "")))

        if not lines:
            return Context(contents=None)

        content = TextContent(f"{self.context_prompt}\n" + "\n".join(lines))
        return Context(contents=[content])

    # ---------- Optional convenience API ----------

    async def add(self, *, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Convenience method to add a single user-text memory with optional metadata."""
        self._validate_filters()
        self._ensure_history()
        md = {
            "mime_type": "text/plain",
            "application_id": self.application_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "thread_id": self._effective_thread_id,
            **(metadata or {}),
        }
        role = md.get("role", "user")
        md["role"] = role
        self._message_history.add_message(
            {"role": role, "content": text, "metadata": serialize(md)}  # type: ignore[reportArgumentType]
        )

    async def query(
        self,
        query: str,
        *,
        top_k: int | None = None,
        distance_threshold: float | None = None,
        sequential: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience method to run a raw recent/semantic query against RedisVL.

        Returns raw RedisVL records (dicts) for maximum flexibility.
        """
        self._validate_filters()
        self._ensure_history()
        if sequential or (sequential is None and self.sequential):
            return list(self._get_recent(top_k or self.top_k))
        return list(
            self._get_relevant(
                prompt=query,
                top_k=top_k or self.top_k,
                distance_threshold=distance_threshold or self.distance_threshold,
            )
        )

    async def clear(self) -> None:
        """Clear all entries from the underlying message history while preserving index structures."""
        self._ensure_history()
        self._message_history.clear()

    async def close(self) -> None:
        """Placeholder."""
        self._ensure_history()
        self._message_history.delete()

    # ---------- Internal helpers ----------

    def _get_recent(self, top_k: int) -> list[dict[str, Any]]:
        return self._message_history.get_recent(top_k=top_k, raw=False)  # type: ignore[no-any-return]

    def _get_relevant(self, *, prompt: str, top_k: int, distance_threshold: float) -> list[dict[str, Any]]:
        return self._message_history.get_relevant(  # type: ignore[no-any-return]
            prompt=prompt,
            top_k=top_k,
            distance_threshold=distance_threshold,
            raw=False,
        )

    # ---------- Partition helpers ----------

    @property
    def _effective_thread_id(self) -> str | None:
        return self._per_operation_thread_id if self.scope_to_per_operation_thread_id else self.thread_id

    def _compute_partition_prefix(self) -> str:
        parts: list[str] = [self.prefix]
        if self.application_id:
            parts.append(f"app:{self.application_id}")
        if self.agent_id:
            parts.append(f"agent:{self.agent_id}")
        if self.user_id:
            parts.append(f"user:{self.user_id}")
        if tid := self._effective_thread_id:
            parts.append(f"thread:{tid}")
        return ":".join(parts)

    def _ensure_history(self) -> None:
        desired_prefix = self._compute_partition_prefix()
        if self._message_history is not None and self._current_prefix == desired_prefix:
            return
        # (Re)create history with desired prefix
        if self.sequential:
            self._message_history = MessageHistory(
                name=self.index_name, prefix=desired_prefix, redis_client=self._redis_client
            )
        else:
            vectorizer = HFTextVectorizer(model=self.model_name, dtype=self.datatype)
            self._message_history = SemanticMessageHistory(
                name=self.index_name,
                prefix=desired_prefix,
                vectorizer=vectorizer,
                distance_threshold=self.distance_threshold,
                redis_client=self._redis_client,
            )
        self._current_prefix = desired_prefix

    def _validate_filters(self) -> None:
        if (
            not self.agent_id
            and not self.user_id
            and not self.application_id
            and not self.thread_id
            and not (self.scope_to_per_operation_thread_id and self._per_operation_thread_id)
        ):
            raise ServiceInitializationError(
                "At least one of the filters: agent_id, user_id, application_id, or thread_id is required."
            )

    def _validate_per_operation_thread_id(self, thread_id: str | None) -> None:
        if (
            self.scope_to_per_operation_thread_id
            and thread_id
            and self._per_operation_thread_id
            and thread_id != self._per_operation_thread_id
        ):
            raise ValueError(
                "RedisProvider can only be used with one thread at a time "
                "when scope_to_per_operation_thread_id is True."
            )
