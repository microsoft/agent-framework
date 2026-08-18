# Copyright (c) Microsoft. All rights reserved.

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("dhms_agentfuse")

_SAMPLE_PATH = Path(__file__).parents[4] / "samples" / "02-agents" / "middleware" / "agentfuse_function_middleware.py"
_SPEC = importlib.util.spec_from_file_location("agentfuse_function_middleware_sample", _SAMPLE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SAMPLE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SAMPLE)


async def test_agentfuse_sample_runs_real_dispatch_and_blocks_before_dispatch() -> None:
    summary = await _SAMPLE.run_contract_verification()

    assert summary == {
        "allow_handler_count": 1,
        "block_handler_count": 0,
        "guard_failure_handler_count": 0,
        "allow_tool_call_id": "call-allow-1",
        "block_tool_call_id": "call-block-1",
    }


async def test_agentfuse_sample_fails_closed_without_host_identity() -> None:
    counter = {"count": 0}
    middleware = _SAMPLE.AgentFuseFunctionMiddleware(_SAMPLE.RuntimeGuard(default_action="allow"))

    @_SAMPLE.tool(name="safe_read", approval_mode="never_require")
    def protected_tool() -> str:
        counter["count"] += 1
        return "handled"

    context = _SAMPLE.FunctionInvocationContext(function=protected_tool, arguments={})

    async def call_next() -> None:
        context.result = await protected_tool.invoke(arguments={}, context=context, skip_parsing=True)

    await middleware.process(context, call_next)

    assert context.result == {
        "type": "agentfuse_policy_result",
        "tool_call_id": None,
        "tool_name": "safe_read",
        "decision": "block",
        "reason_code": "missing_tool_call_id",
        "execution_outcome": "not_executed",
        "handler_invoked": False,
    }
    assert counter["count"] == 0


async def test_agentfuse_sample_leaves_allowed_handler_failure_to_the_host() -> None:
    counter = {"count": 0}
    middleware = _SAMPLE.AgentFuseFunctionMiddleware(_SAMPLE.RuntimeGuard(allow_tools={"failing_tool"}))

    @_SAMPLE.tool(name="failing_tool", approval_mode="never_require")
    def protected_tool() -> str:
        counter["count"] += 1
        raise RuntimeError("simulated handler failure")

    context = _SAMPLE.FunctionInvocationContext(
        function=protected_tool,
        arguments={},
        metadata={"call_id": "call-handler-failure-1"},
    )

    async def call_next() -> None:
        context.result = await protected_tool.invoke(
            arguments={},
            context=context,
            tool_call_id="call-handler-failure-1",
            skip_parsing=True,
        )

    with pytest.raises(RuntimeError, match="simulated handler failure"):
        await middleware.process(context, call_next)

    assert counter["count"] == 1
    assert context.metadata["agentfuse_decision"].action == "allow"


async def test_agentfuse_sample_preserves_task_cancellation_before_dispatch() -> None:
    counter = {"count": 0}

    class CancellingRuntimeGuard(_SAMPLE.RuntimeGuard):
        async def aevaluate(self, _tool_call: object) -> object:
            raise asyncio.CancelledError

    middleware = _SAMPLE.AgentFuseFunctionMiddleware(CancellingRuntimeGuard())

    @_SAMPLE.tool(name="safe_read", approval_mode="never_require")
    def protected_tool() -> str:
        counter["count"] += 1
        return "handled"

    context = _SAMPLE.FunctionInvocationContext(
        function=protected_tool,
        arguments={},
        metadata={"call_id": "call-cancelled-1"},
    )

    async def call_next() -> None:
        context.result = await protected_tool.invoke(
            arguments={},
            context=context,
            tool_call_id="call-cancelled-1",
            skip_parsing=True,
        )

    with pytest.raises(asyncio.CancelledError):
        await middleware.process(context, call_next)

    assert counter["count"] == 0
    assert "agentfuse_decision" not in context.metadata
