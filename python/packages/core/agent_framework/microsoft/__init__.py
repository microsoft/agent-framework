# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, list[str]]] = {
    "CopilotStudioAgent": ("agent_framework_copilotstudio", ["microsoft-copilotstudio", "copilotstudio"]),
    "__version__": ("agent_framework_copilotstudio", ["microsoft-copilotstudio", "copilotstudio"]),
    "acquire_token": ("agent_framework_copilotstudio", ["microsoft-copilotstudio", "copilotstudio"]),
    # Purview (Graph Data Security & Governance) integration exports
    "PurviewPolicyMiddleware": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewChatPolicyMiddleware": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewSettings": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewAppLocation": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewLocationType": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewAuthenticationError": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewRateLimitError": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewRequestError": ("agent_framework_purview", ["microsoft-purview", "purview"]),
    "PurviewServiceError": ("agent_framework_purview", ["microsoft-purview", "purview"]),
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
    raise AttributeError(f"Module `microsoft` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
