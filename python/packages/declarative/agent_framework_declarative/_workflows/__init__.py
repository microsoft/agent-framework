# Copyright (c) Microsoft. All rights reserved.

"""Declarative workflow support for agent-framework.

This module provides the ability to create executable Workflow objects from YAML definitions,
enabling multi-agent orchestration patterns like Foreach, conditionals, and agent invocations.
"""

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
    "ActionHandler",
    "DeclarativeWorkflowError",
    "ExternalLoopEvent",
    "QuestionRequest",
    "WorkflowFactory",
    "WorkflowState",
    "action_handler",
    "get_action_handler",
    "process_external_loop",
    "validate_input_response",
]
