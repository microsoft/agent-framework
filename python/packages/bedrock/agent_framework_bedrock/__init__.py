# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import BedrockChatClient, BedrockChatOptions, BedrockGuardrailConfig, BedrockSettings
from ._embedding_client import BedrockEmbeddingClient, BedrockEmbeddingOptions, BedrockEmbeddingSettings
from ._knowledge_base import BedrockKnowledgeBaseTool
from ._knowledge_base_provider import BedrockKnowledgeBaseProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "BedrockChatClient",
    "BedrockChatOptions",
    "BedrockEmbeddingClient",
    "BedrockEmbeddingOptions",
    "BedrockEmbeddingSettings",
    "BedrockGuardrailConfig",
    "BedrockSettings",
    "BedrockKnowledgeBaseTool",
    "BedrockKnowledgeBaseProvider",
    "__version__",
]
