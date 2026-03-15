# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_framework_azure_ai._client import RawAzureAIClient


def _make_client(**overrides: Any) -> RawAzureAIClient:
    """Create a minimally-configured RawAzureAIClient for unit testing.

    Skips AIProjectClient creation by injecting mocks for the required
    instance attributes.
    """
    client = object.__new__(RawAzureAIClient)
    # Satisfy the attributes that _remove_agent_level_run_options reads.
    client.warn_runtime_tools_and_structure_changed = overrides.get(
        "warn_runtime_tools_and_structure_changed", False
    )
    client._created_agent_tool_names = overrides.get("_created_agent_tool_names", set())
    client._created_agent_structured_output_signature = overrides.get(
        "_created_agent_structured_output_signature", None
    )
    return client


class TestRemoveAgentLevelRunOptionsWarning:
    """Tests for _remove_agent_level_run_options runtime mismatch warning."""

    # ------------------------------------------------------------------
    # No warning when warn_runtime_tools_and_structure_changed is False
    # ------------------------------------------------------------------

    def test_no_warning_when_flag_is_false(self, caplog: pytest.LogCaptureFixture) -> None:
        """When warn_runtime_tools_and_structure_changed is False (e.g.
        use_latest_version path), no warning should be emitted even if
        runtime tools are present.  Regression test for #4681."""
        client = _make_client(warn_runtime_tools_and_structure_changed=False)
        run_options: dict[str, Any] = {
            "tools": [{"type": "function", "function": {"name": "my_tool"}}],
            "model": "gpt-4",
        }

        with caplog.at_level(logging.WARNING, logger="agent_framework.azure"):
            client._remove_agent_level_run_options(run_options)

        assert "does not support runtime tools" not in caplog.text

    def test_no_warning_when_flag_is_false_with_structured_output(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Same as above but with response_format (structured output)."""
        client = _make_client(warn_runtime_tools_and_structure_changed=False)
        run_options: dict[str, Any] = {"model": "gpt-4"}
        chat_options: dict[str, Any] = {"response_format": {"type": "json_object"}}

        with caplog.at_level(logging.WARNING, logger="agent_framework.azure"):
            client._remove_agent_level_run_options(run_options, chat_options)

        assert "does not support runtime tools" not in caplog.text

    # ------------------------------------------------------------------
    # Warning when tools actually changed after agent creation
    # ------------------------------------------------------------------

    def test_warning_when_tools_changed(self, caplog: pytest.LogCaptureFixture) -> None:
        """Warn when tools differ from what was used at agent creation time."""
        client = _make_client(
            warn_runtime_tools_and_structure_changed=True,
            _created_agent_tool_names={"old_tool"},
        )
        run_options: dict[str, Any] = {
            "tools": [{"type": "function", "function": {"name": "new_tool"}}],
            "model": "gpt-4",
        }

        with caplog.at_level(logging.WARNING, logger="agent_framework.azure"):
            client._remove_agent_level_run_options(run_options)

        assert "does not support runtime tools" in caplog.text

    def test_no_warning_when_tools_identical(self, caplog: pytest.LogCaptureFixture) -> None:
        """No warning when tools match what was used at agent creation time."""
        client = _make_client(
            warn_runtime_tools_and_structure_changed=True,
            _created_agent_tool_names={"my_tool"},
        )
        run_options: dict[str, Any] = {
            "tools": [{"type": "function", "function": {"name": "my_tool"}}],
            "model": "gpt-4",
        }

        with caplog.at_level(logging.WARNING, logger="agent_framework.azure"):
            client._remove_agent_level_run_options(run_options)

        assert "does not support runtime tools" not in caplog.text

    def test_warning_when_structured_output_changed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warn when structured_output differs from agent creation time."""
        client = _make_client(
            warn_runtime_tools_and_structure_changed=True,
            _created_agent_structured_output_signature='{"type": "json_object"}',
        )
        run_options: dict[str, Any] = {"model": "gpt-4"}
        chat_options: dict[str, Any] = {"response_format": {"type": "json_schema"}}

        with caplog.at_level(logging.WARNING, logger="agent_framework.azure"):
            client._remove_agent_level_run_options(run_options, chat_options)

        assert "does not support runtime tools" in caplog.text

    # ------------------------------------------------------------------
    # Agent-level keys are always stripped from run_options
    # ------------------------------------------------------------------

    def test_agent_level_keys_stripped(self) -> None:
        """Ensure agent-level keys are removed from run_options regardless of warning state."""
        client = _make_client(warn_runtime_tools_and_structure_changed=False)
        run_options: dict[str, Any] = {
            "tools": [{"type": "function", "function": {"name": "t"}}],
            "model": "gpt-4",
            "temperature": 0.7,
            "top_p": 0.9,
            "rai_config": {},
            "reasoning": {},
            "other_key": "keep",
        }

        client._remove_agent_level_run_options(run_options)

        # Agent-level keys should be removed
        for key in ("tools", "model", "temperature", "top_p", "rai_config", "reasoning"):
            assert key not in run_options, f"'{key}' should have been stripped"
        # Non-agent keys should remain
        assert run_options["other_key"] == "keep"
