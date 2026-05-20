# Copyright (c) Microsoft. All rights reserved.

"""Hyperlight CodeAct namespace for optional Agent Framework connectors.

This module lazily re-exports objects from ``agent-framework-hyperlight``.
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "AllowedDomain": ("agent_framework_hyperlight", "agent-framework-hyperlight"),
    "AllowedDomainInput": ("agent_framework_hyperlight", "agent-framework-hyperlight"),
    "FileMount": ("agent_framework_hyperlight", "agent-framework-hyperlight"),
    "FileMountInput": ("agent_framework_hyperlight", "agent-framework-hyperlight"),
    "HyperlightCodeActProvider": ("agent_framework_hyperlight", "agent-framework-hyperlight"),
    "HyperlightExecuteCodeTool": ("agent_framework_hyperlight", "agent-framework-hyperlight"),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The package {package_name} is required to use `{name}`. "
                f"Please use `pip install {package_name}`, or update your requirements.txt or pyproject.toml file."
            ) from exc
    raise AttributeError(f"Module `hyperlight` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
