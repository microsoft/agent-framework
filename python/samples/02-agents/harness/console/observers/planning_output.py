# Copyright (c) Microsoft. All rights reserved.

"""Planning output observer for structured agent responses in plan mode.

In planning mode, this observer configures structured JSON output via
response_format, collects streamed text silently, then deserializes the
result as a PlanningResponse to present clarification/approval questions.

In execution mode, text is streamed through directly.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from rich.markup import escape

from ..app_state import (
    ChoiceFollowUpQuestion,
    FollowUpAction,
    TextFollowUpQuestion,
)
from .base import ConsoleObserver
from .planning_models import PlanningResponse, PlanningResponseType

if TYPE_CHECKING:
    from agent_framework import Agent, AgentModeProvider, Message

    from ..state_driver import IUXStateDriver


class PlanningOutputObserver(ConsoleObserver):
    """Mode-aware observer that uses structured output in plan mode.

    In planning mode:
    - Configures response_format to PlanningResponse schema
    - Collects streamed text silently
    - Deserializes JSON into PlanningResponse
    - Builds follow-up questions (clarification or approval)

    In execution mode:
    - Streams text directly to the UX driver

    If JSON parsing fails, falls back to rendering the raw text as regular
    output so the user always sees what the agent produced.
    """

    def __init__(
        self,
        mode_provider: AgentModeProvider,
        plan_mode_name: str,
        execution_mode_name: str,
        *,
        mode_colors: dict[str, str] | None = None,
    ) -> None:
        """Initialize the planning output observer.

        Args:
            mode_provider: The mode provider for reading/switching modes.
            plan_mode_name: The mode name that represents planning mode.
            execution_mode_name: The mode name to switch to on approval.
            mode_colors: Optional mapping of mode names to Rich color strings.
        """
        self._mode_provider = mode_provider
        self._plan_mode_name = plan_mode_name
        self._execution_mode_name = execution_mode_name
        self._mode_colors = mode_colors or {}
        self._text_collector: list[str] = []

    def configure_run_options(
        self,
        options: dict[str, Any],
        agent: Agent,
        session: Any,
    ) -> None:
        """Set response_format to PlanningResponse when in plan mode."""
        if self._is_planning_mode(session):
            options["response_format"] = PlanningResponse

    async def on_text(
        self,
        ux: IUXStateDriver,
        text: str,
        agent: Agent,
        session: Any,
    ) -> None:
        """Collect text in plan mode; stream through in execute mode."""
        if self._is_planning_mode_from_ux(ux):
            self._text_collector.append(text)
        else:
            ux.write_text(escape(text))

    async def on_stream_complete(
        self,
        ux: IUXStateDriver,
        agent: Agent,
        session: Any,
    ) -> list[FollowUpAction] | None:
        """Parse collected text as PlanningResponse and build follow-up actions."""
        if not self._is_planning_mode_from_ux(ux):
            self._text_collector.clear()
            return None

        collected_text = "".join(self._text_collector)
        self._text_collector.clear()

        if not collected_text.strip():
            return None

        # Attempt to deserialize structured response
        try:
            planning_response = PlanningResponse.model_validate_json(collected_text)
        except (json.JSONDecodeError, ValueError):
            # JSON parsing failed — fall back to rendering as regular text
            ux.write_text(escape(collected_text))
            return None

        if planning_response.type == PlanningResponseType.CLARIFICATION:
            return self._build_clarification_actions(planning_response)

        if planning_response.type == PlanningResponseType.APPROVAL:
            if not planning_response.questions:
                ux.append_info_line("(approval response had no content)", "yellow")
                return None
            question = planning_response.questions[0]
            return [self._build_approval_action(question, session)]

        # Unexpected type — fall back to rendering as regular text
        ux.write_text(escape(collected_text))
        return None

    def _is_planning_mode(self, session: Any) -> bool:
        """Check if session is in planning mode."""
        from agent_framework import get_agent_mode

        try:
            current_mode = get_agent_mode(session)
        except (AttributeError, TypeError):
            return True  # No mode provider → treat as planning
        return current_mode.lower() == self._plan_mode_name.lower()

    def _is_planning_mode_from_ux(self, ux: IUXStateDriver) -> bool:
        """Check if UX is in planning mode."""
        current = ux.current_mode
        if current is None:
            return True
        return current.lower() == self._plan_mode_name.lower()

    def _build_clarification_actions(
        self,
        response: PlanningResponse,
    ) -> list[FollowUpAction]:
        """Build follow-up questions for clarification."""
        actions: list[FollowUpAction] = []

        for question in response.questions:
            prompt = question.message
            cont = self._make_clarification_continuation(prompt)

            if question.choices and len(question.choices) > 0:
                actions.append(
                    ChoiceFollowUpQuestion(
                        prompt=prompt,
                        choices=question.choices,
                        allow_custom_text=True,
                        continuation=cont,
                    )
                )
            else:
                actions.append(
                    TextFollowUpQuestion(
                        prompt=prompt,
                        continuation=cont,
                    )
                )

        return actions

    @staticmethod
    def _make_clarification_continuation(prompt: str):
        """Create a clarification continuation closure capturing the prompt."""

        async def continuation(
            answer: str,
            ux: IUXStateDriver,
        ) -> Message | None:
            if not answer.strip():
                ux.append_info_line(f"🔹 {prompt}\n   └─ (no answer)", "dim")
                return None

            ux.append_info_line(f"🔹 {prompt}\n   └─ [green]{answer}[/green]", "dim")

            from agent_framework import Message

            return Message(role="user", contents=[f"Q: {prompt}\nA: {answer}"])

        return continuation

    def _build_approval_action(
        self,
        question: Any,
        session: Any,
    ) -> ChoiceFollowUpQuestion:
        """Build the approval follow-up question."""
        approve_option = "Approve and switch to execute mode"
        prompt = question.message

        async def continuation(
            selection: str,
            ux: IUXStateDriver,
        ) -> Message | None:
            ux.append_info_line(
                f"🔹 {prompt}\n   └─ [green]{selection}[/green]",
                "dim",
            )

            if selection == approve_option:
                from agent_framework import set_agent_mode

                set_agent_mode(session, self._execution_mode_name)
                exec_color = self._mode_colors.get(self._execution_mode_name)
                ux.set_mode(self._execution_mode_name, exec_color)
                ux.append_info_line(
                    f"✅ Switched to {self._execution_mode_name} mode.",
                    exec_color,
                )
                from agent_framework import Message

                return Message(role="user", contents=["Approved"])

            # Custom freeform input — treat as suggested changes
            from agent_framework import Message

            return Message(role="user", contents=[selection])

        return ChoiceFollowUpQuestion(
            prompt=prompt,
            choices=[approve_option],
            allow_custom_text=True,
            continuation=continuation,
        )
