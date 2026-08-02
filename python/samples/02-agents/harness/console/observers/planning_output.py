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
    from agent_framework import Agent, AgentModeProvider, AgentResponseUpdate, Message

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
        # Track the current response so that, when a run produces multiple model
        # invocations for a structured-output request (for example after message
        # injection), only the last response's text is retained for JSON parsing.
        self._last_response_id: str | None = None

    def configure_run_options(
        self,
        options: dict[str, Any],
        agent: Agent,
        session: Any,
    ) -> None:
        """Set response_format to PlanningResponse when in plan mode."""
        if self._is_planning_mode(session):
            options["response_format"] = PlanningResponse

    async def on_response_update(
        self,
        ux: IUXStateDriver,
        update: AgentResponseUpdate,
        agent: Agent,
        session: Any,
    ) -> None:
        """Stream in execute mode; collect the last response's text in plan mode.

        In planning mode a single agent run may produce multiple model
        invocations for one structured-output request (for example message
        injection triggers a follow-up response). Each model invocation is a new
        response with a distinct, non-``None`` ``response_id`` (surfaced on the
        provider's lifecycle events). When a new response begins, the previously
        collected text is flushed to the UX as plain streamed text so that only
        the final response's text is retained for JSON parsing.

        Text-delta updates in the Responses/Foundry path carry ``response_id =
        None``; those are simply accumulated and never treated as a boundary.
        """
        # Execution mode: stream text straight through to the console.
        if not self._is_planning_mode_from_ux(ux):
            if update.text:
                ux.write_text(escape(update.text))
            return

        # A new model invocation starts a new response with a different,
        # non-None response_id. Flush the previously collected (earlier) message
        # as plain text and reset the collector so only the latest response's
        # text is parsed as structured output.
        if update.response_id and update.response_id != self._last_response_id:
            if self._last_response_id is not None:
                collected_text = "".join(self._text_collector)
                if collected_text.strip():
                    ux.write_text(escape(collected_text))
                self._text_collector.clear()
            self._last_response_id = update.response_id

        if update.text:
            self._text_collector.append(update.text)

    async def on_stream_complete(
        self,
        ux: IUXStateDriver,
        agent: Agent,
        session: Any,
    ) -> list[FollowUpAction] | None:
        """Parse collected text as PlanningResponse and build follow-up actions."""
        if not self._is_planning_mode_from_ux(ux):
            self._text_collector.clear()
            self._reset_response_tracking()
            return None

        collected_text = "".join(self._text_collector)
        self._text_collector.clear()
        self._reset_response_tracking()

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
            # Thread the provider's own configuration (source id, default mode, and the set of
            # available modes) so this read matches what the provider resolves in ``before_run``.
            # ``get_agent_mode`` persists the resolved default into session state, so reading with
            # the built-in default here would wrongly store ``plan`` and override the provider's
            # configured default (e.g. ``execute``) before the agent ever runs.
            current_mode = get_agent_mode(
                session,
                source_id=self._mode_provider.source_id,
                default_mode=self._mode_provider.default_mode,
                available_modes=self._mode_provider.available_modes,
            )
        except (AttributeError, TypeError):
            return True  # No mode provider → treat as planning
        return current_mode.lower() == self._plan_mode_name.lower()

    def _is_planning_mode_from_ux(self, ux: IUXStateDriver) -> bool:
        """Check if UX is in planning mode."""
        current = ux.current_mode
        if current is None:
            return True
        return current.lower() == self._plan_mode_name.lower()

    def _reset_response_tracking(self) -> None:
        """Reset response-boundary tracking for the next stream."""
        self._last_response_id = None

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

                set_agent_mode(
                    session,
                    self._execution_mode_name,
                    source_id=self._mode_provider.source_id,
                    available_modes=self._mode_provider.available_modes,
                )
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
