# Copyright (c) Microsoft. All rights reserved.

"""Mistral AI namespace for optional Agent Framework connectors.

This module lazily re-exports objects from ``agent-framework-mistral``.
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "MistralEmbeddingClient": ("agent_framework_mistral", "agent-framework-mistral"),
    "MistralEmbeddingOptions": ("agent_framework_mistral", "agent-framework-mistral"),
    "MistralEmbeddingSettings": ("agent_framework_mistral", "agent-framework-mistral"),
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
    raise AttributeError(f"Module `mistral` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
