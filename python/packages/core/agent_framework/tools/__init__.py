# Copyright (c) Microsoft. All rights reserved.

"""Built-in tools namespace for optional Agent Framework connectors.

This module lazily re-exports objects from ``agent-framework-tools``.
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "DOCKER_DEFAULT_IMAGE": ("agent_framework_tools.shell", "agent-framework-tools"),
    "DockerNotAvailableError": ("agent_framework_tools.shell", "agent-framework-tools"),
    "DockerShellTool": ("agent_framework_tools.shell", "agent-framework-tools"),
    "LocalShellTool": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellCommandError": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellDecision": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellEnvironmentProvider": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellEnvironmentProviderOptions": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellEnvironmentSnapshot": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellExecutionError": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellExecutor": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellFamily": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellMode": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellPolicy": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellRequest": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellResult": ("agent_framework_tools.shell", "agent-framework-tools"),
    "ShellTimeoutError": ("agent_framework_tools.shell", "agent-framework-tools"),
    "default_instructions_formatter": ("agent_framework_tools.shell", "agent-framework-tools"),
    "is_docker_available": ("agent_framework_tools.shell", "agent-framework-tools"),
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
    raise AttributeError(f"Module `tools` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
