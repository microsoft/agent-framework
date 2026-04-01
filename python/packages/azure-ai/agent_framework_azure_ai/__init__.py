# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._embedding_client import (
    AzureAIInferenceEmbeddingClient,
    AzureAIInferenceEmbeddingOptions,
    AzureAIInferenceEmbeddingSettings,
    RawAzureAIInferenceEmbeddingClient,
)
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider
from ._shared import AzureAISettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AzureAIInferenceEmbeddingClient",
    "AzureAIInferenceEmbeddingOptions",
    "AzureAIInferenceEmbeddingSettings",
    "AzureAISettings",
    "AzureCredentialTypes",
    "AzureTokenProvider",
    "RawAzureAIInferenceEmbeddingClient",
    "__version__",
]
