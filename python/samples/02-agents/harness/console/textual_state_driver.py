# Copyright (c) Microsoft. All rights reserved.

"""Textual-based UX state driver implementation.

This module provides the full HarnessConsoleUXStateDriver that connects
the agent runner and observers to the Textual UI components. It mutates
the application state and triggers UI updates through the Textual app.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .app_state import (
    BottomPanelMode,
    ChoiceFollowUpQuestion,
    FollowUpAction,
    FollowUpMessage,
    FollowUpQuestion,
    HarnessAppState,
    OutputEntry,
    OutputEntryType,
)

if TYPE_CHECKING:
    from agent_framework import Message


# Default mode colors (mode name -> Rich color string)
DEFAULT_MODE_COLORS: dict[str, str] = {
    "plan": "cyan",
    "execute": "green",
    "review": "yellow",
    "default": "blue",
}


def get_mode_color(mode: str | None, mode_colors: dict[str, str] | None = None) -> str:
    """Get the color for a mode name.

    Args:
        mode: The mode name.
        mode_colors: Optional custom mode color mapping.

    Returns:
        A Rich color string for the mode.
    """
    colors = mode_colors or DEFAULT_MODE_COLORS
    if mode is None:
        return colors.get("default", "blue")
    return colors.get(mode, colors.get("default", "blue"))


class HarnessConsoleUXStateDriver:
    """Full Textual-based UX state driver.

    Implements the IUXStateDriver protocol by mutating application state
    and calling back into the Textual app to trigger UI updates.

    The driver owns the output entry list and streaming state, and produces
    state snapshots that the app uses to render the UI.
    """

    def __init__(
        self,
        app_state: HarnessAppState,
        on_state_changed: Callable[[], None],
        mode_colors: dict[str, str] | None = None,
    ) -> None:
        """Initialize the state driver.

        Args:
            app_state: The application state object to mutate.
            on_state_changed: Callback invoked after state changes to trigger UI refresh.
            mode_colors: Optional mapping of mode names to Rich color strings.
        """
        self._state = app_state
        self._on_state_changed = on_state_changed
        self._mode_colors = mode_colors

        # Streaming bookkeeping
        self._has_received_any_text = False
        self._current_streaming_entry: OutputEntry | None = None
        self._current_streaming_entry_index: int = -1
        self._last_entry_type: OutputEntryType | None = None

    @property
    def state(self) -> HarnessAppState:
        """Get the current application state."""
        return self._state

    @property
    def current_mode(self) -> str | None:
        """Get the current agent mode."""
        return self._state.mode_text

    @current_mode.setter
    def current_mode(self, value: str | None) -> None:
        """Set the current agent mode."""
        self._state.mode_text = value
        self._state.mode_color = get_mode_color(value, self._mode_colors)
        self._notify()

    # --- Streaming lifecycle ---

    def begin_streaming(self) -> None:
        """Begin streaming mode - switch bottom panel and show spinner."""
        self._state.mode = BottomPanelMode.STREAMING
        self._state.show_spinner = True
        self._state.input_enabled = False
        self._notify()

    def begin_streaming_output(self) -> None:
        """Reset per-turn streaming bookkeeping."""
        self._has_received_any_text = False
        self._current_streaming_entry = None
        self._current_streaming_entry_index = -1

    def end_streaming(self) -> None:
        """End streaming mode - return to text input."""
        self._state.mode = BottomPanelMode.TEXT_INPUT
        self._state.show_spinner = False
        self._state.input_enabled = True
        self._notify()

    async def end_streaming_output(self) -> None:
        """Finalize streaming output - add trailing newline if text was received."""
        if self._has_received_any_text:
            self._current_streaming_entry = None
            self._last_entry_type = OutputEntryType.STREAM_FOOTER
            self._notify()

    def set_show_spinner(self, show: bool) -> None:
        """Show or hide the spinner."""
        self._state.show_spinner = show
        self._notify()

    # --- Text output ---

    def write_user_input_echo(self, text: str) -> None:
        """Echo user input to the output area."""
        entry = OutputEntry(
            type=OutputEntryType.USER_INPUT,
            text=f"You: {text}",
            color="green",
        )
        self._append_entry(entry)
        self._last_entry_type = OutputEntryType.USER_INPUT
        self._notify()

    def append_info_line(self, text: str, color: str | None = None) -> None:
        """Append an informational line to the output."""
        effective_color = color or get_mode_color(self._state.mode_text, self._mode_colors)

        # Add separator when transitioning from streaming text
        prefix = ""
        if self._last_entry_type in (OutputEntryType.STREAMING_TEXT, OutputEntryType.STREAM_FOOTER):
            prefix = ""  # Textual handles spacing via widget layout

        entry = OutputEntry(
            type=OutputEntryType.INFO_LINE,
            text=prefix + text,
            color=effective_color,
        )
        self._append_entry(entry)
        self._last_entry_type = OutputEntryType.INFO_LINE
        self._notify()

    def append_stream_footer(self, text: str) -> None:
        """Append a footer line after streaming ends."""
        entry = OutputEntry(
            type=OutputEntryType.STREAM_FOOTER,
            text=text,
            color="dim",
        )
        self._append_entry(entry)
        self._last_entry_type = OutputEntryType.STREAM_FOOTER
        self._notify()

    async def write_info_line(self, text: str, color: str | None = None) -> None:
        """Async version of append_info_line."""
        self.append_info_line(text, color)

    def write_text(self, text: str, color: str | None = None) -> None:
        """Write streaming text from the agent.

        Accumulates text into the current streaming entry. If the streaming
        entry is still the last output item, appends to it in place. Otherwise
        starts a new streaming entry.

        Args:
            text: The text chunk to append.
            color: Optional Rich color.
        """
        self._last_entry_type = OutputEntryType.STREAMING_TEXT
        self._has_received_any_text = True

        effective_color = color or get_mode_color(self._state.mode_text, self._mode_colors)

        if (
            self._current_streaming_entry is not None
            and self._current_streaming_entry_index == len(self._state.output_entries) - 1
        ):
            # Append to existing streaming entry in place
            self._current_streaming_entry.text += text
            # Update the entry in the list (same object, but trigger notify)
        else:
            # Start a fresh streaming entry
            self._current_streaming_entry = OutputEntry(
                type=OutputEntryType.STREAMING_TEXT,
                text=text,
                color=effective_color,
            )
            self._state.output_entries.append(self._current_streaming_entry)
            self._current_streaming_entry_index = len(self._state.output_entries) - 1

        self._notify()

    def update_streaming_text(self, accumulated_text: str) -> None:
        """Update the accumulated streaming text (full replacement).

        Alternative to write_text() - replaces the entire streaming entry text.
        If an info_line was appended after the streaming entry (e.g., a tool
        call), creates a new streaming entry at the end of the list so the
        UI can render it.

        Args:
            accumulated_text: The full accumulated text so far.
        """
        effective_color = get_mode_color(self._state.mode_text, self._mode_colors)

        if (
            self._current_streaming_entry is not None
            and self._current_streaming_entry_index == len(self._state.output_entries) - 1
        ):
            # Streaming entry is still the last entry — update in place
            self._current_streaming_entry.text = accumulated_text
        else:
            # Either no current entry, or it's no longer at the end (an
            # info_line was appended after it). Create a new streaming entry
            # so the panel can render the continued text.
            self._current_streaming_entry = OutputEntry(
                type=OutputEntryType.STREAMING_TEXT,
                text=accumulated_text,
                color=effective_color,
            )
            self._state.output_entries.append(self._current_streaming_entry)
            self._current_streaming_entry_index = len(self._state.output_entries) - 1

        self._last_entry_type = OutputEntryType.STREAMING_TEXT
        self._has_received_any_text = True
        self._notify()

    async def write_no_text_warning(self, has_follow_up_actions: bool) -> None:
        """Write '(no text response)' warning if no text was received."""
        if not self._has_received_any_text and not has_follow_up_actions:
            self.append_stream_footer("(no text response from agent)")

    # --- Usage and mode ---

    def set_usage_text(self, usage_text: str | None) -> None:
        """Set the token usage text."""
        self._state.usage_text = usage_text
        self._notify()

    def set_mode(self, mode: str | None, mode_color: str | None = None) -> None:
        """Set the current mode."""
        self._state.mode_text = mode
        self._state.mode_color = mode_color or get_mode_color(mode, self._mode_colors)
        self._notify()

    # --- Follow-up actions ---

    def enqueue_follow_up_action(self, action: FollowUpAction) -> None:
        """Enqueue a follow-up action."""
        if isinstance(action, FollowUpMessage):
            self._state.accumulated_follow_up_responses.append(action.message)
        elif isinstance(action, FollowUpQuestion):
            self.queue_follow_up_questions([action])

    def queue_follow_up_questions(self, questions: list[FollowUpQuestion]) -> None:
        """Queue follow-up questions for user interaction.

        Args:
            questions: List of questions to queue.
        """
        if not questions:
            return

        was_empty = len(self._state.pending_questions) == 0
        self._state.pending_questions.extend(questions)

        if was_empty:
            self._configure_for_head_question(self._state.pending_questions[0])

        self._notify()

    def add_follow_up_response(self, response: Message) -> None:
        """Add a follow-up response message."""
        self._state.accumulated_follow_up_responses.append(response)

    def advance_follow_up_question(self) -> None:
        """Advance to the next follow-up question.

        Removes the head question from the queue. If more questions remain,
        configures the UI for the next one. Otherwise returns to text input.
        """
        if not self._state.pending_questions:
            return

        self._state.pending_questions.pop(0)

        if self._state.pending_questions:
            self._configure_for_head_question(self._state.pending_questions[0])
        else:
            # No more questions - return to text input
            self._state.mode = BottomPanelMode.TEXT_INPUT
            self._state.list_selection_options = []
            self._state.list_selection_title = None
            self._state.list_selection_custom_text_placeholder = None
            self._state.list_selection_index = 0
            self._state.list_selection_custom_input_text = ""

        self._notify()

    def take_follow_up_responses(self) -> list[Message]:
        """Take and clear all accumulated follow-up responses.

        Returns:
            List of accumulated response messages.
        """
        responses = list(self._state.accumulated_follow_up_responses)
        self._state.accumulated_follow_up_responses.clear()
        return responses

    def has_pending_questions(self) -> bool:
        """Check if there are pending follow-up questions.

        Returns:
            True if unanswered questions exist in the queue.
        """
        return len(self._state.pending_questions) > 0

    # --- Queued messages (message injection) ---

    def set_queued_messages(self, pending: list[str]) -> None:
        """Set the queued message display.

        Args:
            pending: List of pending message texts.
        """
        self._state.queued_items = [f"💬 {text}" for text in pending]
        self._notify()

    # --- Internal helpers ---

    def _append_entry(self, entry: OutputEntry) -> None:
        """Append an output entry to the state."""
        self._state.output_entries.append(entry)

    def _configure_for_head_question(self, question: FollowUpQuestion) -> None:
        """Configure the UI for the current head question.

        Args:
            question: The question to display.
        """
        if isinstance(question, ChoiceFollowUpQuestion):
            self._state.mode = BottomPanelMode.LIST_SELECTION
            self._state.list_selection_options = list(question.choices)
            self._state.list_selection_title = question.prompt
            self._state.list_selection_custom_text_placeholder = (
                "✏️  Type a custom response..." if question.allow_custom_text else None
            )
            self._state.list_selection_index = 0
            self._state.list_selection_custom_input_text = ""
        else:
            # Text question - show as info line and switch to text input
            self.append_info_line(question.prompt)
            self._state.mode = BottomPanelMode.TEXT_INPUT
            self._state.list_selection_options = []
            self._state.list_selection_title = None

    def _notify(self) -> None:
        """Notify the app that state has changed."""
        self._on_state_changed()

    def request_shutdown(self) -> None:
        """Request the application to shut down."""
        self._state.shutdown_requested = True
        self._notify()

    def replace_session(self, session) -> None:
        """Replace the current agent session.

        Args:
            session: The new AgentSession to use.
        """
        self._state.replaced_session = session
        self._notify()
