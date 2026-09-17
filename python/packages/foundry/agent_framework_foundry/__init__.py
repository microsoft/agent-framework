# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from ._agent import (
        FoundryAgent,
        FoundryAgentOptions,
        RawFoundryAgent,
        RawFoundryAgentChatClient,
    )
    from ._chat_client import FoundryChatClient, FoundryChatOptions, RawFoundryChatClient
    from ._constants import FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY
    from ._embedding_client import (
        FoundryEmbeddingClient,
        FoundryEmbeddingOptions,
        FoundryEmbeddingSettings,
        RawFoundryEmbeddingClient,
    )
    from ._foundry_evals import (
        FoundryEvals,
        GeneratedEvaluatorRef,
        evaluate_foundry_target,
        evaluate_traces,
    )
    from ._memory_provider import FoundryMemoryProvider
    from ._to_prompt_agent import to_prompt_agent

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

_LAZY_EXPORTS: Final[dict[str, str]] = {
    "FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY": "._constants",
    "FoundryAgent": "._agent",
    "FoundryAgentOptions": "._agent",
    "FoundryChatClient": "._chat_client",
    "FoundryChatOptions": "._chat_client",
    "FoundryEmbeddingClient": "._embedding_client",
    "FoundryEmbeddingOptions": "._embedding_client",
    "FoundryEmbeddingSettings": "._embedding_client",
    "FoundryEvals": "._foundry_evals",
    "FoundryMemoryProvider": "._memory_provider",
    "GeneratedEvaluatorRef": "._foundry_evals",
    "RawFoundryAgent": "._agent",
    "RawFoundryAgentChatClient": "._agent",
    "RawFoundryChatClient": "._chat_client",
    "RawFoundryEmbeddingClient": "._embedding_client",
    "evaluate_foundry_target": "._foundry_evals",
    "evaluate_traces": "._foundry_evals",
    "to_prompt_agent": "._to_prompt_agent",
}

__all__ = [
    "FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY",
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
    "__version__",
    "evaluate_foundry_target",
    "evaluate_traces",
    "to_prompt_agent",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve public Foundry exports."""
    if module_name := _LAZY_EXPORTS.get(name):
        value = getattr(importlib.import_module(module_name, __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return public names for interactive discovery."""
    return sorted(set(globals()) | set(__all__))
