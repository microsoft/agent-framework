# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "GitHubCopilotAgent": ("agent_framework_github_copilot", "agent-framework-github-copilot"),
    "GitHubCopilotOptions": ("agent_framework_github_copilot", "agent-framework-github-copilot"),
    "GitHubCopilotSettings": ("agent_framework_github_copilot", "agent-framework-github-copilot"),
    "__version__": ("agent_framework_github_copilot", "agent-framework-github-copilot"),
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
    raise AttributeError(f"Module `agent_framework.github` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
