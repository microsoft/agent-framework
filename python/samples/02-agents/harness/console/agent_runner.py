# Copyright (c) Microsoft. All rights reserved.

"""Agent runner orchestration for the harness console.

This module provides the HarnessAgentRunner class, which orchestrates agent
invocations with observer lifecycle management. It handles:
- User input dispatch
- Agent streaming with observer notifications
- Follow-up action collection
- Streaming state management
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework import Agent, AgentSession

    from .app_state import FollowUpAction
    from .observers.base import ConsoleObserver
    from .state_driver import IUXStateDriver


class HarnessAgentRunner:
    """Orchestrates agent invocations driven by user-input events from the UI.

    The component invokes the runner's input handlers (run_turn) directly;
    the runner mutates UI state through the supplied IUXStateDriver.

    This is a minimal implementation focusing on the core agent loop without
    command handling or complex message injection (those can be added later).
    """

    def __init__(
        self,
        agent: Agent,
        observers: list[ConsoleObserver],
        state_driver: IUXStateDriver,
        *,
        max_context_window_tokens: int | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        """Initialize the agent runner.

        Args:
            agent: The agent to orchestrate.
            observers: List of console observers for lifecycle events.
            state_driver: The UI state driver for observer updates.
            max_context_window_tokens: Optional max context window size for usage display.
            max_output_tokens: Optional max output tokens for usage display.
        """
        self._agent = agent
        self._observers = observers
        self._ux = state_driver
        self._max_context_window_tokens = max_context_window_tokens
        self._max_output_tokens = max_output_tokens
        self._input_gate = asyncio.Semaphore(1)  # Single turn at a time

    async def run_turn(
        self,
        user_input: str,
        session: AgentSession | None = None,
    ) -> None:
        """Run a single agent turn with the given user input.

        Echoes the input, then delegates to the agent loop.

        Args:
            user_input: The user's input text.
            session: Optional agent session for conversation history.
        """
        async with self._input_gate:
            self._ux.write_user_input_echo(user_input)

            from agent_framework import Message

            messages = [Message(role="user", contents=[user_input])]
            await self._run_agent_loop(messages, session)

    async def start_agent_turn(
        self,
        messages: list,
        session: AgentSession | None = None,
    ) -> None:
        """Resume the agent loop with pre-built messages (from follow-up responses).

        Called by the app after the user finishes answering follow-up questions.
        If messages is empty, just completes the turn.

        Args:
            messages: List of Message objects to send to the agent.
            session: Optional agent session.
        """
        async with self._input_gate:
            if not messages:
                self._complete_turn()
                return
            await self._run_agent_loop(messages, session)

    async def _run_agent_loop(
        self,
        messages: list,
        session: AgentSession | None,
    ) -> None:
        """Run the agent loop, re-invoking as needed for follow-up messages.

        Loops while there are messages to send. After each stream:
        - Collects follow-up actions from observers
        - If questions exist → queue them and return (UI will collect answers)
        - If only direct messages → loop with those messages
        - If nothing → complete the turn

        Args:
            messages: Initial messages to send.
            session: Optional agent session.
        """
        next_messages = messages

        while next_messages:
            # Configure run options
            options = self._configure_run_options(session)

            # Begin streaming
            self._ux.begin_streaming()
            self._ux.begin_streaming_output()
            self._ux.set_show_spinner(True)

            try:
                await self._stream_response_messages(next_messages, session, options)
            except Exception as ex:
                self._ux.append_info_line(
                    f"❌ Stream error: {ex.__class__.__name__}:\n{ex}",
                    color="red",
                )

            # Stop spinner and end streaming output
            self._ux.set_show_spinner(False)

            # Collect follow-up actions from observers
            follow_up_actions = await self._collect_follow_up_actions(session)

            # Separate direct messages from questions
            has_follow_ups = len(follow_up_actions) > 0

            # Write no-text warning if applicable
            await self._ux.write_no_text_warning(has_follow_ups)

            # Enqueue all follow-up actions
            for action in follow_up_actions:
                self._ux.enqueue_follow_up_action(action)

            # Check if there are pending questions (UI needs user input)
            if self._ux.has_pending_questions():
                # Pause — the UI will collect answers and call start_agent_turn
                return

            # No questions — drain any accumulated direct messages and loop
            drained = self._ux.take_follow_up_responses()
            next_messages = drained if drained else None

        self._complete_turn()

    def _complete_turn(self) -> None:
        """Complete the current turn (end streaming)."""
        self._ux.end_streaming()

    def _configure_run_options(
        self,
        session: AgentSession | None,
    ) -> dict:
        """Configure run options via observers.

        Each observer can modify the options dict to influence agent behavior.

        Args:
            session: Optional agent session.

        Returns:
            Options dict for agent.run().
        """
        options = {}
        for observer in self._observers:
            observer.configure_run_options(options, self._agent, session)
        return options

    async def _stream_response(
        self,
        user_input: str,
        session: AgentSession | None,
        options: dict,
    ) -> None:
        """Stream agent response from a text input and dispatch to observers.

        Args:
            user_input: The user's input text.
            session: Optional agent session.
            options: Run options configured by observers.
        """
        # Stream response using agent.run(stream=True)
        stream = self._agent.run(
            user_input,
            stream=True,
            session=session,
            options=options,
        )

        # Process each update chunk
        async for update in stream:
            await self._dispatch_update(update, session)

        # Extract usage from the final response
        self._extract_usage(stream)

    async def _stream_response_messages(
        self,
        messages: list,
        session: AgentSession | None,
        options: dict,
    ) -> None:
        """Stream agent response from Message objects and dispatch to observers.

        Args:
            messages: List of Message objects to send.
            session: Optional agent session.
            options: Run options configured by observers.
        """
        stream = self._agent.run(
            messages,
            stream=True,
            session=session,
            options=options,
        )

        async for update in stream:
            await self._dispatch_update(update, session)

        self._extract_usage(stream)

    def _extract_usage(self, stream) -> None:
        """Extract token usage from a completed stream."""
        try:
            get_final = getattr(stream, "get_final_response", None)
            if not get_final:
                return

            import inspect

            if inspect.iscoroutinefunction(get_final):
                return

            final_response = get_final()
            if final_response is None:
                return

            usage = getattr(final_response, "usage_details", None)
            if not isinstance(usage, dict):
                return

            input_tokens = usage.get("input_token_count", 0) or 0
            output_tokens = usage.get("output_token_count", 0) or 0
            if input_tokens or output_tokens:
                self._ux.set_usage_text(self._format_usage(input_tokens, output_tokens))
        except (AttributeError, TypeError):
            pass

    async def _dispatch_update(
        self,
        update,  # AgentResponseUpdate
        session: AgentSession | None,
    ) -> None:
        """Dispatch a single update to all observers.

        Calls observer lifecycle methods in order:
        1. on_response_update (once per update)
        2. on_content (for each content item)
        3. on_text (if text is present)

        Args:
            update: The agent response update.
            session: Optional agent session.
        """
        # on_response_update
        for observer in self._observers:
            await observer.on_response_update(self._ux, update, self._agent, session)

        # on_content for each content item
        if hasattr(update, "contents") and update.contents:
            for content in update.contents:
                for observer in self._observers:
                    await observer.on_content(self._ux, content, self._agent, session)

        # on_text for text chunks
        if hasattr(update, "text") and update.text:
            for observer in self._observers:
                await observer.on_text(self._ux, update.text, self._agent, session)

    async def _collect_follow_up_actions(
        self,
        session: AgentSession | None,
    ) -> list[FollowUpAction]:
        """Collect follow-up actions from all observers.

        Called after streaming completes to gather any follow-up questions
        or messages from observers.

        Args:
            session: Optional agent session.

        Returns:
            List of follow-up actions from all observers.
        """
        actions: list[FollowUpAction] = []
        for observer in self._observers:
            observer_actions = await observer.on_stream_complete(self._ux, self._agent, session)
            if observer_actions:
                actions.extend(observer_actions)
        return actions

    def _format_usage(self, input_tokens: int, output_tokens: int) -> str:
        """Format token counts matching C# harness style: 📊 Tokens — input: X | output: Y | total: Z."""
        total_tokens = input_tokens + output_tokens

        input_budget = None
        if self._max_context_window_tokens and self._max_output_tokens:
            input_budget = self._max_context_window_tokens - self._max_output_tokens

        return (
            f"📊 Tokens — input: {self._format_token_count(input_tokens, input_budget)}"
            f" | output: {self._format_token_count(output_tokens, self._max_output_tokens)}"
            f" | total: {self._format_token_count(total_tokens, self._max_context_window_tokens)}"
        )

    @staticmethod
    def _format_token_count(count: int, budget: int | None) -> str:
        """Format a token count, optionally showing budget percentage."""
        if budget and budget > 0:
            pct = count / budget * 100
            return f"{count:,}/{budget:,} ({pct:.1f}%)"
        return f"{count:,}"
