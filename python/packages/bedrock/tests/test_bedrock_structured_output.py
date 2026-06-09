# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import patch

import pytest
from agent_framework import Content, Message
from botocore.exceptions import ClientError
from pydantic import BaseModel

from agent_framework_bedrock import BedrockChatClient

# region Test models


class WeatherReport(BaseModel):
    city: str
    temperature: float
    summary: str


class NestedAddress(BaseModel):
    street: str
    city: str
    zip_code: str


class Person(BaseModel):
    name: str
    age: int
    address: NestedAddress


# endregion


# region Helpers


class _StubBedrockRuntime:
    """Stub that records calls and returns a canned response."""

    def __init__(self, response_text: str = "Bedrock says hi") -> None:
        self.calls: list[dict[str, Any]] = []
        self._response_text = response_text

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "modelId": kwargs["modelId"],
            "responseId": "resp-structured",
            "usage": {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30},
            "output": {
                "completionReason": "end_turn",
                "message": {
                    "id": "msg-structured",
                    "role": "assistant",
                    "content": [{"text": self._response_text}],
                },
            },
        }


def _make_client(response_text: str = "Bedrock says hi") -> tuple[BedrockChatClient, _StubBedrockRuntime]:
    stub = _StubBedrockRuntime(response_text)
    client = BedrockChatClient(
        model="us.anthropic.claude-haiku-4-5-v1:0",
        region="us-east-1",
        client=stub,
    )
    return client, stub


def _user_messages() -> list[Message]:
    return [Message(role="user", contents=[Content.from_text(text="Give me a weather report")])]


# endregion


# region Tests


def test_prepare_output_config_correct_wire_shape() -> None:
    """_prepare_output_config(WeatherReport) must produce the correct
    textFormat → structure → jsonSchema shape with type: 'json_schema'."""
    client, _ = _make_client()

    output_config = client._prepare_output_config(WeatherReport)

    assert output_config is not None
    text_format = output_config["textFormat"]
    assert text_format["type"] == "json_schema"
    assert "structure" in text_format
    json_schema = text_format["structure"]["jsonSchema"]
    assert json_schema["name"] == "WeatherReport"
    assert "schema" in json_schema


def test_prepare_output_config_schema_is_json_string() -> None:
    """The schema value inside jsonSchema must be a JSON string, not a dict."""
    client, _ = _make_client()

    output_config = client._prepare_output_config(WeatherReport)

    assert output_config is not None
    schema_value = output_config["textFormat"]["structure"]["jsonSchema"]["schema"]
    assert isinstance(schema_value, str), f"Expected str, got {type(schema_value)}"
    # Verify it's valid JSON
    parsed = json.loads(schema_value)
    assert isinstance(parsed, dict)
    assert parsed["type"] == "object"


def test_additional_properties_false_set_recursively() -> None:
    """additionalProperties: false must be set on all nested object types."""
    client, _ = _make_client()

    output_config = client._prepare_output_config(Person)

    assert output_config is not None
    schema_str = output_config["textFormat"]["structure"]["jsonSchema"]["schema"]
    schema = json.loads(schema_str)

    # Top-level object
    assert schema.get("additionalProperties") is False

    # Check $defs for NestedAddress
    defs = schema.get("$defs", {})
    assert "NestedAddress" in defs, "Expected NestedAddress to be present in $defs"
    assert defs["NestedAddress"].get("additionalProperties") is False, (
        "Expected additionalProperties=False on nested NestedAddress schema"
    )


def test_no_output_config_when_response_format_none() -> None:
    """When response_format is None, no outputConfig key should appear in the request."""
    client, stub = _make_client()
    messages = _user_messages()

    request = client._prepare_options(messages, {"max_tokens": 100})

    assert "outputConfig" not in request, (
        f"outputConfig should not be present when response_format is None, got: {request.get('outputConfig')}"
    )


async def test_chat_response_value_populated() -> None:
    """After a mocked response with response_format, .value should be a populated Pydantic model."""
    json_response = json.dumps({"city": "Seattle", "temperature": 72.5, "summary": "Sunny and warm"})
    client, stub = _make_client(response_text=json_response)
    messages = _user_messages()

    response = await client.get_response(
        messages=messages,
        options={"max_tokens": 100, "response_format": WeatherReport},
    )

    assert response.text == json_response
    assert response.value is not None
    assert isinstance(response.value, WeatherReport)
    assert response.value.city == "Seattle"
    assert response.value.temperature == 72.5
    assert response.value.summary == "Sunny and warm"

    # Verify outputConfig was sent to the API
    assert len(stub.calls) == 1
    api_request = stub.calls[0]
    assert "outputConfig" in api_request
    assert api_request["outputConfig"]["textFormat"]["type"] == "json_schema"


def test_dict_schema_response_format() -> None:
    """_prepare_output_config should work when response_format is a dict, not just a Pydantic class."""
    client, _ = _make_client()

    dict_schema = {
        "json_schema": {
            "name": "weather_output",
            "schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "temp": {"type": "number"},
                },
            },
        }
    }

    output_config = client._prepare_output_config(dict_schema)

    assert output_config is not None
    json_schema = output_config["textFormat"]["structure"]["jsonSchema"]
    assert json_schema["name"] == "weather_output"
    schema_parsed = json.loads(json_schema["schema"])
    assert schema_parsed["type"] == "object"
    assert "city" in schema_parsed["properties"]


def test_prepare_output_config_none_returns_none() -> None:
    """_prepare_output_config(None) must return None."""
    client, _ = _make_client()

    result = client._prepare_output_config(None)

    assert result is None


async def test_chat_response_value_populated_streaming() -> None:
    """In streaming mode, .value should also be populated on the final response."""
    json_response = json.dumps({"city": "Portland", "temperature": 68.0, "summary": "Cloudy"})
    client, stub = _make_client(response_text=json_response)
    messages = _user_messages()

    stream = client.get_response(
        messages=messages,
        stream=True,
        options={"max_tokens": 100, "response_format": WeatherReport},
    )

    # Consume stream and get final response
    async for _ in stream:
        pass
    response = await stream.get_final_response()

    assert response.value is not None
    assert isinstance(response.value, WeatherReport)
    assert response.value.city == "Portland"

    # Verify outputConfig was sent
    assert len(stub.calls) == 1
    assert "outputConfig" in stub.calls[0]


async def test_unsupported_model_validation_exception() -> None:
    """When a model doesn't support outputConfig, a clear error should be raised."""

    class _FailingStubBedrockRuntime:
        def converse(self, **kwargs: Any) -> dict[str, Any]:
            # Simulate botocore ClientError for ValidationException
            error_response = {"Error": {"Code": "ValidationException", "Message": "Invalid field outputConfig"}}
            raise ClientError(error_response, "Converse")

    client = BedrockChatClient(
        model="us.anthropic.claude-v2",
        region="us-east-1",
        client=_FailingStubBedrockRuntime(),
    )

    with pytest.raises(ValueError) as exc:
        await client.get_response(
            messages=_user_messages(),
            options={"response_format": WeatherReport},
        )

    assert "does not support structured output via outputConfig.textFormat" in str(exc.value)
    assert "Check the model's Bedrock Converse outputConfig/textFormat support." in str(exc.value)


def test_invalid_response_format_type_raises() -> None:
    """Non-dict, non-BaseModel response_format should raise TypeError."""
    client, _ = _make_client()
    with pytest.raises(TypeError, match="Pydantic BaseModel subclass"):
        client._prepare_output_config("not_a_valid_format")


def test_mapping_response_format_accepted() -> None:
    """A non-dict Mapping response_format must be accepted and produce
    correct outputConfig, not raise TypeError."""
    from collections.abc import MutableMapping

    class _WrappedMapping(MutableMapping):
        def __init__(self, data):
            self._data = dict(data)

        def __getitem__(self, key):
            return self._data[key]

        def __setitem__(self, key, value):
            self._data[key] = value

        def __delitem__(self, key):
            del self._data[key]

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    client, _ = _make_client()
    mapping_format = _WrappedMapping({
        "json_schema": {
            "name": "test_output",
            "schema": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
        }
    })

    output_config = client._prepare_output_config(mapping_format)

    assert output_config is not None
    json_schema = output_config["textFormat"]["structure"]["jsonSchema"]
    assert json_schema["name"] == "test_output"
    schema = json.loads(json_schema["schema"])
    assert schema.get("additionalProperties") is False


def test_shape_b_dict_schema_wire_format() -> None:
    """Dict response_format in Shape B (inner shape directly) should
    produce correct outputConfig."""
    client, _ = _make_client()

    response_format = {
        "name": "weather_output",
        "schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "temperature": {"type": "number"},
            },
        },
    }

    output_config = client._prepare_output_config(response_format)

    assert output_config is not None
    text_format = output_config["textFormat"]
    assert text_format["type"] == "json_schema"
    json_schema = text_format["structure"]["jsonSchema"]
    assert json_schema["name"] == "weather_output"
    schema = json.loads(json_schema["schema"])
    assert schema.get("additionalProperties") is False


def test_dict_schema_not_mutated() -> None:
    """Caller's dict schema must not be mutated by _prepare_output_config."""
    client, _ = _make_client()
    original_schema = {
        "json_schema": {
            "name": "test",
            "schema": {
                "type": "object",
                "properties": {"a": {"type": "string"}},
            },
        }
    }
    snapshot = copy.deepcopy(original_schema)
    client._prepare_output_config(original_schema)
    assert original_schema == snapshot, "Original dict schema was mutated"


async def test_non_outputconfig_validation_exception_propagates() -> None:
    """ValidationException unrelated to outputConfig must propagate
    as raw ClientError, not be caught and reclassified."""
    client, _ = _make_client()
    error_response = {
        "Error": {
            "Code": "ValidationException",
            "Message": "Invalid message format",
        }
    }
    with (
        patch.object(
            client,
            "_bedrock_client",
            **{"converse.side_effect": ClientError(error_response, "Converse")},
        ),
        pytest.raises(ClientError),
    ):
        await client.get_response(
            messages=_user_messages(),
            options={"max_tokens": 100},
        )


# endregion
