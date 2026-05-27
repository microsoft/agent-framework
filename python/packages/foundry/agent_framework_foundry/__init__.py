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
    EvalGenerationSource,
    FoundryEvals,
    GeneratedEvaluatorRef,
    RubricDimension,
    agent_as_eval_source,
    evaluate_foundry_target,
    evaluate_traces,
    workflow_as_eval_source,
)
from ._memory_provider import FoundryMemoryProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "EvalGenerationSource",
    "FoundryAgent",
    "FoundryAgentOptions",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryEmbeddingClient",
    "FoundryEmbeddingOptions",
    "FoundryEmbeddingSettings",
    "FoundryEvals",
    "FoundryMemoryProvider",
    "GeneratedEvaluatorRef",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "RawFoundryEmbeddingClient",
    "RubricDimension",
    "__version__",
    "agent_as_eval_source",
    "evaluate_foundry_target",
    "evaluate_traces",
    "workflow_as_eval_source",
]
