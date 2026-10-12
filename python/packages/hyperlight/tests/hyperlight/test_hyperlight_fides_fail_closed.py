# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for opt-in fail-closed FIDES handling in Hyperlight CodeAct."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest
from agent_framework import Content, tool
from agent_framework.exceptions import CodeActFidesCoverageError

from agent_framework_hyperlight import HyperlightCodeActProvider, HyperlightExecuteCodeTool
from agent_framework_hyperlight import _execute_code_tool as execute_module

host_calls: list[str] = []


@tool
def sensitive_tool(value: str) -> str:
    """Example sensitive host function."""
    host_calls.append(value)
    return value


class SpyRuntime:
    def __init__(self) -> None:
        self.invocations = 0

    def execute(self, *, config: Any, code: str) -> list[Content]:
        self.invocations += 1
        return [Content.from_text("No host-tool invocation")]


@pytest.fixture(autouse=True)
def reset_side_effects() -> None:
    host_calls.clear()


@pytest.mark.parametrize("entry_point", [HyperlightExecuteCodeTool, HyperlightCodeActProvider])
def test_strict_rejects_registered_host_tool(entry_point: type) -> None:
    spy = SpyRuntime()
    with pytest.raises(CodeActFidesCoverageError, match="require_fides=True"):
        entry_point(tools=[sensitive_tool], require_fides=True, _registry=spy)
    assert spy.invocations == 0
    assert not host_calls


@pytest.mark.parametrize("entry_point", [HyperlightExecuteCodeTool, HyperlightCodeActProvider])
def test_strict_rejects_dynamic_tools_without_mutation(entry_point: type) -> None:
    codeact = entry_point(require_fides=True, _registry=SpyRuntime())
    with pytest.raises(CodeActFidesCoverageError):
        codeact.add_tools(sensitive_tool)
    assert codeact.get_tools() == []
    assert not host_calls


@pytest.mark.parametrize("invalid", [None, 1, "true", [], object()])
def test_strict_option_requires_bool(invalid: object) -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        HyperlightExecuteCodeTool(require_fides=invalid, _registry=SpyRuntime())  # type: ignore[arg-type]


async def test_strict_no_host_tools_can_execute_and_snapshot() -> None:
    spy = SpyRuntime()
    provider = HyperlightCodeActProvider(require_fides=True, _registry=spy)
    execute_code = provider._execute_code_tool
    assert execute_code.require_fides
    with pytest.raises(AttributeError):
        execute_code.require_fides = False  # type: ignore[misc]
    assert execute_code.build_serializable_state()["require_fides"] is True
    assert execute_code.build_instructions(tools_visible_to_model=False)
    run_tool = execute_code.create_run_tool()
    assert run_tool.require_fides
    assert run_tool._build_run_config().require_fides
    assert run_tool.build_serializable_state()["require_fides"] is True
    assert run_tool.get_tools() == []
    contents = await run_tool._run_code(code="print('safe')")
    assert contents[0].type == "text"
    assert spy.invocations == 1
    assert not host_calls


def test_legacy_default_preserves_host_tool_registration() -> None:
    codeact = HyperlightExecuteCodeTool(tools=sensitive_tool, _registry=SpyRuntime())
    assert codeact.require_fides is False
    assert codeact.get_tools() == [sensitive_tool]
    assert codeact._build_run_config().tools == (sensitive_tool,)
    assert codeact.build_serializable_state()["require_fides"] is False


async def test_strict_rechecks_run_config_before_runtime() -> None:
    spy = SpyRuntime()
    codeact = HyperlightExecuteCodeTool(require_fides=True, _registry=spy)
    codeact._managed_tools.append(sensitive_tool)
    with pytest.raises(CodeActFidesCoverageError):
        await codeact._run_code(code="call_tool('sensitive_tool', value='secret')")
    with pytest.raises(CodeActFidesCoverageError):
        codeact.create_run_tool()
    with pytest.raises(CodeActFidesCoverageError):
        codeact.build_serializable_state()
    with pytest.raises(CodeActFidesCoverageError):
        codeact.build_instructions(tools_visible_to_model=True)
    assert spy.invocations == 0
    assert not host_calls


def test_strict_registry_rechecks_forged_run_config_before_any_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    codeact = HyperlightExecuteCodeTool(require_fides=True, _registry=SpyRuntime())
    config = replace(codeact._build_run_config(), tools=(sensitive_tool,))
    runtime = execute_module._SandboxRegistry()
    try:

        def unexpected_entry(*args: Any, **kwargs: Any) -> None:
            pytest.fail("Sandbox should not be allocated on denied requests")

        monkeypatch.setattr(runtime, "_get_or_create_entry", unexpected_entry)
        with pytest.raises(CodeActFidesCoverageError):
            runtime.execute(config=config, code="call_tool('sensitive_tool', value='secret')")
        with pytest.raises(CodeActFidesCoverageError):
            runtime._create_entry(config)
    finally:
        runtime.close()
    assert not host_calls


def test_strict_callback_never_invokes_host_tool() -> None:
    callback = execute_module._make_sandbox_callback(sensitive_tool, require_fides=True)
    with pytest.raises(CodeActFidesCoverageError):
        callback(value="private-value")
    assert not host_calls


async def test_concurrent_strict_requests_fail_before_runtime() -> None:
    spy = SpyRuntime()
    codeact = HyperlightExecuteCodeTool(require_fides=True, _registry=spy)
    codeact._managed_tools.append(sensitive_tool)
    results = await asyncio.gather(
        *(codeact._run_code(code="call_tool('sensitive_tool', value='secret')") for _ in range(25)),
        return_exceptions=True,
    )
    assert all(isinstance(item, CodeActFidesCoverageError) for item in results)
    assert spy.invocations == 0
    assert not host_calls
