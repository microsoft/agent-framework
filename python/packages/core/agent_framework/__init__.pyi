# Copyright (c) Microsoft. All rights reserved.

from typing import Final

__version__: Final[str]

from ._agents import Agent as Agent
from ._agents import BaseAgent as BaseAgent
from ._agents import RawAgent as RawAgent
from ._agents import SupportsAgentRun as SupportsAgentRun
from ._clients import (
    BaseChatClient as BaseChatClient,
)
from ._clients import (
    BaseEmbeddingClient as BaseEmbeddingClient,
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
    SupportsGetEmbeddings as SupportsGetEmbeddings,
)
from ._clients import (
    SupportsImageGenerationTool as SupportsImageGenerationTool,
)
from ._clients import (
    SupportsMCPTool as SupportsMCPTool,
)
from ._clients import (
    SupportsShellTool as SupportsShellTool,
)
from ._clients import (
    SupportsWebSearchTool as SupportsWebSearchTool,
)
from ._compaction import (
    COMPACTION_STATE_KEY as COMPACTION_STATE_KEY,
)
from ._compaction import (
    EXCLUDE_REASON_KEY as EXCLUDE_REASON_KEY,
)
from ._compaction import (
    EXCLUDED_KEY as EXCLUDED_KEY,
)
from ._compaction import (
    GROUP_ANNOTATION_KEY as GROUP_ANNOTATION_KEY,
)
from ._compaction import (
    GROUP_HAS_REASONING_KEY as GROUP_HAS_REASONING_KEY,
)
from ._compaction import (
    GROUP_ID_KEY as GROUP_ID_KEY,
)
from ._compaction import (
    GROUP_INDEX_KEY as GROUP_INDEX_KEY,
)
from ._compaction import (
    GROUP_KIND_KEY as GROUP_KIND_KEY,
)
from ._compaction import (
    GROUP_TOKEN_COUNT_KEY as GROUP_TOKEN_COUNT_KEY,
)
from ._compaction import (
    SUMMARIZED_BY_SUMMARY_ID_KEY as SUMMARIZED_BY_SUMMARY_ID_KEY,
)
from ._compaction import (
    SUMMARY_OF_GROUP_IDS_KEY as SUMMARY_OF_GROUP_IDS_KEY,
)
from ._compaction import (
    SUMMARY_OF_MESSAGE_IDS_KEY as SUMMARY_OF_MESSAGE_IDS_KEY,
)
from ._compaction import (
    CharacterEstimatorTokenizer as CharacterEstimatorTokenizer,
)
from ._compaction import (
    CompactionProvider as CompactionProvider,
)
from ._compaction import (
    CompactionStrategy as CompactionStrategy,
)
from ._compaction import (
    ContextWindowCompactionStrategy as ContextWindowCompactionStrategy,
)
from ._compaction import (
    SelectiveToolCallCompactionStrategy as SelectiveToolCallCompactionStrategy,
)
from ._compaction import (
    SlidingWindowStrategy as SlidingWindowStrategy,
)
from ._compaction import (
    SummarizationStrategy as SummarizationStrategy,
)
from ._compaction import (
    TokenBudgetComposedStrategy as TokenBudgetComposedStrategy,
)
from ._compaction import (
    TokenizerProtocol as TokenizerProtocol,
)
from ._compaction import (
    ToolResultCompactionStrategy as ToolResultCompactionStrategy,
)
from ._compaction import (
    TruncationStrategy as TruncationStrategy,
)
from ._compaction import (
    annotate_message_groups as annotate_message_groups,
)
from ._compaction import (
    apply_compaction as apply_compaction,
)
from ._compaction import (
    included_messages as included_messages,
)
from ._compaction import (
    included_token_count as included_token_count,
)
from ._evaluation import (
    AgentEvalConverter as AgentEvalConverter,
)
from ._evaluation import (
    CheckResult as CheckResult,
)
from ._evaluation import (
    ConversationSplit as ConversationSplit,
)
from ._evaluation import (
    ConversationSplitter as ConversationSplitter,
)
from ._evaluation import (
    EvalItem as EvalItem,
)
from ._evaluation import (
    EvalItemResult as EvalItemResult,
)
from ._evaluation import (
    EvalNotPassedError as EvalNotPassedError,
)
from ._evaluation import (
    EvalResults as EvalResults,
)
from ._evaluation import (
    EvalScoreResult as EvalScoreResult,
)
from ._evaluation import (
    Evaluator as Evaluator,
)
from ._evaluation import (
    ExpectedToolCall as ExpectedToolCall,
)
from ._evaluation import (
    LocalEvaluator as LocalEvaluator,
)
from ._evaluation import (
    RubricScore as RubricScore,
)
from ._evaluation import (
    evaluate_agent as evaluate_agent,
)
from ._evaluation import (
    evaluate_workflow as evaluate_workflow,
)
from ._evaluation import (
    evaluator as evaluator,
)
from ._evaluation import (
    keyword_check as keyword_check,
)
from ._evaluation import (
    tool_call_args_match as tool_call_args_match,
)
from ._evaluation import (
    tool_called_check as tool_called_check,
)
from ._evaluation import (
    tool_calls_present as tool_calls_present,
)
from ._feature_stage import (
    ExperimentalFeature as ExperimentalFeature,
)
from ._feature_stage import (
    ReleaseCandidateFeature as ReleaseCandidateFeature,
)
from ._harness._agent import (
    DEFAULT_HARNESS_INSTRUCTIONS as DEFAULT_HARNESS_INSTRUCTIONS,
)
from ._harness._agent import (
    create_harness_agent as create_harness_agent,
)
from ._harness._background_agents import (
    DEFAULT_BACKGROUND_AGENTS_SOURCE_ID as DEFAULT_BACKGROUND_AGENTS_SOURCE_ID,
)
from ._harness._background_agents import (
    BackgroundAgentsProvider as BackgroundAgentsProvider,
)
from ._harness._background_agents import (
    BackgroundTaskInfo as BackgroundTaskInfo,
)
from ._harness._background_agents import (
    BackgroundTaskStatus as BackgroundTaskStatus,
)
from ._harness._file_access import (
    DEFAULT_FILE_ACCESS_INSTRUCTIONS as DEFAULT_FILE_ACCESS_INSTRUCTIONS,
)
from ._harness._file_access import (
    DEFAULT_FILE_ACCESS_SOURCE_ID as DEFAULT_FILE_ACCESS_SOURCE_ID,
)
from ._harness._file_access import (
    AgentFileStore as AgentFileStore,
)
from ._harness._file_access import (
    FileAccessProvider as FileAccessProvider,
)
from ._harness._file_access import (
    FileSearchMatch as FileSearchMatch,
)
from ._harness._file_access import (
    FileSearchResult as FileSearchResult,
)
from ._harness._file_access import (
    FileSystemAgentFileStore as FileSystemAgentFileStore,
)
from ._harness._file_access import (
    InMemoryAgentFileStore as InMemoryAgentFileStore,
)
from ._harness._file_memory import (
    DEFAULT_FILE_MEMORY_INSTRUCTIONS as DEFAULT_FILE_MEMORY_INSTRUCTIONS,
)
from ._harness._file_memory import (
    DEFAULT_FILE_MEMORY_SOURCE_ID as DEFAULT_FILE_MEMORY_SOURCE_ID,
)
from ._harness._file_memory import (
    FileMemoryProvider as FileMemoryProvider,
)
from ._harness._loop import (
    AgentLoopMiddleware as AgentLoopMiddleware,
)
from ._harness._loop import (
    JudgeVerdict as JudgeVerdict,
)
from ._harness._loop import (
    background_tasks_running as background_tasks_running,
)
from ._harness._loop import (
    background_tasks_running_message as background_tasks_running_message,
)
from ._harness._loop import (
    todos_remaining as todos_remaining,
)
from ._harness._loop import (
    todos_remaining_message as todos_remaining_message,
)
from ._harness._memory import (
    DEFAULT_MEMORY_SOURCE_ID as DEFAULT_MEMORY_SOURCE_ID,
)
from ._harness._memory import (
    MemoryContextProvider as MemoryContextProvider,
)
from ._harness._memory import (
    MemoryFileStore as MemoryFileStore,
)
from ._harness._memory import (
    MemoryIndexEntry as MemoryIndexEntry,
)
from ._harness._memory import (
    MemoryStore as MemoryStore,
)
from ._harness._memory import (
    MemoryTopicRecord as MemoryTopicRecord,
)
from ._harness._mode import (
    DEFAULT_MODE_SOURCE_ID as DEFAULT_MODE_SOURCE_ID,
)
from ._harness._mode import (
    AgentModeProvider as AgentModeProvider,
)
from ._harness._mode import (
    get_agent_mode as get_agent_mode,
)
from ._harness._mode import (
    set_agent_mode as set_agent_mode,
)
from ._harness._todo import (
    DEFAULT_TODO_SOURCE_ID as DEFAULT_TODO_SOURCE_ID,
)
from ._harness._todo import (
    TodoFileStore as TodoFileStore,
)
from ._harness._todo import (
    TodoInput as TodoInput,
)
from ._harness._todo import (
    TodoItem as TodoItem,
)
from ._harness._todo import (
    TodoProvider as TodoProvider,
)
from ._harness._todo import (
    TodoSessionStore as TodoSessionStore,
)
from ._harness._todo import (
    TodoStore as TodoStore,
)
from ._harness._tool_approval import (
    DEFAULT_TOOL_APPROVAL_SOURCE_ID as DEFAULT_TOOL_APPROVAL_SOURCE_ID,
)
from ._harness._tool_approval import (
    ToolApprovalMiddleware as ToolApprovalMiddleware,
)
from ._harness._tool_approval import (
    ToolApprovalRule as ToolApprovalRule,
)
from ._harness._tool_approval import (
    ToolApprovalRuleCallback as ToolApprovalRuleCallback,
)
from ._harness._tool_approval import (
    ToolApprovalState as ToolApprovalState,
)
from ._harness._tool_approval import (
    create_always_approve_tool_response as create_always_approve_tool_response,
)
from ._harness._tool_approval import (
    create_always_approve_tool_with_arguments_response as create_always_approve_tool_with_arguments_response,
)
from ._mcp import (
    MCPStdioTool as MCPStdioTool,
)
from ._mcp import (
    MCPStreamableHTTPTool as MCPStreamableHTTPTool,
)
from ._mcp import (
    MCPTaskOptions as MCPTaskOptions,
)
from ._mcp import (
    MCPWebsocketTool as MCPWebsocketTool,
)
from ._mcp import (
    SamplingApprovalCallback as SamplingApprovalCallback,
)
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
    ContextProvider as ContextProvider,
)
from ._sessions import (
    FileHistoryProvider as FileHistoryProvider,
)
from ._sessions import (
    HistoryProvider as HistoryProvider,
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
from ._settings import SecretString as SecretString
from ._settings import load_settings as load_settings
from ._skills import (
    AggregatingSkillsSource as AggregatingSkillsSource,
)
from ._skills import (
    ClassSkill as ClassSkill,
)
from ._skills import (
    DeduplicatingSkillsSource as DeduplicatingSkillsSource,
)
from ._skills import (
    DelegatingSkillsSource as DelegatingSkillsSource,
)
from ._skills import (
    FileSkill as FileSkill,
)
from ._skills import (
    FileSkillScript as FileSkillScript,
)
from ._skills import (
    FileSkillsSource as FileSkillsSource,
)
from ._skills import (
    FilteringSkillsSource as FilteringSkillsSource,
)
from ._skills import (
    InlineSkill as InlineSkill,
)
from ._skills import (
    InlineSkillResource as InlineSkillResource,
)
from ._skills import (
    InlineSkillScript as InlineSkillScript,
)
from ._skills import (
    InMemorySkillsSource as InMemorySkillsSource,
)
from ._skills import (
    MCPSkill as MCPSkill,
)
from ._skills import (
    MCPSkillResource as MCPSkillResource,
)
from ._skills import (
    MCPSkillsSource as MCPSkillsSource,
)
from ._skills import (
    Skill as Skill,
)
from ._skills import (
    SkillFrontmatter as SkillFrontmatter,
)
from ._skills import (
    SkillResource as SkillResource,
)
from ._skills import (
    SkillScript as SkillScript,
)
from ._skills import (
    SkillScriptRunner as SkillScriptRunner,
)
from ._skills import (
    SkillsProvider as SkillsProvider,
)
from ._skills import (
    SkillsSource as SkillsSource,
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
    SKIP_PARSING as SKIP_PARSING,
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
    ToolTypes as ToolTypes,
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
    AgentRunInputs as AgentRunInputs,
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
    Embedding as Embedding,
)
from ._types import (
    EmbeddingGenerationOptions as EmbeddingGenerationOptions,
)
from ._types import (
    EmbeddingInputT as EmbeddingInputT,
)
from ._types import (
    EmbeddingT as EmbeddingT,
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
    GeneratedEmbeddings as GeneratedEmbeddings,
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
from ._workflows._agent import WorkflowAgent as WorkflowAgent
from ._workflows._agent_executor import (
    AgentExecutor as AgentExecutor,
)
from ._workflows._agent_executor import (
    AgentExecutorRequest as AgentExecutorRequest,
)
from ._workflows._agent_executor import (
    AgentExecutorResponse as AgentExecutorResponse,
)
from ._workflows._agent_utils import resolve_agent_id as resolve_agent_id
from ._workflows._checkpoint import (
    CheckpointID as CheckpointID,
)
from ._workflows._checkpoint import (
    CheckpointStorage as CheckpointStorage,
)
from ._workflows._checkpoint import (
    FileCheckpointStorage as FileCheckpointStorage,
)
from ._workflows._checkpoint import (
    InMemoryCheckpointStorage as InMemoryCheckpointStorage,
)
from ._workflows._checkpoint import (
    WorkflowCheckpoint as WorkflowCheckpoint,
)
from ._workflows._const import DEFAULT_MAX_ITERATIONS as DEFAULT_MAX_ITERATIONS
from ._workflows._edge import (
    Case as Case,
)
from ._workflows._edge import (
    Default as Default,
)
from ._workflows._edge import (
    Edge as Edge,
)
from ._workflows._edge import (
    EdgeCondition as EdgeCondition,
)
from ._workflows._edge import (
    FanInEdgeGroup as FanInEdgeGroup,
)
from ._workflows._edge import (
    FanOutEdgeGroup as FanOutEdgeGroup,
)
from ._workflows._edge import (
    SingleEdgeGroup as SingleEdgeGroup,
)
from ._workflows._edge import (
    SwitchCaseEdgeGroup as SwitchCaseEdgeGroup,
)
from ._workflows._edge import (
    SwitchCaseEdgeGroupCase as SwitchCaseEdgeGroupCase,
)
from ._workflows._edge import (
    SwitchCaseEdgeGroupDefault as SwitchCaseEdgeGroupDefault,
)
from ._workflows._edge_runner import create_edge_runner as create_edge_runner
from ._workflows._events import (
    WorkflowErrorDetails as WorkflowErrorDetails,
)
from ._workflows._events import (
    WorkflowEvent as WorkflowEvent,
)
from ._workflows._events import (
    WorkflowEventSource as WorkflowEventSource,
)
from ._workflows._events import (
    WorkflowEventType as WorkflowEventType,
)
from ._workflows._events import (
    WorkflowRunState as WorkflowRunState,
)
from ._workflows._executor import Executor as Executor
from ._workflows._executor import handler as handler
from ._workflows._function_executor import FunctionExecutor as FunctionExecutor
from ._workflows._function_executor import executor as executor
from ._workflows._functional import (
    FunctionalWorkflow as FunctionalWorkflow,
)
from ._workflows._functional import (
    FunctionalWorkflowAgent as FunctionalWorkflowAgent,
)
from ._workflows._functional import (
    RunContext as RunContext,
)
from ._workflows._functional import (
    StepWrapper as StepWrapper,
)
from ._workflows._functional import (
    get_run_context as get_run_context,
)
from ._workflows._functional import (
    step as step,
)
from ._workflows._functional import (
    workflow as workflow,
)
from ._workflows._request_info_mixin import response_handler as response_handler
from ._workflows._runner import Runner as Runner
from ._workflows._runner_context import (
    InProcRunnerContext as InProcRunnerContext,
)
from ._workflows._runner_context import (
    RunnerContext as RunnerContext,
)
from ._workflows._runner_context import (
    WorkflowMessage as WorkflowMessage,
)
from ._workflows._validation import (
    EdgeDuplicationError as EdgeDuplicationError,
)
from ._workflows._validation import (
    GraphConnectivityError as GraphConnectivityError,
)
from ._workflows._validation import (
    TypeCompatibilityError as TypeCompatibilityError,
)
from ._workflows._validation import (
    ValidationTypeEnum as ValidationTypeEnum,
)
from ._workflows._validation import (
    WorkflowValidationError as WorkflowValidationError,
)
from ._workflows._validation import (
    validate_workflow_graph as validate_workflow_graph,
)
from ._workflows._viz import WorkflowViz as WorkflowViz
from ._workflows._workflow import Workflow as Workflow
from ._workflows._workflow import WorkflowRunResult as WorkflowRunResult
from ._workflows._workflow_builder import WorkflowBuilder as WorkflowBuilder
from ._workflows._workflow_context import WorkflowContext as WorkflowContext
from ._workflows._workflow_executor import (
    SubWorkflowRequestMessage as SubWorkflowRequestMessage,
)
from ._workflows._workflow_executor import (
    SubWorkflowResponseMessage as SubWorkflowResponseMessage,
)
from ._workflows._workflow_executor import (
    WorkflowExecutor as WorkflowExecutor,
)
from .exceptions import (
    AgentFrameworkException as AgentFrameworkException,
)
from .exceptions import (
    MiddlewareException as MiddlewareException,
)
from .exceptions import (
    UserInputRequiredException as UserInputRequiredException,
)
from .exceptions import (
    WorkflowCheckpointException as WorkflowCheckpointException,
)
from .exceptions import (
    WorkflowConvergenceException as WorkflowConvergenceException,
)
from .exceptions import (
    WorkflowException as WorkflowException,
)
from .exceptions import (
    WorkflowRunnerException as WorkflowRunnerException,
)
