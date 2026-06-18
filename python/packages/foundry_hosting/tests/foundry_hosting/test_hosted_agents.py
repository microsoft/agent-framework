# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from agent_framework_foundry_hosting.hosted_agents import foundry_response_id, foundry_response_id_factory

_RESPONSE_PREFIX = "caresp_"
_PARTITION_KEY_LENGTH = 18
_ENTROPY_LENGTH = 32


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


def test_foundry_response_id_factory_returns_helper() -> None:
    factory = foundry_response_id_factory()

    response_id = factory(None)
    assert response_id.startswith(_RESPONSE_PREFIX)
