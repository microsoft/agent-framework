# Copyright (c) Microsoft. All rights reserved.

"""Helpers for running Agent Framework apps as Foundry Hosted Agents."""

from __future__ import annotations

from collections.abc import Callable

from azure.ai.agentserver.responses._id_generator import IdGenerator

FoundryResponseIdFactory = Callable[[str | None], str]


def foundry_response_id(previous_response_id: str | None = None) -> str:
    """Mint a Foundry-storage-compatible response ID.

    Args:
        previous_response_id: Optional previous response ID. When it already uses
            the Foundry response ID shape, the new ID reuses its partition key so
            chained responses are stored together.

    Returns:
        A response ID that the Foundry Hosted Agents storage backend accepts.
    """
    return IdGenerator.new_response_id(previous_response_id or "")


def foundry_response_id_factory() -> FoundryResponseIdFactory:
    """Return a callable suitable for response ID factory hooks.

    Returns:
        The :func:`foundry_response_id` function.
    """
    return foundry_response_id
