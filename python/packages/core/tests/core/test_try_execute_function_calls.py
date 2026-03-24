# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for _try_execute_function_calls mixed-batch handling.

Covers:
- Full-batch validation (no early break on first approval/declaration-only call)
- Termination signal propagation from non-approval calls in mixed batches
- Preservation of original sequence indices for non-approval calls
"""

from typing import Any
from unittest.mock import patch

import pytest

from agent_framework import Content, FunctionTool, tool
from agent_framework._middleware import MiddlewareTermination
from agent_framework._tools import _try_execute_function_calls


def _make_function_call(call_id: str, name: str) -> Content:
    return Content.from_function_call(call_id=call_id, name=name, arguments="{}")


@tool(approval_mode="always_require")
def approval_tool(query: str = "") -> str:
    """Tool requiring approval."""
    return "approved"


@tool()
def normal_tool(query: str = "") -> str:
    """Normal tool."""
    return "normal result"


declaration_only_tool = FunctionTool(
    name="decl_tool",
    func=None,
    description="Declaration-only tool.",
    input_model={"type": "object", "properties": {}},
)


async def test_unknown_tool_detected_after_approval_tool() -> None:
    """terminate_on_unknown_calls should raise even when an approval tool appears first in batch."""
    function_calls = [
        _make_function_call("1", "approval_tool"),
        _make_function_call("2", "nonexistent_tool"),
    ]
    with pytest.raises(KeyError, match="nonexistent_tool"):
        await _try_execute_function_calls(
            custom_args={},
            attempt_idx=0,
            function_calls=function_calls,
            tools=[approval_tool],
            config={"terminate_on_unknown_calls": True},
        )


async def test_declaration_only_detected_after_approval_tool() -> None:
    """declaration_only flag should be set even when an approval tool appears first."""
    function_calls = [
        _make_function_call("1", "approval_tool"),
        _make_function_call("2", "decl_tool"),
    ]
    results, should_terminate = await _try_execute_function_calls(
        custom_args={},
        attempt_idx=0,
        function_calls=function_calls,
        tools=[approval_tool, declaration_only_tool],
        config={},
    )
    # declaration_only_flag takes precedence: all calls returned as user_input_request
    assert len(results) == 2
    for r in results:
        assert r.user_input_request is True


async def test_unknown_tool_detected_after_declaration_only_tool() -> None:
    """terminate_on_unknown_calls should raise even when a declaration-only tool appears first."""
    function_calls = [
        _make_function_call("1", "decl_tool"),
        _make_function_call("2", "nonexistent_tool"),
    ]
    with pytest.raises(KeyError, match="nonexistent_tool"):
        await _try_execute_function_calls(
            custom_args={},
            attempt_idx=0,
            function_calls=function_calls,
            tools=[declaration_only_tool],
            config={"terminate_on_unknown_calls": True},
        )


async def test_termination_propagated_from_non_approval_call() -> None:
    """should_terminate must propagate when a non-approval tool triggers MiddlewareTermination."""
    function_calls = [
        _make_function_call("1", "approval_tool"),
        _make_function_call("2", "normal_tool"),
    ]

    async def _mock_auto_invoke(*, function_call_content: Any, **kwargs: Any) -> Content:
        if function_call_content.name == "normal_tool":
            raise MiddlewareTermination("terminated", result="terminated result")
        return Content.from_function_result(call_id=function_call_content.call_id, result="ok")

    with patch("agent_framework._tools._auto_invoke_function", side_effect=_mock_auto_invoke):
        results, should_terminate = await _try_execute_function_calls(
            custom_args={},
            attempt_idx=0,
            function_calls=function_calls,
            tools=[approval_tool, normal_tool],
            config={},
        )

    assert should_terminate is True
    approval_requests = [r for r in results if r.type == "function_approval_request"]
    assert len(approval_requests) == 1


async def test_sequence_index_preserved_for_non_approval_calls() -> None:
    """Non-approval calls should receive their original index from the batch, not re-enumerated."""
    function_calls = [
        _make_function_call("1", "approval_tool"),
        _make_function_call("2", "normal_tool"),
        _make_function_call("3", "approval_tool"),
        _make_function_call("4", "normal_tool"),
    ]

    captured_indices: list[int] = []

    async def _mock_auto_invoke(*, function_call_content: Any, sequence_index: int, **kwargs: Any) -> Content:
        captured_indices.append(sequence_index)
        return Content.from_function_result(call_id=function_call_content.call_id, result="ok")

    with patch("agent_framework._tools._auto_invoke_function", side_effect=_mock_auto_invoke):
        results, _ = await _try_execute_function_calls(
            custom_args={},
            attempt_idx=0,
            function_calls=function_calls,
            tools=[approval_tool, normal_tool],
            config={},
        )

    # normal_tool calls were at indices 1 and 3 in the original batch
    assert sorted(captured_indices) == [1, 3]


async def test_no_termination_when_no_non_approval_tools_terminate() -> None:
    """should_terminate should be False when non-approval tools complete normally."""
    function_calls = [
        _make_function_call("1", "approval_tool"),
        _make_function_call("2", "normal_tool"),
    ]

    async def _mock_auto_invoke(*, function_call_content: Any, **kwargs: Any) -> Content:
        return Content.from_function_result(call_id=function_call_content.call_id, result="ok")

    with patch("agent_framework._tools._auto_invoke_function", side_effect=_mock_auto_invoke):
        results, should_terminate = await _try_execute_function_calls(
            custom_args={},
            attempt_idx=0,
            function_calls=function_calls,
            tools=[approval_tool, normal_tool],
            config={},
        )

    assert should_terminate is False


async def test_approval_only_batch_returns_no_termination() -> None:
    """A batch with only approval-required calls should return should_terminate=False."""
    function_calls = [
        _make_function_call("1", "approval_tool"),
        _make_function_call("2", "approval_tool"),
    ]

    results, should_terminate = await _try_execute_function_calls(
        custom_args={},
        attempt_idx=0,
        function_calls=function_calls,
        tools=[approval_tool],
        config={},
    )

    assert should_terminate is False
    assert all(r.type == "function_approval_request" for r in results)
