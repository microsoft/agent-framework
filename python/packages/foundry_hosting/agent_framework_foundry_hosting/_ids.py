# Copyright (c) Microsoft. All rights reserved.

"""Foundry-storage-compatible identifier helpers.

The Foundry hosted-agent storage backend partitions records by extracting
an embedded partition-key segment from every record/item id. The id
format is ``{prefix}_{18charPartitionKey}{32charEntropy}`` (or a 48-char
legacy body).  Free-form ids such as ``resp_<uuid hex>`` carry no valid
partition key and the storage API rejects writes with an opaque
``HTTP 500 server_error``.

These helpers wrap :class:`azure.ai.agentserver.responses._id_generator.IdGenerator`
so callers (e.g. the ``ResponsesChannel.response_id_factory`` argument
or :class:`FoundryHostedAgentHistoryProvider.save_messages`) can mint
ids that the storage backend accepts without leaking the SDK import
path into user code.
"""

from __future__ import annotations

from typing import Any

from azure.ai.agentserver.responses._id_generator import IdGenerator

__all__ = [
    "foundry_item_id",
    "foundry_response_id",
    "foundry_response_id_factory",
]


def foundry_response_id(previous_response_id: str | None = None) -> str:
    """Mint a Foundry-storage-compatible response id (``caresp_*``).

    Args:
        previous_response_id: When supplied (and shaped like a Foundry
            id with an embedded partition key), the new id co-locates
            with the chain by reusing that partition key. The storage
            backend rejects chained writes whose new record sits in a
            different partition than the prior one.

    Returns:
        A new id of the form ``caresp_<18charPartitionKey><32charEntropy>``.
    """
    return IdGenerator.new_response_id(previous_response_id or "")


def foundry_response_id_factory() -> "Any":
    """Return a callable suitable for ``ResponsesChannel(response_id_factory=...)``.

    The returned callable accepts an optional ``previous_response_id``
    hint which the channel passes for chained turns so the new id
    inherits the prior turn's partition key (Foundry storage requirement).
    """
    return foundry_response_id


def foundry_item_id(item: "Any", response_id: str | None = None) -> str | None:
    """Mint a Foundry-storage-compatible item id for *item*.

    Dispatches via :meth:`IdGenerator.new_item_id` so the id picks up
    the right type prefix (``msg`` / ``om`` / ``fc`` / ``rs`` / ...).
    When ``response_id`` is supplied it acts as a partition-key hint so
    every item written under one response co-locates with the response
    record (Foundry storage requirement).

    Returns:
        A new id of the form ``{type-prefix}_<partitionKey><entropy>``,
        or ``None`` when *item* is an unrecognised / reference-only type
        (mirrors the SDK helper's contract).
    """
    return IdGenerator.new_item_id(item, response_id)
