# Copyright (c) Microsoft. All rights reserved.

"""Verify that steering fails before starting a host while the AgentServer SDK is affected.

This script does not require Azure credentials or make model requests. The full end-to-end
steering verifier must be restored when a patched core wheel and overflow regression are in place.

Expected output: Steering is temporarily unavailable; no agent or host was started.
"""

from agent_framework import SupportsAgentRun
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions


def _agent_factory() -> SupportsAgentRun:
    raise AssertionError("A guarded steering host must not create an agent.")


def main() -> None:
    """Confirm that the constructor rejects steering before creating an agent or host."""
    try:
        ResponsesHostServer(agent=_agent_factory, options=ResponsesServerOptions(steerable_conversations=True))
    except RuntimeError as exc:
        if "steerable_conversations=True is temporarily unavailable" not in str(exc):
            raise
        print("Steering is temporarily unavailable; no agent or host was started.")
        return
    raise RuntimeError("Steering guard was removed; restore end-to-end and queue-overflow verification.")


if __name__ == "__main__":
    main()
