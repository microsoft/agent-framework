# Copyright (c) Microsoft. All rights reserved.

import pytest
from agent_framework_foundry import FoundryChatClient, FoundryMemoryProvider
from agent_framework_foundry_local import FoundryLocalClient

import agent_framework.azure as azure
import agent_framework.foundry as foundry


def test_foundry_namespace_exposes_cloud_and_local_symbols() -> None:
    assert foundry.FoundryChatClient is FoundryChatClient
    assert foundry.FoundryMemoryProvider is FoundryMemoryProvider
    assert foundry.FoundryLocalClient is FoundryLocalClient
    assert "FoundryChatClient" in dir(foundry)
    assert "FoundryLocalClient" in dir(foundry)


def test_azure_namespace_no_longer_exposes_foundry_symbols() -> None:
    assert "FoundryChatClient" not in dir(azure)
    assert "FoundryLocalClient" not in dir(azure)

    with pytest.raises(AttributeError, match="Module `azure` has no attribute FoundryChatClient\\."):
        _ = azure.FoundryChatClient
