# Copyright (c) Microsoft. All rights reserved.

"""Tests for restricted checkpoint deserialization.

These tests verify that persisted checkpoint loading uses a restricted
unpickler by default:
- Arbitrary callables are blocked during deserialization
- __reduce__ payloads cannot execute code during deserialization
- FileCheckpointStorage accepts allowed_checkpoint_types for extension
- User-defined types are blocked unless explicitly allowed
- Built-in safe types and framework types are always allowed
"""

import base64
import os
import pickle
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from agent_framework import WorkflowCheckpointException
from agent_framework._workflows._checkpoint import FileCheckpointStorage
from agent_framework._workflows._checkpoint_encoding import (
    _PICKLE_MARKER,
    _TYPE_MARKER,
    _base64_to_unpickle,  # pyright: ignore[reportPrivateUsage]
    decode_checkpoint_value,
    encode_checkpoint_value,
)


class MaliciousPayload:
    """A class whose __reduce__ executes code during unpickling."""

    def __reduce__(self):
        return (os.getpid, ())


class FrameworkHelperPayload:
    """A payload that references a framework helper during unpickling."""

    def __init__(self, nested_payload: str) -> None:
        self.nested_payload = nested_payload

    def __reduce__(self) -> tuple[Any, tuple[str]]:
        return (_base64_to_unpickle, (self.nested_payload,))


class _NestedTypeContainer:
    class NestedType:
        pass


def test_restricted_decode_blocks_arbitrary_callable():
    """Restricted decoding blocks arbitrary module-level callables."""
    pickled = pickle.dumps(os.getpid, protocol=pickle.HIGHEST_PROTOCOL)
    encoded_b64 = base64.b64encode(pickled).decode("ascii")

    checkpoint_value = {
        _PICKLE_MARKER: encoded_b64,
        _TYPE_MARKER: "builtins:builtin_function_or_method",
    }

    with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
        decode_checkpoint_value(checkpoint_value, allowed_types=frozenset())


def test_restricted_decode_blocks_reduce_payload():
    """__reduce__-based payloads are blocked before code can execute."""
    payload = MaliciousPayload()
    pickled = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    encoded_b64 = base64.b64encode(pickled).decode("ascii")

    checkpoint_value = {
        _PICKLE_MARKER: encoded_b64,
        _TYPE_MARKER: f"{MaliciousPayload.__module__}:{MaliciousPayload.__qualname__}",
    }

    with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
        decode_checkpoint_value(checkpoint_value, allowed_types=frozenset())


def test_restricted_decode_prevents_code_execution():
    """Restricted deserialization prevents __reduce__ code from running."""
    with tempfile.TemporaryDirectory() as tmpdir:
        marker_file = os.path.join(tmpdir, "checkpoint_test_marker")

        payload_bytes = pickle.dumps(
            type(
                "Exploit",
                (),
                {
                    "__reduce__": lambda self: (
                        eval,
                        (f"open({marker_file!r}, 'w').write('pwned')",),
                    )
                },
            )(),
            protocol=pickle.HIGHEST_PROTOCOL,
        )
        encoded_b64 = base64.b64encode(payload_bytes).decode("ascii")

        checkpoint_value = {
            _PICKLE_MARKER: encoded_b64,
            _TYPE_MARKER: "builtins:int",
        }
        with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
            decode_checkpoint_value(checkpoint_value, allowed_types=frozenset())

        assert not os.path.exists(marker_file), (
            "Restricted unpickler should have prevented code execution, but the marker file was created."
        )


def test_restricted_decode_blocks_framework_deserialization_helpers() -> None:
    """Restricted deserialization blocks framework helper callables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        marker_file = os.path.join(tmpdir, "checkpoint_helper_marker")
        nested_payload = pickle.dumps(
            type(
                "NestedExploit",
                (),
                {
                    "__reduce__": lambda self: (
                        eval,
                        (f"open({marker_file!r}, 'w').write('pwned')",),
                    )
                },
            )(),
            protocol=pickle.HIGHEST_PROTOCOL,
        )
        payload = FrameworkHelperPayload(base64.b64encode(nested_payload).decode("ascii"))
        encoded_b64 = base64.b64encode(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)).decode("ascii")

        checkpoint_value = {
            _PICKLE_MARKER: encoded_b64,
            _TYPE_MARKER: "builtins:int",
        }
        with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
            decode_checkpoint_value(checkpoint_value, allowed_types=frozenset())

        assert not os.path.exists(marker_file)


def test_restricted_decode_blocks_dotted_framework_global() -> None:
    """Restricted deserialization blocks dotted globals in allowed framework modules."""
    module = b"agent_framework._workflows._checkpoint_encoding"
    name = b"pickle.loads"
    dotted_global_payload = (
        b"\x80\x04\x8c" + bytes([len(module)]) + module + b"\x8c" + bytes([len(name)]) + name + b"\x93C\x05NESTD\x85R."
    )
    encoded_b64 = base64.b64encode(dotted_global_payload).decode("ascii")

    checkpoint_value = {
        _PICKLE_MARKER: encoded_b64,
        _TYPE_MARKER: "builtins:int",
    }

    with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
        decode_checkpoint_value(checkpoint_value, allowed_types=frozenset())


def test_file_checkpoint_storage_accepts_allowed_types():
    """FileCheckpointStorage.__init__ accepts allowed_checkpoint_types."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileCheckpointStorage(
            tmpdir,
            allowed_checkpoint_types=["some.module:SomeType"],
        )
        assert storage is not None


@dataclass
class _AllowedTestState:
    """Test dataclass that will be explicitly allowed."""

    name: str
    value: int


def test_restricted_decode_blocks_unlisted_user_type():
    """User-defined types are blocked when not in allowed_checkpoint_types."""
    original = _AllowedTestState(name="test", value=42)
    encoded = encode_checkpoint_value(original)

    with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
        decode_checkpoint_value(encoded, allowed_types=frozenset())


def test_restricted_decode_allows_listed_user_type():
    """User-defined types are allowed when listed in allowed_types."""
    original = _AllowedTestState(name="test", value=42)
    encoded = encode_checkpoint_value(original)

    type_key = f"{_AllowedTestState.__module__}:{_AllowedTestState.__qualname__}"
    decoded = decode_checkpoint_value(encoded, allowed_types=frozenset({type_key}))

    assert isinstance(decoded, _AllowedTestState)
    assert decoded.name == "test"
    assert decoded.value == 42


def test_restricted_decode_allows_builtin_safe_types():
    """Built-in safe types (datetime, set, etc.) are always allowed."""
    test_values = [
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        {1, 2, 3},
        frozenset({4, 5, 6}),
        (1, "two", 3.0),
        complex(1, 2),
    ]
    for original in test_values:
        encoded = encode_checkpoint_value(original)
        decoded = decode_checkpoint_value(encoded, allowed_types=frozenset())
        assert decoded == original


def test_unrestricted_decode_allows_arbitrary_types():
    """Without allowed_types, decode_checkpoint_value remains unrestricted."""
    original = _AllowedTestState(name="test", value=42)
    encoded = encode_checkpoint_value(original)

    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded, _AllowedTestState)
    assert decoded.name == "test"


async def test_file_storage_blocks_unlisted_user_type():
    """FileCheckpointStorage blocks user types not in allowed_checkpoint_types."""
    from agent_framework import WorkflowCheckpoint

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save with a storage that allows the type
        type_key = f"{_AllowedTestState.__module__}:{_AllowedTestState.__qualname__}"
        save_storage = FileCheckpointStorage(tmpdir, allowed_checkpoint_types=[type_key])

        checkpoint = WorkflowCheckpoint(
            workflow_name="test",
            graph_signature_hash="hash",
            state={"data": _AllowedTestState(name="test", value=1)},
        )
        await save_storage.save(checkpoint)

        # Load with a storage that does NOT allow the type
        load_storage = FileCheckpointStorage(tmpdir)
        with pytest.raises(WorkflowCheckpointException, match="deserialization blocked"):
            await load_storage.load(checkpoint.checkpoint_id)


async def test_file_storage_allows_listed_user_type():
    """FileCheckpointStorage allows user types listed in allowed_checkpoint_types."""
    from agent_framework import WorkflowCheckpoint

    with tempfile.TemporaryDirectory() as tmpdir:
        type_key = f"{_AllowedTestState.__module__}:{_AllowedTestState.__qualname__}"
        storage = FileCheckpointStorage(tmpdir, allowed_checkpoint_types=[type_key])

        checkpoint = WorkflowCheckpoint(
            workflow_name="test",
            graph_signature_hash="hash",
            state={"data": _AllowedTestState(name="allowed", value=99)},
        )
        await storage.save(checkpoint)
        loaded = await storage.load(checkpoint.checkpoint_id)

        assert isinstance(loaded.state["data"], _AllowedTestState)
        assert loaded.state["data"].name == "allowed"
        assert loaded.state["data"].value == 99


async def test_file_storage_round_trips_marker_shaped_dict_state() -> None:
    """FileCheckpointStorage preserves marker-shaped dictionaries as user data."""
    from agent_framework import WorkflowCheckpoint

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileCheckpointStorage(tmpdir)
        state_data = {
            _PICKLE_MARKER: "some_value",
            _TYPE_MARKER: "some_type",
        }
        checkpoint = WorkflowCheckpoint(
            workflow_name="test",
            graph_signature_hash="hash",
            state={"data": state_data},
        )
        checkpoint_id = await storage.save(checkpoint)

        loaded = await storage.load(checkpoint_id)

        assert loaded.state["data"] == state_data


def test_restricted_unpickler_raises_pickle_error():
    """_RestrictedUnpickler.find_class raises pickle.UnpicklingError, not a framework exception."""
    from agent_framework._workflows._checkpoint_encoding import _RestrictedUnpickler

    pickled = pickle.dumps(os.getpid, protocol=pickle.HIGHEST_PROTOCOL)

    unpickler = _RestrictedUnpickler(pickled, frozenset())
    with pytest.raises(pickle.UnpicklingError, match="deserialization blocked"):
        unpickler.load()


def test_restricted_decode_rejects_non_type_global_in_allowed_types():
    """Explicit allowed_types entries must resolve to types."""
    from agent_framework._workflows._checkpoint_encoding import _RestrictedUnpickler

    unpickler = _RestrictedUnpickler(pickle.dumps(object), frozenset({"os:getpid"}))
    with pytest.raises(pickle.UnpicklingError, match="non-type global"):
        unpickler.find_class("os", "getpid")


def test_restricted_decode_rejects_non_type_global_under_prefix():
    """Allowed package prefixes must not expose arbitrary module globals."""
    from agent_framework._workflows._checkpoint_encoding import _RestrictedUnpickler

    unpickler = _RestrictedUnpickler(pickle.dumps(object), frozenset())
    with pytest.raises(pickle.UnpicklingError, match="non-type global"):
        unpickler.find_class(
            "agent_framework._workflows._checkpoint_encoding",
            "encode_checkpoint_value",
        )


def test_restricted_getattr_allows_nested_type_resolution():
    """The restricted getattr replacement preserves nested-type reconstruction."""
    from agent_framework._workflows._checkpoint_encoding import _RestrictedUnpickler

    unpickler = _RestrictedUnpickler(pickle.dumps(object), frozenset())
    restricted_getattr = unpickler.find_class("builtins", "getattr")

    assert restricted_getattr(_NestedTypeContainer, "NestedType") is _NestedTypeContainer.NestedType


def test_restricted_decode_blocks_getattr_globals_pickle_loads_chain():
    """Restricted decoding blocks attribute traversal to an inner unrestricted pickle load."""
    inner_pickle = b"cbuiltins\neval\n(V40 + 2\ntR."
    escaped_inner_pickle = inner_pickle.decode("ascii").replace("\\", "\\u005c").replace("\n", "\\u000a")
    # The outer pickle memoizes getattr and walks __init__.__globals__["pickle"].loads.
    payload = (
        b"cbuiltins\ngetattr\np0\n0"
        b"g0\n(cagent_framework._workflows._checkpoint_encoding\n_RestrictedUnpickler\nV__init__\ntRp1\n0"
        b"g0\n(g1\nV__globals__\ntRp2\n0"
        b"g0\n(cbuiltins\ndict\nV__getitem__\ntRp3\n0"
        b"g3\n(g2\nVpickle\ntRp4\n0"
        b"g0\n(g4\nVloads\ntRp5\n0"
        b"g5\n(cbuiltins\nbytearray\n(V" + escaped_inner_pickle.encode("ascii") + b"\nVascii\ntRtR."
    )
    checkpoint_value = {
        _PICKLE_MARKER: base64.b64encode(payload).decode("ascii"),
        _TYPE_MARKER: "builtins:int",
    }

    with pytest.raises(WorkflowCheckpointException, match="non-type attribute"):
        decode_checkpoint_value(checkpoint_value, allowed_types=frozenset())


def test_restricted_decode_allows_openai_types():
    """OpenAI SDK types are always allowed during restricted deserialization."""
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage
    from openai.types.completion_usage import CompletionUsage

    completion = ChatCompletion(
        id="chatcmpl-test",
        choices=[
            Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(role="assistant", content="hello"),
            )
        ],
        created=1700000000,
        model="gpt-4",
        object="chat.completion",
        usage=CompletionUsage(completion_tokens=1, prompt_tokens=1, total_tokens=2),
    )
    encoded = encode_checkpoint_value(completion)
    decoded = decode_checkpoint_value(encoded, allowed_types=frozenset())

    assert isinstance(decoded, ChatCompletion)
    assert decoded.id == "chatcmpl-test"
    assert decoded.choices[0].message.content == "hello"


def test_restricted_decode_allows_openai_response_types():
    """OpenAI Responses API types are always allowed during restricted deserialization."""
    from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails, ResponseUsage

    usage = ResponseUsage(
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        input_tokens_details=InputTokensDetails(cached_tokens=0, cache_write_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    encoded = encode_checkpoint_value(usage)
    decoded = decode_checkpoint_value(encoded, allowed_types=frozenset())

    assert isinstance(decoded, ResponseUsage)
    assert decoded.input_tokens == 10
    assert decoded.output_tokens == 20
