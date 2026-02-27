# Copyright (c) Microsoft. All rights reserved.

"""Public API surface for Agent Framework core.

This module exposes the primary abstractions for agents, chat clients, tools, sessions,
middleware, observability, and workflows. Connector namespaces such as
``agent_framework.azure`` and ``agent_framework.anthropic`` provide provider-specific
integrations, many of which are lazy-loaded from optional packages.
"""

import importlib.metadata
from typing import Final

try:
    _version = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    _version = "0.0.0"  # Fallback for development mode
__version__: Final[str] = _version

from ._agents import Agent, BaseAgent, RawAgent, SupportsAgentRun
from ._clients import (
    BaseChatClient,
    BaseEmbeddingClient,
    SupportsChatGetResponse,
    SupportsCodeInterpreterTool,
    SupportsFileSearchTool,
    SupportsGetEmbeddings,
    SupportsImageGenerationTool,
    SupportsMCPTool,
    SupportsWebSearchTool,
)
from ._mcp import MCPStdioTool, MCPStreamableHTTPTool, MCPWebsocketTool
from ._middleware import (
    AgentContext,
    AgentMiddleware,
    AgentMiddlewareLayer,
    AgentMiddlewareTypes,
    ChatAndFunctionMiddlewareTypes,
    ChatContext,
    ChatMiddleware,
    ChatMiddlewareLayer,
    ChatMiddlewareTypes,
    FunctionInvocationContext,
    FunctionMiddleware,
    FunctionMiddlewareTypes,
    MiddlewareTermination,
    MiddlewareType,
    MiddlewareTypes,
    agent_middleware,
    chat_middleware,
    function_middleware,
)
from ._sessions import (
    AgentSession,
    BaseContextProvider,
    BaseHistoryProvider,
    InMemoryHistoryProvider,
    SessionContext,
    register_state_type,
)
from ._settings import SecretString, load_settings
from ._skills import FileAgentSkillsProvider
from ._telemetry import (
    AGENT_FRAMEWORK_USER_AGENT,
    APP_INFO,
    USER_AGENT_KEY,
    USER_AGENT_TELEMETRY_DISABLED_ENV_VAR,
    prepend_agent_framework_to_user_agent,
)
from ._tools import (
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    ToolTypes,
    normalize_function_invocation_configuration,
    tool,
)
from ._types import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    Annotation,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ContinuationToken,
    Embedding,
    EmbeddingGenerationOptions,
    EmbeddingInputT,
    EmbeddingT,
    FinalT,
    FinishReason,
    FinishReasonLiteral,
    GeneratedEmbeddings,
    Message,
    OuterFinalT,
    OuterUpdateT,
    ResponseStream,
    Role,
    RoleLiteral,
    TextSpanRegion,
    ToolMode,
    UpdateT,
    UsageDetails,
    add_usage_details,
    detect_media_type_from_base64,
    map_chat_to_agent_update,
    merge_chat_options,
    normalize_messages,
    normalize_tools,
    prepend_instructions_to_messages,
    validate_chat_options,
    validate_tool_mode,
    validate_tools,
)
from ._workflows._agent import WorkflowAgent
from ._workflows._agent_executor import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
)
from ._workflows._agent_utils import resolve_agent_id
from ._workflows._checkpoint import (
    CheckpointStorage,
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    WorkflowCheckpoint,
)
from ._workflows._const import (
    DEFAULT_MAX_ITERATIONS,
)
from ._workflows._edge import (
    Case,
    Default,
    Edge,
    EdgeCondition,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from ._workflows._edge_runner import create_edge_runner
from ._workflows._events import (
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowEventSource,
    WorkflowEventType,
    WorkflowRunState,
)
from ._workflows._executor import (
    Executor,
    handler,
)
from ._workflows._function_executor import FunctionExecutor, executor
from ._workflows._request_info_mixin import response_handler
from ._workflows._runner import Runner
from ._workflows._runner_context import (
    InProcRunnerContext,
    RunnerContext,
    WorkflowMessage,
)
from ._workflows._validation import (
    EdgeDuplicationError,
    GraphConnectivityError,
    TypeCompatibilityError,
    ValidationTypeEnum,
    WorkflowValidationError,
    validate_workflow_graph,
)
from ._workflows._viz import WorkflowViz
from ._workflows._workflow import Workflow, WorkflowRunResult
from ._workflows._workflow_builder import WorkflowBuilder
from ._workflows._workflow_context import WorkflowContext
from ._workflows._workflow_executor import (
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    WorkflowExecutor,
)
from .exceptions import (
    MiddlewareException,
    WorkflowCheckpointException,
    WorkflowConvergenceException,
    WorkflowException,
    WorkflowRunnerException,
)

__all__ = [
    "AGENT_FRAMEWORK_USER_AGENT",
    "APP_INFO",
    "DEFAULT_MAX_ITERATIONS",
    "USER_AGENT_KEY",
    "USER_AGENT_TELEMETRY_DISABLED_ENV_VAR",
    "Agent",
    "AgentContext",
    "AgentExecutor",
    "AgentExecutorRequest",
    "AgentExecutorResponse",
    "AgentMiddleware",
    "AgentMiddlewareLayer",
    "AgentMiddlewareTypes",
    "AgentResponse",
    "AgentResponseUpdate",
    "AgentRunInputs",
    "AgentSession",
    "Annotation",
    "BaseAgent",
    "BaseChatClient",
    "BaseContextProvider",
    "BaseEmbeddingClient",
    "BaseHistoryProvider",
    "Case",
    "ChatAndFunctionMiddlewareTypes",
    "ChatContext",
    "ChatMiddleware",
    "ChatMiddlewareLayer",
    "ChatMiddlewareTypes",
    "ChatOptions",
    "ChatResponse",
    "ChatResponseUpdate",
    "CheckpointStorage",
    "Content",
    "ContinuationToken",
    "Default",
    "Edge",
    "EdgeCondition",
    "EdgeDuplicationError",
    "Embedding",
    "EmbeddingGenerationOptions",
    "EmbeddingInputT",
    "EmbeddingT",
    "Executor",
    "FanInEdgeGroup",
    "FanOutEdgeGroup",
    "FileAgentSkillsProvider",
    "FileCheckpointStorage",
    "FinalT",
    "FinishReason",
    "FinishReasonLiteral",
    "FunctionExecutor",
    "FunctionInvocationConfiguration",
    "FunctionInvocationContext",
    "FunctionInvocationLayer",
    "FunctionMiddleware",
    "FunctionMiddlewareTypes",
    "FunctionTool",
    "GeneratedEmbeddings",
    "GraphConnectivityError",
    "InMemoryCheckpointStorage",
    "InMemoryHistoryProvider",
    "InProcRunnerContext",
    "MCPStdioTool",
    "MCPStreamableHTTPTool",
    "MCPWebsocketTool",
    "Message",
    "MiddlewareException",
    "MiddlewareTermination",
    "MiddlewareType",
    "MiddlewareTypes",
    "OuterFinalT",
    "OuterUpdateT",
    "RawAgent",
    "ResponseStream",
    "Role",
    "RoleLiteral",
    "Runner",
    "RunnerContext",
    "SecretString",
    "SessionContext",
    "SingleEdgeGroup",
    "SubWorkflowRequestMessage",
    "SubWorkflowResponseMessage",
    "SupportsAgentRun",
    "SupportsChatGetResponse",
    "SupportsCodeInterpreterTool",
    "SupportsFileSearchTool",
    "SupportsGetEmbeddings",
    "SupportsImageGenerationTool",
    "SupportsMCPTool",
    "SupportsWebSearchTool",
    "SwitchCaseEdgeGroup",
    "SwitchCaseEdgeGroupCase",
    "SwitchCaseEdgeGroupDefault",
    "TextSpanRegion",
    "ToolMode",
    "ToolTypes",
    "TypeCompatibilityError",
    "UpdateT",
    "UsageDetails",
    "ValidationTypeEnum",
    "Workflow",
    "WorkflowAgent",
    "WorkflowBuilder",
    "WorkflowCheckpoint",
    "WorkflowCheckpointException",
    "WorkflowContext",
    "WorkflowConvergenceException",
    "WorkflowErrorDetails",
    "WorkflowEvent",
    "WorkflowEventSource",
    "WorkflowEventType",
    "WorkflowException",
    "WorkflowExecutor",
    "WorkflowMessage",
    "WorkflowRunResult",
    "WorkflowRunState",
    "WorkflowRunnerException",
    "WorkflowValidationError",
    "WorkflowViz",
    "__version__",
    "add_usage_details",
    "agent_middleware",
    "chat_middleware",
    "create_edge_runner",
    "detect_media_type_from_base64",
    "executor",
    "function_middleware",
    "handler",
    "load_settings",
    "map_chat_to_agent_update",
    "merge_chat_options",
    "normalize_function_invocation_configuration",
    "normalize_messages",
    "normalize_tools",
    "prepend_agent_framework_to_user_agent",
    "prepend_instructions_to_messages",
    "register_state_type",
    "resolve_agent_id",
    "response_handler",
    "tool",
    "validate_chat_options",
    "validate_tool_mode",
    "validate_tools",
    "validate_workflow_graph",
]
