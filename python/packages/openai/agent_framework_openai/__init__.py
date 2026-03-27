# Copyright (c) Microsoft. All rights reserved.

"""OpenAI integration for Microsoft Agent Framework.

This package provides OpenAI client implementations for the Agent Framework,
including clients for the Responses API and Chat Completions API.
"""

import importlib.metadata
import sys

if sys.version_info >= (3, 13):
    from warnings import deprecated  # type: ignore # pragma: no cover
else:
    from typing_extensions import deprecated  # type: ignore # pragma: no cover

from ._assistant_provider import OpenAIAssistantProvider
from ._assistants_client import (
    AssistantToolResources,
    OpenAIAssistantsClient,
    OpenAIAssistantsOptions,
)
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

# Deprecated aliases for old names — use subclasses so the warning only fires for the alias


@deprecated(
    "OpenAIResponsesClient is deprecated, use OpenAIChatClient instead.",
    category=DeprecationWarning,
)
class OpenAIResponsesClient(OpenAIChatClient):  # type: ignore[misc]
    """Deprecated alias for :class:`OpenAIChatClient`."""


@deprecated(
    "RawOpenAIResponsesClient is deprecated, use RawOpenAIChatClient instead.",
    category=DeprecationWarning,
)
class RawOpenAIResponsesClient(RawOpenAIChatClient):  # type: ignore[misc]
    """Deprecated alias for :class:`RawOpenAIChatClient`."""


OpenAIResponsesOptions = OpenAIChatOptions
"""Deprecated alias for :class:`OpenAIChatOptions`."""


__all__ = [
    "AssistantToolResources",
    "ContentFilterResultSeverity",
    "OpenAIAssistantProvider",
    "OpenAIAssistantsClient",
    "OpenAIAssistantsOptions",
    "OpenAIChatClient",
    "OpenAIChatCompletionClient",
    "OpenAIChatCompletionOptions",
    "OpenAIChatOptions",
    "OpenAIContentFilterException",
    "OpenAIContinuationToken",
    "OpenAIEmbeddingClient",
    "OpenAIEmbeddingOptions",
    "OpenAIResponsesClient",
    "OpenAIResponsesOptions",
    "OpenAISettings",
    "RawOpenAIChatClient",
    "RawOpenAIChatCompletionClient",
    "RawOpenAIResponsesClient",
    "__version__",
]
