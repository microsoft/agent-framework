# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from pgvector import Vector as PgVector
from psycopg import sql
from psycopg.rows import tuple_row

from ._memory_types import (
    PostgresMemoryClientOptions,
    PostgresMemoryRecord,
    PostgresMemoryScope,
    PostgresMemoryType,
    PostgresMemoryVectorIndexKind,
)
from ._vector_store import _Client, _prepare_identifier  # pyright: ignore[reportPrivateUsage]

_STRICT_USER_SCOPE = sql.SQL(
    "application_id IS NOT DISTINCT FROM %s AND agent_id IS NOT DISTINCT FROM %s AND user_id = %s"
)
_STRICT_THREAD_SCOPE = sql.SQL(
    "application_id IS NOT DISTINCT FROM %s "
    "AND agent_id IS NOT DISTINCT FROM %s "
    "AND user_id = %s "
    "AND thread_id IS NOT DISTINCT FROM %s"
)
_RETRIEVAL_SCOPE = sql.SQL(
    "application_id IS NOT DISTINCT FROM %s "
    "AND agent_id IS NOT DISTINCT FROM %s "
    "AND user_id = %s "
    "AND (%s::text IS NULL OR thread_id IS NOT DISTINCT FROM %s)"
)


@dataclass(frozen=True, slots=True)
class _ProcessingState:
    fact_through_turn_id: int = 0
    summary_through_turn_id: int = 0
    user_summary_through_turn_id: int = 0
    extraction_runs: int = 0


@dataclass(frozen=True, slots=True)
class _PostgresMemoryRerankResult:
    id: int
    rank: int
    relevance_score: float


class _PostgresMemoryStore:  # pyright: ignore[reportUnusedClass]
    """Provide PostgreSQL persistence primitives for the memory client."""

    def __init__(self, client: _Client, options: PostgresMemoryClientOptions) -> None:
        _prepare_identifier(options.schema)
        if len(options.table_name.encode()) > 40:
            raise ValueError("table_name must contain at most 40 UTF-8 bytes.")
        _prepare_identifier(options.table_name)
        self._client = client
        self._options = options
        self._turns = self._table(f"{options.table_name}_turns")
        self._memories = self._table(f"{options.table_name}_memories")
        self._summaries = self._table(f"{options.table_name}_summaries")
        self._processing = self._table(f"{options.table_name}_processing")
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        """Create the four memory tables and their indexes when absent."""
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            await self._ensure_schema_core()
            self._schema_ready = True

    async def _ensure_schema_core(self) -> None:
        dimension = sql.Literal(self._options.embedding_dimensions)
        base = self._options.table_name
        memory_vector_indexes = self._get_vector_index_statements(
            self._memories,
            f"ix_{base}_memories_embedding",
            f"ix_{base}_memories_diskann",
        )
        statements: list[sql.Composed] = [
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    application_id TEXT,
                    agent_id TEXT,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ).format(self._turns, dimension),
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (application_id, agent_id, user_id, thread_id, id)").format(
                _prepare_identifier(f"ix_{base}_turns_scope"), self._turns
            ),
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    application_id TEXT,
                    agent_id TEXT,
                    user_id TEXT NOT NULL,
                    thread_id TEXT,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL,
                    salience DOUBLE PRECISION,
                    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                    embedding vector({}) NOT NULL,
                    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
                    content_hash CHAR(64) NOT NULL,
                    is_superseded BOOLEAN NOT NULL DEFAULT FALSE,
                    superseded_by BIGINT,
                    supersede_reason TEXT,
                    expires_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ).format(self._memories, dimension),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {} ON {} (application_id, agent_id, user_id, thread_id, memory_type)"
            ).format(_prepare_identifier(f"ix_{base}_memories_scope"), self._memories),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {} ON {} (application_id, agent_id, user_id, memory_type, content_hash)"
            ).format(_prepare_identifier(f"ix_{base}_memories_hash"), self._memories),
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING gin (content_tsv)").format(
                _prepare_identifier(f"ix_{base}_memories_tsv"), self._memories
            ),
            *memory_vector_indexes,
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    application_id TEXT,
                    agent_id TEXT,
                    user_id TEXT NOT NULL,
                    thread_id TEXT,
                    summary_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({}) NOT NULL,
                    covers_through_turn_id BIGINT NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ).format(self._summaries, dimension),
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {} ON {} "
                "(application_id, agent_id, user_id, thread_id, summary_type, version DESC)"
            ).format(_prepare_identifier(f"ix_{base}_summaries_scope"), self._summaries),
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    scope_key CHAR(64) PRIMARY KEY,
                    fact_through_turn_id BIGINT NOT NULL DEFAULT 0,
                    summary_through_turn_id BIGINT NOT NULL DEFAULT 0,
                    user_summary_through_turn_id BIGINT NOT NULL DEFAULT 0,
                    extraction_runs INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ).format(self._processing),
        ]
        if self._options.enable_turn_embeddings:
            statements[2:2] = self._get_vector_index_statements(
                self._turns,
                f"ix_{base}_turns_embedding",
                f"ix_{base}_turns_diskann",
            )
        async with self._client.connection(vectors=True) as connection:
            for statement in statements:
                await connection.execute(statement)

    def _get_vector_index_statements(
        self,
        table: sql.Identifier,
        hnsw_index_name: str,
        disk_ann_index_name: str,
    ) -> list[sql.Composed]:
        hnsw_index = sql.Identifier(self._options.schema, hnsw_index_name)
        disk_ann_index = sql.Identifier(self._options.schema, disk_ann_index_name)
        if self._options.vector_index_kind is PostgresMemoryVectorIndexKind.HNSW:
            return [
                sql.SQL("DROP INDEX IF EXISTS {}").format(disk_ann_index),
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING hnsw (embedding vector_cosine_ops)").format(
                    _prepare_identifier(hnsw_index_name), table
                ),
            ]
        if self._options.vector_index_kind is PostgresMemoryVectorIndexKind.DISK_ANN:
            return [
                sql.SQL("DROP INDEX IF EXISTS {}").format(hnsw_index),
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING diskann (embedding vector_cosine_ops)").format(
                    _prepare_identifier(disk_ann_index_name), table
                ),
            ]
        raise ValueError("Unsupported memory vector index kind.")

    async def insert_turn(
        self,
        scope: PostgresMemoryScope,
        role: str,
        content: str,
        embedding: list[float] | None,
    ) -> int:
        if embedding is None:
            statement = sql.SQL(
                "INSERT INTO {} (application_id, agent_id, user_id, thread_id, role, content) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
            ).format(self._turns)
            params: list[Any] = [scope.application_id, scope.agent_id, scope.user_id, scope.thread_id, role, content]
        else:
            statement = sql.SQL(
                "INSERT INTO {} (application_id, agent_id, user_id, thread_id, role, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id"
            ).format(self._turns)
            params = [
                scope.application_id,
                scope.agent_id,
                scope.user_id,
                scope.thread_id,
                role,
                content,
                PgVector(embedding),
            ]
        async with self._client.connection(vectors=embedding is not None) as connection:
            row = await (await connection.execute(statement, params)).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return an identifier for the inserted turn.")
        return int(row[0])

    async def get_thread(self, scope: PostgresMemoryScope, recent_k: int | None) -> list[PostgresMemoryRecord]:
        limit = sql.SQL("LIMIT %s") if recent_k is not None else sql.SQL("")
        statement = sql.SQL(
            """
            SELECT id, application_id, agent_id, user_id, thread_id, role, content, created_at
            FROM (
                SELECT id, application_id, agent_id, user_id, thread_id, role, content, created_at
                FROM {}
                WHERE {}
                ORDER BY id DESC
                {}
            ) turns
            ORDER BY id ASC
            """
        ).format(self._turns, _STRICT_THREAD_SCOPE, limit)
        params = self._scope_params(scope, include_thread=True)
        if recent_k is not None:
            params.append(recent_k)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        return [self._read_turn(row) for row in rows]

    async def get_turns_after(self, scope: PostgresMemoryScope, after_turn_id: int) -> list[PostgresMemoryRecord]:
        statement = sql.SQL(
            """
            SELECT id, application_id, agent_id, user_id, thread_id, role, content, created_at
            FROM {}
            WHERE {} AND id > %s
            ORDER BY id ASC
            """
        ).format(self._turns, _STRICT_THREAD_SCOPE)
        params = [*self._scope_params(scope, include_thread=True), after_turn_id]
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        return [self._read_turn(row) for row in rows]

    async def get_turn_stats_after(
        self,
        scope: PostgresMemoryScope,
        after_turn_id: int,
        *,
        include_thread: bool,
    ) -> tuple[int, int]:
        scope_sql = _STRICT_THREAD_SCOPE if include_thread else _STRICT_USER_SCOPE
        statement = sql.SQL("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM {} WHERE {} AND id > %s").format(
            self._turns, scope_sql
        )
        params = [*self._scope_params(scope, include_thread=include_thread), after_turn_id]
        async with self._client.connection() as connection:
            row = await (await connection.execute(statement, params)).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return turn statistics.")
        return int(row[0]), int(row[1])

    async def find_duplicate(
        self,
        scope: PostgresMemoryScope,
        memory_type: PostgresMemoryType,
        content_hash: str,
        embedding: list[float],
        similarity_threshold: float,
    ) -> PostgresMemoryRecord | None:
        statement = sql.SQL(
            """
            SELECT id, application_id, agent_id, user_id, thread_id, memory_type, content,
                   confidence, salience, tags, created_at, updated_at, is_superseded,
                   superseded_by, supersede_reason,
                   1.0 - (embedding <=> %s) AS score
            FROM {}
            WHERE {}
              AND memory_type = %s
              AND is_superseded = FALSE
              AND (expires_at IS NULL OR expires_at > now())
              AND (content_hash = %s OR (1.0 - (embedding <=> %s)) >= %s)
            ORDER BY (content_hash = %s) DESC, score DESC
            LIMIT 1
            """
        ).format(self._memories, _STRICT_USER_SCOPE)
        vector = PgVector(embedding)
        params = [
            vector,
            *self._scope_params(scope, include_thread=False),
            memory_type.value,
            content_hash,
            vector,
            similarity_threshold,
            content_hash,
        ]
        async with (
            self._client.connection(vectors=True) as connection,
            connection.cursor(row_factory=tuple_row) as cursor,
        ):
            await cursor.execute(statement, params)
            row = await cursor.fetchone()
        return self._read_derived_memory(row, score_index=15) if row is not None else None

    async def insert_derived_memory(
        self,
        scope: PostgresMemoryScope,
        memory_type: PostgresMemoryType,
        content: str,
        confidence: float,
        salience: float | None,
        tags: tuple[str, ...],
        embedding: list[float],
        expires_at: datetime | None,
    ) -> int:
        statement = sql.SQL(
            """
            INSERT INTO {} (
                application_id, agent_id, user_id, thread_id, memory_type, content, confidence,
                salience, tags, embedding, content_hash, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
        ).format(self._memories)
        params = [
            scope.application_id,
            scope.agent_id,
            scope.user_id,
            scope.thread_id,
            memory_type.value,
            content,
            confidence,
            salience,
            list(tags),
            PgVector(embedding),
            _compute_content_hash(content),
            expires_at,
        ]
        async with self._client.connection(vectors=True) as connection:
            row = await (await connection.execute(statement, params)).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return an identifier for the inserted memory.")
        return int(row[0])

    async def get_active_memories(
        self,
        scope: PostgresMemoryScope,
        memory_types: tuple[PostgresMemoryType, ...],
        limit: int,
        min_confidence: float,
    ) -> list[PostgresMemoryRecord]:
        statement = sql.SQL(
            """
            SELECT id, application_id, agent_id, user_id, thread_id, memory_type, content,
                   confidence, salience, tags, created_at, updated_at, is_superseded,
                   superseded_by, supersede_reason
            FROM {}
            WHERE {}
              AND memory_type = ANY(%s)
              AND confidence >= %s
              AND is_superseded = FALSE
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """
        ).format(self._memories, _RETRIEVAL_SCOPE)
        params = [
            *self._retrieval_scope_params(scope),
            [memory_type.value for memory_type in memory_types],
            min_confidence,
            limit,
        ]
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        return [self._read_derived_memory(row) for row in rows]

    async def search(
        self,
        scope: PostgresMemoryScope,
        search_terms: str,
        query_embedding: list[float],
        memory_types: tuple[PostgresMemoryType, ...],
        top_k: int,
        min_confidence: float,
    ) -> list[PostgresMemoryRecord]:
        candidate_limit = max(top_k * 5, top_k)
        statement = sql.SQL(
            """
            WITH eligible AS (
                SELECT *
                FROM {}
                WHERE {}
                  AND memory_type = ANY(%s)
                  AND confidence >= %s
                  AND is_superseded = FALSE
                  AND (expires_at IS NULL OR expires_at > now())
            ),
            vector_ranked AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %s, id DESC) AS rnk
                FROM eligible
                ORDER BY embedding <=> %s, id DESC
                LIMIT %s
            ),
            text_ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %s)) DESC, id DESC
                ) AS rnk
                FROM eligible
                WHERE content_tsv @@ plainto_tsquery('english', %s)
                ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %s)) DESC, id DESC
                LIMIT %s
            ),
            fused AS (
                SELECT COALESCE(v.id, t.id) AS id,
                       COALESCE(1.0::double precision / (%s + v.rnk), 0) +
                       COALESCE(1.0::double precision / (%s + t.rnk), 0) AS score
                FROM vector_ranked v
                FULL OUTER JOIN text_ranked t ON v.id = t.id
            )
            SELECT e.id, e.application_id, e.agent_id, e.user_id, e.thread_id, e.memory_type,
                   e.content, e.confidence, e.salience, e.tags, e.created_at, e.updated_at,
                   e.is_superseded, e.superseded_by, e.supersede_reason, f.score
            FROM fused f
            JOIN eligible e ON e.id = f.id
            ORDER BY f.score DESC, e.id DESC
            LIMIT %s
            """
        ).format(self._memories, _RETRIEVAL_SCOPE)
        vector = PgVector(query_embedding)
        params = [
            *self._retrieval_scope_params(scope),
            [memory_type.value for memory_type in memory_types],
            min_confidence,
            vector,
            vector,
            candidate_limit,
            search_terms,
            search_terms,
            search_terms,
            candidate_limit,
            self._options.reciprocal_rank_fusion_k,
            self._options.reciprocal_rank_fusion_k,
            top_k,
        ]
        async with (
            self._client.connection(vectors=True) as connection,
            connection.cursor(row_factory=tuple_row) as cursor,
        ):
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        return [self._read_derived_memory(row, score_index=15) for row in rows]

    async def rerank(
        self,
        search_terms: str,
        candidates: list[PostgresMemoryRecord],
        model: str,
    ) -> list[_PostgresMemoryRerankResult]:
        if not candidates:
            return []
        statement = sql.SQL(
            """
            SELECT document_id, rank, relevance_score
            FROM azure_ai.rank(
                query => %s,
                document_contents => %s::text[],
                document_ids => %s::text[],
                model => %s)
            ORDER BY rank
            """
        )
        params = [
            search_terms,
            [candidate.content for candidate in candidates],
            [str(candidate.id) for candidate in candidates],
            model,
        ]
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        return [
            _PostgresMemoryRerankResult(id=int(row[0]), rank=int(row[1]), relevance_score=float(row[2]))
            for row in rows
        ]

    async def mark_superseded(self, superseded_id: int, winner_id: int, reason: str) -> bool:
        statement = sql.SQL(
            """
            UPDATE {}
            SET is_superseded = TRUE,
                superseded_by = %s,
                supersede_reason = %s,
                updated_at = now()
            WHERE id = %s AND is_superseded = FALSE
            """
        ).format(self._memories)
        async with self._client.connection() as connection:
            cursor = await connection.execute(statement, [winner_id, reason, superseded_id])
        return cursor.rowcount > 0

    async def get_latest_summary(
        self,
        scope: PostgresMemoryScope,
        summary_type: PostgresMemoryType,
    ) -> tuple[PostgresMemoryRecord | None, int]:
        include_thread = summary_type is PostgresMemoryType.SUMMARY
        scope_sql = _STRICT_THREAD_SCOPE if include_thread else _STRICT_USER_SCOPE
        statement = sql.SQL(
            """
            SELECT id, application_id, agent_id, user_id, thread_id, summary_type, content,
                   covers_through_turn_id, created_at, updated_at
            FROM {}
            WHERE {} AND summary_type = %s
            ORDER BY version DESC
            LIMIT 1
            """
        ).format(self._summaries, scope_sql)
        params = [*self._scope_params(scope, include_thread=include_thread), summary_type.value]
        async with (
            self._client.connection() as connection,
            connection.cursor(row_factory=tuple_row) as cursor,
        ):
            await cursor.execute(statement, params)
            row = await cursor.fetchone()
        if row is None:
            return None, 0
        return self._read_summary(row), int(row[7])

    async def insert_summary(
        self,
        scope: PostgresMemoryScope,
        summary_type: PostgresMemoryType,
        content: str,
        embedding: list[float],
        covers_through_turn_id: int,
    ) -> int | None:
        include_thread = summary_type is PostgresMemoryType.SUMMARY
        scope_sql = _STRICT_THREAD_SCOPE if include_thread else _STRICT_USER_SCOPE
        scope_key = f"{self.compute_scope_key(scope, include_thread=include_thread)}:{summary_type.value}"
        statement = sql.SQL(
            """
            INSERT INTO {} (
                application_id, agent_id, user_id, thread_id, summary_type, content,
                embedding, covers_through_turn_id, version
            )
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(MAX(version), 0) + 1
            FROM {}
            WHERE {} AND summary_type = %s
            HAVING COALESCE(MAX(covers_through_turn_id), 0) < %s
            RETURNING id
            """
        ).format(self._summaries, self._summaries, scope_sql)
        params = [
            scope.application_id,
            scope.agent_id,
            scope.user_id,
            scope.thread_id,
            summary_type.value,
            content,
            PgVector(embedding),
            covers_through_turn_id,
            *self._scope_params(scope, include_thread=include_thread),
            summary_type.value,
            covers_through_turn_id,
        ]
        async with self._client.connection(vectors=True) as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [scope_key])
            row = await (await connection.execute(statement, params)).fetchone()
        return int(row[0]) if row is not None else None

    async def get_recent_thread_summaries(
        self,
        scope: PostgresMemoryScope,
        limit: int,
    ) -> list[PostgresMemoryRecord]:
        statement = sql.SQL(
            """
            SELECT id, application_id, agent_id, user_id, thread_id, summary_type, content,
                   covers_through_turn_id, created_at, updated_at
            FROM (
                SELECT DISTINCT ON (thread_id)
                       id, application_id, agent_id, user_id, thread_id, summary_type, content,
                       covers_through_turn_id, created_at, updated_at, version
                FROM {}
                WHERE {} AND summary_type = 'summary'
                ORDER BY thread_id, version DESC
            ) latest
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """
        ).format(self._summaries, _STRICT_USER_SCOPE)
        params = [*self._scope_params(scope, include_thread=False), limit]
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, params)
            rows = await cursor.fetchall()
        return [self._read_summary(row) for row in rows]

    async def get_processing_state(self, scope_key: str) -> _ProcessingState:
        statement = sql.SQL(
            """
            SELECT fact_through_turn_id, summary_through_turn_id,
                   user_summary_through_turn_id, extraction_runs
            FROM {}
            WHERE scope_key = %s
            """
        ).format(self._processing)
        async with self._client.connection() as connection:
            row = await (await connection.execute(statement, [scope_key])).fetchone()
        return (
            _ProcessingState(int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            if row is not None
            else _ProcessingState()
        )

    async def upsert_processing_state(self, scope_key: str, state: _ProcessingState) -> None:
        statement = sql.SQL(
            """
            INSERT INTO {} AS current (
                scope_key, fact_through_turn_id, summary_through_turn_id,
                user_summary_through_turn_id, extraction_runs, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (scope_key) DO UPDATE SET
                fact_through_turn_id = GREATEST(
                    current.fact_through_turn_id, EXCLUDED.fact_through_turn_id
                ),
                summary_through_turn_id = GREATEST(
                    current.summary_through_turn_id, EXCLUDED.summary_through_turn_id
                ),
                user_summary_through_turn_id = GREATEST(
                    current.user_summary_through_turn_id, EXCLUDED.user_summary_through_turn_id
                ),
                extraction_runs = GREATEST(current.extraction_runs, EXCLUDED.extraction_runs),
                updated_at = now()
            """
        ).format(self._processing)
        params = [
            scope_key,
            state.fact_through_turn_id,
            state.summary_through_turn_id,
            state.user_summary_through_turn_id,
            state.extraction_runs,
        ]
        async with self._client.connection() as connection:
            await connection.execute(statement, params)

    @staticmethod
    def compute_scope_key(scope: PostgresMemoryScope, *, include_thread: bool) -> str:
        """Compute the stable processing and advisory-lock key for a scope."""
        components = (
            scope.application_id or "",
            scope.agent_id or "",
            scope.user_id,
            scope.thread_id or "" if include_thread else "",
        )
        encoded = b"".join(f"{len(component.encode())}:".encode() + component.encode() for component in components)
        return hashlib.sha256(encoded).hexdigest().upper()

    def _table(self, name: str) -> sql.Composed:
        return sql.SQL("{}.{}").format(_prepare_identifier(self._options.schema), _prepare_identifier(name))

    @staticmethod
    def _scope_params(scope: PostgresMemoryScope, *, include_thread: bool) -> list[Any]:
        params: list[Any] = [scope.application_id, scope.agent_id, scope.user_id]
        if include_thread:
            params.append(scope.thread_id)
        return params

    @staticmethod
    def _retrieval_scope_params(scope: PostgresMemoryScope) -> list[Any]:
        return [scope.application_id, scope.agent_id, scope.user_id, scope.thread_id, scope.thread_id]

    @staticmethod
    def _read_turn(row: tuple[Any, ...]) -> PostgresMemoryRecord:
        created_at = cast(datetime, row[7])
        return PostgresMemoryRecord(
            id=int(row[0]),
            application_id=cast(str | None, row[1]),
            agent_id=cast(str | None, row[2]),
            user_id=cast(str, row[3]),
            thread_id=cast(str, row[4]),
            role=cast(str, row[5]),
            content=cast(str, row[6]),
            memory_type=PostgresMemoryType.TURN,
            created_at=created_at,
            updated_at=created_at,
        )

    @staticmethod
    def _read_derived_memory(row: tuple[Any, ...], *, score_index: int | None = None) -> PostgresMemoryRecord:
        return PostgresMemoryRecord(
            id=int(row[0]),
            application_id=cast(str | None, row[1]),
            agent_id=cast(str | None, row[2]),
            user_id=cast(str, row[3]),
            thread_id=cast(str | None, row[4]),
            memory_type=PostgresMemoryType(cast(str, row[5])),
            content=cast(str, row[6]),
            confidence=float(row[7]),
            salience=float(row[8]) if row[8] is not None else None,
            tags=tuple(cast(list[str], row[9])),
            created_at=cast(datetime, row[10]),
            updated_at=cast(datetime, row[11]),
            is_superseded=bool(row[12]),
            superseded_by=int(row[13]) if row[13] is not None else None,
            supersede_reason=cast(str | None, row[14]),
            score=float(row[score_index]) if score_index is not None and row[score_index] is not None else None,
        )

    @staticmethod
    def _read_summary(row: tuple[Any, ...]) -> PostgresMemoryRecord:
        return PostgresMemoryRecord(
            id=int(row[0]),
            application_id=cast(str | None, row[1]),
            agent_id=cast(str | None, row[2]),
            user_id=cast(str, row[3]),
            thread_id=cast(str | None, row[4]),
            memory_type=PostgresMemoryType(cast(str, row[5])),
            content=cast(str, row[6]),
            created_at=cast(datetime, row[8]),
            updated_at=cast(datetime, row[9]),
        )


def _compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.strip().upper().encode()).hexdigest().upper()
