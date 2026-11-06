# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agent_framework import FunctionTool

from agent_framework_hyperlight import HyperlightExecuteCodeTool
from agent_framework_hyperlight import _execute_code_tool as execute_code_module


@pytest.fixture
def interruptible_execution(monkeypatch: pytest.MonkeyPatch):
    entered = threading.Event()
    release = threading.Event()
    interrupted = threading.Event()
    kill_attempted = threading.Event()
    completed = threading.Event()

    class Sandbox:
        def __init__(self, **kwargs: Any) -> None:
            self._host_callback = False

        def interrupt_handle(self) -> SimpleNamespace:
            def kill() -> bool:
                kill_attempted.set()
                interrupted.set()
                return not self._host_callback

            return SimpleNamespace(kill=kill)

        def run(self, code: str) -> SimpleNamespace:
            if code in {"guest", "host"}:
                self._host_callback = code == "host"
                entered.set()
                try:
                    if self._host_callback:
                        if not release.wait(5):
                            raise RuntimeError("Host callback was not released.")
                    elif not interrupted.wait(5):
                        raise RuntimeError("Guest was not interrupted.")
                    if interrupted.is_set():
                        raise InterruptedError("Guest execution interrupted.")
                finally:
                    completed.set()
                    self._host_callback = False
            return SimpleNamespace(success=True, stdout="ok\n", stderr="")

        def snapshot(self) -> object:
            return object()

        def restore(self, snapshot: object) -> None:
            interrupted.clear()

    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: Sandbox)
    execute_code = HyperlightExecuteCodeTool(execution_timeout_seconds=0.1)
    yield SimpleNamespace(
        tool=execute_code,
        entered=entered,
        release=release,
        kill_attempted=kill_attempted,
        completed=completed,
    )
    release.set()
    cast(Any, execute_code._registry).close()


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

            def interrupt_handle(self) -> SimpleNamespace:
                return SimpleNamespace(kill=lambda: False)

            def restore(self, snapshot: object) -> None:
                self._record("restore")

            def close(self) -> None:
                self._record("close")

            def __del__(self) -> None:
                self.events.append(("drop", threading.get_ident()))

        return LifecycleSandbox

    return factory
