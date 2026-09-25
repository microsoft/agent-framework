# Copyright (c) Microsoft. All rights reserved.

"""Only the Responses request view and option policy are part of this slice."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse

from agent_framework_foundry_hosting import HostedResponseRequest
from agent_framework_foundry_hosting._request import (
    prepare_response_options,
    response_run_options,
    validate_request_options,
    validate_unsupported_options,
)
from agent_framework_foundry_hosting._scope import FoundryRequestScope


def test_native_options_are_translated_before_flattened_extra_body() -> None:
    request = cast(
        CreateResponse,
        {
            "input": "hello",
            "model": "test-model",
            "store": True,
            "background": False,
            "conversation": "outer-conversation",
            "agent_session_id": "forged-sandbox",
            "session_id": "caller-session",
            "user": "forged-user",
            "user_id": "forged-user",
            "call_id": "forged-call",
            "conversation_id": "inner-conversation",
            "service_session_id": "private-session",
            "continuation_token": {"response_id": "private"},
            "max_output_tokens": 300,
            "max_tokens": 150,
            "parallel_tool_calls": False,
            "reasoning": {"effort": "high"},
            "slogan_style": "retro",
        },
    )

    assert response_run_options(request) == {
        "model": "test-model",
        "max_tokens": 150,
        "allow_multiple_tool_calls": False,
        "reasoning": {"effort": "high"},
        "slogan_style": "retro",
    }


def test_nested_extra_body_is_also_overlaid_last_without_reserved_fields() -> None:
    request = cast(
        CreateResponse,
        {
            "max_output_tokens": 300,
            "extra_body": {
                "max_tokens": 150,
                "session_id": "forged",
                "continuation_token": {"response_id": "private"},
            },
        },
    )
    assert response_run_options(request) == {"max_tokens": 150}
    with pytest.raises(TypeError, match="extra_body must be a mapping"):
        response_run_options(cast(CreateResponse, {"extra_body": ["not a mapping"]}))


async def test_hook_uses_a_request_copy_and_does_not_mutate_defaults() -> None:
    payload = cast(CreateResponse, {"input": "hello", "metadata": {"source": "caller"}})
    context = MagicMock(spec=ResponseContext)
    context.response_id = "outer-id"
    context.conversation_id = None
    context.get_input_text = AsyncMock(return_value="hello")
    scope = FoundryRequestScope(session_id="sandbox", user_id="user", call_id="call", is_hosted=True)
    request = HostedResponseRequest(payload, context, scope, {"temperature": 0.8})
    original = {"temperature": 0.8}

    async def remove_temperature(view: HostedResponseRequest, options: dict[str, Any]) -> dict[str, Any]:
        assert view.scope is scope
        assert view.response_id == "outer-id"
        assert await view.get_input_text() == "hello"
        options.pop("temperature")
        view.request["metadata"]["source"] = "copied"
        return options

    await prepare_response_options(request, remove_temperature)
    assert dict(request.options) == {}
    assert original == {"temperature": 0.8}
    assert payload["metadata"] == {"source": "caller"}


async def test_hook_rejects_reserved_fields_and_non_mapping_result() -> None:
    context = MagicMock(spec=ResponseContext)
    context.response_id = "outer-id"
    context.conversation_id = None
    scope = FoundryRequestScope(session_id="sandbox", user_id=None, call_id=None, is_hosted=False)
    request = HostedResponseRequest(cast(CreateResponse, {"input": "hello"}), context, scope, {})

    await prepare_response_options(request, lambda _view, _options: {"store": True, "session_id": "forged"})
    with pytest.raises(ValueError, match="session_id, store"):
        validate_request_options(request.options)
    with pytest.raises(TypeError, match="must return a mapping"):
        await prepare_response_options(request, lambda _view, _options: cast(Any, None))


@pytest.mark.parametrize("mode", ["ignore", "warn", "error"])
def test_supported_unsupported_option_modes(mode: str) -> None:
    assert validate_unsupported_options(mode) == mode


def test_unknown_unsupported_option_mode_fails_at_construction() -> None:
    with pytest.raises(ValueError, match="unsupported_options"):
        validate_unsupported_options("silent")
