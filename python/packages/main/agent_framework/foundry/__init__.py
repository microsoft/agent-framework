# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import TYPE_CHECKING, Any

PACKAGE_EXTRA = "foundry"

_IMPORTS = {
    "__version__": "agent_framework_foundry",
    "FoundryChatClient": "agent_framework_foundry",
}

__all__ = ["FoundryChatClient", "__version__"]


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        submod_name = _IMPORTS[name]
        try:
            module = importlib.import_module(submod_name, package=__name__)
            return getattr(module, name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The '{PACKAGE_EXTRA}' extra is not installed, "
                f"please do `pip install agent-framework[{PACKAGE_EXTRA}]`"
            ) from exc
    raise AttributeError(f"module {__name__} has no attribute {name}")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())


if TYPE_CHECKING:
    from agent_framework_foundry import (
        FoundryChatClient,
        __version__,
    )
