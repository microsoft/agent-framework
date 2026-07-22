# Copyright (c) Microsoft. All rights reserved.

import sys
from types import ModuleType

import pytest

import agent_framework.tools as tools


def test_tools_namespace_dir_lists_lazy_exports() -> None:
    names = dir(tools)
    for expected in (
        "DockerShellTool",
        "LocalShellTool",
        "ShellEnvironmentProvider",
        "ShellEnvironmentProviderOptions",
        "ShellExecutor",
        "ShellPolicy",
    ):
        assert expected in names


def test_tools_namespace_lazy_loads_known_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_module = ModuleType("agent_framework_tools.shell")
    fake_module.LocalShellTool = sentinel  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "agent_framework_tools.shell", fake_module)

    assert tools.LocalShellTool is sentinel


def test_tools_namespace_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="Module `tools` has no attribute DoesNotExist."):
        _ = tools.DoesNotExist  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]


def test_tools_namespace_missing_package_raises_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "agent_framework_tools.shell", None)

    with pytest.raises(ModuleNotFoundError, match="agent-framework-tools"):
        _ = tools.LocalShellTool
