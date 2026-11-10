# Copyright (c) Microsoft. All rights reserved.

"""Local runtime regressions that do not require external services."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_monty import MontyRuntimeError

from agent_framework_monty import MontyExecuteCodeTool
from agent_framework_monty._monty_bridge import InlineCodeBridge


@pytest.mark.parametrize(
    "resource_limits",
    [
        {"max_duration_secs": 5.0, "max_memory": 64 * 1024 * 1024},
        {"max_feed_duration_secs": 5.0},
        {"max_turn_duration_secs": 5.0},
        {"max_duration_secs": 5.0, "max_turn_duration_secs": 1.0},
        {"max_duration_secs": None},
    ],
)
async def test_duration_limits_allow_execution_without_mutating_configuration(resource_limits: dict[str, Any]) -> None:
    original_limits = dict(resource_limits)
    execute_code = MontyExecuteCodeTool(resource_limits=resource_limits)

    contents = await execute_code._run_code(code="print('completed')")

    assert not any(content.type == "error" for content in contents)
    assert any(content.type == "text" and "completed" in (content.text or "") for content in contents)
    assert resource_limits == original_limits
    assert execute_code.resource_limits == original_limits
    assert execute_code.build_serializable_state()["resource_limits"] == original_limits


@pytest.mark.parametrize(
    ("duration_key", "limit_scope"),
    [
        ("max_duration_secs", "feed"),
        ("max_feed_duration_secs", "feed"),
        ("max_turn_duration_secs", "turn"),
    ],
)
async def test_duration_limits_stop_execution_with_a_timeout(duration_key: str, limit_scope: str) -> None:
    bridge = InlineCodeBridge({}, resource_limits={duration_key: 0.001})

    with pytest.raises(MontyRuntimeError, match=f"TimeoutError: {limit_scope} time limit exceeded"):
        await bridge.run("while True:\n    pass")


@pytest.mark.parametrize("legacy_duration", [None, 5.0])
async def test_legacy_and_feed_duration_limits_are_rejected_as_ambiguous(legacy_duration: float | None) -> None:
    bridge = InlineCodeBridge(
        {},
        resource_limits={"max_duration_secs": legacy_duration, "max_feed_duration_secs": 1.0},
    )

    with pytest.raises(ValueError, match="Specify only one of max_duration_secs and max_feed_duration_secs"):
        await bridge.run("print('must not run')")
