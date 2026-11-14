# Copyright (c) Microsoft. All rights reserved.

import pytest

pytest.importorskip("agent_framework_orchestrations")

from agent_framework import AgentResponse, Message
from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from agent_framework.orchestrations import HandoffAgentUserRequest, MagenticPlanReviewRequest


@pytest.mark.parametrize(
    ("request_value", "request_type"),
    [
        (
            HandoffAgentUserRequest(
                agent_response=AgentResponse(messages=[Message("assistant", ["handoff response"])])
            ),
            HandoffAgentUserRequest,
        ),
        (
            MagenticPlanReviewRequest(
                plan=Message("assistant", ["review this plan"]),
                current_progress=None,
                is_stalled=False,
            ),
            MagenticPlanReviewRequest,
        ),
    ],
)
def test_restricted_decode_roundtrips_orchestration_requests(request_value: object, request_type: type[object]) -> None:
    """Pending orchestration requests can be restored from a restricted checkpoint."""
    encoded = encode_checkpoint_value(request_value)

    decoded = decode_checkpoint_value(encoded, allowed_types=frozenset())

    assert isinstance(decoded, request_type)
