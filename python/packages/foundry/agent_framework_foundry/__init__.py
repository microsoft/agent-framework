# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import FoundryAgent, FoundryAgentOptions, RawFoundryAgent, RawFoundryAgentChatClient
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
from ._tools import FoundryHostedToolType, get_toolbox_tool_name, get_toolbox_tool_type, select_toolbox_tools

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "FoundryAgent",
    "FoundryAgentOptions",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryEmbeddingClient",
    "FoundryEmbeddingOptions",
    "FoundryEmbeddingSettings",
    "FoundryEvals",
    "FoundryHostedToolType",
    "FoundryMemoryProvider",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "RawFoundryEmbeddingClient",
    "__version__",
    "evaluate_foundry_target",
    "evaluate_traces",
    "get_toolbox_tool_name",
    "get_toolbox_tool_type",
    "select_toolbox_tools",
]
