# Copyright (c) Microsoft. All rights reserved.

"""
Core modules for Enterprise Chat Agent.

This package contains foundational components:
- cosmos_store: Azure Cosmos DB storage for thread metadata
- observability: OpenTelemetry instrumentation for tracing
- agent_service: ChatAgent with CosmosHistoryProvider and MCP integration
"""

from services.cosmos_store import CosmosConversationStore
from services.observability import (
    init_observability,
    http_request_span,
    cosmos_span,
    validation_span,
    EnterpriseAgentAttr,
)
from services.agent_service import (
    get_agent,
    get_history_provider,
    get_mcp_tool,
    close_providers,
)

__all__ = [
    "CosmosConversationStore",
    "init_observability",
    "http_request_span",
    "cosmos_span",
    "validation_span",
    "EnterpriseAgentAttr",
    "get_agent",
    "get_history_provider",
    "get_mcp_tool",
    "close_providers",
]
