# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent_provider import AzureAIAgentsProvider
from ._chat_client import AzureAIAgentClient, AzureAIAgentOptions
from ._client import AzureAIClient, AzureAIProjectAgentOptions, RawAzureAIClient
from ._embedding_client import (
    AzureAIInferenceEmbeddingClient,
    AzureAIInferenceEmbeddingOptions,
    AzureAIInferenceEmbeddingSettings,
    RawAzureAIInferenceEmbeddingClient,
)
from ._foundry_evals import (
    FoundryEvals,
    evaluate_foundry_target,
    evaluate_traces,
)
from ._foundry_memory_provider import FoundryMemoryProvider
from ._project_provider import AzureAIProjectAgentProvider
from ._shared import AzureAISettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

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
    "FoundryEvals",
    "FoundryMemoryProvider",
    "RawAzureAIClient",
    "RawAzureAIInferenceEmbeddingClient",
    "__version__",
    "evaluate_foundry_target",
    "evaluate_traces",
]
