# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from agent_framework import FunctionTool


@pytest.fixture
def host_error_detail() -> str:
    return "synthetic backend diagnostic"


@pytest.fixture
def failing_host_tool(request: pytest.FixtureRequest, host_error_detail: str) -> FunctionTool:
    def fail() -> str:
        raise ValueError(host_error_detail)

    async def fail_async() -> str:
        await asyncio.sleep(0)
        raise ValueError(host_error_detail)

    return FunctionTool(
        name="failing_host_tool",
        description="Raise a synthetic diagnostic.",
        func=fail_async if request.param else fail,
    )


@pytest.fixture
def cancelled_host_tool() -> FunctionTool:
    async def cancel() -> str:
        raise asyncio.CancelledError

    return FunctionTool(name="cancelled_host_tool", func=cancel)


@pytest.fixture
def lifecycle_sandbox_factory(host_error_detail: str) -> Callable[..., type[Any]]:
    def factory(failure_stage: str, error_type: type[BaseException] = ValueError) -> type[Any]:
        class LifecycleSandbox:
            events: list[tuple[str, int]] = []

            def __init__(self, **kwargs: Any) -> None:
                self._owner_thread = threading.get_ident()
                self._record("build")

            def _record(self, stage: str) -> None:
                self.events.append((stage, threading.get_ident()))
                if stage == failure_stage:
                    raise error_type(host_error_detail)

            def register_tool(self, name: str, callback: Any) -> None:
                self._record("register_tool")

            def allow_domain(self, target: str, methods: Any = None) -> None:
                self._record("allow_domain")

            def run(self, code: str) -> Any:
                self._record("warmup" if code == "None" else "run")
                return SimpleNamespace(success=True, stdout="ok\n", stderr="")

            def snapshot(self) -> object:
                self._record("snapshot")
                return object()

            def restore(self, snapshot: object) -> None:
                self._record("restore")

            def close(self) -> None:
                self._record("close")

            def __del__(self) -> None:
                self.events.append(("drop", threading.get_ident()))

        return LifecycleSandbox

    return factory
