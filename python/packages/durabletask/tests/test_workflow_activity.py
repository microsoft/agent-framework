# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for execute_workflow_activity (shared non-agent executor activity body).

These tests exercise the host-agnostic activity execution shared by the Azure
Functions and standalone durabletask workflow hosts. In particular they protect
the state snapshot/diff semantics: the snapshot must be a *deep* copy so that
in-place mutations to nested objects (dicts, lists) are correctly detected as
updates (regression guard for the shallow-copy bug, #4500).
"""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock

from agent_framework_durabletask import execute_workflow_activity
from agent_framework_durabletask._workflows.orchestrator import SOURCE_ORCHESTRATOR


def _make_executor(executor_id: str, mutate: Any) -> Mock:
    """Build a mock non-agent executor whose execute() mutates shared state."""
    executor = Mock()
    executor.id = executor_id
    executor.execute = AsyncMock(side_effect=mutate)
    return executor


def _run(executor: Mock, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Invoke execute_workflow_activity and return the parsed result dict."""
    input_data = json.dumps({
        "message": "test",
        "shared_state_snapshot": snapshot,
        "source_executor_ids": [SOURCE_ORCHESTRATOR],
    })
    return json.loads(execute_workflow_activity(executor, input_data))


class TestExecuteWorkflowActivityStateDiff:
    """State snapshot/diff behavior of the shared workflow activity body."""

    def test_nested_dict_mutation_detected(self) -> None:
        """In-place mutation of a nested dict is reported as an update."""

        async def mutate(message: Any, source_executor_ids: Any, state: Any, runner_context: Any) -> None:
            config = state.get("Local.config")
            config["code"] = "SOMECODEXXX"
            config["enabled"] = True
            state.commit()

        executor = _make_executor("test-exec", mutate)
        result = _run(executor, {"Local.config": {"code": "", "enabled": False}, "simple_key": "simple_value"})

        updates = result["shared_state_updates"]
        assert "Local.config" in updates, "nested mutation not detected — snapshot may be a shallow copy"
        assert updates["Local.config"]["code"] == "SOMECODEXXX"
        assert updates["Local.config"]["enabled"] is True

    def test_new_key_in_nested_dict_detected(self) -> None:
        """Adding a key to a nested dict is reported as an update."""

        async def mutate(message: Any, source_executor_ids: Any, state: Any, runner_context: Any) -> None:
            state.get("Local.data")["code"] = "NEW_CODE"
            state.commit()

        executor = _make_executor("test-exec", mutate)
        result = _run(executor, {"Local.data": {"existing": "value"}})

        assert result["shared_state_updates"]["Local.data"]["code"] == "NEW_CODE"

    def test_nested_list_mutation_detected(self) -> None:
        """Appending to a nested list is reported as an update."""

        async def mutate(message: Any, source_executor_ids: Any, state: Any, runner_context: Any) -> None:
            state.get("Local.items").append(4)
            state.commit()

        executor = _make_executor("test-exec", mutate)
        result = _run(executor, {"Local.items": [1, 2, 3]})

        assert result["shared_state_updates"]["Local.items"] == [1, 2, 3, 4]

    def test_new_top_level_key_detected(self) -> None:
        """Setting a new top-level key is reported as an update."""

        async def mutate(message: Any, source_executor_ids: Any, state: Any, runner_context: Any) -> None:
            state.set("Local.code", "SOMECODEXXX")
            state.commit()

        executor = _make_executor("test-exec", mutate)
        result = _run(executor, {"existing": "value"})

        assert result["shared_state_updates"]["Local.code"] == "SOMECODEXXX"

    def test_unchanged_state_produces_empty_diff(self) -> None:
        """Unmodified state produces no updates."""

        async def mutate(message: Any, source_executor_ids: Any, state: Any, runner_context: Any) -> None:
            # No mutations performed.
            state.commit()

        executor = _make_executor("test-exec", mutate)
        result = _run(executor, {"Local.config": {"code": "existing", "enabled": True}, "simple_key": "v"})

        assert result["shared_state_updates"] == {}

    def test_deleted_key_reported(self) -> None:
        """A key removed during execution is reported as a delete."""

        async def mutate(message: Any, source_executor_ids: Any, state: Any, runner_context: Any) -> None:
            state.delete("to_remove")
            state.commit()

        executor = _make_executor("test-exec", mutate)
        result = _run(executor, {"to_remove": "value", "keep": "value"})

        assert "to_remove" in result["shared_state_deletes"]
        assert "keep" not in result["shared_state_deletes"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v", "--tb=short"])
