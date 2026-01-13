# Copyright (c) Microsoft. All rights reserved.

"""Action handlers for declarative workflow execution.

This module provides the ActionHandler protocol and registry for executing
workflow actions defined in YAML. Each action type (InvokeAzureAgent, Foreach, etc.)
has a corresponding handler registered via the @action_handler decorator.
"""

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from agent_framework import get_logger

if TYPE_CHECKING:
    from ._state import WorkflowState

logger = get_logger("agent_framework.declarative.workflows")


@dataclass
class ActionContext:
    """Context passed to action handlers during execution.

    Provides access to workflow state, the action definition, and methods
    for executing nested actions (for control flow constructs like Foreach).
    """

    state: "WorkflowState"
    """The current workflow state with variables and agent results."""

    action: dict[str, Any]
    """The action definition from the YAML."""

    execute_actions: "ExecuteActionsFn"
    """Function to execute a list of nested actions (for Foreach, If, etc.)."""

    agents: dict[str, Any]
    """Registry of agent instances by name."""

    bindings: dict[str, Any]
    """Function bindings for tool calls."""

    @property
    def action_id(self) -> str | None:
        """Get the action's unique identifier."""
        return self.action.get("id")

    @property
    def display_name(self) -> str | None:
        """Get the action's human-readable display name for debugging/logging."""
        return self.action.get("displayName")

    @property
    def action_kind(self) -> str | None:
        """Get the action's type/kind."""
        return self.action.get("kind")


# Type alias for the nested action executor function
ExecuteActionsFn = Callable[
    [list[dict[str, Any]], "WorkflowState"],
    AsyncGenerator["WorkflowEvent", None],
]


@dataclass
class WorkflowEvent:
    """Base class for events emitted during workflow execution."""

    pass


@dataclass
class TextOutputEvent(WorkflowEvent):
    """Event emitted when text should be sent to the user."""

    text: str
    """The text content to output."""


@dataclass
class AttachmentOutputEvent(WorkflowEvent):
    """Event emitted when an attachment should be sent to the user."""

    content: Any
    """The attachment content."""

    content_type: str = "application/octet-stream"
    """The MIME type of the attachment."""


@dataclass
class AgentResponseEvent(WorkflowEvent):
    """Event emitted when an agent produces a response."""

    agent_name: str
    """The name of the agent that produced the response."""

    text: str | None
    """The text content of the response, if any."""

    messages: list[Any]
    """The messages from the agent response."""

    tool_calls: list[Any] | None = None
    """Any tool calls made by the agent."""


@dataclass
class AgentStreamingChunkEvent(WorkflowEvent):
    """Event emitted for streaming chunks from an agent."""

    agent_name: str
    """The name of the agent producing the chunk."""

    chunk: str
    """The streaming chunk content."""


@dataclass
class CustomEvent(WorkflowEvent):
    """Custom event emitted via EmitEvent action."""

    name: str
    """The event name."""

    data: Any
    """The event data."""


@dataclass
class LoopControlSignal(WorkflowEvent):
    """Signal for loop control (break/continue)."""

    signal_type: str
    """Either 'break' or 'continue'."""


@runtime_checkable
class ActionHandler(Protocol):
    """Protocol for action handlers.

    Action handlers are async generators that execute a single action type
    and yield events as they process. They receive an ActionContext with
    the current state, action definition, and utilities for nested execution.
    """

    def __call__(
        self,
        ctx: ActionContext,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Execute the action and yield events.

        Args:
            ctx: The action context containing state, action definition, and utilities

        Yields:
            WorkflowEvent instances as the action executes
        """
        ...


# Global registry of action handlers
_ACTION_HANDLERS: dict[str, ActionHandler] = {}


def action_handler(action_kind: str) -> Callable[[ActionHandler], ActionHandler]:
    """Decorator to register an action handler for a specific action type.

    Args:
        action_kind: The action type this handler processes (e.g., 'InvokeAzureAgent')

    Example:
        @action_handler("SetValue")
        async def handle_set_value(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
            path = ctx.action.get("path")
            value = ctx.state.eval_if_expression(ctx.action.get("value"))
            ctx.state.set(path, value)
            return
            yield  # Make it a generator
    """

    def decorator(func: ActionHandler) -> ActionHandler:
        _ACTION_HANDLERS[action_kind] = func
        logger.debug(f"Registered action handler for '{action_kind}'")
        return func

    return decorator


def get_action_handler(action_kind: str) -> ActionHandler | None:
    """Get the registered handler for an action type.

    Args:
        action_kind: The action type to look up

    Returns:
        The registered ActionHandler, or None if not found
    """
    return _ACTION_HANDLERS.get(action_kind)


def list_action_handlers() -> list[str]:
    """List all registered action handler types.

    Returns:
        A list of registered action type names
    """
    return list(_ACTION_HANDLERS.keys())
