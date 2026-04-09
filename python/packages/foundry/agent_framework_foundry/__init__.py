# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import FoundryAgent, RawFoundryAgent, RawFoundryAgentChatClient
from ._chat_client import FoundryChatClient, FoundryChatOptions, RawFoundryChatClient
from ._embedding_client import (
    FoundryEmbeddingClient,
    FoundryEmbeddingOptions,
    FoundryEmbeddingSettings,
    RawFoundryEmbeddingClient,
)
from ._foundry_evals import (
    FoundryEvals,
    evaluate_foundry_target,
    evaluate_traces,
)
from ._memory_provider import FoundryMemoryProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "FoundryAgent",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryEmbeddingClient",
    "FoundryEmbeddingOptions",
    "FoundryEmbeddingSettings",
    "FoundryEvals",
    "FoundryMemoryProvider",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "RawFoundryEmbeddingClient",
    "__version__",
    "evaluate_foundry_target",
    "evaluate_traces",
]
