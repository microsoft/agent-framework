# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework_foundry import FoundryChatClient

_TEST_FOUNDRY_PROJECT_ENDPOINT = "https://test-project.services.ai.azure.com/"
_TEST_FOUNDRY_MODEL = "test-gpt-4o"


def _make_mock_openai_client() -> MagicMock:
    client = MagicMock()
    client.default_headers = {}
    client.responses = MagicMock()
    client.responses.create = AsyncMock()
    client.responses.parse = AsyncMock()
    return client


async def test_context_manager_closes_owned_project_client() -> None:
    credential = MagicMock()
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    project_client.close = AsyncMock()

    with patch("agent_framework_foundry._chat_client.AIProjectClient", return_value=project_client):
        async with FoundryChatClient(
            project_endpoint=_TEST_FOUNDRY_PROJECT_ENDPOINT,
            model=_TEST_FOUNDRY_MODEL,
            credential=credential,
        ) as client:
            assert client.project_client is project_client

    project_client.close.assert_awaited_once_with()


async def test_context_manager_does_not_close_injected_project_client() -> None:
    project_client = MagicMock()
    project_client.get_openai_client.return_value = _make_mock_openai_client()
    project_client.close = AsyncMock()

    async with FoundryChatClient(project_client=project_client, model=_TEST_FOUNDRY_MODEL) as client:
        assert client.project_client is project_client

    project_client.close.assert_not_awaited()


async def test_constructor_closes_owned_project_client_when_openai_client_creation_fails() -> None:
    credential = MagicMock()
    project_client = MagicMock()
    project_client.get_openai_client.side_effect = RuntimeError("boom")
    project_client.close = AsyncMock()

    with (
        patch("agent_framework_foundry._chat_client.AIProjectClient", return_value=project_client),
        pytest.raises(RuntimeError, match="boom"),
    ):
        FoundryChatClient(
            project_endpoint=_TEST_FOUNDRY_PROJECT_ENDPOINT,
            model=_TEST_FOUNDRY_MODEL,
            credential=credential,
        )

    await asyncio.sleep(0)
    project_client.close.assert_awaited_once_with()
