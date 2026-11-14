# Copyright (c) Microsoft. All rights reserved.

"""Responses and Invocations request models and option policies."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.ai.agentserver.responses import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse

from agent_framework_foundry_hosting import AgentTurn, ResponsesRequest, response_input_messages
from agent_framework_foundry_hosting._scope import FoundryRequestScope
from agent_framework_foundry_hosting._shared import (
    apply_extra_fields_policy,
    parse_agent_turn,
    response_extra_fields,
    validate_default_transport_options,
    validate_extra_fields_policy,
    validate_run_options,
)


def test_response_extra_fields_names_unconsumed_settings_and_extra_body_keys() -> None:
    request = cast(
        CreateResponse,
        {
            "input": "hello",
            "model": "test-model",
            "metadata": {"source": "caller"},
            "store": True,
            "stream": False,
            "background": False,
            "conversation": "outer-conversation",
            "previous_response_id": None,
            "agent_session_id": "forged-sandbox",
            "max_output_tokens": 300,
            "temperature": None,
            "reasoning": {"effort": "high"},
            "extra_body": {"max_tokens": 150, "session_id": "forged"},
        },
    )

    assert response_extra_fields(request) == ["max_output_tokens", "max_tokens", "reasoning"]
    assert response_extra_fields(cast(CreateResponse, {"input": "hi", "model": "m"})) == []


def test_response_request_copies_the_payload() -> None:
    payload = cast(CreateResponse, {"input": "hello", "metadata": {"source": "caller"}})
    context = MagicMock(spec=ResponseContext)
    context.response_id = "outer-id"
    context.conversation_id = None
    scope = FoundryRequestScope(session_id="sandbox", user_id="user", call_id="call", is_hosted=True)
    request = ResponsesRequest(payload, context, scope)

    request.request["metadata"]["source"] = "copied"
    assert payload["metadata"] == {"source": "caller"}
    assert request.scope is scope
    assert request.response_id == "outer-id"
    assert not hasattr(request, "options")


async def test_explicit_message_migration_helper_converts_only_current_turn() -> None:
    context = MagicMock(spec=ResponseContext)
    context.response_id = "outer-id"
    context.conversation_id = None
    items = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "current"}]}]
    context.get_input_items = AsyncMock(return_value=items)
    request = ResponsesRequest(
        cast(CreateResponse, {"input": "current"}),
        context,
        FoundryRequestScope("sandbox", "user", "call", True),
    )
    converted = [MagicMock()]
    with patch(
        "agent_framework_foundry_hosting._responses_shared._items_to_messages",
        new=AsyncMock(return_value=converted),
    ) as converter:
        result = await response_input_messages(request)

    assert result is converted
    converter.assert_awaited_once_with(items)


@pytest.mark.parametrize(
    "options",
    [{"store": True, "session_id": "forged"}, {"extra_body": {"store": True}}, {"tools": []}, {"instructions": "x"}],
)
def test_run_options_reject_host_and_agent_controlled_fields(options: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="host- or agent-controlled fields"):
        validate_run_options(options)
    validate_run_options({"temperature": 0.5, "max_tokens": 10})


def test_default_transport_cannot_override_host_storage_or_identity() -> None:
    with pytest.raises(ValueError, match="store"):
        validate_default_transport_options({"extra_body": {"store": True}}, allow_agent_store=False)
    with pytest.raises(ValueError, match="extra_body"):
        validate_default_transport_options({"extra_body": {"extra_body": {"store": True}}}, allow_agent_store=True)
    validate_default_transport_options({"extra_body": {"store": True}}, allow_agent_store=True)
    validate_default_transport_options({"extra_body": {"temperature": 0.5}}, allow_agent_store=False)


@pytest.mark.parametrize("mode", ["ignore", "warn", "error"])
def test_supported_extra_field_policies(mode: str) -> None:
    assert validate_extra_fields_policy(mode) == mode


def test_unknown_extra_field_policy_fails_at_construction() -> None:
    with pytest.raises(ValueError, match="extra_fields"):
        validate_extra_fields_policy("silent")


def test_extra_fields_policy_warns_ignores_or_rejects(caplog: pytest.LogCaptureFixture) -> None:
    apply_extra_fields_policy("ignore", ["temperature"], protocol="Responses")
    apply_extra_fields_policy("warn", [], protocol="Responses")
    assert caplog.text == ""
    apply_extra_fields_policy("warn", ["tools", "temperature"], protocol="Responses")
    assert "Responses request fields are not used by the default input parser: temperature, tools." in caplog.text
    with pytest.raises(ValueError, match="Supply parse_input"):
        apply_extra_fields_policy("error", ["temperature"], protocol="Invocations")


async def test_parse_agent_turn_accepts_sync_and_async_parsers() -> None:
    async def parse_async(request: str) -> AgentTurn:
        return AgentTurn(messages=request)

    assert (await parse_agent_turn(lambda request: AgentTurn(messages=request), "sync")).messages == "sync"
    assert (await parse_agent_turn(parse_async, "async")).messages == "async"
    with pytest.raises(TypeError, match="parse_input must return AgentTurn"):
        await parse_agent_turn(lambda _request: cast(Any, "hello"), "invalid")


def test_agent_turn_accepts_typed_messages_with_independent_defaults() -> None:
    first = AgentTurn(messages="hello")
    second = AgentTurn(messages="world", stream=True, background=False)
    assert first.messages == "hello"
    assert first.options == second.options == {}
    assert first.options is not second.options
    assert first.stream is None
    assert first.background is None
    assert second.stream is True
    assert second.background is False


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"messages": None}, "messages"),
        ({"messages": [object()]}, "messages"),
        ({"messages": "hello", "options": "not an object"}, "options"),
        ({"messages": "hello", "options": {1: "wrong key"}}, "options"),
        ({"messages": "hello", "stream": "true"}, "stream"),
        ({"messages": "hello", "background": 1}, "background"),
    ],
)
def test_agent_turn_rejects_invalid_parser_values(kwargs: dict[str, Any], error: str) -> None:
    with pytest.raises(TypeError, match=error):
        AgentTurn(**cast(Any, kwargs))
