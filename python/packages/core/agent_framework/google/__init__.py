# Copyright (c) Microsoft. All rights reserved.

"""Google integration namespace for optional Agent Framework connectors.

This module lazily re-exports Google-hosted Anthropic clients from:
- ``agent-framework-anthropic``

Supported classes:
- AnthropicVertexClient
- RawAnthropicVertexClient
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "AnthropicVertexClient": ("agent_framework_anthropic", "agent-framework-anthropic"),
    "RawAnthropicVertexClient": ("agent_framework_anthropic", "agent-framework-anthropic"),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{package_name}' package is not installed, please do `pip install {package_name}`"
            ) from exc
    raise AttributeError(f"Module `google` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
