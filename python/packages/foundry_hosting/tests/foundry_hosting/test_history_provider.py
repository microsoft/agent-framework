# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import pytest
from agent_framework import Content, ExperimentalFeature, Message

from agent_framework_foundry_hosting import FoundryHostedAgentHistoryProvider, foundry_response_id

_RESPONSE_PREFIX = "caresp_"
_PARTITION_KEY_LENGTH = 18
_ENTROPY_LENGTH = 32


def test_history_provider_public_api_is_marked_experimental() -> None:
    assert getattr(FoundryHostedAgentHistoryProvider, "__feature_id__", None) == ExperimentalFeature.HOSTING.value
    assert getattr(foundry_response_id, "__feature_id__", None) == ExperimentalFeature.HOSTING.value


def test_foundry_response_id_uses_foundry_shape() -> None:
    response_id = foundry_response_id()

    assert response_id.startswith(_RESPONSE_PREFIX)
    assert len(response_id) == len(_RESPONSE_PREFIX) + _PARTITION_KEY_LENGTH + _ENTROPY_LENGTH


def test_foundry_response_id_reuses_previous_partition_key() -> None:
    first_id = foundry_response_id()
    next_id = foundry_response_id(first_id)

    partition_start = len(_RESPONSE_PREFIX)
    partition_end = partition_start + _PARTITION_KEY_LENGTH
    assert next_id != first_id
    assert next_id[partition_start:partition_end] == first_id[partition_start:partition_end]


async def test_history_provider_round_trips_messages_locally() -> None:
    provider = FoundryHostedAgentHistoryProvider()
    response_id = foundry_response_id()

    with provider.bind_request_context(response_id=response_id):
        await provider.save_messages(
            None,
            [
                Message(role="user", contents=[Content.from_text("hello")]),
                Message(role="assistant", contents=[Content.from_text("hi")]),
            ],
        )

    loaded = await provider.get_messages(response_id)

    assert [message.role for message in loaded] == ["user", "assistant"]
    assert [message.text for message in loaded] == ["hello", "hi"]


async def test_history_provider_chains_previous_response_history() -> None:
    provider = FoundryHostedAgentHistoryProvider()
    first_id = foundry_response_id()
    second_id = foundry_response_id(first_id)

    with provider.bind_request_context(response_id=first_id):
        await provider.save_messages(None, [Message(role="user", contents=[Content.from_text("first")])])

    with provider.bind_request_context(response_id=second_id, previous_response_id=first_id):
        await provider.save_messages(None, [Message(role="assistant", contents=[Content.from_text("second")])])

    loaded = await provider.get_messages(second_id)

    assert [message.text for message in loaded] == ["first", "second"]


def test_history_provider_requires_credentials_when_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.test")

    provider = FoundryHostedAgentHistoryProvider()

    with pytest.raises(RuntimeError, match="credential"):
        provider._resolve_backend()  # pyright: ignore[reportPrivateUsage]
