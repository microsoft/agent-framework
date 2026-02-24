# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

import pytest

from agent_framework import WorkflowCheckpointException
from agent_framework._workflows._checkpoint_encoding import (
    _TYPE_MARKER,  # type: ignore
    decode_checkpoint_value,
    encode_checkpoint_value,
)


@dataclass
class SampleRequest:
    """Sample request message for testing checkpoint encoding/decoding."""

    request_id: str
    prompt: str


@dataclass
class SampleResponse:
    """Sample response message for testing checkpoint encoding/decoding."""

    data: str
    original_request: SampleRequest
    request_id: str


# --- Tests for round-trip encode/decode ---


def test_roundtrip_simple_dataclass() -> None:
    """Test encoding and decoding of a simple dataclass."""
    original = SampleRequest(request_id="test-123", prompt="test prompt")

    encoded = encode_checkpoint_value(original)
    decoded = cast(SampleRequest, decode_checkpoint_value(encoded))

    assert isinstance(decoded, SampleRequest)
    assert decoded.request_id == "test-123"
    assert decoded.prompt == "test prompt"


def test_roundtrip_dataclass_with_nested_request() -> None:
    """Test that dataclass with nested dataclass fields can be encoded and decoded correctly."""
    original = SampleResponse(
        data="approve",
        original_request=SampleRequest(request_id="abc", prompt="prompt"),
        request_id="abc",
    )

    encoded = encode_checkpoint_value(original)
    decoded = cast(SampleResponse, decode_checkpoint_value(encoded))

    assert isinstance(decoded, SampleResponse)
    assert decoded.data == "approve"
    assert decoded.request_id == "abc"
    assert isinstance(decoded.original_request, SampleRequest)
    assert decoded.original_request.prompt == "prompt"
    assert decoded.original_request.request_id == "abc"


def test_roundtrip_nested_structures() -> None:
    """Test encoding and decoding of complex nested structures."""
    nested_data = {
        "requests": [
            SampleRequest(request_id="req-1", prompt="first prompt"),
            SampleRequest(request_id="req-2", prompt="second prompt"),
        ],
        "responses": {
            "req-1": SampleResponse(
                data="first response",
                original_request=SampleRequest(request_id="req-1", prompt="first prompt"),
                request_id="req-1",
            ),
        },
    }

    encoded = encode_checkpoint_value(nested_data)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded, dict)
    assert "requests" in decoded
    assert "responses" in decoded

    requests = cast(list[Any], decoded["requests"])
    assert isinstance(requests, list)
    assert len(requests) == 2
    assert all(isinstance(req, SampleRequest) for req in requests)
    first_request = cast(SampleRequest, requests[0])
    second_request = cast(SampleRequest, requests[1])
    assert first_request.request_id == "req-1"
    assert second_request.request_id == "req-2"

    responses = cast(dict[str, Any], decoded["responses"])
    assert isinstance(responses, dict)
    assert "req-1" in responses
    response = cast(SampleResponse, responses["req-1"])
    assert isinstance(response, SampleResponse)
    assert response.data == "first response"
    assert isinstance(response.original_request, SampleRequest)
    assert response.original_request.request_id == "req-1"


def test_roundtrip_datetime() -> None:
    """Test round-trip encoding/decoding of datetime objects."""
    original = datetime(2024, 5, 4, 12, 30, 45, tzinfo=timezone.utc)

    encoded = encode_checkpoint_value(original)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded, datetime)
    assert decoded == original


def test_roundtrip_primitives() -> None:
    """Test that primitive types round-trip unchanged."""
    for value in ["hello", 42, 3.14, True, False, None]:
        assert decode_checkpoint_value(encode_checkpoint_value(value)) == value


def test_roundtrip_dict_with_mixed_values() -> None:
    """Test round-trip of a dict containing both primitives and complex types."""
    original = {
        "name": "test",
        "request": SampleRequest(request_id="r1", prompt="p1"),
        "count": 5,
    }

    encoded = encode_checkpoint_value(original)
    decoded = decode_checkpoint_value(encoded)

    assert decoded["name"] == "test"
    assert decoded["count"] == 5
    assert isinstance(decoded["request"], SampleRequest)
    assert decoded["request"].request_id == "r1"


# --- Tests for decode primitives ---


def test_decode_string() -> None:
    """Test decoding a string passes through unchanged."""
    assert decode_checkpoint_value("hello") == "hello"


def test_decode_integer() -> None:
    """Test decoding an integer passes through unchanged."""
    assert decode_checkpoint_value(42) == 42


def test_decode_none() -> None:
    """Test decoding None passes through unchanged."""
    assert decode_checkpoint_value(None) is None


# --- Tests for decode collections ---


def test_decode_plain_dict() -> None:
    """Test decoding a plain dictionary with primitive values."""
    data = {"a": 1, "b": "two"}
    assert decode_checkpoint_value(data) == {"a": 1, "b": "two"}


def test_decode_plain_list() -> None:
    """Test decoding a plain list with primitive values."""
    data = [1, "two", 3.0]
    assert decode_checkpoint_value(data) == [1, "two", 3.0]


# --- Tests for type verification ---


def test_decode_raises_on_type_mismatch() -> None:
    """Test that decoding raises WorkflowCheckpointException when type doesn't match."""
    # Encode a SampleRequest but tamper with the type marker
    encoded = encode_checkpoint_value(SampleRequest(request_id="r1", prompt="p1"))
    assert isinstance(encoded, dict)
    encoded[_TYPE_MARKER] = "nonexistent.module:FakeClass"

    with pytest.raises(WorkflowCheckpointException, match="Type mismatch"):
        decode_checkpoint_value(encoded)


class NotADataclass:  # noqa: B903
    """A regular class that is not a dataclass."""

    def __init__(self, value: str) -> None:
        self.value = value


def test_roundtrip_regular_class() -> None:
    """Test that regular (non-dataclass) objects can be round-tripped via pickle."""
    original = NotADataclass(value="test_value")

    encoded = encode_checkpoint_value(original)
    decoded = cast(NotADataclass, decode_checkpoint_value(encoded))

    assert isinstance(decoded, NotADataclass)
    assert decoded.value == "test_value"


def test_roundtrip_tuple() -> None:
    """Test that tuples preserve their type through encode/decode roundtrip."""
    original = (1, "two", 3.0)

    encoded = encode_checkpoint_value(original)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded, tuple)
    assert decoded == original


def test_roundtrip_set() -> None:
    """Test that sets preserve their type through encode/decode roundtrip."""
    original = {1, 2, 3}

    encoded = encode_checkpoint_value(original)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded, set)
    assert decoded == original


def test_roundtrip_nested_tuple_in_dict() -> None:
    """Test that tuples nested inside dicts preserve their type."""
    original = {"items": (1, 2, 3), "name": "test"}

    encoded = encode_checkpoint_value(original)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded["items"], tuple)
    assert decoded["items"] == (1, 2, 3)
    assert decoded["name"] == "test"


def test_roundtrip_set_in_list() -> None:
    """Test that sets nested inside lists preserve their type."""
    original = [{"tags": {1, 2, 3}}]

    encoded = encode_checkpoint_value(original)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded[0]["tags"], set)
    assert decoded[0]["tags"] == {1, 2, 3}
