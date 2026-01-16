# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from agent_framework_durabletask import AgentCallbackContext, AgentResponseCallbackProtocol, DurableAIAgent

from ._app import AgentFunctionApp
from ._shared_state import DurableSharedState

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AgentCallbackContext",
    "AgentFunctionApp",
    "AgentResponseCallbackProtocol",
    "DurableAIAgent",
    "DurableSharedState",
    "__version__",
]
