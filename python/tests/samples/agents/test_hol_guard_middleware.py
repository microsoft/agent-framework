# Copyright (c) Microsoft. All rights reserved.

"""Tests for the HOL Guard FunctionMiddleware sample (issue #7833)."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from agent_framework import FunctionInvocationContext, MiddlewareFailure

_HOL_GUARD_SAMPLE_PATH = (
    Path(__file__).parents[3] / "samples" / "02-agents" / "middleware" / "hol_guard_middleware.py"
)


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


def _context(name: str, arguments: dict) -> FunctionInvocationContext:
    fake_tool = SimpleNamespace(name=name)
    return FunctionInvocationContext(function=fake_tool, arguments=arguments)


# --- evaluate_with_hol_guard: free function, no middleware needed ---


async def test_evaluate_fails_closed_when_cli_unavailable() -> None:
    decision, _ = await evaluate_with_hol_guard("delete_production_database", {"confirm": True})
    assert decision is GuardDecision.UNAVAILABLE


async def test_offline_fallback_denies_known_dangerous_call() -> None:
    decision, _ = await evaluate_with_hol_guard(
        "delete_production_database", {"confirm": True}, offline_fallback=True
    )
    assert decision is GuardDecision.DENY


async def test_offline_fallback_allows_benign_call() -> None:
    decision, _ = await evaluate_with_hol_guard("get_weather", {"location": "Tokyo"}, offline_fallback=True)
    assert decision is GuardDecision.ALLOW


# --- HOLGuardMiddleware wiring: allow => tool runs once, deny/unavailable => zero times ---


async def test_allow_runs_tool_once() -> None:
    middleware = HOLGuardMiddleware(offline_fallback=True)
    context = _context("get_weather", {"location": "Tokyo"})
    calls = 0

    async def call_next() -> None:
        nonlocal calls
        calls += 1

    await middleware.process(context, call_next)
    assert calls == 1


async def test_deny_runs_tool_zero_times() -> None:
    middleware = HOLGuardMiddleware(offline_fallback=True)
    context = _context("delete_production_database", {"confirm": True})
    calls = 0

    async def call_next() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(MiddlewareFailure):
        await middleware.process(context, call_next)
    assert calls == 0


async def test_unavailable_fails_closed_by_default() -> None:
    middleware = HOLGuardMiddleware(offline_fallback=False)
    context = _context("get_weather", {"location": "Tokyo"})
    calls = 0

    async def call_next() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(MiddlewareFailure):
        await middleware.process(context, call_next)
    assert calls == 0
