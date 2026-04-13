# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any

import pytest
from agent_framework import Content, Message

from agent_framework_bedrock import BedrockChatClient


class _StubBedrockRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "modelId": kwargs["modelId"],
            "responseId": "resp-123",
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
            "output": {
                "completionReason": "end_turn",
                "message": {
                    "id": "msg-1",
                    "role": "assistant",
                    "content": [{"text": "Bedrock says hi"}],
                },
            },
        }


def _make_client() -> BedrockChatClient:
    """Create a BedrockChatClient with a stub runtime for unit tests."""
    return BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=_StubBedrockRuntime(),
    )


async def test_get_response_invokes_bedrock_runtime() -> None:
    stub = _StubBedrockRuntime()
    client = BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=stub,
    )

    messages = [
        Message(role="system", contents=[Content.from_text(text="You are concise.")]),
        Message(role="user", contents=[Content.from_text(text="hello")]),
    ]

    response = await client.get_response(messages=messages, options={"max_tokens": 32})

    assert stub.calls, "Expected the runtime client to be called"
    payload = stub.calls[0]
    assert payload["modelId"] == "amazon.titan-text"
    assert payload["messages"][0]["content"][0]["text"] == "hello"
    assert response.messages[0].contents[0].text == "Bedrock says hi"
    assert response.usage_details and response.usage_details["input_token_count"] == 10


def test_build_request_requires_non_system_messages() -> None:
    client = BedrockChatClient(
        model="amazon.titan-text",
        region="us-west-2",
        client=_StubBedrockRuntime(),
    )

    messages = [Message(role="system", contents=[Content.from_text(text="Only system text")])]

    with pytest.raises(ValueError):
        client._prepare_options(messages, {})


def test_prepare_options_tool_choice_none_omits_tool_config() -> None:
    """When tool_choice='none', toolConfig must be omitted entirely.

    Bedrock's Converse API only accepts 'auto', 'any', or 'tool' as valid
    toolChoice keys. Sending {"none": {}} causes a ParamValidationError.
    The fix omits toolConfig so the model won't attempt tool calls.

    Fixes #4529.
    """
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    # Even when tools are provided, tool_choice="none" should strip toolConfig
    options: dict[str, Any] = {
        "tool_choice": "none",
        "tools": [
            {"toolSpec": {"name": "get_weather", "description": "Get weather", "inputSchema": {"json": {}}}},
        ],
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" not in request, (
        f"toolConfig should be omitted when tool_choice='none', got: {request.get('toolConfig')}"
    )


def test_prepare_options_tool_choice_auto_includes_tool_config() -> None:
    """When tool_choice='auto', toolConfig.toolChoice should be {'auto': {}}."""
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "auto",
        "tools": [
            {"toolSpec": {"name": "get_weather", "description": "Get weather", "inputSchema": {"json": {}}}},
        ],
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" in request
    assert request["toolConfig"]["toolChoice"] == {"auto": {}}


def test_prepare_options_tool_choice_required_includes_any() -> None:
    """When tool_choice='required' (no specific function), toolChoice should be {'any': {}}."""
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "required",
        "tools": [
            {"toolSpec": {"name": "get_weather", "description": "Get weather", "inputSchema": {"json": {}}}},
        ],
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" in request
    assert request["toolConfig"]["toolChoice"] == {"any": {}}
