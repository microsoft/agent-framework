# Copyright (c) Microsoft. All rights reserved.

__version__ = "0.1.0"
__all__ = []
"""Azure Durable Agent Function App.

This package provides integration between Microsoft Agent Framework and Azure Durable Functions,
enabling durable, stateful AI agents deployed as Azure Function Apps.
"""

from ._app import AgentFunctionApp
from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._orchestration import DurableAIAgent

__all__ = [
    "AgentCallbackContext",
    "AgentFunctionApp",
    "AgentResponseCallbackProtocol",
    "DurableAIAgent",
]
