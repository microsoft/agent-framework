# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from azure.ai.agentserver.core import FoundryAgentRequestContext

_PROTOCOL_V2_REQUIRED_MESSAGE = (
    "The hosted environment is running on protocol 1.0.0, but the agent requires protocol 2.0.0. "
    "Please upgrade your agent protocol to 2.0.0 in `agent.manifest.yaml` or `agent.yaml`, or "
    "downgrade the `agent-framework-foundry-hosting` package to `1.0.0a260625` or before to use 1.0.0."
)


def validate_foundry_request_context(
    context: FoundryAgentRequestContext,
    *,
    is_hosted: bool,
) -> None:
    """Validate that a hosted request contains protocol-v2 user identity."""
    if is_hosted and context.call_id is None:
        raise RuntimeError(_PROTOCOL_V2_REQUIRED_MESSAGE)
    if is_hosted and not context.user_id:
        raise RuntimeError(
            "The hosted environment is missing the platform user ID in the request context. "
            "Please ensure that the request is coming from a valid Foundry platform service."
        )
