# Copyright (c) Microsoft. All rights reserved.

import pytest

import agent_framework.azure as azure

CosmosHistoryProvider = pytest.importorskip("agent_framework_azure_cosmos").CosmosHistoryProvider


def test_azure_namespace_exposes_cosmos_history_provider() -> None:
    assert azure.CosmosHistoryProvider is CosmosHistoryProvider
    assert "CosmosHistoryProvider" in dir(azure)
