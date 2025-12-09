# Copyright (c) Microsoft. All rights reserved.

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "CopilotStudioAgent": ("agent_framework_copilotstudio", "agent-framework-copilotstudio"),
    "__version__": ("agent_framework_copilotstudio", "agent-framework-copilotstudio"),
    "acquire_token": ("agent_framework_copilotstudio", "agent-framework-copilotstudio"),
    "PurviewPolicyMiddleware": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewChatPolicyMiddleware": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewSettings": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewAppLocation": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewLocationType": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewAuthenticationError": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewPaymentRequiredError": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewRateLimitError": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewRequestError": ("agent_framework_purview", "agent-framework-purview"),
    "PurviewServiceError": ("agent_framework_purview", "agent-framework-purview"),
    "CacheProvider": ("agent_framework_purview", "agent-framework-purview"),
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
    raise AttributeError(f"Module `microsoft` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
