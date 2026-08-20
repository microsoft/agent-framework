# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import pytest
from agent_framework import Message
from agent_framework._workflows._checkpoint_encoding import (
    _REGISTERED_CHECKPOINT_TYPE_KEYS,
    decode_checkpoint_value,
    encode_checkpoint_value,
)

from agent_framework_orchestrations._base_group_chat_orchestrator import (
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
)
from agent_framework_orchestrations._handoff import HandoffAgentUserRequest
from agent_framework_orchestrations._magentic import (
    MagenticPlanReviewRequest,
    MagenticPlanReviewResponse,
    MagenticResetSignal,
)
from agent_framework_orchestrations._orchestration_request_info import AgentRequestInfoResponse


@pytest.mark.parametrize(
    "value",
    [
        GroupChatRequestMessage(additional_instruction="go"),
        GroupChatParticipantMessage(messages=[Message(role="user", contents=[])]),
        GroupChatResponseMessage(message=Message(role="assistant", contents=[])),
        MagenticResetSignal(),
    ],
)
def test_builtin_envelopes_restore_without_extra_allowed_types(value: Any) -> None:
    """Framework-owned envelopes decode under a restricted allowlist (issue #7789)."""
    restored = decode_checkpoint_value(encode_checkpoint_value(value), allowed_types=frozenset())

    assert type(restored) is type(value)


@pytest.mark.parametrize(
    "cls",
    [
        HandoffAgentUserRequest,
        AgentRequestInfoResponse,
        MagenticPlanReviewRequest,
        MagenticPlanReviewResponse,
    ],
)
def test_builtin_request_info_types_are_registered(cls: type) -> None:
    """Request/response payloads that get persisted are trusted by default."""
    assert f"{cls.__module__}:{cls.__qualname__}" in _REGISTERED_CHECKPOINT_TYPE_KEYS
