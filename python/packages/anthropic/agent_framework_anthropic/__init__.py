# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._bedrock_client import AnthropicBedrockClient, RawAnthropicBedrockClient
from ._chat_client import AnthropicChatOptions, AnthropicClient, RawAnthropicClient
from ._foundry_client import AnthropicFoundryClient, RawAnthropicFoundryClient
from ._vertex_client import AnthropicVertexClient, RawAnthropicVertexClient

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AnthropicBedrockClient",
    "AnthropicChatOptions",
    "AnthropicClient",
    "AnthropicFoundryClient",
    "AnthropicVertexClient",
    "RawAnthropicBedrockClient",
    "RawAnthropicClient",
    "RawAnthropicFoundryClient",
    "RawAnthropicVertexClient",
    "__version__",
]
