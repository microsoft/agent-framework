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
    FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY,
    FoundryAgent,
    FoundryAgentOptions,
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
from agent_framework_foundry_hosting import (
    AgentSessionStoreProvider,
    AgentTurn,
    CheckpointStoreProvider,
    ContextScopedStoreProvider,
    FoundryAgentSessionStore,
    FoundryCheckpointStore,
    FoundryRequestScope,
    FoundryToolbox,
    InvocationsHostServer,
    ResponsesHostServer,
    StoreProvider,
    WorkflowSource,
    WorkflowTurn,
    response_input_messages,
)
from agent_framework_foundry_hosting import (
    InvocationsWorkflowHostServer as InvocationsWorkflowHostServer,
)
from agent_framework_foundry_hosting import (
    ResponsesRequest as ResponsesRequest,
)
from agent_framework_foundry_hosting import (
    ResponsesWorkflowHostServer as ResponsesWorkflowHostServer,
)
from agent_framework_foundry_local import (
    FoundryLocalChatOptions,
    FoundryLocalClient,
    FoundryLocalSettings,
)

__all__ = [
    "FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY",
    "AgentSessionStoreProvider",
    "AgentTurn",
    "AnalysisSection",
    "AnthropicFoundryClient",
    "CheckpointStoreProvider",
    "ContentUnderstandingContextProvider",
    "ContextScopedStoreProvider",
    "DocumentStatus",
    "FileSearchBackend",
    "FileSearchConfig",
    "FoundryAgent",
    "FoundryAgentOptions",
    "FoundryAgentSessionStore",
    "FoundryChatClient",
    "FoundryChatOptions",
    "FoundryCheckpointStore",
    "FoundryEmbeddingClient",
    "FoundryEmbeddingOptions",
    "FoundryEmbeddingSettings",
    "FoundryEvals",
    "FoundryLocalChatOptions",
    "FoundryLocalClient",
    "FoundryLocalSettings",
    "FoundryMemoryProvider",
    "FoundryRequestScope",
    "FoundryToolbox",
    "GeneratedEvaluatorRef",
    "InvocationsHostServer",
    "InvocationsWorkflowHostServer",
    "RawAnthropicFoundryClient",
    "RawFoundryAgent",
    "RawFoundryAgentChatClient",
    "RawFoundryChatClient",
    "RawFoundryEmbeddingClient",
    "ResponsesHostServer",
    "ResponsesRequest",
    "ResponsesWorkflowHostServer",
    "StoreProvider",
    "WorkflowSource",
    "WorkflowTurn",
    "evaluate_foundry_target",
    "evaluate_traces",
    "response_input_messages",
    "to_prompt_agent",
]
