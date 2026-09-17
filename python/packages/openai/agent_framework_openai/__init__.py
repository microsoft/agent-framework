# Copyright (c) Microsoft. All rights reserved.

"""OpenAI integration for Microsoft Agent Framework.

This package provides OpenAI client implementations for the Agent Framework,
including clients for the Responses API and Chat Completions API.
"""

import importlib.metadata
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from ._chat_client import (
        OpenAIChatClient,
        OpenAIChatOptions,
        OpenAIContinuationToken,
        RawOpenAIChatClient,
    )
    from ._chat_completion_client import (
        OpenAIChatCompletionClient,
        OpenAIChatCompletionOptions,
        OpenAIChatMessagePreparer,
        OpenAIChatResponseContentsParser,
        RawOpenAIChatCompletionClient,
    )
    from ._embedding_client import OpenAIEmbeddingClient, OpenAIEmbeddingOptions
    from ._exceptions import ContentFilterResultSeverity, OpenAIContentFilterException
    from ._shared import OpenAISettings

try:
    __version__ = importlib.metadata.version("agent-framework-openai")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

_LAZY_EXPORTS: Final[dict[str, str]] = {
    "ContentFilterResultSeverity": "._exceptions",
    "OpenAIChatClient": "._chat_client",
    "OpenAIChatCompletionClient": "._chat_completion_client",
    "OpenAIChatCompletionOptions": "._chat_completion_client",
    "OpenAIChatMessagePreparer": "._chat_completion_client",
    "OpenAIChatOptions": "._chat_client",
    "OpenAIChatResponseContentsParser": "._chat_completion_client",
    "OpenAIContentFilterException": "._exceptions",
    "OpenAIContinuationToken": "._chat_client",
    "OpenAIEmbeddingClient": "._embedding_client",
    "OpenAIEmbeddingOptions": "._embedding_client",
    "OpenAISettings": "._shared",
    "RawOpenAIChatClient": "._chat_client",
    "RawOpenAIChatCompletionClient": "._chat_completion_client",
}

__all__ = [
    "ContentFilterResultSeverity",
    "OpenAIChatClient",
    "OpenAIChatCompletionClient",
    "OpenAIChatCompletionOptions",
    "OpenAIChatMessagePreparer",
    "OpenAIChatOptions",
    "OpenAIChatResponseContentsParser",
    "OpenAIContentFilterException",
    "OpenAIContinuationToken",
    "OpenAIEmbeddingClient",
    "OpenAIEmbeddingOptions",
    "OpenAISettings",
    "RawOpenAIChatClient",
    "RawOpenAIChatCompletionClient",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve public OpenAI integration exports."""
    if module_name := _LAZY_EXPORTS.get(name):
        value = getattr(importlib.import_module(module_name, __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return public names for interactive discovery."""
    return sorted(set(globals()) | set(__all__))
