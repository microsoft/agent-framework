# Copyright (c) Microsoft. All rights reserved.

"""OpenAI namespace for Agent Framework clients.

This module lazily re-exports objects from the ``agent-framework-openai`` package.
Install it with: ``pip install agent-framework-openai``

Supported classes include:
- OpenAIChatClient (Responses API)
- OpenAIChatCompletionClient (Chat Completions API)
- OpenAIEmbeddingClient
- OpenAIAssistantsClient (deprecated)
"""

import importlib
from typing import Any

_IMPORTS: dict[str, tuple[str, str]] = {
    "OpenAIChatClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIChatOptions": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIContinuationToken": ("agent_framework_openai", "agent-framework-openai"),
    "RawOpenAIChatClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIChatCompletionClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIChatCompletionOptions": ("agent_framework_openai", "agent-framework-openai"),
    "RawOpenAIChatCompletionClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIEmbeddingClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIEmbeddingOptions": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAISettings": ("agent_framework_openai", "agent-framework-openai"),
    "ContentFilterResultSeverity": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIContentFilterException": ("agent_framework_openai", "agent-framework-openai"),
    "AssistantToolResources": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIAssistantProvider": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIAssistantsClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIAssistantsOptions": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIResponsesClient": ("agent_framework_openai", "agent-framework-openai"),
    "OpenAIResponsesOptions": ("agent_framework_openai", "agent-framework-openai"),
    "RawOpenAIResponsesClient": ("agent_framework_openai", "agent-framework-openai"),
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
    raise AttributeError(f"Module `openai` has no attribute {name}.")


def __dir__() -> list[str]:
    return list(_IMPORTS.keys())
