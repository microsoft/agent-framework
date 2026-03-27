# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent_provider import AzureAIAgentsProvider  # pyright: ignore[reportDeprecated]
from ._chat_client import AzureAIAgentClient, AzureAIAgentOptions  # pyright: ignore[reportDeprecated]
from ._client import AzureAIClient, AzureAIProjectAgentOptions, RawAzureAIClient  # pyright: ignore[reportDeprecated]
from ._deprecated_azure_openai import (
    AzureOpenAIAssistantsClient,  # pyright: ignore[reportDeprecated]
    AzureOpenAIAssistantsOptions,
    AzureOpenAIChatClient,  # pyright: ignore[reportDeprecated]
    AzureOpenAIChatOptions,
    AzureOpenAIConfigMixin,
    AzureOpenAIEmbeddingClient,  # pyright: ignore[reportDeprecated]
    AzureOpenAIResponsesClient,  # pyright: ignore[reportDeprecated]
    AzureOpenAIResponsesOptions,
    AzureOpenAISettings,
    AzureUserSecurityContext,
)
from ._embedding_client import (
    AzureAIInferenceEmbeddingClient,
    AzureAIInferenceEmbeddingOptions,
    AzureAIInferenceEmbeddingSettings,
    RawAzureAIInferenceEmbeddingClient,
)
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider
from ._project_provider import AzureAIProjectAgentProvider  # pyright: ignore[reportDeprecated]
from ._shared import AzureAISettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AzureAIAgentClient",
    "AzureAIAgentOptions",
    "AzureAIAgentsProvider",
    "AzureAIClient",
    "AzureAIInferenceEmbeddingClient",
    "AzureAIInferenceEmbeddingOptions",
    "AzureAIInferenceEmbeddingSettings",
    "AzureAIProjectAgentOptions",
    "AzureAIProjectAgentProvider",
    "AzureAISettings",
    "AzureCredentialTypes",
    "AzureOpenAIAssistantsClient",
    "AzureOpenAIAssistantsOptions",
    "AzureOpenAIChatClient",
    "AzureOpenAIChatOptions",
    "AzureOpenAIConfigMixin",
    "AzureOpenAIEmbeddingClient",
    "AzureOpenAIResponsesClient",
    "AzureOpenAIResponsesOptions",
    "AzureOpenAISettings",
    "AzureTokenProvider",
    "AzureUserSecurityContext",
    "RawAzureAIClient",
    "RawAzureAIInferenceEmbeddingClient",
    "__version__",
]
