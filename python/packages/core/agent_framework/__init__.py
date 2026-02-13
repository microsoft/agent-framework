# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata
from typing import Final

try:
    _version = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    _version = "0.0.0"  # Fallback for development mode
__version__: Final[str] = _version

from ._agents import Agent as Agent
from ._agents import BaseAgent as BaseAgent
from ._agents import RawAgent as RawAgent
from ._agents import SupportsAgentRun as SupportsAgentRun
from ._clients import (
    BaseChatClient as BaseChatClient,
)
from ._clients import (
    SupportsChatGetResponse as SupportsChatGetResponse,
)
from ._clients import (
    SupportsCodeInterpreterTool as SupportsCodeInterpreterTool,
)
from ._clients import (
    SupportsFileSearchTool as SupportsFileSearchTool,
)
from ._clients import (
    SupportsImageGenerationTool as SupportsImageGenerationTool,
)
from ._clients import (
    SupportsMCPTool as SupportsMCPTool,
)
from ._clients import (
    SupportsWebSearchTool as SupportsWebSearchTool,
)
from ._logging import get_logger as get_logger
from ._logging import setup_logging as setup_logging
from ._mcp import MCPStdioTool as MCPStdioTool
from ._mcp import MCPStreamableHTTPTool as MCPStreamableHTTPTool
from ._mcp import MCPWebsocketTool as MCPWebsocketTool
from ._middleware import (
    AgentContext as AgentContext,
)
from ._middleware import (
    AgentMiddleware as AgentMiddleware,
)
from ._middleware import (
    AgentMiddlewareLayer as AgentMiddlewareLayer,
)
from ._middleware import (
    AgentMiddlewareTypes as AgentMiddlewareTypes,
)
from ._middleware import (
    ChatAndFunctionMiddlewareTypes as ChatAndFunctionMiddlewareTypes,
)
from ._middleware import (
    ChatContext as ChatContext,
)
from ._middleware import (
    ChatMiddleware as ChatMiddleware,
)
from ._middleware import (
    ChatMiddlewareLayer as ChatMiddlewareLayer,
)
from ._middleware import (
    ChatMiddlewareTypes as ChatMiddlewareTypes,
)
from ._middleware import (
    FunctionInvocationContext as FunctionInvocationContext,
)
from ._middleware import (
    FunctionMiddleware as FunctionMiddleware,
)
from ._middleware import (
    FunctionMiddlewareTypes as FunctionMiddlewareTypes,
)
from ._middleware import (
    MiddlewareException as MiddlewareException,
)
from ._middleware import (
    MiddlewareTermination as MiddlewareTermination,
)
from ._middleware import (
    MiddlewareType as MiddlewareType,
)
from ._middleware import (
    MiddlewareTypes as MiddlewareTypes,
)
from ._middleware import (
    agent_middleware as agent_middleware,
)
from ._middleware import (
    chat_middleware as chat_middleware,
)
from ._middleware import (
    function_middleware as function_middleware,
)
from ._sessions import (
    AgentSession as AgentSession,
)
from ._sessions import (
    BaseContextProvider as BaseContextProvider,
)
from ._sessions import (
    BaseHistoryProvider as BaseHistoryProvider,
)
from ._sessions import (
    InMemoryHistoryProvider as InMemoryHistoryProvider,
)
from ._sessions import (
    SessionContext as SessionContext,
)
from ._sessions import (
    register_state_type as register_state_type,
)
from ._telemetry import (
    AGENT_FRAMEWORK_USER_AGENT as AGENT_FRAMEWORK_USER_AGENT,
)
from ._telemetry import (
    APP_INFO as APP_INFO,
)
from ._telemetry import (
    USER_AGENT_KEY as USER_AGENT_KEY,
)
from ._telemetry import (
    USER_AGENT_TELEMETRY_DISABLED_ENV_VAR as USER_AGENT_TELEMETRY_DISABLED_ENV_VAR,
)
from ._telemetry import (
    prepend_agent_framework_to_user_agent as prepend_agent_framework_to_user_agent,
)
from ._tools import (
    FunctionInvocationConfiguration as FunctionInvocationConfiguration,
)
from ._tools import (
    FunctionInvocationLayer as FunctionInvocationLayer,
)
from ._tools import (
    FunctionTool as FunctionTool,
)
from ._tools import (
    normalize_function_invocation_configuration as normalize_function_invocation_configuration,
)
from ._tools import (
    tool as tool,
)
from ._types import (
    AgentResponse as AgentResponse,
)
from ._types import (
    AgentResponseUpdate as AgentResponseUpdate,
)
from ._types import (
    Annotation as Annotation,
)
from ._types import (
    ChatOptions as ChatOptions,
)
from ._types import (
    ChatResponse as ChatResponse,
)
from ._types import (
    ChatResponseUpdate as ChatResponseUpdate,
)
from ._types import (
    Content as Content,
)
from ._types import (
    ContinuationToken as ContinuationToken,
)
from ._types import (
    FinalT as FinalT,
)
from ._types import (
    FinishReason as FinishReason,
)
from ._types import (
    FinishReasonLiteral as FinishReasonLiteral,
)
from ._types import (
    Message as Message,
)
from ._types import (
    OuterFinalT as OuterFinalT,
)
from ._types import (
    OuterUpdateT as OuterUpdateT,
)
from ._types import (
    ResponseStream as ResponseStream,
)
from ._types import (
    Role as Role,
)
from ._types import (
    RoleLiteral as RoleLiteral,
)
from ._types import (
    TextSpanRegion as TextSpanRegion,
)
from ._types import (
    ToolMode as ToolMode,
)
from ._types import (
    UpdateT as UpdateT,
)
from ._types import (
    UsageDetails as UsageDetails,
)
from ._types import (
    add_usage_details as add_usage_details,
)
from ._types import (
    detect_media_type_from_base64 as detect_media_type_from_base64,
)
from ._types import (
    map_chat_to_agent_update as map_chat_to_agent_update,
)
from ._types import (
    merge_chat_options as merge_chat_options,
)
from ._types import (
    normalize_messages as normalize_messages,
)
from ._types import (
    normalize_tools as normalize_tools,
)
from ._types import (
    prepend_instructions_to_messages as prepend_instructions_to_messages,
)
from ._types import (
    validate_chat_options as validate_chat_options,
)
from ._types import (
    validate_tool_mode as validate_tool_mode,
)
from ._types import (
    validate_tools as validate_tools,
)
from ._workflows import (
    DEFAULT_MAX_ITERATIONS as DEFAULT_MAX_ITERATIONS,
)
from ._workflows import (
    AgentExecutor as AgentExecutor,
)
from ._workflows import (
    AgentExecutorRequest as AgentExecutorRequest,
)
from ._workflows import (
    AgentExecutorResponse as AgentExecutorResponse,
)
from ._workflows import (
    Case as Case,
)
from ._workflows import (
    CheckpointStorage as CheckpointStorage,
)
from ._workflows import (
    Default as Default,
)
from ._workflows import (
    Edge as Edge,
)
from ._workflows import (
    EdgeCondition as EdgeCondition,
)
from ._workflows import (
    EdgeDuplicationError as EdgeDuplicationError,
)
from ._workflows import (
    Executor as Executor,
)
from ._workflows import (
    FanInEdgeGroup as FanInEdgeGroup,
)
from ._workflows import (
    FanOutEdgeGroup as FanOutEdgeGroup,
)
from ._workflows import (
    FileCheckpointStorage as FileCheckpointStorage,
)
from ._workflows import (
    FunctionExecutor as FunctionExecutor,
)
from ._workflows import (
    GraphConnectivityError as GraphConnectivityError,
)
from ._workflows import (
    InMemoryCheckpointStorage as InMemoryCheckpointStorage,
)
from ._workflows import (
    InProcRunnerContext as InProcRunnerContext,
)
from ._workflows import (
    Runner as Runner,
)
from ._workflows import (
    RunnerContext as RunnerContext,
)
from ._workflows import (
    SingleEdgeGroup as SingleEdgeGroup,
)
from ._workflows import (
    SubWorkflowRequestMessage as SubWorkflowRequestMessage,
)
from ._workflows import (
    SubWorkflowResponseMessage as SubWorkflowResponseMessage,
)
from ._workflows import (
    SwitchCaseEdgeGroup as SwitchCaseEdgeGroup,
)
from ._workflows import (
    SwitchCaseEdgeGroupCase as SwitchCaseEdgeGroupCase,
)
from ._workflows import (
    SwitchCaseEdgeGroupDefault as SwitchCaseEdgeGroupDefault,
)
from ._workflows import (
    TypeCompatibilityError as TypeCompatibilityError,
)
from ._workflows import (
    ValidationTypeEnum as ValidationTypeEnum,
)
from ._workflows import (
    Workflow as Workflow,
)
from ._workflows import (
    WorkflowAgent as WorkflowAgent,
)
from ._workflows import (
    WorkflowBuilder as WorkflowBuilder,
)
from ._workflows import (
    WorkflowCheckpoint as WorkflowCheckpoint,
)
from ._workflows import (
    WorkflowCheckpointException as WorkflowCheckpointException,
)
from ._workflows import (
    WorkflowContext as WorkflowContext,
)
from ._workflows import (
    WorkflowConvergenceException as WorkflowConvergenceException,
)
from ._workflows import (
    WorkflowErrorDetails as WorkflowErrorDetails,
)
from ._workflows import (
    WorkflowEvent as WorkflowEvent,
)
from ._workflows import (
    WorkflowEventSource as WorkflowEventSource,
)
from ._workflows import (
    WorkflowEventType as WorkflowEventType,
)
from ._workflows import (
    WorkflowException as WorkflowException,
)
from ._workflows import (
    WorkflowExecutor as WorkflowExecutor,
)
from ._workflows import (
    WorkflowMessage as WorkflowMessage,
)
from ._workflows import (
    WorkflowRunnerException as WorkflowRunnerException,
)
from ._workflows import (
    WorkflowRunResult as WorkflowRunResult,
)
from ._workflows import (
    WorkflowRunState as WorkflowRunState,
)
from ._workflows import (
    WorkflowValidationError as WorkflowValidationError,
)
from ._workflows import (
    WorkflowViz as WorkflowViz,
)
from ._workflows import (
    create_edge_runner as create_edge_runner,
)
from ._workflows import (
    executor as executor,
)
from ._workflows import (
    handler as handler,
)
from ._workflows import (
    resolve_agent_id as resolve_agent_id,
)
from ._workflows import (
    response_handler as response_handler,
)
from ._workflows import (
    validate_workflow_graph as validate_workflow_graph,
)
