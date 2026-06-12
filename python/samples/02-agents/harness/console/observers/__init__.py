# Copyright (c) Microsoft. All rights reserved.

"""Console observers for agent streaming lifecycle.

This module provides observers that display events during agent streaming
and collect follow-up actions. All observers use the IUXStateDriver interface
to update the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ConsoleObserver
from .error_display import ErrorDisplayObserver
from .planning_output import PlanningOutputObserver
from .reasoning_display import ReasoningDisplayObserver
from .text_output import TextOutputObserver
from .tool_approval import ToolApprovalObserver
from .tool_call_display import ToolCallDisplayObserver
from .usage_display import UsageDisplayObserver

if TYPE_CHECKING:
    from agent_framework import Agent


def build_default_observers() -> list[ConsoleObserver]:
    """Build the default set of observers for the harness console.

    Returns a standard observer list covering:
    - Text output (streaming text display)
    - Tool call display (formatted tool invocations)
    - Error display (error messages)
    - Usage display (token counts)
    - Reasoning display (reasoning/thinking blocks)
    - Tool approval (user approval for tool calls)

    Note: PlanningOutputObserver is NOT included here because it requires
    a mode_provider. Use build_observers_with_planning() for agents that
    have an AgentModeProvider (i.e. agents created with create_harness_agent).

    Returns:
        List of default console observers.
    """
    return [
        TextOutputObserver(),
        ToolCallDisplayObserver(),
        ErrorDisplayObserver(),
        UsageDisplayObserver(),
        ReasoningDisplayObserver(),
        ToolApprovalObserver(),
    ]


def build_observers_with_planning(
    agent: Agent,
    plan_mode_name: str = "plan",
    execution_mode_name: str = "execute",
    *,
    mode_colors: dict[str, str] | None = None,
) -> list[ConsoleObserver]:
    """Build observers with planning support (structured output in plan mode).

    Replaces TextOutputObserver with PlanningOutputObserver, which configures
    structured JSON output via response_format when in plan mode. This enables
    the list picker UI for clarification and approval questions.

    Requires that the agent has an AgentModeProvider in its context_providers
    (automatically added by create_harness_agent).

    Args:
        agent: The agent to resolve the AgentModeProvider from.
        plan_mode_name: The mode name that represents planning mode.
        execution_mode_name: The mode name to switch to on approval.
        mode_colors: Optional mapping of mode names to Rich color strings.

    Returns:
        List of observers with planning support.

    Raises:
        ValueError: If the agent has no AgentModeProvider.
    """
    from agent_framework import AgentModeProvider

    mode_provider = next(
        (p for p in agent.context_providers if isinstance(p, AgentModeProvider)),
        None,
    )
    if mode_provider is None:
        msg = (
            "Planning observers require an AgentModeProvider on the agent. "
            "Use create_harness_agent() or add AgentModeProvider to context_providers."
        )
        raise ValueError(msg)

    return [
        ToolCallDisplayObserver(),
        ToolApprovalObserver(),
        ErrorDisplayObserver(),
        ReasoningDisplayObserver(),
        UsageDisplayObserver(),
        PlanningOutputObserver(
            mode_provider,
            plan_mode_name,
            execution_mode_name,
            mode_colors=mode_colors,
        ),
    ]


__all__ = [
    "ConsoleObserver",
    "ErrorDisplayObserver",
    "PlanningOutputObserver",
    "ReasoningDisplayObserver",
    "TextOutputObserver",
    "ToolApprovalObserver",
    "ToolCallDisplayObserver",
    "UsageDisplayObserver",
    "build_default_observers",
    "build_observers_with_planning",
]
