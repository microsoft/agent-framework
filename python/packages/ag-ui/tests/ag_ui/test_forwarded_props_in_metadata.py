# Copyright (c) Microsoft. All rights reserved.

"""Tests for forwarded_props inclusion in AG-UI session metadata."""

import json
from typing import Any

from agent_framework_ag_ui._agent_run import AG_UI_INTERNAL_METADATA_KEYS, _build_safe_metadata


class TestForwardedPropsInSessionMetadata:
    """Verify that forwarded_props is surfaced in session metadata and filtered from LLM metadata."""

    def test_forwarded_props_in_internal_metadata_keys(self):
        """forwarded_props is listed in AG_UI_INTERNAL_METADATA_KEYS to prevent LLM leakage."""
        assert "forwarded_props" in AG_UI_INTERNAL_METADATA_KEYS

    def test_forwarded_props_filtered_from_client_metadata(self):
        """forwarded_props is filtered out when building LLM-bound client metadata."""
        session_metadata: dict[str, Any] = {
            "ag_ui_thread_id": "t1",
            "ag_ui_run_id": "r1",
            "forwarded_props": '{"custom_flag": true}',
        }

        client_metadata = {k: v for k, v in session_metadata.items() if k not in AG_UI_INTERNAL_METADATA_KEYS}

        assert "forwarded_props" not in client_metadata
        assert "ag_ui_thread_id" not in client_metadata


class TestBuildSafeMetadata:
    """Verify _build_safe_metadata handles various value types correctly."""

    def test_string_value_unchanged(self):
        result = _build_safe_metadata({"key": "hello"})
        assert result == {"key": "hello"}

    def test_dict_value_serialized_to_json(self):
        result = _build_safe_metadata({"fp": {"flag": True, "source": "frontend"}})
        assert "fp" in result
        assert isinstance(result["fp"], str)
        # Must be valid, decodable JSON
        decoded = json.loads(result["fp"])
        assert decoded == {"flag": True, "source": "frontend"}

    def test_empty_dict_serialized_to_json(self):
        result = _build_safe_metadata({"fp": {}})
        assert result["fp"] == "{}"
        assert json.loads(result["fp"]) == {}

    def test_value_within_limit_kept(self):
        value = "x" * 512
        result = _build_safe_metadata({"key": value})
        assert result["key"] == value

    def test_value_exceeding_limit_dropped(self):
        """Values exceeding 512 chars are dropped entirely (not truncated)."""
        value = "x" * 513
        result = _build_safe_metadata({"key": value})
        assert "key" not in result

    def test_json_value_exceeding_limit_dropped(self):
        """JSON-serialized dict exceeding 512 chars is dropped, not truncated into invalid JSON."""
        big_dict = {f"key_{i}": "v" * 100 for i in range(50)}
        result = _build_safe_metadata({"forwarded_props": big_dict})
        assert "forwarded_props" not in result

    def test_other_keys_preserved_when_one_dropped(self):
        """Dropping one oversized key does not affect other keys."""
        result = _build_safe_metadata(
            {
                "small": "ok",
                "big": "x" * 600,
            }
        )
        assert result == {"small": "ok"}

    def test_none_input_returns_empty(self):
        assert _build_safe_metadata(None) == {}

    def test_empty_input_returns_empty(self):
        assert _build_safe_metadata({}) == {}
