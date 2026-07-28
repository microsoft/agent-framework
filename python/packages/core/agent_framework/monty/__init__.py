# Copyright (c) Microsoft. All rights reserved.

"""Monty CodeAct namespace for optional Agent Framework connectors.

This module lazily re-exports objects from ``agent-framework-monty``.
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "FileMount": ("agent_framework_monty", "agent-framework-monty"),
    "FileMountInput": ("agent_framework_monty", "agent-framework-monty"),
    "MontyCodeActProvider": ("agent_framework_monty", "agent-framework-monty"),
    "MontyExecuteCodeTool": ("agent_framework_monty", "agent-framework-monty"),
    "MountMode": ("agent_framework_monty", "agent-framework-monty"),
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
    raise AttributeError(f"Module `monty` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
