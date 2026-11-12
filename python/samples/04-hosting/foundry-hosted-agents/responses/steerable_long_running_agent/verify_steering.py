# Copyright (c) Microsoft. All rights reserved.

"""Verify that the unsupported steering setting cannot start an agent or host.

This script does not require Azure credentials or make model requests. A future steering verifier
requires a supported steering API, a patched core wheel, and an overflow regression.

Expected output: Steering is temporarily unavailable; no agent or host was started.
"""

from typing import Any

from agent_framework import SupportsAgentRun
from agent_framework_foundry_hosting import ResponsesHostServer, ResponsesRequest


def _agent_factory(*, request: ResponsesRequest) -> SupportsAgentRun:
    raise AssertionError("A guarded steering host must not create an agent.")


def main() -> None:
    """Confirm that the constructor rejects steering before creating an agent or host."""
    removed_settings: dict[str, Any] = {"steerable_conversations": True}
    try:
        ResponsesHostServer(agent=_agent_factory, **removed_settings)
    except TypeError as exc:
        if "steerable_conversations" not in str(exc):
            raise
        print("Steering is temporarily unavailable; no agent or host was started.")
        return
    raise RuntimeError("Steering guard was removed; restore end-to-end and queue-overflow verification.")


if __name__ == "__main__":
    main()
