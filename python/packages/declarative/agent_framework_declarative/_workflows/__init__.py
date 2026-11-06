# Copyright (c) Microsoft. All rights reserved.

"""Declarative workflow support for agent-framework.

This module provides the ability to create executable Workflow objects from YAML definitions,
enabling multi-agent orchestration patterns like Foreach, conditionals, and agent invocations.

Graph-based execution enables:
- Checkpointing at action boundaries
- Workflow visualization
- Pause/resume capabilities
- Full integration with the workflow runtime
"""

from agent_framework import register_checkpoint_type

from ._declarative_base import (
    DECLARATIVE_STATE_KEY,
    ActionComplete,
    ActionTrigger,
    ConditionResult,
    ConversationData,
    DeclarativeActionExecutor,
    DeclarativeMessage,
    DeclarativeStateData,
    DeclarativeWorkflowState,
    LoopControl,
    LoopIterationResult,
)
from ._declarative_builder import ALL_ACTION_EXECUTORS, DeclarativeWorkflowBuilder
from ._errors import DeclarativeActionError, DeclarativeWorkflowError
from ._executors_agents import (
    AGENT_ACTION_EXECUTORS,
    AGENT_REGISTRY_KEY,
    TOOL_REGISTRY_KEY,
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    AgentResult,
    ExternalLoopState,
    InvokeAzureAgentExecutor,
)
from ._executors_basic import (
    BASIC_ACTION_EXECUTORS,
    ClearAllVariablesExecutor,
    CreateConversationExecutor,
    ResetVariableExecutor,
    SendActivityExecutor,
    SetMultipleVariablesExecutor,
    SetTextVariableExecutor,
    SetValueExecutor,
    SetVariableExecutor,
)
from ._executors_control_flow import (
    CONTROL_FLOW_EXECUTORS,
    BreakLoopExecutor,
    ContinueLoopExecutor,
    EndConversationExecutor,
    EndWorkflowExecutor,
    ForeachInitExecutor,
    ForeachNextExecutor,
    JoinExecutor,
)
from ._executors_external_input import (
    EXTERNAL_INPUT_EXECUTORS,
    ExternalInputRequest,
    ExternalInputResponse,
    QuestionExecutor,
    RequestExternalInputExecutor,
)
from ._executors_http import (
    HTTP_ACTION_EXECUTORS,
    HttpRequestActionExecutor,
)
from ._executors_mcp import (
    MCP_ACTION_EXECUTORS,
    InvokeMcpToolActionExecutor,
    MCPToolApprovalRequest,
)
from ._executors_tools import (
    FUNCTION_TOOL_REGISTRY_KEY,
    TOOL_ACTION_EXECUTORS,
    BaseToolExecutor,
    InvokeFunctionToolExecutor,
    ToolApprovalRequest,
    ToolApprovalResponse,
    ToolInvocationResult,
)
from ._factory import WorkflowFactory
from ._http_handler import (
    DefaultHttpRequestHandler,
    HttpRequestHandler,
    HttpRequestInfo,
    HttpRequestResult,
)
from ._mcp_handler import (
    DefaultMCPToolHandler,
    MCPToolHandler,
    MCPToolInvocation,
    MCPToolResult,
)
from ._state import WorkflowState

# Framework-owned types that cross a checkpoint boundary.
#
# Checkpoint restore runs pickle through a restricted unpickler whose default allowlist
# trusts ``agent_framework.`` and ``agent_framework_orchestrations.`` but not this
# distribution, so these types opt in by name, as the orchestrations package does.
# Without this, ``FileCheckpointStorage`` cannot save any checkpoint taken after the
# first action, and a paused workflow cannot be resumed from storage.
for _checkpoint_type in (
    # Executor-to-executor message envelopes (``DeclarativeMessage``).
    ActionTrigger,
    ActionComplete,
    ConditionResult,
    LoopIterationResult,
    LoopControl,
    # ``request_info`` payloads and their response types, checkpointed as pending
    # requests while a workflow waits for input or approval.
    ExternalInputRequest,
    ExternalInputResponse,
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    ToolApprovalRequest,
    ToolApprovalResponse,
    MCPToolApprovalRequest,
    # Stored in workflow state while an agent's external input loop is paused.
    ExternalLoopState,
):
    register_checkpoint_type(_checkpoint_type)

del _checkpoint_type

__all__ = [
    "AGENT_ACTION_EXECUTORS",
    "AGENT_REGISTRY_KEY",
    "ALL_ACTION_EXECUTORS",
    "BASIC_ACTION_EXECUTORS",
    "CONTROL_FLOW_EXECUTORS",
    "DECLARATIVE_STATE_KEY",
    "EXTERNAL_INPUT_EXECUTORS",
    "FUNCTION_TOOL_REGISTRY_KEY",
    "HTTP_ACTION_EXECUTORS",
    "MCP_ACTION_EXECUTORS",
    "TOOL_ACTION_EXECUTORS",
    "TOOL_REGISTRY_KEY",
    "ActionComplete",
    "ActionTrigger",
    "AgentExternalInputRequest",
    "AgentExternalInputResponse",
    "AgentResult",
    "BaseToolExecutor",
    "BreakLoopExecutor",
    "ClearAllVariablesExecutor",
    "ContinueLoopExecutor",
    "ConversationData",
    "CreateConversationExecutor",
    "DeclarativeActionError",
    "DeclarativeActionExecutor",
    "DeclarativeMessage",
    "DeclarativeStateData",
    "DeclarativeWorkflowBuilder",
    "DeclarativeWorkflowError",
    "DeclarativeWorkflowState",
    "DefaultHttpRequestHandler",
    "DefaultMCPToolHandler",
    "EndConversationExecutor",
    "EndWorkflowExecutor",
    "ExternalInputRequest",
    "ExternalInputResponse",
    "ExternalLoopState",
    "ForeachInitExecutor",
    "ForeachNextExecutor",
    "HttpRequestActionExecutor",
    "HttpRequestHandler",
    "HttpRequestInfo",
    "HttpRequestResult",
    "InvokeAzureAgentExecutor",
    "InvokeFunctionToolExecutor",
    "InvokeMcpToolActionExecutor",
    "JoinExecutor",
    "LoopControl",
    "LoopIterationResult",
    "MCPToolApprovalRequest",
    "MCPToolHandler",
    "MCPToolInvocation",
    "MCPToolResult",
    "QuestionExecutor",
    "RequestExternalInputExecutor",
    "ResetVariableExecutor",
    "SendActivityExecutor",
    "SetMultipleVariablesExecutor",
    "SetTextVariableExecutor",
    "SetValueExecutor",
    "SetVariableExecutor",
    "ToolApprovalRequest",
    "ToolApprovalResponse",
    "ToolInvocationResult",
    "WorkflowFactory",
    "WorkflowState",
]
