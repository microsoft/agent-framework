# Copyright (c) Microsoft. All rights reserved.

"""Tests for :class:`InProcessTaskRunner` and runtime-mode auto-detection."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from agent_framework_hosting import (
    AgentFrameworkHost,
    ChannelContext,
    ChannelContribution,
    InProcessTaskRunner,
    RetryPolicy,
    TaskHandle,
)
from agent_framework_hosting._host import _detect_runtime_mode

# --------------------------------------------------------------------------- #
# Test helpers                                                                  #
# --------------------------------------------------------------------------- #


class _AgentStub:
    """Bare-minimum SupportsAgentRun stub for host construction."""

    async def run(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - unused
        return None


class _ChannelStub:
    name = "stub"
    path = "/stub"

    def contribute(self, _context: ChannelContext) -> ChannelContribution:
        return ChannelContribution()


# --------------------------------------------------------------------------- #
# Runtime-mode auto-detection                                                  #
# --------------------------------------------------------------------------- #


class TestRuntimeModeDetection:
    """``_detect_runtime_mode`` is pure: tests pass a synthetic env so
    they never depend on the test runner's environment. Auto-detected
    mode + matched marker drive the per-host startup banner so operators
    can confirm the host is running in the expected shape."""

    def test_no_markers_defaults_to_long_running(self) -> None:
        mode, marker = _detect_runtime_mode(env={})
        assert mode == "long_running"
        assert marker is None

    def test_foundry_marker_selects_ephemeral(self) -> None:
        mode, marker = _detect_runtime_mode(env={"FOUNDRY_HOSTING_ENVIRONMENT": "production"})
        assert mode == "ephemeral"
        assert marker == "FOUNDRY_HOSTING_ENVIRONMENT"

    def test_azure_functions_marker_selects_ephemeral(self) -> None:
        mode, marker = _detect_runtime_mode(env={"AZURE_FUNCTIONS_ENVIRONMENT": "Development"})
        assert mode == "ephemeral"
        assert marker == "AZURE_FUNCTIONS_ENVIRONMENT"

    def test_lambda_marker_selects_ephemeral(self) -> None:
        mode, marker = _detect_runtime_mode(env={"AWS_LAMBDA_FUNCTION_NAME": "my-fn"})
        assert mode == "ephemeral"
        assert marker == "AWS_LAMBDA_FUNCTION_NAME"

    def test_empty_marker_value_ignored(self) -> None:
        # Empty-string env var should not count as "set" — Foundry's
        # template uses unset-or-empty as "not deployed".
        mode, marker = _detect_runtime_mode(env={"FOUNDRY_HOSTING_ENVIRONMENT": ""})
        assert mode == "long_running"
        assert marker is None


class TestHostRuntimeMode:
    """``runtime_mode`` ctor argument overrides auto-detect; ``None``
    triggers auto-detect. The detected mode is exposed via the
    ``runtime_mode`` property for operator inspection (and is logged at
    startup via ``_log_startup``)."""

    def test_explicit_long_running(self) -> None:
        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub()],
            runtime_mode="long_running",
        )
        assert host.runtime_mode == "long_running"

    def test_explicit_ephemeral_warns_with_default_runner(self, caplog: pytest.LogCaptureFixture) -> None:
        # Default runner is in-process and not durable; ephemeral
        # deployments should be warned at construction so the operator
        # doesn't ship a config that silently loses pushes.
        with caplog.at_level("WARNING", logger="agent_framework.hosting"):
            host = AgentFrameworkHost(
                target=_AgentStub(),
                channels=[_ChannelStub()],
                runtime_mode="ephemeral",
            )
        assert host.runtime_mode == "ephemeral"
        assert any("ephemeral" in r.getMessage() and "InProcessTaskRunner" in r.getMessage() for r in caplog.records)

    def test_explicit_ephemeral_with_supplied_runner_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        runner = InProcessTaskRunner()
        with caplog.at_level("WARNING", logger="agent_framework.hosting"):
            host = AgentFrameworkHost(
                target=_AgentStub(),
                channels=[_ChannelStub()],
                runtime_mode="ephemeral",
                durable_task_runner=runner,
            )
        # No warning — operator opted into a specific runner.
        assert host.runtime_mode == "ephemeral"
        assert host.durable_task_runner is runner
        assert not any("ephemeral" in r.getMessage() for r in caplog.records)

    def test_auto_detect_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "production")
        host = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()])
        assert host.runtime_mode == "ephemeral"

    def test_default_runner_is_in_process_task_runner(self) -> None:
        host = AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()])
        assert isinstance(host.durable_task_runner, InProcessTaskRunner)


# --------------------------------------------------------------------------- #
# InProcessTaskRunner                                                          #
# --------------------------------------------------------------------------- #


class TestInProcessTaskRunner:
    async def test_schedule_runs_handler_and_records_succeeded(self) -> None:
        runner = InProcessTaskRunner()
        seen: list[Mapping[str, Any]] = []

        async def handler(payload: Mapping[str, Any]) -> None:
            seen.append(payload)

        runner.register("ping", handler)
        handle = await runner.schedule("ping", {"x": 1})
        # ``schedule`` returns immediately; the task runs on the loop.
        # Drain explicitly via ``shutdown`` to flush in-flight work,
        # then assert.
        await _drain(runner, handle)
        assert seen == [{"x": 1}]
        assert await runner.get(handle) == "succeeded"

    async def test_unknown_handler_raises_keyerror(self) -> None:
        runner = InProcessTaskRunner()
        with pytest.raises(KeyError):
            await runner.schedule("missing", {})

    async def test_register_after_start_raises(self) -> None:
        runner = InProcessTaskRunner()

        async def noop(_p: Mapping[str, Any]) -> None:
            return None

        runner.register("x", noop)
        handle = await runner.schedule("x", {})
        await _drain(runner, handle)
        # Re-registering after the runner has started scheduling is
        # rejected so in-flight tasks can't have their handler swapped
        # out from under them.
        with pytest.raises(RuntimeError, match="register"):
            runner.register("y", noop)

    async def test_handler_retried_then_succeeds(self) -> None:
        runner = InProcessTaskRunner()
        attempts = {"n": 0}

        async def flaky(_p: Mapping[str, Any]) -> None:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError(f"attempt {attempts['n']}")

        runner.register("flaky", flaky)
        # Tight retry policy so the test doesn't sleep visibly.
        policy = RetryPolicy(max_attempts=5, initial_backoff_seconds=0.001, max_backoff_seconds=0.005)
        handle = await runner.schedule("flaky", {}, retry_policy=policy)
        await _drain(runner, handle)
        assert attempts["n"] == 3
        assert await runner.get(handle) == "succeeded"

    async def test_handler_failure_records_failed_after_max_attempts(self) -> None:
        runner = InProcessTaskRunner()

        async def always_fails(_p: Mapping[str, Any]) -> None:
            raise RuntimeError("nope")

        runner.register("doomed", always_fails)
        policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0.001)
        handle = await runner.schedule("doomed", {}, retry_policy=policy)
        await _drain(runner, handle)
        assert await runner.get(handle) == "failed"

    async def test_shutdown_cancels_pending_tasks(self) -> None:
        runner = InProcessTaskRunner()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def long_running(_p: Mapping[str, Any]) -> None:
            started.set()
            try:
                # Sleep longer than the test wait so shutdown can cancel.
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        runner.register("long", long_running)
        handle = await runner.schedule("long", {})
        await asyncio.wait_for(started.wait(), timeout=1.0)
        await runner.shutdown(timeout=1.0)
        assert cancelled.is_set()
        assert await runner.get(handle) == "cancelled"

    async def test_get_returns_none_for_unknown_handle(self) -> None:
        runner = InProcessTaskRunner()
        handle = TaskHandle(task_id="never-scheduled", name="x")
        assert await runner.get(handle) is None

    async def test_terminal_cache_evicts_oldest(self) -> None:
        # Cache size of 2: drain three tasks in sequence, the first
        # should age out by the time the third's terminal lands.
        runner = InProcessTaskRunner(terminal_cache_size=2)

        async def noop(_p: Mapping[str, Any]) -> None:
            return None

        runner.register("noop", noop)
        h1 = await runner.schedule("noop", {})
        await _drain(runner, h1)
        h2 = await runner.schedule("noop", {})
        await _drain(runner, h2)
        h3 = await runner.schedule("noop", {})
        await _drain(runner, h3)
        # Oldest handle's terminal status should be evicted by now.
        assert await runner.get(h1) is None
        assert await runner.get(h2) == "succeeded"
        assert await runner.get(h3) == "succeeded"

    async def test_shutdown_is_safe_when_no_tasks_pending(self) -> None:
        runner = InProcessTaskRunner()
        # No-op shouldn't raise.
        await runner.shutdown()


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


async def _drain(runner: InProcessTaskRunner, handle: TaskHandle, *, timeout: float = 1.0) -> None:
    """Wait for ``handle`` to reach a terminal state.

    Polls ``get`` rather than reaching into runner internals so we exercise the
    public surface from the test side too.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        status = await runner.get(handle)
        if status in ("succeeded", "failed", "cancelled"):
            return
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(f"task {handle.task_id} did not reach terminal in {timeout}s; status={status}")
        await asyncio.sleep(0.01)
