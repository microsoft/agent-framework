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

from ._declarative_base import (
    DECLARATIVE_STATE_KEY,
    ActionComplete,
    ActionTrigger,
    ConversationData,
    DeclarativeActionExecutor,
    DeclarativeMessage,
    DeclarativeStateData,
    DeclarativeWorkflowState,
    LoopControl,
    LoopIterationResult,
)
from ._declarative_builder import ALL_ACTION_EXECUTORS, DeclarativeWorkflowBuilder
from ._executors_agents import (
    AGENT_ACTION_EXECUTORS,
    AGENT_REGISTRY_KEY,
    TOOL_REGISTRY_KEY,
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    AgentInvocationError,
    AgentResult,
    ExternalLoopState,
    InvokeAzureAgentExecutor,
    InvokeToolExecutor,
)
from ._executors_basic import (
    BASIC_ACTION_EXECUTORS,
    AppendValueExecutor,
    ClearAllVariablesExecutor,
    EmitEventExecutor,
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
    ConfirmationExecutor,
    ExternalInputRequest,
    ExternalInputResponse,
    QuestionExecutor,
    RequestExternalInputExecutor,
    WaitForInputExecutor,
)
from ._factory import DeclarativeWorkflowError, WorkflowFactory
from ._handlers import ActionHandler, action_handler, get_action_handler
from ._human_input import (
    ExternalLoopEvent,
    QuestionRequest,
    process_external_loop,
    validate_input_response,
)
from ._state import WorkflowState

__all__ = [
    "AGENT_ACTION_EXECUTORS",
    "AGENT_REGISTRY_KEY",
    "ALL_ACTION_EXECUTORS",
    "BASIC_ACTION_EXECUTORS",
    "CONTROL_FLOW_EXECUTORS",
    "DECLARATIVE_STATE_KEY",
    "EXTERNAL_INPUT_EXECUTORS",
    "TOOL_REGISTRY_KEY",
    "ActionComplete",
    "ActionHandler",
    "ActionTrigger",
    "AgentExternalInputRequest",
    "AgentExternalInputResponse",
    "AgentInvocationError",
    "AgentResult",
    "AppendValueExecutor",
    "BreakLoopExecutor",
    "ClearAllVariablesExecutor",
    "ConfirmationExecutor",
    "ContinueLoopExecutor",
    "ConversationData",
    "DeclarativeActionExecutor",
    "DeclarativeMessage",
    "DeclarativeStateData",
    "DeclarativeWorkflowBuilder",
    "DeclarativeWorkflowError",
    "DeclarativeWorkflowState",
    "EmitEventExecutor",
    "EndConversationExecutor",
    "EndWorkflowExecutor",
    "ExternalInputRequest",
    "ExternalInputResponse",
    "ExternalLoopEvent",
    "ExternalLoopState",
    "ForeachInitExecutor",
    "ForeachNextExecutor",
    "InvokeAzureAgentExecutor",
    "InvokeToolExecutor",
    "JoinExecutor",
    "LoopControl",
    "LoopIterationResult",
    "QuestionExecutor",
    "QuestionRequest",
    "RequestExternalInputExecutor",
    "ResetVariableExecutor",
    "SendActivityExecutor",
    "SetMultipleVariablesExecutor",
    "SetTextVariableExecutor",
    "SetValueExecutor",
    "SetVariableExecutor",
    "WaitForInputExecutor",
    "WorkflowFactory",
    "WorkflowState",
    "action_handler",
    "get_action_handler",
    "process_external_loop",
    "validate_input_response",
]
