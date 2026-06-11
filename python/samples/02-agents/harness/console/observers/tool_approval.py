# Copyright (c) Microsoft. All rights reserved.

"""Tool approval observer for user confirmation of tool calls.

Detects function_approval_request content items during streaming, displays
approval notifications, and after the stream completes presents one
ChoiceFollowUpQuestion per pending approval request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..app_state import ChoiceFollowUpQuestion, FollowUpAction
from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent, Content, Message

    from ..state_driver import IUXStateDriver


class ToolApprovalObserver(ConsoleObserver):
    """Asks user to approve tool calls before execution.

    Collects `function_approval_request` content during streaming and presents
    a multi-choice approval question for each after the stream completes.
    The continuation builds a `function_approval_response` Content to inject
    into the next agent turn.
    """

    def __init__(self) -> None:
        """Initialize the tool approval observer."""
        self._approval_requests: list[Content] = []

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Collect function_approval_request content for approval.

        Args:
            ux: The UX state driver for UI updates.
            content: The content item to check.
            agent: The AI agent.
            session: The agent session.
        """
        if content.type == "function_approval_request":
            self._approval_requests.append(content)
            tool_name = self._format_tool_name(content)
            ux.append_info_line(f"⚠️ Approval needed: {tool_name}", "yellow")

    async def on_stream_complete(
        self,
        ux: IUXStateDriver,
        agent: Agent,
        session: Any,
    ) -> list[FollowUpAction] | None:
        """Build approval questions for collected requests.

        Args:
            ux: The UX state driver for UI updates.
            agent: The AI agent.
            session: The agent session.

        Returns:
            List of ChoiceFollowUpQuestions, one per approval request.
        """
        if not self._approval_requests:
            return None

        actions: list[FollowUpAction] = []
        for request in self._approval_requests:
            actions.append(self._build_approval_question(request))

        self._approval_requests.clear()
        return actions

    def _build_approval_question(self, request: Content) -> ChoiceFollowUpQuestion:
        """Build a multi-choice approval question for a single request."""
        tool_name = self._format_tool_name(request)
        prompt = f"🔐 Tool approval: {tool_name}"

        # TODO(westey-m): Add "Always approve" options when the framework supports
        # CreateAlwaysApproveToolResponse / CreateAlwaysApproveToolWithArgumentsResponse.
        choices = [
            "Approve this call",
            "Deny",
        ]

        async def continuation(
            selection: str,
            ux: IUXStateDriver,
        ) -> Message | None:
            from agent_framework import Message

            if selection == "Deny":
                response_content = request.to_function_approval_response(approved=False)
                action_label = "❌ Denied"
                color = "red"
            else:
                response_content = request.to_function_approval_response(approved=True)
                action_label = "✅ Approved"
                color = "green"

            ux.append_info_line(
                f"🔹 {prompt}\n   └─ [{color}]{action_label}[/{color}]",
                "dim",
            )

            return Message(role="user", contents=[response_content])

        return ChoiceFollowUpQuestion(
            prompt=prompt,
            choices=choices,
            allow_custom_text=False,
            continuation=continuation,
        )

    @staticmethod
    def _format_tool_name(content: Content) -> str:
        """Extract a readable tool name from approval request content."""
        # The function_call is stored on the approval request content
        function_call = getattr(content, "function_call", None)
        if function_call is not None:
            from ..formatters import build_default_formatters, format_tool_call

            try:
                return format_tool_call(build_default_formatters(), function_call)
            except (AttributeError, TypeError):
                pass
            # Fall back to name attribute
            name = getattr(function_call, "name", None)
            if name:
                return str(name)
        return "unknown tool"
