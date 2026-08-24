# Copyright (c) Microsoft. All rights reserved.

import sys
from types import ModuleType

import pytest

import agent_framework.monty as monty


def test_monty_namespace_dir_lists_lazy_exports() -> None:
    names = dir(monty)
    for expected in (
        "FileMount",
        "FileMountInput",
        "MontyCodeActProvider",
        "MontyExecuteCodeTool",
        "MountMode",
    ):
        assert expected in names


def test_monty_namespace_lazy_loads_known_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_module = ModuleType("agent_framework_monty")
    fake_module.MontyCodeActProvider = sentinel  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "agent_framework_monty", fake_module)

    assert monty.MontyCodeActProvider is sentinel


def test_monty_namespace_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="Module `monty` has no attribute DoesNotExist."):
        _ = monty.DoesNotExist  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]


def test_monty_namespace_missing_package_raises_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "agent_framework_monty", None)

    with pytest.raises(ModuleNotFoundError, match="agent-framework-monty"):
        _ = monty.MontyCodeActProvider
