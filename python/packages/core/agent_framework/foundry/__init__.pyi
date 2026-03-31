# Copyright (c) Microsoft. All rights reserved.

# Type stubs for the agent_framework.foundry lazy-loading namespace.
# Install the relevant packages for full type support.

from agent_framework_foundry import (
    FoundryAgent,
    FoundryChatClient,
    FoundryChatOptions,
    FoundryEvals,
    FoundryMemoryProvider,
    RawFoundryAgent,
    RawFoundryAgentChatClient,
    RawFoundryChatClient,
    evaluate_foundry_target,
    evaluate_traces,
)
from agent_framework_foundry_local import (
    FoundryLocalChatOptions,
    FoundryLocalClient,
    FoundryLocalSettings,
)

__all__ = [
    "FoundryAgent",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryEvals",
    "FoundryLocalChatOptions",
    "FoundryLocalClient",
    "FoundryLocalSettings",
    "FoundryMemoryProvider",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "evaluate_foundry_target",
    "evaluate_traces",
]
