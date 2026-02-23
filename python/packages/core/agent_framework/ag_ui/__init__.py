# Copyright (c) Microsoft. All rights reserved.

"""AG-UI integration namespace for optional Agent Framework connectors.

This module lazily re-exports objects from:
- ``agent-framework-ag-ui``

Supported classes and functions:
- AgentFrameworkAgent
- AGUIChatClient
- AGUIEventConverter
- AGUIHttpService
- add_agent_framework_fastapi_endpoint
"""

import importlib
from typing import Any

IMPORT_PATH = "agent_framework_ag_ui"
PACKAGE_NAME = "agent-framework-ag-ui"
_IMPORTS = [
    "AgentFrameworkAgent",
    "AgentFrameworkWorkflow",
    "add_agent_framework_fastapi_endpoint",
    "AGUIChatClient",
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
