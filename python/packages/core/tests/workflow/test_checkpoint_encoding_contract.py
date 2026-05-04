# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from pathlib import Path

from agent_framework._workflows._checkpoint_encoding import (
    decode_checkpoint_value,
    encode_checkpoint_value,
)


def _fixture_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "testdata" / "checkpoint_primitive_contract.json"
        if candidate.exists():
            return candidate
    raise AssertionError("checkpoint primitive contract fixture not found")


def test_checkpoint_primitive_contract_fixture_matches_python_encoding() -> None:
    fixture = json.loads(_fixture_path().read_text(encoding="utf-8"))

    encoded = encode_checkpoint_value(fixture)

    assert encoded == fixture
    assert decode_checkpoint_value(encoded) == fixture


def test_checkpoint_primitive_contract_fixture_preserves_json_native_types() -> None:
    fixture = json.loads(_fixture_path().read_text(encoding="utf-8"))

    assert isinstance(fixture["string"], str)
    assert isinstance(fixture["integer"], int)
    assert isinstance(fixture["float"], float)
    assert isinstance(fixture["boolean"], bool)
    assert fixture["nullValue"] is None
    assert fixture["list"] == [1, "two", False, None]
    assert fixture["object"] == {"nested": {"value": "ok"}, "count": 2}
