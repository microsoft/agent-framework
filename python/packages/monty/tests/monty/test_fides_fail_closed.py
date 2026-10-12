# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for opt-in fail-closed FIDES handling in Monty CodeAct."""

from __future__ import annotations

import asyncio

import pytest
from agent_framework import tool
from agent_framework.exceptions import CodeActFidesCoverageError

from agent_framework_monty import MontyCodeActProvider, MontyExecuteCodeTool


@tool
def sensitive_tool(value: str) -> str:
    """Example sensitive host function."""
    sensitive_tool_calls.append(value)
    return value


sensitive_tool_calls: list[str] = []


@pytest.fixture(autouse=True)
def reset_side_effects() -> None:
    sensitive_tool_calls.clear()


@pytest.mark.parametrize("entry_point", [MontyExecuteCodeTool, MontyCodeActProvider])
def test_strict_rejects_initial_host_tool_surface(entry_point: type) -> None:
    with pytest.raises(CodeActFidesCoverageError, match="require_fides=True") as exc:
        entry_point(tools=[sensitive_tool], require_fides=True)
    assert "private-value" not in str(exc.value)
    assert not sensitive_tool_calls


@pytest.mark.parametrize("entry_point", [MontyExecuteCodeTool, MontyCodeActProvider])
def test_strict_rejects_dynamic_registration_without_mutation(entry_point: type) -> None:
    codeact = entry_point(require_fides=True)
    assert codeact.get_tools() == []
    with pytest.raises(CodeActFidesCoverageError):
        codeact.add_tools(sensitive_tool)
    assert codeact.get_tools() == []
    assert not sensitive_tool_calls


@pytest.mark.parametrize("invalid", [None, 1, "true", [], object()])
def test_strict_option_requires_bool(invalid: object) -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        MontyExecuteCodeTool(require_fides=invalid)  # type: ignore[arg-type]


def test_strict_empty_surface_snapshots_and_instruction_generation() -> None:
    provider = MontyCodeActProvider(require_fides=True)
    execute_code = provider._execute_code_tool
    assert execute_code.require_fides is True
    with pytest.raises(AttributeError):
        execute_code.require_fides = False  # type: ignore[misc]
    assert execute_code.build_serializable_state()["require_fides"] is True
    assert execute_code.build_instructions(tools_visible_to_model=False)
    run_tool = execute_code.create_run_tool()
    assert run_tool.require_fides is True
    assert run_tool.get_tools() == []
    assert run_tool.build_serializable_state()["require_fides"] is True


def test_legacy_default_accepts_unannotated_tool_and_snapshot() -> None:
    codeact = MontyExecuteCodeTool(tools=sensitive_tool)
    assert not codeact.require_fides
    assert codeact.get_tools() == [sensitive_tool]
    assert not codeact.create_run_tool().require_fides
    assert codeact.build_serializable_state()["require_fides"] is False


async def test_strict_dispatch_guard_blocks_tampered_registry_before_bridge() -> None:
    codeact = MontyExecuteCodeTool(require_fides=True)
    # Defense in depth against accidental internal registry mutation after validation.
    codeact._managed_tools.append(sensitive_tool)
    with pytest.raises(CodeActFidesCoverageError):
        await codeact._run_code(code="await sensitive_tool(value='private-value')")
    with pytest.raises(CodeActFidesCoverageError):
        codeact._build_tool_map([sensitive_tool])
    with pytest.raises(CodeActFidesCoverageError):
        codeact.create_run_tool()
    with pytest.raises(CodeActFidesCoverageError):
        codeact.build_serializable_state()
    with pytest.raises(CodeActFidesCoverageError):
        codeact.build_instructions(tools_visible_to_model=True)
    assert not sensitive_tool_calls


async def test_concurrent_refusals_have_no_side_effects() -> None:
    codeact = MontyExecuteCodeTool(require_fides=True)
    codeact._managed_tools.append(sensitive_tool)
    results = await asyncio.gather(
        *(codeact._run_code(code="await sensitive_tool(value='private-value')") for _ in range(25)),
        return_exceptions=True,
    )
    assert all(isinstance(item, CodeActFidesCoverageError) for item in results)
    assert not sensitive_tool_calls
