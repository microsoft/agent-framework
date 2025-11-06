# Copyright (c) Microsoft. All rights reserved.
"""Azure Durable Agent Function App.

This package provides integration between Microsoft Agent Framework and Azure Durable Functions,
enabling durable, stateful AI agents deployed as Azure Function Apps.
"""

from ._app import AgentFunctionApp
from ._callbacks import AgentCallbackContext, AgentResponseCallbackProtocol
from ._orchestration import DurableAIAgent, get_agent

__all__ = [
    "AgentCallbackContext",
    "AgentFunctionApp",
    "AgentResponseCallbackProtocol",
    "DurableAIAgent",
    "get_agent",
]
