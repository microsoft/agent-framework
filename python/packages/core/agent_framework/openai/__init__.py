# Copyright (c) Microsoft. All rights reserved.

"""OpenAI namespace for built-in Agent Framework clients.

This module re-exports objects from the core OpenAI implementation modules in
``agent_framework.openai``.

Supported classes include:
- OpenAIChatClient
- OpenAIResponsesClient
- OpenAIAssistantsClient
- OpenAIAssistantProvider
"""

from ._assistant_provider import OpenAIAssistantProvider
from ._assistants_client import (
    AssistantToolResources,
    OpenAIAssistantsClient,
    OpenAIAssistantsOptions,
)
from ._chat_client import OpenAIChatClient, OpenAIChatOptions
from ._embedding_client import OpenAIEmbeddingClient, OpenAIEmbeddingOptions
from ._exceptions import ContentFilterResultSeverity, OpenAIContentFilterException
from ._responses_client import (
    OpenAIContinuationToken,
    OpenAIResponsesClient,
    OpenAIResponsesOptions,
    RawOpenAIResponsesClient,
)
from ._shared import OpenAISettings

__all__ = [
    "AssistantToolResources",
    "ContentFilterResultSeverity",
    "OpenAIAssistantProvider",
    "OpenAIAssistantsClient",
    "OpenAIAssistantsOptions",
    "OpenAIChatClient",
    "OpenAIChatOptions",
    "OpenAIContentFilterException",
    "OpenAIContinuationToken",
    "OpenAIEmbeddingClient",
    "OpenAIEmbeddingOptions",
    "OpenAIResponsesClient",
    "OpenAIResponsesOptions",
    "OpenAISettings",
    "RawOpenAIResponsesClient",
]
