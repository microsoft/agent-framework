# Copyright (c) Microsoft. All rights reserved.
"""Tests for the HOL Guard FunctionMiddleware sample (issue #7833)."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from agent_framework import FunctionInvocationContext, MiddlewareFailure

_HOL_GUARD_SAMPLE_PATH = Path(__file__).parents[3] / "samples" / "02-agents" / "middleware" / "hol_guard_middleware.py"


def _load_hol_guard_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hol_guard_middleware", _HOL_GUARD_SAMPLE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hol_guard_middleware = _load_hol_guard_module()
GuardDecision = hol_guard_middleware.GuardDecision
HOLGuardMiddleware = hol_guard_middleware.HOLGuardMiddleware
evaluate_with_hol_guard = hol_guard_middleware.evaluate_with_hol_guard


@pytest.fixture(autouse=True)
def _disable_hol_guard_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the CLI to look absent so tests are deterministic regardless of the host PATH."""
    monkeypatch.setattr(hol_guard_middleware.shutil, "which", lambda _: None)


def _context(name: str, arguments: dict) -> FunctionInvocationContext:
    fake_tool = SimpleNamespace(name=name)
    return FunctionInvocationContext(function=fake_tool, arguments=arguments)


class _FakeProcess:
    """Stand-in for asyncio.subprocess.Process, returning canned stdout."""

    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""


class _HangingProcess:
    """Stand-in whose communicate() never completes, to exercise the timeout path."""

    def __init__(self) -> None:
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self.killed:
            return b"", b""
        await asyncio.sleep(10)
        return b"", b""  # pragma: no cover - unreachable within the test's short timeout

    def kill(self) -> None:
        self.killed = True


# --- CLI unavailable / offline fallback (free function, no middleware needed) ---


async def test_evaluate_fails_closed_when_cli_unavailable() -> None:
    """An absent CLI with no offline fallback must return UNAVAILABLE, not allow the call."""
    decision, _ = await evaluate_with_hol_guard("delete_production_database", {"confirm": True})
    assert decision is GuardDecision.UNAVAILABLE


async def test_offline_fallback_denies_known_dangerous_call() -> None:
    """The offline deny-list still blocks an obviously dangerous call name."""
    decision, _ = await evaluate_with_hol_guard("delete_production_database", {"confirm": True}, offline_fallback=True)
    assert decision is GuardDecision.DENY


async def test_offline_fallback_allows_benign_call() -> None:
    """The offline deny-list allows a call that matches no known-dangerous pattern."""
    decision, _ = await evaluate_with_hol_guard("get_weather", {"location": "Tokyo"}, offline_fallback=True)
    assert decision is GuardDecision.ALLOW


# --- Real CLI JSON schema: status + policy_evaluation, not decision/reason ---


async def test_real_cli_no_match_maps_to_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hol-guard status of 'no_match' is an allow."""
    monkeypatch.setattr(hol_guard_middleware.shutil, "which", lambda _: "/usr/local/bin/hol-guard")

    async def fake_exec(*args: object, **kwargs: object) -> _FakeProcess:
        await asyncio.sleep(0)
        payload = json.dumps({"status": "no_match", "policy_evaluation": "not_run"}).encode()
        return _FakeProcess(payload)

    monkeypatch.setattr(hol_guard_middleware.asyncio, "create_subprocess_exec", fake_exec)

    decision, _ = await evaluate_with_hol_guard("get_weather", {"location": "Tokyo"})
    assert decision is GuardDecision.ALLOW


async def test_real_cli_review_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hol-guard status of 'review' fails closed rather than allowing the call through."""
    monkeypatch.setattr(hol_guard_middleware.shutil, "which", lambda _: "/usr/local/bin/hol-guard")

    async def fake_exec(*args: object, **kwargs: object) -> _FakeProcess:
        await asyncio.sleep(0)
        payload = json.dumps({"status": "review", "summary": "looks suspicious"}).encode()
        return _FakeProcess(payload)

    monkeypatch.setattr(hol_guard_middleware.asyncio, "create_subprocess_exec", fake_exec)

    decision, reason = await evaluate_with_hol_guard("delete_production_database", {"confirm": True})
    assert decision is GuardDecision.REVIEW
    assert "suspicious" in reason


async def test_real_cli_unrecognized_response_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unrecognized response shape fails closed instead of defaulting to allow."""
    monkeypatch.setattr(hol_guard_middleware.shutil, "which", lambda _: "/usr/local/bin/hol-guard")

    async def fake_exec(*args: object, **kwargs: object) -> _FakeProcess:
        await asyncio.sleep(0)
        return _FakeProcess(json.dumps({"unexpected": "shape"}).encode())

    monkeypatch.setattr(hol_guard_middleware.asyncio, "create_subprocess_exec", fake_exec)

    decision, _ = await evaluate_with_hol_guard("get_weather", {"location": "Tokyo"})
    assert decision is GuardDecision.ERROR


async def test_timeout_kills_process_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung hol-guard process is killed and reaped, and the call fails closed."""
    monkeypatch.setattr(hol_guard_middleware.shutil, "which", lambda _: "/usr/local/bin/hol-guard")
    fake_process = _HangingProcess()

    async def fake_exec(*args: object, **kwargs: object) -> _HangingProcess:
        await asyncio.sleep(0)
        return fake_process

    monkeypatch.setattr(hol_guard_middleware.asyncio, "create_subprocess_exec", fake_exec)

    decision, _ = await evaluate_with_hol_guard("get_weather", {"location": "Tokyo"}, timeout_seconds=0.05)
    assert decision is GuardDecision.ERROR
    assert fake_process.killed is True


# --- HOLGuardMiddleware wiring: allow => tool runs once, deny/unavailable => zero times ---


async def test_allow_runs_tool_once() -> None:
    """An allow verdict lets the wrapped tool execute exactly once."""
    middleware = HOLGuardMiddleware(offline_fallback=True)
    context = _context("get_weather", {"location": "Tokyo"})
    calls = 0

    async def call_next() -> None:
        await asyncio.sleep(0)
        nonlocal calls
        calls += 1

    await middleware.process(context, call_next)
    assert calls == 1


async def test_deny_runs_tool_zero_times() -> None:
    """A deny verdict raises MiddlewareFailure and never runs the wrapped tool."""
    middleware = HOLGuardMiddleware(offline_fallback=True)
    context = _context("delete_production_database", {"confirm": True})
    calls = 0

    async def call_next() -> None:
        await asyncio.sleep(0)
        nonlocal calls
        calls += 1

    with pytest.raises(MiddlewareFailure):
        await middleware.process(context, call_next)
    assert calls == 0


async def test_unavailable_fails_closed_by_default() -> None:
    """An unavailable Guard with no offline fallback also fails closed."""
    middleware = HOLGuardMiddleware(offline_fallback=False)
    context = _context("get_weather", {"location": "Tokyo"})
    calls = 0

    async def call_next() -> None:
        await asyncio.sleep(0)
        nonlocal calls
        calls += 1

    with pytest.raises(MiddlewareFailure):
        await middleware.process(context, call_next)
    assert calls == 0