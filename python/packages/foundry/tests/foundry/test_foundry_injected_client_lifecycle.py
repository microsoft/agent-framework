# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Self
from unittest.mock import AsyncMock, patch

from agent_framework_foundry import FoundryMemoryProvider, RawFoundryEmbeddingClient


class _InjectedProjectClient(AsyncMock, AbstractAsyncContextManager):  # type: ignore[misc]
    async def __aenter__(self) -> Self:
        await AsyncMock.__aenter__(self)
        return self

    async def __aexit__(self, *args: Any) -> None:
        await AsyncMock.__aexit__(self, *args)


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


async def test_foundry_memory_provider_skips_injected_project_client_lifecycle() -> None:
    project = _InjectedProjectClient()
    memory = FoundryMemoryProvider(
        project_client=project,
        memory_store_name="store",
        scope="scope",
    )

    assert memory._owns_project_client is False
    enter_mock = AsyncMock()
    exit_mock = AsyncMock()
    with (
        patch.object(project, "__aenter__", enter_mock),
        patch.object(project, "__aexit__", exit_mock),
    ):
        await memory.__aenter__()
        await memory.__aexit__(None, None, None)

    enter_mock.assert_not_awaited()
    exit_mock.assert_not_awaited()
