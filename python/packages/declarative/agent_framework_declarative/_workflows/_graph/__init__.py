# Copyright (c) Microsoft. All rights reserved.

"""Graph-based declarative workflow execution.

This module provides a graph-based approach to declarative workflows where
each YAML action is transformed into an actual workflow graph node (Executor).
This enables:
- Checkpointing at action boundaries
- Workflow visualization
- Pause/resume capabilities
- Full integration with the workflow runtime
"""

from ._base import (
    DECLARATIVE_STATE_KEY,
    ActionComplete,
    ActionTrigger,
    DeclarativeActionExecutor,
    DeclarativeMessage,
    DeclarativeWorkflowState,
    LoopControl,
    LoopIterationResult,
)
from ._builder import ALL_ACTION_EXECUTORS, DeclarativeGraphBuilder
from ._executors_agents import (
    AGENT_ACTION_EXECUTORS,
    AGENT_REGISTRY_KEY,
    TOOL_REGISTRY_KEY,
    AgentInvocationError,
    AgentResult,
    ExternalInputRequest,
    ExternalInputResponse,
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
from ._executors_human_input import (
    HUMAN_INPUT_EXECUTORS,
    ConfirmationExecutor,
    HumanInputRequest,
    QuestionChoice,
    QuestionExecutor,
    RequestExternalInputExecutor,
    WaitForInputExecutor,
)

__all__ = [
    "AGENT_ACTION_EXECUTORS",
    "AGENT_REGISTRY_KEY",
    "ALL_ACTION_EXECUTORS",
    "BASIC_ACTION_EXECUTORS",
    "CONTROL_FLOW_EXECUTORS",
    "DECLARATIVE_STATE_KEY",
    "HUMAN_INPUT_EXECUTORS",
    "TOOL_REGISTRY_KEY",
    "ActionComplete",
    "ActionTrigger",
    "AgentInvocationError",
    "AgentResult",
    "AppendValueExecutor",
    "BreakLoopExecutor",
    "ClearAllVariablesExecutor",
    "ConfirmationExecutor",
    "ContinueLoopExecutor",
    "DeclarativeActionExecutor",
    "DeclarativeGraphBuilder",
    "DeclarativeMessage",
    "DeclarativeWorkflowState",
    "EmitEventExecutor",
    "EndConversationExecutor",
    "EndWorkflowExecutor",
    "ExternalInputRequest",
    "ExternalInputResponse",
    "ExternalLoopState",
    "ForeachInitExecutor",
    "ForeachNextExecutor",
    "HumanInputRequest",
    "InvokeAzureAgentExecutor",
    "InvokeToolExecutor",
    "JoinExecutor",
    "LoopControl",
    "LoopIterationResult",
    "QuestionChoice",
    "QuestionExecutor",
    "RequestExternalInputExecutor",
    "ResetVariableExecutor",
    "SendActivityExecutor",
    "SetMultipleVariablesExecutor",
    "SetTextVariableExecutor",
    "SetValueExecutor",
    "SetVariableExecutor",
    "WaitForInputExecutor",
]
