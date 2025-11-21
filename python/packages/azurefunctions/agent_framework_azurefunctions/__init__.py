# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._app import AgentFunctionApp
from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._orchestration import DurableAIAgent

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AgentCallbackContext",
    "AgentFunctionApp",
    "AgentResponseCallbackProtocol",
    "DurableAIAgent",
    "__version__",
]
