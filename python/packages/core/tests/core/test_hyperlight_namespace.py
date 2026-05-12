# Copyright (c) Microsoft. All rights reserved.

import sys
from types import ModuleType

import pytest

import agent_framework.hyperlight as hyperlight


def test_hyperlight_namespace_dir_lists_lazy_exports() -> None:
    names = dir(hyperlight)
    for expected in (
        "AllowedDomain",
        "AllowedDomainInput",
        "FileMount",
        "FileMountInput",
        "HyperlightCodeActProvider",
        "HyperlightExecuteCodeTool",
    ):
        assert expected in names


def test_hyperlight_namespace_lazy_loads_known_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_module = ModuleType("agent_framework_hyperlight")
    fake_module.HyperlightCodeActProvider = sentinel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agent_framework_hyperlight", fake_module)

    assert hyperlight.HyperlightCodeActProvider is sentinel


def test_hyperlight_namespace_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="Module `hyperlight` has no attribute DoesNotExist."):
        _ = hyperlight.DoesNotExist  # type: ignore[attr-defined]


def test_hyperlight_namespace_missing_package_raises_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "agent_framework_hyperlight", None)

    with pytest.raises(ModuleNotFoundError, match="agent-framework-hyperlight"):
        _ = hyperlight.HyperlightCodeActProvider
