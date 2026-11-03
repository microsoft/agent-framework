# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from typing_extensions import Self

from agent_framework_foundry import FoundryMemoryProvider, RawFoundryEmbeddingClient


class _InjectedProjectClient(AsyncMock, AbstractAsyncContextManager):  # type: ignore[misc]
    async def __aenter__(self) -> Self:
        await AsyncMock.__aenter__(self)
        return self

    async def __aexit__(self, *args: Any) -> None:
        await AsyncMock.__aexit__(self, *args)


@pytest.mark.asyncio
async def test_raw_foundry_embedding_close_skips_injected_clients() -> None:
    text = AsyncMock()
    image = AsyncMock()
    embeddings = RawFoundryEmbeddingClient(
        model="embed-model",
        endpoint="https://configured.example",
        text_client=text,
        image_client=image,
    )

    await embeddings.close()

    text.close.assert_not_awaited()
    image.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_foundry_memory_provider_skips_injected_project_client_lifecycle() -> None:
    project = _InjectedProjectClient()
    memory = FoundryMemoryProvider(
        project_client=project,
        memory_store_name="store",
        scope="scope",
    )

    assert memory._owns_project_client is False
    await memory.__aenter__()
    await memory.__aexit__(None, None, None)

    project.__aenter__.assert_not_awaited()
    project.__aexit__.assert_not_awaited()
