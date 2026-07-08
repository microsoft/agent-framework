# Copyright (c) Microsoft. All rights reserved.

# Type stubs for the agent_framework.foundry lazy-loading namespace.
# Install the relevant packages for full type support.

from agent_framework_anthropic import AnthropicFoundryClient, RawAnthropicFoundryClient
from agent_framework_azure_contentunderstanding import (
    AnalysisSection,
    ContentUnderstandingContextProvider,
    DocumentStatus,
    FileSearchBackend,
    FileSearchConfig,
)
from agent_framework_foundry import (
    FoundryAgent,
    FoundryChatClient,
    FoundryChatOptions,
    FoundryEmbeddingClient,
    FoundryEmbeddingOptions,
    FoundryEmbeddingSettings,
    FoundryEvals,
    FoundryMemoryProvider,
    GeneratedEvaluatorRef,
    RawFoundryAgent,
    RawFoundryAgentChatClient,
    RawFoundryChatClient,
    RawFoundryEmbeddingClient,
    evaluate_foundry_target,
    evaluate_traces,
    to_prompt_agent,
)
from agent_framework_foundry_local import (
    FoundryLocalChatOptions,
    FoundryLocalClient,
    FoundryLocalSettings,
)

__all__ = [
    "AnalysisSection",
    "AnthropicFoundryClient",
    "ContentUnderstandingContextProvider",
    "DocumentStatus",
    "FileSearchBackend",
    "FileSearchConfig",
    "FoundryAgent",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryEmbeddingClient",
    "FoundryEmbeddingOptions",
    "FoundryEmbeddingSettings",
    "FoundryEvals",
    "FoundryLocalChatOptions",
    "FoundryLocalClient",
    "FoundryLocalSettings",
    "FoundryMemoryProvider",
    "GeneratedEvaluatorRef",
    "RawAnthropicFoundryClient",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "RawFoundryEmbeddingClient",
    "evaluate_foundry_target",
    "evaluate_traces",
    "to_prompt_agent",
]
