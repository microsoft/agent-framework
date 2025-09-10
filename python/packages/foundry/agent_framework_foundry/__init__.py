# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import FoundryChatClient, FoundrySettings
from ._critic_agent_executor import (
    CriticAgentExecutorRequest,
    CriticAgentExecutorResponse,
    CriticAgentPromptExecutor,
)
from ._input_guardrail_executor import (
    InputGuardrailExecutor,
)
from ._const import ReviewResult

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "FoundryChatClient",
    "FoundrySettings",
    "InputGuardrailExecutor",
    "CriticAgentExecutorRequest",
    "CriticAgentExecutorResponse",
    "CriticAgentPromptExecutor",
    "ReviewResult",
    "__version__",
]
