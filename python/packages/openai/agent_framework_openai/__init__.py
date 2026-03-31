# Copyright (c) Microsoft. All rights reserved.

"""OpenAI integration for Microsoft Agent Framework.

This package provides OpenAI client implementations for the Agent Framework,
including clients for the Responses API and Chat Completions API.
"""

import importlib.metadata

from ._chat_client import (
    OpenAIChatClient,
    OpenAIChatOptions,
    OpenAIContinuationToken,
    RawOpenAIChatClient,
)
from ._chat_completion_client import (
    OpenAIChatCompletionClient,
    OpenAIChatCompletionOptions,
    RawOpenAIChatCompletionClient,
)
from ._embedding_client import OpenAIEmbeddingClient, OpenAIEmbeddingOptions
from ._exceptions import ContentFilterResultSeverity, OpenAIContentFilterException
from ._shared import OpenAISettings

try:
    __version__ = importlib.metadata.version("agent-framework-openai")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "ContentFilterResultSeverity",
    "OpenAIChatClient",
    "OpenAIChatCompletionClient",
    "OpenAIChatCompletionOptions",
    "OpenAIChatOptions",
    "OpenAIContentFilterException",
    "OpenAIContinuationToken",
    "OpenAIEmbeddingClient",
    "OpenAIEmbeddingOptions",
    "OpenAISettings",
    "RawOpenAIChatClient",
    "RawOpenAIChatCompletionClient",
    "__version__",
]
