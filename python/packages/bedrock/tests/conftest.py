# Copyright (c) Microsoft. All rights reserved.
from typing import Any
from unittest.mock import MagicMock

from pytest import fixture


@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


@fixture
def bedrock_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for BedrockSettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "AWS_BEARER_TOKEN_BEDROCK": "test-bearer-token-12345",
        "AWS_REGION_NAME": "us-east-1",
        "AWS_CHAT_MODEL_ID": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@fixture
def mock_bedrock_client() -> MagicMock:
    """Fixture that provides a mock boto3 bedrock-runtime client."""
    mock_client = MagicMock()

    # Mock converse method
    mock_client.converse = MagicMock()

    # Mock converse_stream method
    mock_client.converse_stream = MagicMock()

    # Mock invoke_model methods
    mock_client.invoke_model = MagicMock()
    mock_client.invoke_model_with_response_stream = MagicMock()

    return mock_client


@fixture
def mock_converse_response() -> dict[str, Any]:
    """Fixture that provides a mock Converse API response."""
    return {
        "ResponseMetadata": {"RequestId": "test-request-id-123", "HTTPStatusCode": 200},
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Hello! I'm here to help. How can I assist you today?"}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 15, "totalTokens": 25},
    }


@fixture
def mock_converse_response_with_tools() -> dict[str, Any]:
    """Fixture that provides a mock Converse API response with tool use."""
    return {
        "ResponseMetadata": {"RequestId": "test-request-id-456", "HTTPStatusCode": 200},
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"text": "Let me check the weather for you."},
                    {
                        "toolUse": {
                            "toolUseId": "tool-123",
                            "name": "get_weather",
                            "input": {"location": "San Francisco"},
                        }
                    },
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 50, "outputTokens": 20, "totalTokens": 70},
    }


@fixture
def mock_stream_events() -> list[dict[str, Any]]:
    """Fixture that provides mock ConverseStream events."""
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"text": ""}, "contentBlockIndex": 0}},
        {"contentBlockDelta": {"delta": {"text": "Hello"}, "contentBlockIndex": 0}},
        {"contentBlockDelta": {"delta": {"text": " world"}, "contentBlockIndex": 0}},
        {"contentBlockDelta": {"delta": {"text": "!"}, "contentBlockIndex": 0}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]
