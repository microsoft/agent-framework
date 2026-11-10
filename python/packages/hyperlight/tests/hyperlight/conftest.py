# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agent_framework import FunctionTool

from agent_framework_hyperlight import HyperlightExecuteCodeTool
from agent_framework_hyperlight import _execute_code_tool as execute_code_module


@pytest.fixture
def execution_clock(monkeypatch: pytest.MonkeyPatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(execute_code_module, "time", SimpleNamespace(monotonic=lambda: clock.now))
    return clock


@pytest.fixture
def interrupted_initialization(monkeypatch: pytest.MonkeyPatch, execution_clock, request: pytest.FixtureRequest):
    stage = request.param
    entered = threading.Event()
    release = threading.Event()
    interrupted = threading.Event()
    cancelled = threading.Event()
    events: list[tuple[int, str, int]] = []
    workers: list[Any] = []
    builds = 0

    original_init = execute_code_module._SandboxWorker.__init__

    def initialize_worker(self, **kwargs: Any) -> None:
        original_init(self, **kwargs)
        workers.append(self)

    class Snapshot:
        def __init__(self, generation: int) -> None:
            self.generation = generation

        def __del__(self) -> None:
            events.append((self.generation, "drop_snapshot", threading.get_ident()))

    class Sandbox:
        def __init__(self, **kwargs: Any) -> None:
            nonlocal builds, cancelled
            builds += 1
            self.generation = builds
            events.append((self.generation, "build", threading.get_ident()))
            if self.generation == 1:
                cancellation = execute_code_module._execution_cancellation.get()
                assert cancellation is not None
                cancelled = cancellation
            if self.generation == 1 and stage == "build":
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Sandbox construction was not released.")

        def interrupt_handle(self) -> SimpleNamespace:
            def kill() -> bool:
                interrupted.set()
                return True

            return SimpleNamespace(kill=kill)

        def run(self, code: str) -> SimpleNamespace:
            events.append((self.generation, "warmup" if code == "None" else "run", threading.get_ident()))
            if self.generation == 1 and stage == "warmup":
                entered.set()
                if not interrupted.wait(5):
                    raise RuntimeError("Warm-up was not interrupted.")
                raise InterruptedError("Warm-up interrupted.")
            return SimpleNamespace(success=True, stdout="ok\n", stderr="")

        def snapshot(self) -> Snapshot:
            snapshot = Snapshot(self.generation)
            if self.generation == 1 and stage == "snapshot":
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Snapshot creation was not released.")
            return snapshot

        def restore(self, snapshot: Snapshot) -> None:
            events.append((self.generation, "restore", threading.get_ident()))

        def __del__(self) -> None:
            events.append((self.generation, "drop", threading.get_ident()))

    monkeypatch.setattr(execute_code_module._SandboxWorker, "__init__", initialize_worker)
    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: Sandbox)
    execute_code = HyperlightExecuteCodeTool(execution_timeout_seconds=10)
    yield SimpleNamespace(
        tool=execute_code,
        clock=execution_clock,
        entered=entered,
        release=release,
        interrupted=interrupted,
        cancellation=lambda: cancelled,
        events=events,
        workers=workers,
        stage=stage,
    )
    release.set()
    interrupted.set()
    cast(Any, execute_code._registry).close()


@pytest.fixture
def concurrent_cold_execution(monkeypatch: pytest.MonkeyPatch, execution_clock, request: pytest.FixtureRequest):
    initialized = threading.Event()
    intervening_entered = threading.Event()
    cold_queued = threading.Event()
    interrupted = threading.Event()
    executed: list[str] = []

    class Sandbox:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def interrupt_handle(self) -> SimpleNamespace:
            def kill() -> bool:
                interrupted.set()
                return True

            return SimpleNamespace(kill=kill)

        def run(self, code: str) -> SimpleNamespace:
            executed.append(code)
            if code == "None":
                execution_clock.now += 3
            elif code == "intervening":
                intervening_entered.set()
                if not cold_queued.wait(5):
                    raise RuntimeError("Cold invocation was not queued.")
                execution_clock.now += 20
            else:
                execution_clock.now += request.param
                if request.param > 7:
                    if not interrupted.wait(5):
                        raise RuntimeError("Cold invocation was not interrupted.")
                    raise InterruptedError("Cold invocation interrupted.")
            return SimpleNamespace(success=True, stdout="ok\n", stderr="")

        def snapshot(self) -> object:
            return object()

        def restore(self, snapshot: object) -> None:
            pass

    monkeypatch.setattr(execute_code_module, "_load_sandbox_class", lambda: Sandbox)
    execute_code = HyperlightExecuteCodeTool(execution_timeout_seconds=10)
    registry = cast(Any, execute_code._registry)
    get_entry = registry._get_or_create_entry

    def get_entry_before_first_submission(config, *, control=None):
        entry = get_entry(config, control=control)
        if not initialized.is_set():
            cancellation = execute_code_module._execution_cancellation.get()
            submit = entry.worker._executor.submit

            def submit_and_signal(fn, *args, **kwargs):
                future = submit(fn, *args, **kwargs)
                if execute_code_module._execution_cancellation.get() is cancellation:
                    cold_queued.set()
                return future

            monkeypatch.setattr(entry.worker._executor, "submit", submit_and_signal)
            initialized.set()
            if not intervening_entered.wait(5):
                raise RuntimeError("Intervening invocation did not start.")
        return entry

    monkeypatch.setattr(registry, "_get_or_create_entry", get_entry_before_first_submission)
    yield SimpleNamespace(
        tool=execute_code,
        initialized=initialized,
        intervening_entered=intervening_entered,
        cold_queued=cold_queued,
        executed=executed,
        duration=request.param,
    )
    intervening_entered.set()
    cold_queued.set()
    interrupted.set()
    registry.close()


@pytest.fixture
async def occupied_default_executor(monkeypatch: pytest.MonkeyPatch):
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    queued = asyncio.Event()
    release = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hl-test-default")
    loop.set_default_executor(executor)

    def occupy_executor() -> None:
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(5):
            raise RuntimeError("Default executor was not released.")

    blocker = loop.run_in_executor(None, occupy_executor)
    original_run_in_executor = loop.run_in_executor

    def run_in_executor(executor, func, *args):
        future = original_run_in_executor(executor, func, *args)
        if executor is None:
            queued.set()
        return future

    monkeypatch.setattr(loop, "run_in_executor", run_in_executor)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        yield SimpleNamespace(queued=queued, release=release, blocker=blocker)
    finally:
        release.set()
        try:
            await asyncio.wait_for(blocker, 2)
        finally:
            executor.shutdown(wait=True)


@pytest.fixture
def observe_sandbox_queue(monkeypatch: pytest.MonkeyPatch):
    def observe(worker):
        loop = asyncio.get_running_loop()
        queued = asyncio.Event()
        submit = worker._executor.submit

        def submit_and_signal(fn, *args, **kwargs):
            future = submit(fn, *args, **kwargs)
            loop.call_soon_threadsafe(queued.set)
            return future

        monkeypatch.setattr(worker._executor, "submit", submit_and_signal)
        return queued

    return observe


@pytest.fixture
def interruptible_execution(monkeypatch: pytest.MonkeyPatch):
    started = threading.Event()
    entered = threading.Event()
    release = threading.Event()
    interrupted = threading.Event()
    kill_attempted = threading.Event()
    completed = threading.Event()
    executed: list[str] = []

    class Sandbox:
        def __init__(self, **kwargs: Any) -> None:
            started.set()
            self._host_callback = False

        def interrupt_handle(self) -> SimpleNamespace:
            def kill() -> bool:
                kill_attempted.set()
                interrupted.set()
                return not self._host_callback

            return SimpleNamespace(kill=kill)

        def run(self, code: str) -> SimpleNamespace:
            executed.append(code)
            if code in {"guest", "host", "final_host"}:
                self._host_callback = code in {"host", "final_host"}
                entered.set()
                try:
                    if self._host_callback:
                        if not release.wait(5):
                            raise RuntimeError("Host callback was not released.")
                    elif not interrupted.wait(5):
                        raise RuntimeError("Guest was not interrupted.")
                    if interrupted.is_set() and code != "final_host":
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
        started=started,
        entered=entered,
        release=release,
        kill_attempted=kill_attempted,
        completed=completed,
        executed=executed,
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
