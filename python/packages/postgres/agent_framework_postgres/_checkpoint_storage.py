# Copyright (c) Microsoft. All rights reserved.

"""Scoped PostgreSQL persistence for workflow checkpoints."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agent_framework import SecretString, WorkflowCheckpoint, WorkflowCheckpointException
from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from psycopg import sql
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb
from typing_extensions import Self

from ._vector_store import PostgresClient, _create_client, _prepare_identifier  # pyright: ignore[reportPrivateUsage]

_PAYLOAD_FORMAT = "agent-framework.python.checkpoint.v1"


class PostgresCheckpointStorage:
    """Persist Python workflow checkpoints within one application, tenant, and run.

    Scope identifiers must come from trusted application code. Recreate the storage
    with the same scope to resume a run. Sharing a workflow name does not grant access
    to another run's checkpoints. Checkpoint payloads use the framework's codec and
    must only be read from trusted storage.

    Call ``ensure_table()`` before first use. It creates a table and index in an
    existing schema, but does not create schemas, install extensions, or migrate
    existing tables. PostgreSQL's vector extension is not required.

    Keyword Args:
        application_id: Application owning the workflow run.
        tenant_id: Authenticated tenant or user isolation boundary.
        run_id: Stable identifier for one execution, independent of workflow name.
        connection_string: PostgreSQL connection string, or use POSTGRES_CONNECTION_STRING.
        client: Borrowed Psycopg async connection or pool; never closed by this storage.
        schema: Existing PostgreSQL schema.
        table_name: Checkpoint table, which can also be shared with the .NET provider.
        allowed_checkpoint_types: Additional types permitted by the framework decoder.
        env_file_path: Optional environment file used to resolve connection settings.
        env_file_encoding: Encoding of the environment file.
    """

    def __init__(
        self,
        *,
        application_id: str,
        tenant_id: str,
        run_id: str,
        connection_string: str | SecretString | None = None,
        client: PostgresClient | None = None,
        schema: str = "public",
        table_name: str = "agent_framework_checkpoints",
        allowed_checkpoint_types: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        for name, value in (("application_id", application_id), ("tenant_id", tenant_id), ("run_id", run_id)):
            if not isinstance(value, str) or not value.strip() or "\0" in value:
                raise ValueError(f"{name} must be a nonempty string without NUL.")
        self._table = sql.SQL("{}.{}").format(_prepare_identifier(schema), _prepare_identifier(table_name))
        digest = hashlib.sha256(self._table.as_string().encode()).hexdigest()[:16].upper()
        self._index = _prepare_identifier(f"af_checkpoint_scope_{digest}")
        self._scope = (application_id, tenant_id, run_id, _PAYLOAD_FORMAT)
        self._lock_key = json.dumps(["agent-framework:checkpoints", schema, table_name, *self._scope])
        self._allowed_types = frozenset(allowed_checkpoint_types or [])
        self._client = _create_client(
            connection_string,
            client=client,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

    async def ensure_table(self) -> None:
        """Create the checkpoint table and its scoped history index if absent."""
        async with self._client.connection() as connection:
            await connection.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        application_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        payload_format TEXT NOT NULL,
                        checkpoint_id TEXT NOT NULL,
                        workflow_name TEXT,
                        parent_checkpoint_id TEXT,
                        version INTEGER NOT NULL DEFAULT 1,
                        sequence BIGINT GENERATED ALWAYS AS IDENTITY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                        payload JSONB NOT NULL,
                        PRIMARY KEY (application_id, tenant_id, run_id, payload_format, checkpoint_id)
                    )
                    """
                ).format(self._table)
            )
            await connection.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {} ON {} (application_id, tenant_id, run_id, payload_format, sequence)"
                ).format(self._index, self._table)
            )

    async def save(self, checkpoint: WorkflowCheckpoint) -> str:
        """Save an immutable checkpoint snapshot and return its identifier.

        Repeating an identical save is idempotent. Reusing an ID for different state
        raises WorkflowCheckpointException. Saves within a run are serialized until
        transaction commit, so history order does not depend on worker clocks.

        Args:
            checkpoint: Complete workflow checkpoint to persist.

        Raises:
            WorkflowCheckpointException: The payload cannot be restored with the
                configured type allowlist, or its ID already has different state.
        """
        encoded = encode_checkpoint_value(checkpoint.to_dict())
        decode_checkpoint_value(encoded, allowed_types=self._allowed_types)
        statement = sql.SQL(
            "INSERT INTO {} AS stored "
            "(application_id, tenant_id, run_id, payload_format, checkpoint_id, workflow_name, "
            "parent_checkpoint_id, payload) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (application_id, tenant_id, run_id, payload_format, checkpoint_id) DO UPDATE "
            "SET checkpoint_id = EXCLUDED.checkpoint_id WHERE stored.payload = EXCLUDED.payload "
            "RETURNING checkpoint_id"
        ).format(self._table)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (self._lock_key,))
            await cursor.execute(
                statement,
                (
                    *self._scope,
                    checkpoint.checkpoint_id,
                    checkpoint.workflow_name,
                    checkpoint.previous_checkpoint_id,
                    Jsonb(encoded),
                ),
            )
            if await cursor.fetchone() is None:
                raise WorkflowCheckpointException("Checkpoint ID already exists with different state in this run.")
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: str) -> WorkflowCheckpoint:
        """Load a caller-owned checkpoint by ID within this storage's scope.

        Args:
            checkpoint_id: Identifier of the checkpoint to retrieve.

        Raises:
            WorkflowCheckpointException: The checkpoint is missing or cannot be decoded.
        """
        statement = sql.SQL(
            "SELECT payload FROM {} WHERE application_id = %s AND tenant_id = %s AND run_id = %s "
            "AND payload_format = %s AND checkpoint_id = %s"
        ).format(self._table)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, (*self._scope, checkpoint_id))
            row = await cursor.fetchone()
        if row is None:
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id} in this run.")
        return self._decode(row[0])

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List independent checkpoint snapshots in committed save order.

        Args:
            workflow_name: Workflow definition name within this storage's run.

        Raises:
            WorkflowCheckpointException: A stored checkpoint cannot be decoded.
        """
        statement = sql.SQL(
            "SELECT payload FROM {} WHERE application_id = %s AND tenant_id = %s AND run_id = %s "
            "AND payload_format = %s AND workflow_name = %s ORDER BY sequence ASC"
        ).format(self._table)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, (*self._scope, workflow_name))
            rows = await cursor.fetchall()
        return [self._decode(row[0]) for row in rows]

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[str]:
        """List checkpoint identifiers in committed save order without loading state.

        Args:
            workflow_name: Workflow definition name within this storage's run.
        """
        statement = sql.SQL(
            "SELECT checkpoint_id FROM {} WHERE application_id = %s AND tenant_id = %s AND run_id = %s "
            "AND payload_format = %s AND workflow_name = %s ORDER BY sequence ASC"
        ).format(self._table)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, (*self._scope, workflow_name))
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Load the last committed checkpoint, or None when this run has no history.

        Args:
            workflow_name: Workflow definition name within this storage's run.

        Raises:
            WorkflowCheckpointException: The latest checkpoint cannot be decoded.
        """
        statement = sql.SQL(
            "SELECT payload FROM {} WHERE application_id = %s AND tenant_id = %s AND run_id = %s "
            "AND payload_format = %s AND workflow_name = %s ORDER BY sequence DESC LIMIT 1"
        ).format(self._table)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, (*self._scope, workflow_name))
            row = await cursor.fetchone()
        return self._decode(row[0]) if row is not None else None

    async def delete(self, checkpoint_id: str) -> bool:
        """Delete one checkpoint in this run, returning whether it existed.

        Deletion does not cascade to children or other runs.

        Args:
            checkpoint_id: Identifier of the checkpoint to delete.
        """
        statement = sql.SQL(
            "DELETE FROM {} WHERE application_id = %s AND tenant_id = %s AND run_id = %s "
            "AND payload_format = %s AND checkpoint_id = %s RETURNING checkpoint_id"
        ).format(self._table)
        async with self._client.connection() as connection, connection.cursor(row_factory=tuple_row) as cursor:
            await cursor.execute(statement, (*self._scope, checkpoint_id))
            return await cursor.fetchone() is not None

    def _decode(self, payload: Any) -> WorkflowCheckpoint:
        return WorkflowCheckpoint.from_dict(decode_checkpoint_value(payload, allowed_types=self._allowed_types))

    async def close(self) -> None:
        """Close this storage, releasing only a connection pool it owns."""
        await self._client.close()

    async def __aenter__(self) -> Self:
        self._client.ensure_open()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
