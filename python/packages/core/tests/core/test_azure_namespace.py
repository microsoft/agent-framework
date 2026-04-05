# Copyright (c) Microsoft. All rights reserved.

from agent_framework_azure_cosmos import CosmosHistoryProvider

import agent_framework.azure as azure


def test_azure_namespace_exposes_cosmos_history_provider() -> None:
    assert azure.CosmosHistoryProvider is CosmosHistoryProvider
    assert "CosmosHistoryProvider" in dir(azure)
