# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, cast

from agent_framework import (
    Message,
    SecretString,
    SupportsChatGetResponse,
    SupportsGetEmbeddings,
)
from agent_framework._telemetry import mark_feature_used
from agent_framework.exceptions import IntegrationInvalidResponseException
from psycopg import AsyncConnection, Error

from ._feature_usage import FeatureIndex
from ._memory_store import _PostgresMemoryStore  # pyright: ignore[reportPrivateUsage]
from ._memory_types import (
    _DERIVED_MEMORY_TYPES,  # pyright: ignore[reportPrivateUsage]
    PostgresMemoryClientOptions,
    PostgresMemoryRecord,
    PostgresMemoryScope,
    PostgresMemoryType,
)
from ._vector_store import PostgresClient, _create_client  # pyright: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_TYPES = (
    PostgresMemoryType.FACT,
    PostgresMemoryType.PROCEDURAL,
    PostgresMemoryType.EPISODIC,
)


@dataclass(frozen=True, slots=True)
class _ExtractedMemory:
    content: str
    memory_type: PostgresMemoryType
    confidence: float
    salience: float | None
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReconciliationDecision:
    superseded_id: int
    winner_id: int
    reason: str


class PostgresMemoryClient:
    """Store, retrieve, and transform durable agent memory with PostgreSQL.

    The client stores raw turns separately from fact, procedural, and episodic
    memories. It also maintains thread and user summaries, supports hybrid
    vector/full-text retrieval, and preserves supersession history when
    reconciling contradictions.
    """

    def __init__(
        self,
        *,
        embedding_generator: SupportsGetEmbeddings[str, list[float], Any],
        chat_client: SupportsChatGetResponse[Any],
        connection_string: str | SecretString | None = None,
        client: PostgresClient | None = None,
        options: PostgresMemoryClientOptions | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a memory client without connecting to PostgreSQL.

        Args:
            embedding_generator: Embedding client used for storage and retrieval.
            chat_client: Chat client used for extraction, summaries, and reconciliation.
            connection_string: Psycopg conninfo or URI for an owned lazy pool. Falls back to
                ``POSTGRES_CONNECTION_STRING`` in the selected .env file or process environment.
            client: Open caller-owned Psycopg async connection or pool.
            options: Memory storage and processing options.
            env_file_path: Optional .env file to read; cannot be combined with an injected client.
            env_file_encoding: Encoding of the .env file; cannot be combined with an injected client.
        """
        self._embedding_generator = embedding_generator
        self._chat_client = chat_client
        self.options = options or PostgresMemoryClientOptions()
        if self.options.auto_process and isinstance(client, AsyncConnection):
            raise ValueError(
                "auto_process requires a connection pool or connection string; "
                "set auto_process=False when borrowing one AsyncConnection."
            )
        self._client = _create_client(
            connection_string,
            client=client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self._store = _PostgresMemoryStore(self._client, self.options)
        self._processing_locks: dict[str, asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    async def ensure_schema(self) -> None:
        """Create the memory tables and indexes when absent.

        The configured PostgreSQL schema and pgvector extension must already exist.
        """
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        await self._store.ensure_schema()

    async def upsert_memory(self, scope: PostgresMemoryScope, role: str, content: str) -> int:
        """Store one raw conversation turn.

        Args:
            scope: Durable user and thread scope.
            role: Turn role: user, agent/assistant, tool, or system.
            content: Turn text.

        Returns:
            Database-generated turn identifier.
        """
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        _require_thread_scope(scope)
        normalized_role = _normalize_role(role)
        normalized_content = _require_text(content, "content")
        await self._ensure_schema_if_enabled()
        embedding = await self._generate_embedding(normalized_content) if self.options.enable_turn_embeddings else None
        turn_id = await self._store.insert_turn(scope, normalized_role, normalized_content, embedding)
        if self.options.auto_process:
            self._schedule_background_processing(scope)
        return turn_id

    async def get_thread(
        self,
        scope: PostgresMemoryScope,
        *,
        recent_k: int | None = None,
    ) -> list[PostgresMemoryRecord]:
        """Get raw turns for one thread in chronological order."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        _require_thread_scope(scope)
        if recent_k is not None and recent_k <= 0:
            raise ValueError("recent_k must be greater than zero.")
        await self._ensure_schema_if_enabled()
        return await self._store.get_thread(scope, recent_k)

    async def get_memories(
        self,
        scope: PostgresMemoryScope,
        *,
        memory_types: Sequence[PostgresMemoryType] | None = None,
        limit: int = 50,
        min_confidence: float = 0,
    ) -> list[PostgresMemoryRecord]:
        """Get active derived memories for a user, optionally constrained to a thread."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        selected_types = _validate_retrieval_arguments(memory_types, limit, min_confidence)
        await self._ensure_schema_if_enabled()
        return await self._store.get_active_memories(scope, selected_types, limit, min_confidence)

    async def search(
        self,
        scope: PostgresMemoryScope,
        search_terms: str,
        *,
        memory_types: Sequence[PostgresMemoryType] | None = None,
        top_k: int = 5,
        min_confidence: float = 0.7,
    ) -> list[PostgresMemoryRecord]:
        """Search active derived memories using vector and PostgreSQL full-text ranking."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        normalized_terms = _require_text(search_terms, "search_terms")
        selected_types = _validate_retrieval_arguments(memory_types, top_k, min_confidence)
        await self._ensure_schema_if_enabled()
        embedding = await self._generate_embedding(normalized_terms)
        candidate_count = (
            max(top_k, self.options.reranking_candidate_count) if self.options.enable_azure_ai_reranking else top_k
        )
        candidates = await self._store.search(
            scope,
            normalized_terms,
            embedding,
            selected_types,
            candidate_count,
            min_confidence,
        )
        if not self.options.enable_azure_ai_reranking or len(candidates) <= 1:
            return candidates

        try:
            reranked = await self._store.rerank(
                normalized_terms,
                candidates,
                self.options.azure_ai_reranker_model,
            )
        except Error:
            logger.warning("Azure AI memory reranking failed; returning hybrid retrieval order.", exc_info=True)
            return candidates[:top_k]

        candidates_by_id = {candidate.id: candidate for candidate in candidates}
        selected_ids: set[int] = set()
        results: list[PostgresMemoryRecord] = []
        for rerank_result in sorted(reranked, key=lambda result: result.rank):
            candidate = candidates_by_id.get(rerank_result.id)
            if candidate is not None and candidate.id not in selected_ids:
                selected_ids.add(candidate.id)
                results.append(replace(candidate, reranker_score=rerank_result.relevance_score))
                if len(results) == top_k:
                    return results

        for candidate in candidates:
            if candidate.id not in selected_ids:
                selected_ids.add(candidate.id)
                results.append(candidate)
                if len(results) == top_k:
                    break
        return results

    async def get_user_summary(self, scope: PostgresMemoryScope) -> PostgresMemoryRecord | None:
        """Get the latest cross-thread user summary."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        await self._ensure_schema_if_enabled()
        record, _ = await self._store.get_latest_summary(scope.to_user_scope(), PostgresMemoryType.USER_SUMMARY)
        return record

    async def extract_memories(self, scope: PostgresMemoryScope) -> int:
        """Extract typed memories from turns not previously processed for the thread."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        _require_thread_scope(scope)
        await self._ensure_schema_if_enabled()
        async with self._get_processing_lock(scope, include_thread=True):
            return await self._extract_memories_core(scope)

    async def _extract_memories_core(self, scope: PostgresMemoryScope) -> int:
        scope_key = self._store.compute_scope_key(scope, include_thread=True)
        state = await self._store.get_processing_state(scope_key)
        turns = await self._store.get_turns_after(scope, state.fact_through_turn_id)
        if not turns:
            return 0

        existing_memories = await self._store.get_active_memories(
            scope.to_user_scope(),
            _DEFAULT_MEMORY_TYPES,
            50,
            0,
        )
        response_text = await self._get_chat_response_text(
            _build_extract_messages(self.options.prompts.extract_memories, turns, existing_memories)
        )
        candidates = _parse_extracted_memories(response_text)
        inserted = 0
        for candidate in candidates:
            embedding = await self._generate_embedding(candidate.content)
            duplicate = await self._store.find_duplicate(
                scope.to_user_scope(),
                candidate.memory_type,
                _compute_content_hash(candidate.content),
                embedding,
                self.options.dedupe_similarity_threshold,
            )
            if duplicate is not None:
                continue
            expires_at = (
                datetime.now(timezone.utc) + self.options.episodic_memory_ttl
                if candidate.memory_type is PostgresMemoryType.EPISODIC and self.options.episodic_memory_ttl is not None
                else None
            )
            await self._store.insert_derived_memory(
                scope,
                candidate.memory_type,
                candidate.content,
                candidate.confidence,
                candidate.salience,
                candidate.tags,
                embedding,
                expires_at,
            )
            inserted += 1

        await self._store.upsert_processing_state(
            scope_key,
            replace(
                state,
                fact_through_turn_id=turns[-1].id,
                extraction_runs=state.extraction_runs + 1,
            ),
        )
        return inserted

    async def generate_thread_summary(self, scope: PostgresMemoryScope) -> PostgresMemoryRecord | None:
        """Generate or incrementally update a summary for one thread."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        _require_thread_scope(scope)
        await self._ensure_schema_if_enabled()
        async with self._get_processing_lock(scope, include_thread=True):
            return await self._generate_thread_summary_core(scope)

    async def _generate_thread_summary_core(
        self,
        scope: PostgresMemoryScope,
    ) -> PostgresMemoryRecord | None:
        previous, covers_through = await self._store.get_latest_summary(scope, PostgresMemoryType.SUMMARY)
        turns = await self._store.get_turns_after(scope, covers_through)
        if not turns:
            return previous
        response_text = (
            await self._get_chat_response_text(
                _build_thread_summary_messages(
                    self.options.prompts.thread_summary,
                    previous.content if previous is not None else None,
                    turns,
                )
            )
        ).strip()
        if not response_text:
            return previous
        embedding = await self._generate_embedding(response_text)
        latest_turn_id = turns[-1].id
        summary_id = await self._store.insert_summary(
            scope,
            PostgresMemoryType.SUMMARY,
            response_text,
            embedding,
            latest_turn_id,
        )
        if summary_id is None:
            latest, _ = await self._store.get_latest_summary(scope, PostgresMemoryType.SUMMARY)
            return latest
        scope_key = self._store.compute_scope_key(scope, include_thread=True)
        state = await self._store.get_processing_state(scope_key)
        await self._store.upsert_processing_state(
            scope_key,
            replace(state, summary_through_turn_id=latest_turn_id),
        )
        return _create_summary_record(summary_id, scope, PostgresMemoryType.SUMMARY, response_text)

    async def generate_user_summary(self, scope: PostgresMemoryScope) -> PostgresMemoryRecord | None:
        """Generate or incrementally update the cross-thread user summary."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        await self._ensure_schema_if_enabled()
        user_scope = scope.to_user_scope()
        async with self._get_processing_lock(user_scope, include_thread=False):
            return await self._generate_user_summary_core(user_scope)

    async def _generate_user_summary_core(
        self,
        user_scope: PostgresMemoryScope,
    ) -> PostgresMemoryRecord | None:
        previous, _ = await self._store.get_latest_summary(user_scope, PostgresMemoryType.USER_SUMMARY)
        _, covers_through_turn_id = await self._store.get_turn_stats_after(
            user_scope,
            0,
            include_thread=False,
        )
        memories = await self._store.get_active_memories(user_scope, _DEFAULT_MEMORY_TYPES, 100, 0.5)
        summaries = await self._store.get_recent_thread_summaries(user_scope, 25)
        if not memories and not summaries:
            return previous
        response_text = (
            await self._get_chat_response_text(
                _build_user_summary_messages(
                    self.options.prompts.user_summary,
                    previous.content if previous is not None else None,
                    memories,
                    summaries,
                )
            )
        ).strip()
        if not response_text:
            return previous
        embedding = await self._generate_embedding(response_text)
        summary_id = await self._store.insert_summary(
            user_scope,
            PostgresMemoryType.USER_SUMMARY,
            response_text,
            embedding,
            covers_through_turn_id,
        )
        if summary_id is None:
            latest, _ = await self._store.get_latest_summary(user_scope, PostgresMemoryType.USER_SUMMARY)
            return latest
        scope_key = self._store.compute_scope_key(user_scope, include_thread=False)
        state = await self._store.get_processing_state(scope_key)
        await self._store.upsert_processing_state(
            scope_key,
            replace(state, user_summary_through_turn_id=covers_through_turn_id),
        )
        return _create_summary_record(
            summary_id,
            user_scope,
            PostgresMemoryType.USER_SUMMARY,
            response_text,
        )

    async def reconcile(self, scope: PostgresMemoryScope, *, pool_size: int | None = None) -> int:
        """Reconcile contradictions among recent active memories."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        limit = pool_size if pool_size is not None else self.options.reconciliation_pool_size
        if not 2 <= limit <= 500:
            raise ValueError("pool_size must be between 2 and 500.")
        await self._ensure_schema_if_enabled()
        user_scope = scope.to_user_scope()
        async with self._get_processing_lock(user_scope, include_thread=False):
            return await self._reconcile_core(user_scope, limit)

    async def _reconcile_core(self, user_scope: PostgresMemoryScope, limit: int) -> int:
        memories = await self._store.get_active_memories(user_scope, _DEFAULT_MEMORY_TYPES, limit, 0)
        if len(memories) < 2:
            return 0
        response_text = await self._get_chat_response_text(
            _build_reconcile_messages(self.options.prompts.reconcile, memories)
        )
        decisions = _parse_reconciliation_decisions(response_text)
        valid_ids = {memory.id for memory in memories}
        reconciled = 0
        for decision in decisions:
            if (
                decision.superseded_id == decision.winner_id
                or decision.superseded_id not in valid_ids
                or decision.winner_id not in valid_ids
            ):
                continue
            if await self._store.mark_superseded(
                decision.superseded_id,
                decision.winner_id,
                decision.reason,
            ):
                reconciled += 1
        return reconciled

    async def process_now(self, scope: PostgresMemoryScope) -> None:
        """Run extraction, summaries, and reconciliation immediately."""
        self._ensure_open()
        mark_feature_used(FeatureIndex.POSTGRES_MEMORY)
        _require_thread_scope(scope)
        await self._ensure_schema_if_enabled()
        async with self._get_processing_lock(scope, include_thread=True):
            await self._extract_memories_core(scope)
            await self._generate_thread_summary_core(scope)
            await self.generate_user_summary(scope)
            await self.reconcile(scope.to_user_scope())

    async def flush(self, timeout: float | None = None) -> None:
        """Wait until currently scheduled background processing completes.

        Args:
            timeout: Maximum seconds to wait. ``None`` waits without a time limit.
                Reaching the timeout leaves unfinished processing running in the background.
        """
        self._ensure_open()
        if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
            raise ValueError("timeout must be a finite, non-negative number or None.")
        if timeout is not None:
            deadline = asyncio.get_running_loop().time() + timeout
            while self._background_tasks:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return
                done, pending = await asyncio.wait(tuple(self._background_tasks), timeout=remaining)
                self._background_tasks.difference_update(done)
                if pending:
                    return
            return
        while self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks))

    async def close(self, timeout: float | None = None) -> None:
        """Drain background work and close resources owned by this client.

        Args:
            timeout: Maximum seconds to wait for background work. ``None`` waits
                without a time limit. Work still pending after a timeout is cancelled
                before database resources are closed.
        """
        if self._closed:
            return
        await self.flush(timeout=timeout)
        pending = tuple(self._background_tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            self._background_tasks.difference_update(pending)
        await self._client.close()
        self._closed = True

    async def __aenter__(self) -> PostgresMemoryClient:
        """Create the memory tables and return this client."""
        try:
            await self.ensure_schema()
        except BaseException:
            if self._client.owned:
                await self._client.close()
                self._closed = True
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Close resources owned by this client."""
        await self.close()

    async def _ensure_schema_if_enabled(self) -> None:
        if self.options.ensure_schema_on_first_use:
            await self._store.ensure_schema()

    async def _generate_embedding(self, text: str) -> list[float]:
        result = await self._embedding_generator.get_embeddings([text])
        if len(result) != 1:
            raise IntegrationInvalidResponseException("The embedding client must return exactly one embedding.")
        vector = result[0].vector
        if isinstance(vector, (str, bytes, bytearray)) or not isinstance(vector, Sequence):
            raise IntegrationInvalidResponseException("The embedding client returned a non-numeric vector.")
        try:
            normalized = [float(component) for component in vector]
        except (TypeError, ValueError) as exc:
            raise IntegrationInvalidResponseException("The embedding client returned a non-numeric vector.") from exc
        if len(normalized) != self.options.embedding_dimensions:
            raise IntegrationInvalidResponseException(
                f"The embedding client returned {len(normalized)} dimensions; "
                f"expected {self.options.embedding_dimensions}."
            )
        if any(not math.isfinite(component) for component in normalized):
            raise IntegrationInvalidResponseException("The embedding client returned a non-finite vector.")
        return normalized

    async def _get_chat_response_text(self, messages: Sequence[Message]) -> str:
        response = await self._chat_client.get_response(messages)
        return response.text or ""

    def _schedule_background_processing(self, scope: PostgresMemoryScope) -> None:
        task = asyncio.create_task(
            self._run_background_processing(scope),
            name=f"postgres-memory-{self._store.compute_scope_key(scope, include_thread=True)[:12]}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run_background_processing(self, scope: PostgresMemoryScope) -> None:
        await asyncio.sleep(0)
        try:
            await self._process_due_steps(scope)
        except Exception:
            logger.warning(
                "Background PostgreSQL memory processing failed for user %r, thread %r.",
                scope.user_id,
                scope.thread_id,
                exc_info=True,
            )

    async def _process_due_steps(self, scope: PostgresMemoryScope) -> None:
        async with self._get_processing_lock(scope, include_thread=True):
            thread_key = self._store.compute_scope_key(scope, include_thread=True)
            thread_state = await self._store.get_processing_state(thread_key)
            if self.options.fact_extraction_every_n_turns > 0:
                count, _ = await self._store.get_turn_stats_after(
                    scope,
                    thread_state.fact_through_turn_id,
                    include_thread=True,
                )
                if count >= self.options.fact_extraction_every_n_turns:
                    await self._extract_memories_core(scope)
                    thread_state = await self._store.get_processing_state(thread_key)
                    if (
                        self.options.reconcile_every_n_extractions > 0
                        and thread_state.extraction_runs % self.options.reconcile_every_n_extractions == 0
                    ):
                        await self.reconcile(scope.to_user_scope())
            if self.options.thread_summary_every_n_turns > 0:
                count, _ = await self._store.get_turn_stats_after(
                    scope,
                    thread_state.summary_through_turn_id,
                    include_thread=True,
                )
                if count >= self.options.thread_summary_every_n_turns:
                    await self._generate_thread_summary_core(scope)
            if self.options.user_summary_every_n_turns > 0:
                user_scope = scope.to_user_scope()
                user_key = self._store.compute_scope_key(user_scope, include_thread=False)
                user_state = await self._store.get_processing_state(user_key)
                count, _ = await self._store.get_turn_stats_after(
                    user_scope,
                    user_state.user_summary_through_turn_id,
                    include_thread=False,
                )
                if count >= self.options.user_summary_every_n_turns:
                    await self.generate_user_summary(user_scope)

    def _get_processing_lock(self, scope: PostgresMemoryScope, *, include_thread: bool) -> asyncio.Lock:
        key = self._store.compute_scope_key(scope, include_thread=include_thread)
        return self._processing_locks.setdefault(key, asyncio.Lock())

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("The Postgres memory client is closed.")


def _require_thread_scope(scope: PostgresMemoryScope) -> None:
    if scope.thread_id is None:
        raise ValueError("A thread_id is required for conversation-turn operations.")


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    return normalized


def _normalize_role(role: str) -> str:
    normalized = _require_text(role, "role").lower()
    if normalized == "assistant":
        return "agent"
    if normalized not in {"user", "agent", "tool", "system"}:
        raise ValueError(f"Unsupported memory role {role!r}.")
    return normalized


def _validate_retrieval_arguments(
    memory_types: Sequence[PostgresMemoryType] | None,
    limit: int,
    min_confidence: float,
) -> tuple[PostgresMemoryType, ...]:
    selected = tuple(memory_types) if memory_types is not None else _DEFAULT_MEMORY_TYPES
    if not selected or any(memory_type not in _DERIVED_MEMORY_TYPES for memory_type in selected):
        raise ValueError("memory_types must contain one or more fact, procedural, or episodic values.")
    if limit <= 0:
        raise ValueError("The retrieval limit must be greater than zero.")
    if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1.")
    return selected


def _build_extract_messages(
    system_prompt: str,
    turns: Sequence[PostgresMemoryRecord],
    existing_memories: Sequence[PostgresMemoryRecord],
) -> list[Message]:
    turns_text = "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
    existing_text = (
        "\n".join(f"[{memory.memory_type.value}] {memory.content}" for memory in existing_memories)
        if existing_memories
        else "(none)"
    )
    return [
        Message(role="system", contents=[system_prompt]),
        Message(
            role="user",
            contents=[
                (
                    f"Conversation excerpt:\n{turns_text}\n\n"
                    f"Existing active memories (avoid duplicating these):\n{existing_text}"
                )
            ],
        ),
    ]


def _build_thread_summary_messages(
    system_prompt: str,
    previous_summary: str | None,
    turns: Sequence[PostgresMemoryRecord],
) -> list[Message]:
    turns_text = "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
    return [
        Message(role="system", contents=[system_prompt]),
        Message(
            role="user",
            contents=[f"Previous summary:\n{previous_summary or '(none)'}\n\nNew turns:\n{turns_text}"],
        ),
    ]


def _build_user_summary_messages(
    system_prompt: str,
    previous_summary: str | None,
    memories: Sequence[PostgresMemoryRecord],
    thread_summaries: Sequence[PostgresMemoryRecord],
) -> list[Message]:
    memories_text = (
        "\n".join(
            f"[{memory.memory_type.value} confidence={memory.confidence or 0:.2f}] {memory.content}"
            for memory in memories
        )
        if memories
        else "(none)"
    )
    summaries_text = "\n".join(summary.content for summary in thread_summaries) or "(none)"
    return [
        Message(role="system", contents=[system_prompt]),
        Message(
            role="user",
            contents=[
                (
                    f"Previous user summary:\n{previous_summary or '(none)'}\n\n"
                    f"Active memories:\n{memories_text}\n\n"
                    f"Latest thread summaries:\n{summaries_text}"
                )
            ],
        ),
    ]


def _build_reconcile_messages(
    system_prompt: str,
    memories: Sequence[PostgresMemoryRecord],
) -> list[Message]:
    memories_text = "\n".join(
        f"{memory.id}: [{memory.memory_type.value} confidence={memory.confidence or 0:.2f} "
        f"created={memory.created_at.isoformat()}] {memory.content}"
        for memory in memories
    )
    return [
        Message(role="system", contents=[system_prompt]),
        Message(role="user", contents=[f"Active memories:\n{memories_text}"]),
    ]


def _parse_extracted_memories(response_text: str) -> list[_ExtractedMemory]:
    payload = _parse_json_array(response_text, "memory extraction")
    results: list[_ExtractedMemory] = []
    for item in payload:
        if not isinstance(item, dict):
            raise IntegrationInvalidResponseException("Every memory extraction item must be a JSON object.")
        item_map = cast(dict[str, Any], item)
        content_value = item_map.get("content")
        type_value = item_map.get("memory_type")
        if not isinstance(content_value, str) or not isinstance(type_value, str):
            raise IntegrationInvalidResponseException(
                'Every memory extraction item requires string "content" and "memory_type" values.'
            )
        content = content_value.strip()
        try:
            memory_type = PostgresMemoryType(type_value.strip().lower())
        except ValueError as exc:
            raise IntegrationInvalidResponseException(
                "Memory extraction types must be fact, procedural, or episodic."
            ) from exc
        if not content or memory_type not in _DERIVED_MEMORY_TYPES:
            raise IntegrationInvalidResponseException(
                "Memory extraction content must be non-empty and use a derived memory type."
            )
        tags_value = item_map.get("tags")
        if tags_value is None:
            tags: tuple[str, ...] = ()
        elif isinstance(tags_value, list):
            tag_items = cast(list[Any], tags_value)
            if any(not isinstance(tag, str) or not tag.strip() for tag in tag_items):
                raise IntegrationInvalidResponseException("Memory extraction tags must be non-empty strings.")
            tags = tuple(cast(str, tag).strip() for tag in tag_items)
        else:
            raise IntegrationInvalidResponseException("Memory extraction tags must be a JSON array.")
        results.append(
            _ExtractedMemory(
                content=content,
                memory_type=memory_type,
                confidence=_parse_score(item_map.get("confidence"), "confidence"),
                salience=_parse_optional_score(item_map.get("salience"), "salience"),
                tags=tags,
            )
        )
    return results


def _parse_reconciliation_decisions(response_text: str) -> list[_ReconciliationDecision]:
    payload = _parse_json_array(response_text, "memory reconciliation")
    results: list[_ReconciliationDecision] = []
    for item in payload:
        if not isinstance(item, dict):
            raise IntegrationInvalidResponseException("Every memory reconciliation item must be a JSON object.")
        item_map = cast(dict[str, Any], item)
        superseded_id = item_map.get("superseded_id")
        winner_id = item_map.get("winner_id")
        if type(superseded_id) is not int or type(winner_id) is not int:
            raise IntegrationInvalidResponseException(
                'Every memory reconciliation item requires integer "superseded_id" and "winner_id" values.'
            )
        reason_value = item_map.get("reason")
        if not isinstance(reason_value, str) or not reason_value.strip():
            raise IntegrationInvalidResponseException(
                'Every memory reconciliation item requires a non-empty string "reason".'
            )
        results.append(_ReconciliationDecision(superseded_id, winner_id, reason_value.strip()))
    return results


def _parse_json_array(response_text: str, operation: str) -> list[Any]:
    try:
        parsed = json.loads(response_text.strip())
    except json.JSONDecodeError as exc:
        raise IntegrationInvalidResponseException(
            f"The {operation} model response was not a valid JSON array."
        ) from exc
    if not isinstance(parsed, list):
        raise IntegrationInvalidResponseException(f"The {operation} model response was not a valid JSON array.")
    return cast(list[Any], parsed)


def _parse_score(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise IntegrationInvalidResponseException(f'Memory extraction "{name}" must be a number between 0 and 1.')
    return float(value)


def _parse_optional_score(value: Any, name: str) -> float | None:
    return None if value is None else _parse_score(value, name)


def _compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.strip().upper().encode()).hexdigest().upper()


def _create_summary_record(
    summary_id: int,
    scope: PostgresMemoryScope,
    memory_type: PostgresMemoryType,
    content: str,
) -> PostgresMemoryRecord:
    now = datetime.now(timezone.utc)
    return PostgresMemoryRecord(
        id=summary_id,
        memory_type=memory_type,
        content=content,
        user_id=scope.user_id,
        thread_id=scope.thread_id,
        application_id=scope.application_id,
        agent_id=scope.agent_id,
        created_at=now,
        updated_at=now,
    )
