# Copyright (c) Microsoft. All rights reserved.

"""agent-sandbox CodeAct namespace for optional Agent Framework connectors.

This module lazily re-exports objects from:
- ``agent-framework-agentsandbox``

Supported classes:
- AgentSandboxCodeActProvider
- AgentSandboxExecuteCodeTool
"""

import importlib
from typing import Any

IMPORT_PATH = "agent_framework_agentsandbox"
PACKAGE_NAME = "agent-framework-agentsandbox"
_IMPORTS = [
    "AgentSandboxCodeActProvider",
    "AgentSandboxExecuteCodeTool",
]


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        try:
            return getattr(importlib.import_module(IMPORT_PATH), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{PACKAGE_NAME}' package is not installed, please do `pip install {PACKAGE_NAME}`"
            ) from exc
    raise AttributeError(f"Module {IMPORT_PATH} has no attribute {name}.")


def __dir__() -> list[str]:
    return _IMPORTS
