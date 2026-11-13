# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, cast

import pytest
from agent_framework import tool

from agent_framework_hyperlight import HyperlightExecuteCodeTool

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("HYPERLIGHT_RUN_GUEST_TESTS") != "true",
        reason="Requires explicit Hyperlight KVM guest-test configuration.",
    ),
]


@pytest.mark.parametrize("backend", ["wasm", "hyperlight-js"])
async def test_cancellation_stops_guest_before_reuse(backend: str) -> None:
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    completed = asyncio.Event()
    deadline = 0.0

    @tool
    def started() -> None:
        """Signal guest entry."""
        nonlocal deadline
        deadline = time.monotonic() + 5
        loop.call_soon_threadsafe(entered.set)

    @tool
    def keep_running() -> bool:
        """Bound the baseline workload using the host clock."""
        return time.monotonic() < deadline

    @tool
    def finished() -> None:
        """Signal guest completion."""
        loop.call_soon_threadsafe(completed.set)

    execute_code = HyperlightExecuteCodeTool(
        tools=[started, keep_running, finished],
        backend=backend,
        module=None if backend == "hyperlight-js" else "python_guest.path",
    )
    code = (
        "call_tool('started')\nwhile call_tool('keep_running'):\n    pass\ncall_tool('finished')"
        if backend == "wasm"
        else "call_tool('started'); while (call_tool('keep_running')) {} call_tool('finished');"
    )
    try:
        warmup = await execute_code.invoke(arguments={"code": "print('ready')" if backend == "wasm" else "1;"})
        assert not any(item.type == "error" for item in warmup), warmup
        execution = asyncio.create_task(execute_code.invoke(arguments={"code": code}))
        await asyncio.wait_for(entered.wait(), 10)
        start = time.monotonic()
        execution.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution
        recovered = await asyncio.wait_for(
            execute_code.invoke(
                arguments={"code": "print('recovered')" if backend == "wasm" else "console.log('recovered');"}
            ),
            10,
        )
        assert not any(item.type == "error" for item in recovered), recovered
        assert not completed.is_set(), "Guest continued executing after caller cancellation."
        assert time.monotonic() - start < 3, "Cancellation did not promptly release guest execution."
        assert any(item.type == "text" and "recovered" in (item.text or "") for item in recovered)
    finally:
        cast(Any, execute_code._registry).close()


@pytest.mark.parametrize("backend", ["wasm", "hyperlight-js"])
async def test_configured_timeout_interrupts_cpu_work_and_allows_reuse(backend: str) -> None:
    warm_tool = HyperlightExecuteCodeTool(
        backend=backend, module=None if backend == "hyperlight-js" else "python_guest.path"
    )
    limited_tool = HyperlightExecuteCodeTool(
        backend=backend,
        module=None if backend == "hyperlight-js" else "python_guest.path",
        execution_timeout_seconds=0.1,
        _registry=warm_tool._registry,
    )
    try:
        warmup = await warm_tool.invoke(arguments={"code": "print('ready')" if backend == "wasm" else "1;"})
        assert not any(item.type == "error" for item in warmup), warmup
        start = time.monotonic()
        result = await limited_tool.invoke(
            arguments={
                "code": (
                    "for value in range(100_000_000):\n    value * value"
                    if backend == "wasm"
                    else "for (let value = 0; value < 100000000; value++) { value * value; }"
                )
            }
        )
        assert time.monotonic() - start < 3
        errors = [item for item in result if item.type == "error"]
        assert len(errors) == 1
        assert errors[0].error_details == "Code execution exceeded its time limit."
        recovered = await asyncio.wait_for(
            warm_tool.invoke(
                arguments={"code": "print('recovered')" if backend == "wasm" else "console.log('recovered');"}
            ),
            10,
        )
        assert not any(item.type == "error" for item in recovered), recovered
        assert any(item.type == "text" and "recovered" in (item.text or "") for item in recovered)
    finally:
        cast(Any, warm_tool._registry).close()


async def test_default_timeout_stops_guest_before_reuse() -> None:
    deadline = 0.0

    @tool
    def keep_running() -> bool:
        """Bound the baseline workload using the host clock."""
        return time.monotonic() < deadline

    execute_code = HyperlightExecuteCodeTool(tools=[keep_running])
    try:
        warmup = await execute_code.invoke(arguments={"code": "print('ready')"})
        assert not any(item.type == "error" for item in warmup), warmup
        deadline = time.monotonic() + 32
        result = await execute_code.invoke(
            arguments={"code": "while call_tool('keep_running'):\n    pass\nprint('finished')"}
        )
        errors = [item for item in result if item.type == "error"]
        assert len(errors) == 1, "The default execution limit was not enforced."
        assert errors[0].error_details == "Code execution exceeded its time limit."
        recovered = await asyncio.wait_for(execute_code.invoke(arguments={"code": "print('recovered')"}), 10)
        assert any(item.type == "text" and "recovered" in (item.text or "") for item in recovered)
        assert not any(item.type == "error" for item in recovered), recovered
    finally:
        cast(Any, execute_code._registry).close()
