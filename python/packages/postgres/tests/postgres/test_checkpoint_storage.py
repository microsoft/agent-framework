# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from agent_framework import CheckpointStorage, WorkflowCheckpoint, WorkflowCheckpointException, WorkflowEvent
from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
from agent_framework._workflows._runner_context import WorkflowMessage
from psycopg import AsyncConnection, sql
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from agent_framework_postgres import PostgresCheckpointStorage

PAYLOAD_FORMAT = "agent-framework.python.checkpoint.v1"


@pytest.fixture
def storage() -> PostgresCheckpointStorage:
    return PostgresCheckpointStorage(
        application_id="app", tenant_id="tenant", run_id="run", connection_string="host=unused"
    )


@pytest.fixture
def database(storage: PostgresCheckpointStorage) -> Generator[tuple[MagicMock, MagicMock, MagicMock], None, None]:
    connection = MagicMock(spec=AsyncConnection)
    connection.execute = AsyncMock()
    cursor = MagicMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=("checkpoint",))
    cursor.fetchall = AsyncMock(return_value=[])
    connection.cursor.return_value.__aenter__.return_value = cursor
    with patch.object(storage._client, "connection") as acquire:
        acquire.return_value.__aenter__.return_value = connection
        yield connection, cursor, acquire


async def test_checkpoint_round_trip_preserves_typed_state_and_requests(
    storage: PostgresCheckpointStorage, database: Any
) -> None:
    _, cursor, acquire = database
    checkpoint = WorkflowCheckpoint(
        workflow_name="approval",
        graph_signature_hash="graph",
        state={"_executor_state": {"review": {"visits": [1]}}, "when": datetime(2026, 9, 17, tzinfo=timezone.utc)},
        messages={"review": [WorkflowMessage(data={"amount": 12}, source_id="start", target_id="review")]},
        pending_request_info_events={
            "approval": WorkflowEvent.request_info(
                request_id="approval", source_executor_id="review", request_data={"amount": 12}, response_type=bool
            )
        },
    )
    assert await storage.save(checkpoint) == checkpoint.checkpoint_id
    params = cursor.execute.await_args_list[1].args[1]
    assert params[:3] == ("app", "tenant", "run")
    payload = params[-1].obj
    checkpoint.state["_executor_state"]["review"]["visits"].append(2)
    cursor.fetchone.return_value = (payload,)

    restored = await storage.load(checkpoint.checkpoint_id)
    assert cursor.execute.await_args.args[1] == ("app", "tenant", "run", PAYLOAD_FORMAT, checkpoint.checkpoint_id)
    assert restored.state["_executor_state"]["review"]["visits"] == [1]
    assert restored.state["when"] == datetime(2026, 9, 17, tzinfo=timezone.utc)
    assert restored.messages["review"][0].data == {"amount": 12}
    assert restored.pending_request_info_events["approval"].data == {"amount": 12}
    restored.state["_executor_state"]["review"]["visits"].append(3)
    assert (await storage.load(checkpoint.checkpoint_id)).state["_executor_state"]["review"]["visits"] == [1]
    assert all(not call.kwargs.get("vectors", False) for call in acquire.call_args_list)


async def test_load_missing_checkpoint_raises(storage: PostgresCheckpointStorage, database: Any) -> None:
    database[1].fetchone.return_value = None
    with pytest.raises(WorkflowCheckpointException, match="No checkpoint"):
        await storage.load("missing")


async def test_conflicting_checkpoint_is_not_overwritten(storage: PostgresCheckpointStorage, database: Any) -> None:
    database[1].fetchone.return_value = None
    with pytest.raises(WorkflowCheckpointException, match="different state"):
        await storage.save(WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph"))


@pytest.mark.parametrize("field", ["application_id", "tenant_id", "run_id"])
@pytest.mark.parametrize("value", ["", " ", "bad\0scope"])
def test_scope_requires_nonempty_identifiers(field: str, value: str) -> None:
    options: dict[str, Any] = {
        "application_id": "app",
        "tenant_id": "tenant",
        "run_id": "run",
        "connection_string": "host=unused",
    }
    options[field] = value
    with pytest.raises(ValueError, match=field):
        PostgresCheckpointStorage(**options)


async def test_schema_uses_jsonb_without_vector_extension(storage: PostgresCheckpointStorage, database: Any) -> None:
    connection, _, _ = database
    await storage.ensure_table()
    statements = [call.args[0].as_string() for call in connection.execute.await_args_list]
    assert "payload JSONB NOT NULL" in statements[0]
    assert "GENERATED ALWAYS AS IDENTITY" in statements[0]
    assert "PRIMARY KEY (application_id, tenant_id, run_id, payload_format, checkpoint_id)" in statements[0]
    assert "(application_id, tenant_id, run_id, payload_format, sequence)" in statements[1]
    assert not any("CREATE EXTENSION" in statement or "vector" in statement for statement in statements)


async def test_lists_filter_by_scope_and_workflow_and_return_copies(
    storage: PostgresCheckpointStorage, database: Any
) -> None:
    protocol: CheckpointStorage = storage
    checkpoint = WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph", state={"visits": [1]})
    cursor = database[1]
    cursor.fetchall.return_value = [(encode_checkpoint_value(checkpoint.to_dict()),)]
    first = await protocol.list_checkpoints(workflow_name="approval")
    first[0].state["visits"].append(2)
    assert (await protocol.list_checkpoints(workflow_name="approval"))[0].state["visits"] == [1]
    assert cursor.execute.await_args.args[1] == ("app", "tenant", "run", PAYLOAD_FORMAT, "approval")
    assert "ORDER BY sequence ASC" in cursor.execute.await_args.args[0].as_string()

    cursor.fetchall.return_value = [("first",), ("second",)]
    assert await protocol.list_checkpoint_ids(workflow_name="approval") == ["first", "second"]
    assert cursor.execute.await_args.args[1] == ("app", "tenant", "run", PAYLOAD_FORMAT, "approval")


async def test_latest_uses_commit_order_not_iteration_or_timestamp(
    storage: PostgresCheckpointStorage, database: Any
) -> None:
    cursor = database[1]
    checkpoint = WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph", state={"visits": [1]})
    cursor.fetchone.return_value = (encode_checkpoint_value(checkpoint.to_dict()),)
    latest = await storage.get_latest(workflow_name="approval")
    assert latest is not None
    latest.state["visits"].append(2)
    reloaded = await storage.get_latest(workflow_name="approval")
    assert reloaded is not None and reloaded.state["visits"] == [1]
    assert cursor.execute.await_args.args[1] == ("app", "tenant", "run", PAYLOAD_FORMAT, "approval")
    assert "ORDER BY sequence DESC LIMIT 1" in cursor.execute.await_args.args[0].as_string()
    cursor.fetchone.return_value = None
    assert await storage.get_latest(workflow_name="approval") is None


@pytest.mark.parametrize("exists", [True, False])
async def test_delete_is_scoped(storage: PostgresCheckpointStorage, database: Any, exists: bool) -> None:
    cursor = database[1]
    cursor.fetchone.return_value = ("checkpoint",) if exists else None
    assert await storage.delete("checkpoint") is exists
    assert cursor.execute.await_args.args[1] == ("app", "tenant", "run", PAYLOAD_FORMAT, "checkpoint")
    assert "DELETE FROM" in cursor.execute.await_args.args[0].as_string()


async def test_save_locks_run_and_only_accepts_identical_duplicate_ids(
    storage: PostgresCheckpointStorage, database: Any
) -> None:
    cursor = database[1]
    await storage.save(WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph"))
    lock_call, insert_call = cursor.execute.await_args_list
    assert "pg_advisory_xact_lock" in lock_call.args[0]
    assert '"tenant", "run"' in lock_call.args[1][0]
    assert "WHERE stored.payload = EXCLUDED.payload" in insert_call.args[0].as_string()


async def test_unregistered_types_are_rejected_before_database_access(
    storage: PostgresCheckpointStorage, database: Any
) -> None:
    checkpoint = WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph", state={"type": MagicMock})
    with pytest.raises(WorkflowCheckpointException):
        await storage.save(checkpoint)
    database[2].assert_not_called()


async def test_borrowed_connection_is_not_closed() -> None:
    client = MagicMock(spec=AsyncConnection)
    client.close = AsyncMock()
    async with PostgresCheckpointStorage(application_id="app", tenant_id="tenant", run_id="run", client=client):
        pass
    client.close.assert_not_called()


async def test_owned_pool_is_closed(storage: PostgresCheckpointStorage) -> None:
    with patch.object(storage._client.client, "close", new_callable=AsyncMock) as close:
        await storage.close()
        await storage.close()
        close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="closed"):
        await storage.__aenter__()


@pytest.fixture
async def checkpoint_database() -> AsyncGenerator[tuple[AsyncConnection[Any], str], None]:
    connection_string = os.getenv("POSTGRES_TEST_CONNECTION_STRING")
    if not connection_string:
        pytest.skip("Set POSTGRES_TEST_CONNECTION_STRING to an explicitly designated test database.")
    async with await AsyncConnection.connect(connection_string, autocommit=True) as connection:
        schema = f"af_checkpoint_test_{uuid4().hex}"
        await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield connection, schema
        finally:
            await connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.integration
@pytest.mark.flaky
@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_CONNECTION_STRING"), reason="No designated PostgreSQL test database.")
class TestPostgresCheckpointIntegration:
    async def test_round_trip_history_idempotency_and_delete(self, checkpoint_database: Any) -> None:
        connection, schema = checkpoint_database
        async with PostgresCheckpointStorage(
            application_id="app",
            tenant_id="tenant",
            run_id="run",
            client=connection,
            schema=schema,
            table_name='checkpoints"; --',
        ) as storage:
            await storage.ensure_table()
            await storage.ensure_table()
            assert await storage.get_latest(workflow_name="approval") is None
            first = WorkflowCheckpoint(
                workflow_name="approval",
                graph_signature_hash="graph",
                state={"nested": {"visits": [1]}},
                iteration_count=2,
                timestamp="2026-09-17T12:00:00+00:00",
            )
            second = replace(
                first,
                checkpoint_id=str(uuid4()),
                previous_checkpoint_id=first.checkpoint_id,
                timestamp="2026-09-16T12:00:00+00:00",
            )
            await storage.save(first)
            await storage.save(second)
            await storage.save(first)
            assert await storage.list_checkpoint_ids(workflow_name="approval") == [
                first.checkpoint_id,
                second.checkpoint_id,
            ]
            latest = await storage.get_latest(workflow_name="approval")
            assert latest is not None and latest.checkpoint_id == second.checkpoint_id
            listed = await storage.list_checkpoints(workflow_name="approval")
            listed[0].state["nested"]["visits"].append(99)
            assert (await storage.load(first.checkpoint_id)).state["nested"]["visits"] == [1]
            first.state["nested"]["visits"].append(2)
            with pytest.raises(WorkflowCheckpointException, match="different state"):
                await storage.save(first)
            assert (await storage.load(first.checkpoint_id)).state["nested"]["visits"] == [1]
            assert await storage.list_checkpoints(workflow_name="other") == []
            assert await storage.delete(second.checkpoint_id)
            assert not await storage.delete(second.checkpoint_id)
            with pytest.raises(WorkflowCheckpointException):
                await storage.load(second.checkpoint_id)
        assert not connection.closed

    @pytest.mark.parametrize("dimension", ["application_id", "tenant_id", "run_id"])
    async def test_all_operations_isolate_scope(self, checkpoint_database: Any, dimension: str) -> None:
        connection, schema = checkpoint_database
        options: dict[str, Any] = {
            "application_id": "app",
            "tenant_id": "tenant",
            "run_id": "run",
            "client": connection,
            "schema": schema,
        }
        async with PostgresCheckpointStorage(**options) as storage:
            await storage.ensure_table()
            checkpoint = WorkflowCheckpoint(
                workflow_name="shared-name", graph_signature_hash="graph", state={"owner": 1}
            )
            await storage.save(checkpoint)
            async with PostgresCheckpointStorage(**{**options, dimension: "other"}) as other:
                assert await other.list_checkpoint_ids(workflow_name="shared-name") == []
                assert await other.list_checkpoints(workflow_name="shared-name") == []
                assert await other.get_latest(workflow_name="shared-name") is None
                assert not await other.delete(checkpoint.checkpoint_id)
                with pytest.raises(WorkflowCheckpointException):
                    await other.load(checkpoint.checkpoint_id)
                await other.save(replace(checkpoint, state={"owner": 2}))
                assert (await storage.load(checkpoint.checkpoint_id)).state == {"owner": 1}
                assert (await other.load(checkpoint.checkpoint_id)).state == {"owner": 2}

    async def test_borrowed_transaction_rollback(self, checkpoint_database: Any) -> None:
        connection, schema = checkpoint_database
        async with PostgresCheckpointStorage(
            application_id="app",
            tenant_id="tenant",
            run_id="run",
            client=connection,
            schema=schema,
        ) as storage:
            await storage.ensure_table()
            checkpoint = WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph")
            with pytest.raises(RuntimeError, match="rollback"):
                async with connection.transaction():
                    await storage.save(checkpoint)
                    raise RuntimeError("rollback")
            assert await storage.list_checkpoint_ids(workflow_name="approval") == []

    async def test_dotnet_payloads_coexist_without_cross_runtime_reads_or_deletes(
        self, checkpoint_database: Any
    ) -> None:
        connection, schema = checkpoint_database
        async with PostgresCheckpointStorage(
            application_id="app",
            tenant_id="tenant",
            run_id="run",
            client=connection,
            schema=schema,
        ) as storage:
            await storage.ensure_table()
            checkpoint = WorkflowCheckpoint(
                workflow_name="approval", graph_signature_hash="graph", state={"runtime": "python"}
            )
            await storage.save(checkpoint)
            await connection.execute(
                sql.SQL(
                    "INSERT INTO {}.agent_framework_checkpoints "
                    "(application_id, tenant_id, run_id, payload_format, checkpoint_id, workflow_name, payload) "
                    "VALUES ('app', 'tenant', 'run', 'agent-framework.dotnet.checkpoint.v1', %s, 'approval', %s), "
                    "('app', 'tenant', 'run', 'agent-framework.dotnet.checkpoint.v1', 'dotnet-only', 'approval', %s)"
                ).format(sql.Identifier(schema)),
                (checkpoint.checkpoint_id, Jsonb({"runtime": "dotnet"}), Jsonb({"runtime": "dotnet"})),
            )
            assert await storage.list_checkpoint_ids(workflow_name="approval") == [checkpoint.checkpoint_id]
            assert len(await storage.list_checkpoints(workflow_name="approval")) == 1
            latest = await storage.get_latest(workflow_name="approval")
            assert latest is not None and latest.checkpoint_id == checkpoint.checkpoint_id
            assert (await storage.load(checkpoint.checkpoint_id)).state == {"runtime": "python"}
            with pytest.raises(WorkflowCheckpointException):
                await storage.load("dotnet-only")
            assert not await storage.delete("dotnet-only")
            assert await storage.delete(checkpoint.checkpoint_id)
            cursor = await connection.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.agent_framework_checkpoints").format(sql.Identifier(schema))
            )
            assert await cursor.fetchone() == (2,)

    async def test_concurrent_pool_writes_preserve_all_checkpoints(self, checkpoint_database: Any) -> None:
        _, schema = checkpoint_database
        async with (
            AsyncConnectionPool[AsyncConnection[Any]](
                os.environ["POSTGRES_TEST_CONNECTION_STRING"], open=False, kwargs={"autocommit": True}
            ) as pool,
            PostgresCheckpointStorage(
                application_id="app",
                tenant_id="tenant",
                run_id="run",
                client=pool,
                schema=schema,
            ) as storage,
        ):
            await storage.ensure_table()
            checkpoints = [
                WorkflowCheckpoint(workflow_name="approval", graph_signature_hash="graph") for _ in range(12)
            ]
            saved = await asyncio.gather(*(storage.save(checkpoint) for checkpoint in checkpoints))
            listed = await storage.list_checkpoint_ids(workflow_name="approval")
            assert len(listed) == 12 and set(listed) == set(saved)
            latest = await storage.get_latest(workflow_name="approval")
            assert latest is not None and latest.checkpoint_id == listed[-1]

    async def test_approval_resumes_in_a_new_process(self, checkpoint_database: Any) -> None:
        _, schema = checkpoint_database
        sample = Path(__file__).parents[2] / "samples" / "postgres_checkpointing.py"
        environment = {**os.environ, "POSTGRES_CONNECTION_STRING": os.environ["POSTGRES_TEST_CONNECTION_STRING"]}
        common = ["--schema", schema, "--tenant-id", "tenant", "--run-id", "process-restart"]
        start = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(sample), "start", *common],
            env=environment,
            capture_output=True,
            check=False,
            timeout=60,
        )
        assert start.returncode == 0, start.stderr.decode()
        assert b"Prepared order: PO-1042" in start.stdout
        assert b"Waiting for approval" in start.stdout

        resume = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(sample), "resume", *common, "--decision", "approve"],
            env=environment,
            capture_output=True,
            check=False,
            timeout=60,
        )
        assert resume.returncode == 0, resume.stderr.decode()
        assert b"Approved order: PO-1042" in resume.stdout
        assert b"Prepared order" not in resume.stdout
