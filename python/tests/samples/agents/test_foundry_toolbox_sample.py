# Copyright (c) Microsoft. All rights reserved.

"""Tests for the azure-ai-projects version guard in the Foundry toolbox sample."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SAMPLE_PATH = (
    Path(__file__).parents[3]
    / "samples"
    / "02-agents"
    / "providers"
    / "foundry"
    / "foundry_chat_client_with_toolbox.py"
)


def _load_sample_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("foundry_chat_client_with_toolbox", _SAMPLE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sample_module = _load_sample_module()


class _StopBeforeNetwork(Exception):
    pass


def _install_models_surface(monkeypatch: pytest.MonkeyPatch, exported: tuple[str, ...]) -> None:
    """Replace azure.ai.projects.models with a module exposing only the given toolbox names."""
    models = ModuleType("azure.ai.projects.models")
    for name in exported:
        setattr(models, name, type(name, (), {}))
    monkeypatch.setitem(sys.modules, "azure.ai.projects.models", models)


@pytest.mark.parametrize(
    "exported",
    [
        pytest.param((), id="azure-ai-projects-2.2"),
        pytest.param(("MCPToolboxTool", "ToolboxTool"), id="azure-ai-projects-2.3"),
    ],
)
def test_create_sample_toolbox_reports_upgrade_for_older_sdk(
    monkeypatch: pytest.MonkeyPatch, exported: tuple[str, ...]
) -> None:
    _install_models_surface(monkeypatch, exported)

    def fail_if_called() -> None:
        raise AssertionError("The version check must run before any credential is created.")

    monkeypatch.setattr(sample_module, "AzureCliCredential", fail_if_called)

    with pytest.raises(ImportError, match=r"azure-ai-projects>=2\.4\.0"):
        sample_module.create_sample_toolbox("toolbox")


def test_create_sample_toolbox_accepts_tool_search_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_models_surface(monkeypatch, ("MCPToolboxTool", "ToolboxTool", "ToolSearchToolboxTool"))

    def stop_before_network() -> None:
        raise _StopBeforeNetwork

    monkeypatch.setattr(sample_module, "AzureCliCredential", stop_before_network)

    with pytest.raises(_StopBeforeNetwork):
        sample_module.create_sample_toolbox("toolbox")
