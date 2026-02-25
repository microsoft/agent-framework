# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import SettingNotFoundError

import agent_framework_azure_cosmos._history_provider as history_provider_module
from agent_framework_azure_cosmos._history_provider import CosmosHistoryProvider


def _to_async_iter(items: list[Any]) -> AsyncIterator[Any]:
    async def _iterator() -> AsyncIterator[Any]:
        for item in items:
            yield item

    return _iterator()


@pytest.fixture
def mock_container() -> MagicMock:
    container = MagicMock()
    container.query_items = MagicMock(return_value=_to_async_iter([]))
    container.execute_item_batch = AsyncMock(return_value=[])
    return container


@pytest.fixture
def mock_cosmos_client(mock_container: MagicMock) -> MagicMock:
    database_client = MagicMock()
    database_client.create_container_if_not_exists = AsyncMock(return_value=mock_container)

    client = MagicMock()
    client.get_database_client.return_value = database_client
    client.close = AsyncMock()
    return client


class TestCosmosHistoryProviderInit:
    def test_uses_provided_container_client(self, mock_container: MagicMock) -> None:
        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)
        assert provider.source_id == "mem"
        assert provider.load_messages is True
        assert provider.store_outputs is True
        assert provider.store_inputs is True

    def test_uses_provided_cosmos_client(self, mock_cosmos_client: MagicMock) -> None:
        provider = CosmosHistoryProvider(
            source_id="mem",
            cosmos_client=mock_cosmos_client,
            database_name="db1",
            container_name="history",
        )

        mock_cosmos_client.get_database_client.assert_called_once_with("db1")
        assert provider.database_name == "db1"
        assert provider.container_name == "history"

    def test_missing_required_settings_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AZURE_COSMOS_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_COSMOS_DATABASE_NAME", raising=False)
        monkeypatch.delenv("AZURE_COSMOS_CONTAINER_NAME", raising=False)
        monkeypatch.delenv("AZURE_COSMOS_KEY", raising=False)

        with pytest.raises(SettingNotFoundError, match="database_name"):
            CosmosHistoryProvider()

    def test_constructs_client_with_string_credential(
        self, monkeypatch: pytest.MonkeyPatch, mock_cosmos_client: MagicMock
    ) -> None:
        mock_factory = MagicMock(return_value=mock_cosmos_client)
        monkeypatch.setattr(history_provider_module, "CosmosClient", mock_factory)

        CosmosHistoryProvider(
            endpoint="https://account.documents.azure.com:443/",
            credential="key-123",
            database_name="db1",
            container_name="history",
        )

        mock_factory.assert_called_once()
        kwargs = mock_factory.call_args.kwargs
        assert kwargs["url"] == "https://account.documents.azure.com:443/"
        assert kwargs["credential"] == "key-123"


class TestCosmosHistoryProviderContainerConfig:
    async def test_provider_container_name_is_used(self, mock_cosmos_client: MagicMock) -> None:
        provider = CosmosHistoryProvider(
            source_id="mem",
            cosmos_client=mock_cosmos_client,
            database_name="db1",
            container_name="custom-history",
        )

        await provider.get_messages("session-123")

        database_client = mock_cosmos_client.get_database_client.return_value
        assert database_client.create_container_if_not_exists.await_count == 1
        kwargs = database_client.create_container_if_not_exists.await_args.kwargs
        assert kwargs["id"] == "custom-history"


class TestCosmosHistoryProviderGetMessages:
    async def test_returns_deserialized_messages(self, mock_container: MagicMock) -> None:
        msg1 = Message(role="user", contents=["Hello"])
        msg2 = Message(role="assistant", contents=["Hi"])
        mock_container.query_items.return_value = _to_async_iter([
            {"message": msg1.to_dict()},
            {"message": msg2.to_dict()},
        ])

        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)
        messages = await provider.get_messages("s1")

        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].text == "Hi"

    async def test_empty_returns_empty(self, mock_container: MagicMock) -> None:
        mock_container.query_items.return_value = _to_async_iter([])

        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)
        messages = await provider.get_messages("s1")

        assert messages == []


class TestCosmosHistoryProviderListSessions:
    async def test_list_sessions_returns_unique_sorted_ids(self, mock_container: MagicMock) -> None:
        mock_container.query_items.return_value = _to_async_iter(["s2", "s1", "s1", "s3"])
        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)

        sessions = await provider.list_sessions()

        assert sessions == ["s1", "s2", "s3"]
        kwargs = mock_container.query_items.call_args.kwargs
        assert kwargs["query"] == "SELECT DISTINCT VALUE c.session_id FROM c"
        assert kwargs["enable_cross_partition_query"] is True


class TestCosmosHistoryProviderSaveMessages:
    async def test_saves_messages(self, mock_container: MagicMock) -> None:
        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)
        messages = [Message(role="user", contents=["Hello"]), Message(role="assistant", contents=["Hi"])]

        await provider.save_messages("s1", messages)

        mock_container.execute_item_batch.assert_awaited_once()
        batch_operations = mock_container.execute_item_batch.await_args.kwargs["batch_operations"]
        assert len(batch_operations) == 2
        first_operation, first_args = batch_operations[0]
        assert first_operation == "upsert"
        first_document = first_args[0]
        assert first_document["session_id"] == "s1"
        assert first_document["message"]["role"] == "user"
        assert mock_container.execute_item_batch.await_args.kwargs["partition_key"] == "s1"

    async def test_empty_messages_noop(self, mock_container: MagicMock) -> None:
        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)

        await provider.save_messages("s1", [])

        mock_container.execute_item_batch.assert_not_awaited()


class TestCosmosHistoryProviderClear:
    async def test_clear_deletes_all_session_items(self, mock_container: MagicMock) -> None:
        mock_container.query_items.return_value = _to_async_iter([{"id": "1"}, {"id": "2"}])
        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)

        await provider.clear("s1")

        mock_container.execute_item_batch.assert_awaited_once()
        batch_operations = mock_container.execute_item_batch.await_args.kwargs["batch_operations"]
        assert len(batch_operations) == 2
        assert batch_operations[0] == ("delete", ("1",))
        assert batch_operations[1] == ("delete", ("2",))
        assert mock_container.execute_item_batch.await_args.kwargs["partition_key"] == "s1"


class TestCosmosHistoryProviderBeforeAfterRun:
    async def test_before_run_loads_history(self, mock_container: MagicMock) -> None:
        msg = Message(role="user", contents=["old msg"])
        mock_container.query_items.return_value = _to_async_iter([{"message": msg.to_dict()}])

        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)
        session = AgentSession(session_id="test")
        context = SessionContext(input_messages=[Message(role="user", contents=["new msg"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert "mem" in context.context_messages
        assert context.context_messages["mem"][0].text == "old msg"

    async def test_after_run_stores_input_and_response(self, mock_container: MagicMock) -> None:
        provider = CosmosHistoryProvider(source_id="mem", container_client=mock_container)
        session = AgentSession(session_id="test")
        context = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")
        context._response = AgentResponse(messages=[Message(role="assistant", contents=["hello"])])

        await provider.after_run(
            agent=None, session=session, context=context, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_container.execute_item_batch.assert_awaited_once()
        batch_operations = mock_container.execute_item_batch.await_args.kwargs["batch_operations"]
        assert len(batch_operations) == 2


class TestCosmosHistoryProviderClose:
    async def test_close_closes_owned_client(
        self, monkeypatch: pytest.MonkeyPatch, mock_cosmos_client: MagicMock
    ) -> None:
        mock_factory = MagicMock(return_value=mock_cosmos_client)
        monkeypatch.setattr(history_provider_module, "CosmosClient", mock_factory)

        provider = CosmosHistoryProvider(
            endpoint="https://account.documents.azure.com:443/",
            credential="key-123",
            database_name="db1",
            container_name="history",
        )

        await provider.close()

        mock_cosmos_client.close.assert_awaited_once()

    async def test_close_does_not_close_external_client(self, mock_cosmos_client: MagicMock) -> None:
        provider = CosmosHistoryProvider(
            source_id="mem",
            cosmos_client=mock_cosmos_client,
            database_name="db1",
            container_name="history",
        )

        await provider.close()

        mock_cosmos_client.close.assert_not_awaited()

    async def test_async_context_manager_closes_owned_client(
        self, monkeypatch: pytest.MonkeyPatch, mock_cosmos_client: MagicMock
    ) -> None:
        mock_factory = MagicMock(return_value=mock_cosmos_client)
        monkeypatch.setattr(history_provider_module, "CosmosClient", mock_factory)

        async with CosmosHistoryProvider(
            endpoint="https://account.documents.azure.com:443/",
            credential="key-123",
            database_name="db1",
            container_name="history",
        ) as provider:
            assert provider is not None

        mock_cosmos_client.close.assert_awaited_once()
