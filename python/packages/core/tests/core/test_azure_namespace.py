# Copyright (c) Microsoft. All rights reserved.

import pytest

import agent_framework.azure as azure

azure_cosmos = pytest.importorskip("agent_framework_azure_cosmos")


def test_azure_namespace_exposes_cosmos_history_provider() -> None:
    assert azure.CosmosHistoryProvider is azure_cosmos.CosmosHistoryProvider
    assert azure.CosmosCollection is azure_cosmos.CosmosCollection
    assert azure.CosmosStore is azure_cosmos.CosmosStore
    assert azure.AzureCosmosSettings is azure_cosmos.AzureCosmosSettings
    assert {
        "AzureCosmosSettings",
        "CosmosCollection",
        "CosmosHistoryProvider",
        "CosmosStore",
    } <= set(dir(azure))
