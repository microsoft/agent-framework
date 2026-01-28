# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from agent_framework import (
    ChatMessage,
    ChatOptions,
    Content,
    FunctionTool,
    Role,
)
from pydantic import BaseModel

from agent_framework_bedrock._chat_client import BedrockChatClient, BedrockSettings


class _WeatherArgs(BaseModel):
    location: str


def _build_client() -> BedrockChatClient:
    fake_runtime = MagicMock()
    fake_runtime.converse.return_value = {}
    return BedrockChatClient(model_id="test-model", client=fake_runtime)


def _dummy_weather(location: str) -> str:  # pragma: no cover - helper
    return f"Weather in {location}"


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_REGION", "us-west-2")
    monkeypatch.setenv("BEDROCK_CHAT_MODEL_ID", "anthropic.claude-v2")
    settings = BedrockSettings()
    assert settings.region == "us-west-2"
    assert settings.chat_model_id == "anthropic.claude-v2"


def test_build_request_includes_tool_config() -> None:
    client = _build_client()

    tool = FunctionTool(name="get_weather", description="desc", func=_dummy_weather, input_model=_WeatherArgs)
    options = {
        "tools": [tool],
        "tool_choice": {"mode": "required", "required_function_name": "get_weather"},
    }
    messages = [ChatMessage(role=Role.USER, contents=[Content.from_text(text="hi")])]

    request = client._prepare_options(messages, options)

    assert request["toolConfig"]["tools"][0]["toolSpec"]["name"] == "get_weather"
    assert request["toolConfig"]["toolChoice"] == {"tool": {"name": "get_weather"}}


def test_build_request_serializes_tool_history() -> None:
    client = _build_client()
    options: ChatOptions = {}
    messages = [
        ChatMessage(role=Role.USER, contents=[Content.from_text(text="how's weather?")]),
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                Content.from_function_call(call_id="call-1", name="get_weather", arguments='{"location": "SEA"}')
            ],
        ),
        ChatMessage(
            role=Role.TOOL,
            contents=[Content.from_function_result(call_id="call-1", result={"answer": "72F"})],
        ),
    ]

    request = client._prepare_options(messages, options)
    assistant_block = request["messages"][1]["content"][0]["toolUse"]
    result_block = request["messages"][2]["content"][0]["toolResult"]

    assert assistant_block["name"] == "get_weather"
    assert assistant_block["input"] == {"location": "SEA"}
    assert result_block["toolUseId"] == "call-1"
    assert result_block["content"][0]["json"] == {"answer": "72F"}


def test_process_response_parses_tool_use_and_result() -> None:
    client = _build_client()
    response = {
        "modelId": "model",
        "output": {
            "message": {
                "id": "msg-1",
                "content": [
                    {"toolUse": {"toolUseId": "call-1", "name": "get_weather", "input": {"location": "NYC"}}},
                    {"text": "Calling tool"},
                ],
            },
            "completionReason": "tool_use",
        },
    }

    chat_response = client._process_converse_response(response)
    contents = chat_response.messages[0].contents

    assert contents[0].type == "function_call"
    assert contents[0].name == "get_weather"
    assert contents[1].type == "text"
    assert chat_response.finish_reason == client._map_finish_reason("tool_use")


def test_process_response_parses_tool_result() -> None:
    client = _build_client()
    response = {
        "modelId": "model",
        "output": {
            "message": {
                "id": "msg-2",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "call-1",
                            "status": "success",
                            "content": [{"json": {"answer": 42}}],
                        }
                    }
                ],
            },
            "completionReason": "end_turn",
        },
    }

    chat_response = client._process_converse_response(response)
    contents = chat_response.messages[0].contents

    assert contents[0].type == "function_result"
    assert contents[0].result == {"answer": 42}
