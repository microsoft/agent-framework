# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

PACKAGE_NAME = "agent_framework_copilotstudio"
PACKAGE_EXTRA = ["microsoft-copilotstudio", "copilotstudio"]
_IMPORTS: dict[str, tuple[str, list[str]]] = {
    "CopilotStudioAgent": ("agent_framework_copilotstudio", ["microsoft-copilotstudio", "copilotstudio"]),
    "__version__": ("agent_framework_copilotstudio", ["microsoft-copilotstudio", "copilotstudio"]),
    "acquire_token": ("agent_framework_copilotstudio", ["microsoft-copilotstudio", "copilotstudio"]),
}


def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        package_name, package_extra = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(package_name), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The {' or '.join(package_extra)} extra is not installed, "
                f"please use `pip install agent-framework-{package_extra[0]}`, "
                "or update your requirements.txt or pyproject.toml file."
            ) from exc
    raise AttributeError(f"Module `azure` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
