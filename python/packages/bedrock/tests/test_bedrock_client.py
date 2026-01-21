# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from agent_framework import ChatMessage, Content, Role
from agent_framework.exceptions import ServiceInitializationError

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


def test_get_response_invokes_bedrock_runtime() -> None:
    stub = _StubBedrockRuntime()
    client = BedrockChatClient(
        model_id="amazon.titan-text",
        region="us-west-2",
        client=stub,
    )

    messages = [
        ChatMessage(role=Role.SYSTEM, contents=[Content.from_text(text="You are concise.")]),
        ChatMessage(role=Role.USER, contents=[Content.from_text(text="hello")]),
    ]

    response = asyncio.run(client.get_response(messages=messages, options={"max_tokens": 32}))

    assert stub.calls, "Expected the runtime client to be called"
    payload = stub.calls[0]
    assert payload["modelId"] == "amazon.titan-text"
    assert payload["messages"][0]["content"][0]["text"] == "hello"
    assert response.messages[0].contents[0].text == "Bedrock says hi"
    assert response.usage_details and response.usage_details["input_token_count"] == 10


def test_build_request_requires_non_system_messages() -> None:
    client = BedrockChatClient(
        model_id="amazon.titan-text",
        region="us-west-2",
        client=_StubBedrockRuntime(),
    )

    messages = [ChatMessage(role=Role.SYSTEM, contents=[Content.from_text(text="Only system text")])]

    with pytest.raises(ServiceInitializationError):
        client._prepare_options(messages, {})
