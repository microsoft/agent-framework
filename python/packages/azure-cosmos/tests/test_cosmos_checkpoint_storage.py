# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework._workflows._checkpoint import WorkflowCheckpoint
from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
from agent_framework.exceptions import SettingNotFoundError, WorkflowCheckpointException
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

import agent_framework_azure_cosmos._checkpoint_storage as checkpoint_storage_module
from agent_framework_azure_cosmos._checkpoint_storage import CosmosCheckpointStorage

skip_if_cosmos_integration_tests_disabled = pytest.mark.skipif(
    any(
        os.getenv(name, "") == ""
        for name in (
            "AZURE_COSMOS_ENDPOINT",
            "AZURE_COSMOS_KEY",
            "AZURE_COSMOS_DATABASE_NAME",
            "AZURE_COSMOS_CONTAINER_NAME",
        )
    ),
    reason=(
        "AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_KEY, AZURE_COSMOS_DATABASE_NAME, and "
        "AZURE_COSMOS_CONTAINER_NAME are required for Cosmos integration tests."
    ),
)


def _to_async_iter(items: list[Any]) -> AsyncIterator[Any]:
    async def _iterator() -> AsyncIterator[Any]:
        for item in items:
            yield item

    return _iterator()


def _make_checkpoint(
    workflow_name: str = "test-workflow",
    checkpoint_id: str | None = None,
    previous_checkpoint_id: str | None = None,
    timestamp: str | None = None,
) -> WorkflowCheckpoint:
    """Create a minimal WorkflowCheckpoint for testing."""
    return WorkflowCheckpoint(
        workflow_name=workflow_name,
        graph_signature_hash="abc123",
        checkpoint_id=checkpoint_id or str(uuid.uuid4()),
        previous_checkpoint_id=previous_checkpoint_id,
        timestamp=timestamp or "2025-01-01T00:00:00+00:00",
        state={"counter": 42},
        iteration_count=1,
    )


def _checkpoint_to_cosmos_document(checkpoint: WorkflowCheckpoint) -> dict[str, Any]:
    """Simulate what a Cosmos DB document looks like after save."""
    encoded = encode_checkpoint_value(checkpoint.to_dict())
    doc: dict[str, Any] = {
        "id": f"{checkpoint.workflow_name}_{checkpoint.checkpoint_id}",
        "workflow_name": checkpoint.workflow_name,
        **encoded,
        # Cosmos system properties
        "_rid": "abc",
        "_self": "dbs/abc/colls/def/docs/ghi",
        "_etag": '"00000000-0000-0000-0000-000000000000"',
        "_attachments": "attachments/",
        "_ts": 1700000000,
    }
    return doc


@pytest.fixture
def mock_container() -> MagicMock:
    container = MagicMock()
    container.query_items = MagicMock(return_value=_to_async_iter([]))
    container.upsert_item = AsyncMock(return_value={})
    container.delete_item = AsyncMock(return_value={})
    return container


@pytest.fixture
def mock_cosmos_client(mock_container: MagicMock) -> MagicMock:
    database_client = MagicMock()
    database_client.create_container_if_not_exists = AsyncMock(return_value=mock_container)

    client = MagicMock()
    client.create_database_if_not_exists = AsyncMock(return_value=database_client)
    client.close = AsyncMock()
    return client


# --- Tests for initialization ---


async def test_init_uses_provided_container_client(mock_container: MagicMock) -> None:
    storage = CosmosCheckpointStorage(container_client=mock_container)
    assert storage.database_name == ""
    assert storage.container_name == ""


async def test_init_uses_provided_cosmos_client(mock_cosmos_client: MagicMock) -> None:
    storage = CosmosCheckpointStorage(
        cosmos_client=mock_cosmos_client,
        database_name="db1",
        container_name="checkpoints",
    )
    assert storage.database_name == "db1"
    assert storage.container_name == "checkpoints"


async def test_init_missing_required_settings_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_COSMOS_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_COSMOS_DATABASE_NAME", raising=False)
    monkeypatch.delenv("AZURE_COSMOS_CONTAINER_NAME", raising=False)
    monkeypatch.delenv("AZURE_COSMOS_KEY", raising=False)

    with pytest.raises(SettingNotFoundError, match="database_name"):
        CosmosCheckpointStorage()


async def test_init_constructs_client_with_credential(
    monkeypatch: pytest.MonkeyPatch, mock_cosmos_client: MagicMock
) -> None:
    """Uses key-based auth when a key string is provided, otherwise falls back to Azure credential (RBAC)."""
    mock_factory = MagicMock(return_value=mock_cosmos_client)
    monkeypatch.setattr(checkpoint_storage_module, "CosmosClient", mock_factory)
    monkeypatch.delenv("AZURE_COSMOS_KEY", raising=False)

    # Simulate real-world pattern: use key if available, else RBAC credential
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")
    credential: Any = cosmos_key if cosmos_key else MagicMock()  # MagicMock simulates DefaultAzureCredential()

    CosmosCheckpointStorage(
        endpoint="https://account.documents.azure.com:443/",
        credential=credential,
        database_name="db1",
        container_name="checkpoints",
    )

    mock_factory.assert_called_once()
    kwargs = mock_factory.call_args.kwargs
    assert kwargs["url"] == "https://account.documents.azure.com:443/"
    assert kwargs["credential"] is credential


async def test_init_creates_database_and_container(mock_cosmos_client: MagicMock) -> None:
    storage = CosmosCheckpointStorage(
        cosmos_client=mock_cosmos_client,
        database_name="db1",
        container_name="custom-checkpoints",
    )

    await storage.list_checkpoint_ids(workflow_name="wf")

    mock_cosmos_client.create_database_if_not_exists.assert_awaited_once_with(id="db1")
    database_client = mock_cosmos_client.create_database_if_not_exists.return_value
    assert database_client.create_container_if_not_exists.await_count == 1
    kwargs = database_client.create_container_if_not_exists.await_args.kwargs
    assert kwargs["id"] == "custom-checkpoints"


# --- Tests for save ---


async def test_save_upserts_document(mock_container: MagicMock) -> None:
    storage = CosmosCheckpointStorage(container_client=mock_container)
    checkpoint = _make_checkpoint()

    result = await storage.save(checkpoint)

    assert result == checkpoint.checkpoint_id
    mock_container.upsert_item.assert_awaited_once()
    document = mock_container.upsert_item.await_args.kwargs["body"]
    assert document["id"] == f"test-workflow_{checkpoint.checkpoint_id}"
    assert document["workflow_name"] == "test-workflow"
    assert document["graph_signature_hash"] == "abc123"
    assert document["state"]["counter"] == 42


async def test_save_returns_checkpoint_id(mock_container: MagicMock) -> None:
    storage = CosmosCheckpointStorage(container_client=mock_container)
    checkpoint = _make_checkpoint(checkpoint_id="cp-123")

    result = await storage.save(checkpoint)

    assert result == "cp-123"


# --- Tests for load ---


async def test_load_returns_checkpoint(mock_container: MagicMock) -> None:
    checkpoint = _make_checkpoint(checkpoint_id="cp-load")
    doc = _checkpoint_to_cosmos_document(checkpoint)
    mock_container.query_items.return_value = _to_async_iter([doc])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    loaded = await storage.load("cp-load")

    assert loaded.checkpoint_id == "cp-load"
    assert loaded.workflow_name == "test-workflow"
    assert loaded.graph_signature_hash == "abc123"
    assert loaded.state["counter"] == 42


async def test_load_nonexistent_raises(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)

    with pytest.raises(WorkflowCheckpointException, match="No checkpoint found"):
        await storage.load("nonexistent-id")


async def test_load_queries_without_partition_key(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    with suppress(WorkflowCheckpointException):
        await storage.load("cp-id")

    kwargs = mock_container.query_items.call_args.kwargs
    assert "partition_key" not in kwargs


async def test_load_multiple_workflows_same_checkpoint_id_raises(mock_container: MagicMock) -> None:
    cp1 = _make_checkpoint(checkpoint_id="shared-id", workflow_name="workflow-a")
    cp2 = _make_checkpoint(checkpoint_id="shared-id", workflow_name="workflow-b")
    mock_container.query_items.return_value = _to_async_iter([
        _checkpoint_to_cosmos_document(cp1),
        _checkpoint_to_cosmos_document(cp2),
    ])

    storage = CosmosCheckpointStorage(container_client=mock_container)

    with pytest.raises(WorkflowCheckpointException, match="Multiple checkpoints found"):
        await storage.load("shared-id")


# --- Tests for list_checkpoints ---


async def test_list_checkpoints_returns_checkpoints_for_workflow(mock_container: MagicMock) -> None:
    cp1 = _make_checkpoint(checkpoint_id="cp-1", timestamp="2025-01-01T00:00:00+00:00")
    cp2 = _make_checkpoint(checkpoint_id="cp-2", timestamp="2025-01-02T00:00:00+00:00")
    mock_container.query_items.return_value = _to_async_iter([
        _checkpoint_to_cosmos_document(cp1),
        _checkpoint_to_cosmos_document(cp2),
    ])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    results = await storage.list_checkpoints(workflow_name="test-workflow")

    assert len(results) == 2
    assert results[0].checkpoint_id == "cp-1"
    assert results[1].checkpoint_id == "cp-2"


async def test_list_checkpoints_uses_partition_key(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    await storage.list_checkpoints(workflow_name="my-workflow")

    kwargs = mock_container.query_items.call_args.kwargs
    assert kwargs["partition_key"] == "my-workflow"


async def test_list_checkpoints_empty_returns_empty(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    results = await storage.list_checkpoints(workflow_name="test-workflow")

    assert results == []


async def test_list_checkpoints_skips_malformed_documents(mock_container: MagicMock) -> None:
    valid_cp = _make_checkpoint(checkpoint_id="cp-valid")
    mock_container.query_items.return_value = _to_async_iter([
        {"id": "bad_doc", "workflow_name": "test-workflow", "not_a_checkpoint": True},
        _checkpoint_to_cosmos_document(valid_cp),
    ])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    results = await storage.list_checkpoints(workflow_name="test-workflow")

    assert len(results) == 1
    assert results[0].checkpoint_id == "cp-valid"


# --- Tests for delete ---


async def test_delete_existing_returns_true(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([
        {"id": "test-workflow_cp-del", "workflow_name": "test-workflow"},
    ])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    result = await storage.delete("cp-del")

    assert result is True
    mock_container.delete_item.assert_awaited_once_with(
        item="test-workflow_cp-del",
        partition_key="test-workflow",
    )


async def test_delete_nonexistent_returns_false(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    result = await storage.delete("nonexistent")

    assert result is False
    mock_container.delete_item.assert_not_awaited()


async def test_delete_cosmos_not_found_returns_false(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([
        {"id": "test-workflow_cp-del", "workflow_name": "test-workflow"},
    ])
    mock_container.delete_item = AsyncMock(side_effect=CosmosResourceNotFoundError)

    storage = CosmosCheckpointStorage(container_client=mock_container)
    result = await storage.delete("cp-del")

    assert result is False


# --- Tests for get_latest ---


async def test_get_latest_returns_latest_checkpoint(mock_container: MagicMock) -> None:
    cp = _make_checkpoint(checkpoint_id="cp-latest", timestamp="2025-06-01T00:00:00+00:00")
    mock_container.query_items.return_value = _to_async_iter([
        _checkpoint_to_cosmos_document(cp),
    ])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    result = await storage.get_latest(workflow_name="test-workflow")

    assert result is not None
    assert result.checkpoint_id == "cp-latest"


async def test_get_latest_returns_none_when_empty(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    result = await storage.get_latest(workflow_name="test-workflow")

    assert result is None


async def test_get_latest_uses_order_by_desc_with_limit(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    await storage.get_latest(workflow_name="test-workflow")

    kwargs = mock_container.query_items.call_args.kwargs
    assert "ORDER BY c.timestamp DESC" in kwargs["query"]
    assert "OFFSET 0 LIMIT 1" in kwargs["query"]


# --- Tests for list_checkpoint_ids ---


async def test_list_checkpoint_ids_returns_ids(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([
        {"checkpoint_id": "cp-1"},
        {"checkpoint_id": "cp-2"},
    ])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    ids = await storage.list_checkpoint_ids(workflow_name="test-workflow")

    assert ids == ["cp-1", "cp-2"]


async def test_list_checkpoint_ids_empty_returns_empty(mock_container: MagicMock) -> None:
    mock_container.query_items.return_value = _to_async_iter([])

    storage = CosmosCheckpointStorage(container_client=mock_container)
    ids = await storage.list_checkpoint_ids(workflow_name="test-workflow")

    assert ids == []


# --- Tests for close and context manager ---


async def test_close_closes_owned_client(monkeypatch: pytest.MonkeyPatch, mock_cosmos_client: MagicMock) -> None:
    mock_factory = MagicMock(return_value=mock_cosmos_client)
    monkeypatch.setattr(checkpoint_storage_module, "CosmosClient", mock_factory)

    storage = CosmosCheckpointStorage(
        endpoint="https://account.documents.azure.com:443/",
        credential="key-123",
        database_name="db1",
        container_name="checkpoints",
    )

    await storage.close()

    mock_cosmos_client.close.assert_awaited_once()


async def test_close_does_not_close_external_client(mock_cosmos_client: MagicMock) -> None:
    storage = CosmosCheckpointStorage(
        cosmos_client=mock_cosmos_client,
        database_name="db1",
        container_name="checkpoints",
    )

    await storage.close()

    mock_cosmos_client.close.assert_not_awaited()


async def test_context_manager_closes_owned_client(
    monkeypatch: pytest.MonkeyPatch, mock_cosmos_client: MagicMock
) -> None:
    mock_factory = MagicMock(return_value=mock_cosmos_client)
    monkeypatch.setattr(checkpoint_storage_module, "CosmosClient", mock_factory)

    async with CosmosCheckpointStorage(
        endpoint="https://account.documents.azure.com:443/",
        credential="key-123",
        database_name="db1",
        container_name="checkpoints",
    ) as storage:
        assert storage is not None

    mock_cosmos_client.close.assert_awaited_once()


async def test_context_manager_preserves_original_exception(mock_container: MagicMock) -> None:
    storage = CosmosCheckpointStorage(container_client=mock_container)

    with (
        patch.object(storage, "close", AsyncMock(side_effect=RuntimeError("close failed"))),
        pytest.raises(ValueError, match="inner error"),
    ):
        async with storage:
            raise ValueError("inner error")


async def test_context_manager_reraises_close_error(mock_container: MagicMock) -> None:
    storage = CosmosCheckpointStorage(container_client=mock_container)

    with (
        patch.object(storage, "close", AsyncMock(side_effect=RuntimeError("close failed"))),
        pytest.raises(RuntimeError, match="close failed"),
    ):
        async with storage:
            pass  # no inner exception — close error should propagate


# --- Tests for save/load round-trip ---


async def test_round_trip_preserves_data(mock_container: MagicMock) -> None:
    checkpoint = _make_checkpoint(
        checkpoint_id="cp-roundtrip",
        previous_checkpoint_id="cp-parent",
    )
    checkpoint.state = {"key": "value", "nested": {"a": 1}}
    checkpoint.metadata = {"superstep": 3}
    checkpoint.iteration_count = 5

    saved_doc: dict[str, Any] = {}

    async def capture_upsert(body: dict[str, Any]) -> dict[str, Any]:
        saved_doc.update(body)
        return body

    mock_container.upsert_item = AsyncMock(side_effect=capture_upsert)

    storage = CosmosCheckpointStorage(container_client=mock_container)
    await storage.save(checkpoint)

    returned_doc = {
        **saved_doc,
        "_rid": "abc",
        "_self": "dbs/abc/colls/def/docs/ghi",
        "_etag": '"etag"',
        "_attachments": "attachments/",
        "_ts": 1700000000,
    }
    mock_container.query_items.return_value = _to_async_iter([returned_doc])

    loaded = await storage.load("cp-roundtrip")

    assert loaded.checkpoint_id == checkpoint.checkpoint_id
    assert loaded.workflow_name == checkpoint.workflow_name
    assert loaded.graph_signature_hash == checkpoint.graph_signature_hash
    assert loaded.previous_checkpoint_id == "cp-parent"
    assert loaded.state == {"key": "value", "nested": {"a": 1}}
    assert loaded.metadata == {"superstep": 3}
    assert loaded.iteration_count == 5
    assert loaded.version == "1.0"


# --- Integration test ---


@pytest.mark.integration
@skip_if_cosmos_integration_tests_disabled
async def test_cosmos_checkpoint_storage_roundtrip_with_emulator() -> None:
    endpoint = os.getenv("AZURE_COSMOS_ENDPOINT", "")
    key = os.getenv("AZURE_COSMOS_KEY", "")
    database_prefix = os.getenv("AZURE_COSMOS_DATABASE_NAME", "")
    container_prefix = os.getenv("AZURE_COSMOS_CONTAINER_NAME", "")
    unique = uuid.uuid4().hex[:8]
    database_name = f"{database_prefix}-cp-{unique}"
    container_name = f"{container_prefix}-cp-{unique}"

    async with CosmosClient(url=endpoint, credential=key) as cosmos_client:
        await cosmos_client.create_database_if_not_exists(id=database_name)

        storage = CosmosCheckpointStorage(
            cosmos_client=cosmos_client,
            database_name=database_name,
            container_name=container_name,
        )

        try:
            # Save two checkpoints for the same workflow
            cp1 = _make_checkpoint(
                checkpoint_id="cp-int-1",
                workflow_name="integration-wf",
                timestamp="2025-01-01T00:00:00+00:00",
            )
            cp2 = _make_checkpoint(
                checkpoint_id="cp-int-2",
                workflow_name="integration-wf",
                previous_checkpoint_id="cp-int-1",
                timestamp="2025-01-02T00:00:00+00:00",
            )
            cp2.state = {"step": 2}

            await storage.save(cp1)
            await storage.save(cp2)

            # Load by ID
            loaded = await storage.load("cp-int-1")
            assert loaded.checkpoint_id == "cp-int-1"
            assert loaded.workflow_name == "integration-wf"

            # List all checkpoints for workflow
            all_cps = await storage.list_checkpoints(workflow_name="integration-wf")
            assert len(all_cps) == 2

            # List checkpoint IDs
            ids = await storage.list_checkpoint_ids(workflow_name="integration-wf")
            assert "cp-int-1" in ids
            assert "cp-int-2" in ids

            # Get latest
            latest = await storage.get_latest(workflow_name="integration-wf")
            assert latest is not None
            assert latest.checkpoint_id == "cp-int-2"
            assert latest.state == {"step": 2}

            # Delete
            assert await storage.delete("cp-int-1") is True
            assert await storage.delete("cp-int-1") is False

            remaining = await storage.list_checkpoint_ids(workflow_name="integration-wf")
            assert remaining == ["cp-int-2"]

            # Cross-workflow isolation
            other_cp = _make_checkpoint(
                checkpoint_id="cp-other",
                workflow_name="other-wf",
            )
            await storage.save(other_cp)
            wf_cps = await storage.list_checkpoints(workflow_name="integration-wf")
            assert len(wf_cps) == 1
            assert wf_cps[0].checkpoint_id == "cp-int-2"

        finally:
            with suppress(Exception):
                await cosmos_client.delete_database(database_name)
