# Copyright (c) Microsoft. All rights reserved.

"""State driver interface for UI updates.

This module defines the IUXStateDriver Protocol, which observers use to
update the UI during agent streaming. This is an interface-only definition;
the concrete implementation will be in a separate module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agent_framework import AgentSession

    from .app_state import FollowUpAction


class IUXStateDriver(Protocol):
    """Protocol for UI state driver.

    Observers call these methods to update the UI during agent streaming.
    This is an interface-only definition - concrete implementation comes later.

    The state driver acts as a controller between the agent framework (model)
    and the Textual UI components (view), coordinating all UI updates.
    """

    def append_info_line(self, text: str, color: str | None = None) -> None:
        """Append an informational line to the output.

        Used for displaying tool calls, errors, warnings, and other
        informational messages that aren't part of the agent's text response.

        Args:
            text: The text to display.
            color: Optional Rich color string (e.g., "yellow", "red", "dim").
        """
        ...

    def append_stream_footer(self, text: str) -> None:
        """Append a footer line after streaming ends.

        Used for displaying final status messages like "(no text response)"
        or other closing information.

        Args:
            text: The footer text to display.
        """
        ...

    def begin_streaming(self) -> None:
        """Begin streaming mode.

        Switches the bottom panel to streaming mode (shows "Streaming..." indicator),
        starts the spinner animation, and prepares for streaming text updates.
        """
        ...

    def update_streaming_text(self, accumulated_text: str) -> None:
        """Update the accumulated streaming text.

        Called repeatedly during streaming to update the displayed text as
        new chunks arrive from the agent. The text should accumulate across
        multiple calls.

        Args:
            accumulated_text: The full accumulated text so far.
        """
        ...

    def write_text(self, text: str, color: str | None = None) -> None:
        """Write a streaming text chunk incrementally.

        Appends the text to the current streaming entry. If the streaming
        entry is no longer the last output item (e.g., an info_line was
        inserted), creates a new streaming entry.

        Args:
            text: The text chunk to append.
            color: Optional Rich color string.
        """
        ...

    def end_streaming(self) -> None:
        """End streaming mode.

        Stops the spinner, switches the bottom panel back to text input mode,
        and finalizes the streaming output.
        """
        ...

    def enqueue_follow_up_action(self, action: FollowUpAction) -> None:
        """Add a follow-up action to the queue.

        Follow-up actions can be questions to ask the user or messages to
        inject into the next agent turn. The state driver queues these and
        processes them after streaming completes.

        Args:
            action: The follow-up action to queue.
        """
        ...

    def has_pending_questions(self) -> bool:
        """Check if there are pending follow-up questions awaiting user answers.

        Returns:
            True if there are unanswered questions in the queue.
        """
        ...

    def take_follow_up_responses(self) -> list:
        """Take and clear all accumulated follow-up response messages.

        Returns:
            List of Message objects accumulated from follow-up actions.
        """
        ...

    async def write_no_text_warning(self, has_follow_up_actions: bool) -> None:
        """Write a warning if the agent produced no text output.

        Called after streaming completes. If no text was received and no
        follow-up actions exist, writes a "(no text response)" footer.

        Args:
            has_follow_up_actions: Whether follow-up actions exist.
        """
        ...

    def set_mode(self, mode: str | None, mode_color: str | None = None) -> None:
        """Set the current agent mode.

        Updates the mode indicator in the UI (e.g., "[plan]", "[execute]")
        with the specified color.

        Args:
            mode: The mode name (e.g., "plan", "execute"), or None to hide.
            mode_color: Optional Rich color string for the mode label.
        """
        ...

    def set_show_spinner(self, show: bool) -> None:
        """Show or hide the spinner animation.

        The spinner provides visual feedback that the agent is processing.

        Args:
            show: True to show the spinner, False to hide it.
        """
        ...

    def set_usage_text(self, usage_text: str | None) -> None:
        """Set the token usage text.

        Displays token usage statistics (e.g., "1.2K in / 856 out") in
        the status bar.

        Args:
            usage_text: The formatted usage text, or None to hide.
        """
        ...

    @property
    def current_mode(self) -> str | None:
        """Get the current agent mode.

        Returns:
            The current mode name, or None if no mode is set.
        """
        ...

    def begin_streaming_output(self) -> None:
        """Reset per-turn streaming bookkeeping.

        Called at the start of each agent turn to reset streaming state
        (e.g., clear accumulated text, reset flags).
        """
        ...

    def write_user_input_echo(self, text: str) -> None:
        """Echo user input to the output area.

        Displays the user's submitted input in the conversation history,
        typically with a "You: " prefix.

        Args:
            text: The user's input text.
        """
        ...

    def request_shutdown(self) -> None:
        """Request the application to shut down.

        Called by the /exit command handler to signal that the user
        wants to quit the console.
        """
        ...

    def replace_session(self, session: AgentSession) -> None:
        """Replace the current agent session.

        Called by the /session-import command handler to swap the
        active session with one loaded from a file.

        Args:
            session: The new session to use.
        """
        ...


class SimpleConsoleStateDriver:
    """Simple console-based state driver for testing.

    This is a minimal implementation that logs all operations to the console.
    Useful for testing the agent runner without a full UI.
    """

    def __init__(self) -> None:
        """Initialize the simple state driver."""
        self._streaming = False
        self._spinner_visible = False
        self._current_mode: str | None = None
        print("[SimpleConsoleStateDriver initialized]")

    def append_info_line(self, text: str, color: str | None = None) -> None:
        """Append an informational line to the output."""
        color_prefix = f"[{color}]" if color else ""
        print(f"{color_prefix} {text}")

    def append_stream_footer(self, text: str) -> None:
        """Append a footer line after streaming ends."""
        print(f"[Footer] {text}")

    async def write_info_line(self, text: str, color: str | None = None) -> None:
        """Async version of append_info_line."""
        self.append_info_line(text, color)

    def write_user_input_echo(self, text: str) -> None:
        """Echo user input to the output."""
        print(f"\n[User] {text}\n")

    def begin_streaming(self) -> None:
        """Begin streaming mode."""
        self._streaming = True
        print("[▶ Streaming started]")

    def begin_streaming_output(self) -> None:
        """Begin streaming output to the scroll panel."""
        print("[▶ Streaming output started]")

    def update_streaming_text(self, text: str) -> None:
        """Update the currently streaming text."""
        # Truncate for readability
        display_text = text[:80] + "..." if len(text) > 80 else text
        print(f"[Assistant] {display_text}", end="", flush=True)

    def write_text(self, text: str, color: str | None = None) -> None:
        """Write a streaming text chunk."""
        print(text, end="", flush=True)

    async def end_streaming_output(self) -> None:
        """End streaming output."""
        print("\n[▪ Streaming output ended]")

    def end_streaming(self) -> None:
        """End streaming mode."""
        self._streaming = False
        print("[▪ Streaming ended]")

    def set_show_spinner(self, show: bool) -> None:
        """Show or hide the spinner."""
        self._spinner_visible = show
        status = "visible" if show else "hidden"
        print(f"[Spinner: {status}]")

    def set_mode(self, mode: str | None, mode_color: str | None = None) -> None:
        """Set the current mode text."""
        self._current_mode = mode
        color_str = f" ({mode_color})" if mode_color else ""
        print(f"[Mode: {mode or 'default'}{color_str}]")

    @property
    def current_mode(self) -> str | None:
        """Get the current agent mode."""
        return self._current_mode

    def set_usage_text(self, usage_text: str | None) -> None:
        """Set the usage display text."""
        if usage_text:
            print(f"[Usage: {usage_text}]")

    def enqueue_follow_up_action(self, action) -> None:
        """Enqueue a follow-up action.

        Args:
            action: The follow-up action to enqueue.
        """
        action_type = type(action).__name__
        print(f"[Follow-up queued: {action_type}]")

    def has_pending_questions(self) -> bool:
        """Check if there are pending follow-up questions."""
        return False

    def take_follow_up_responses(self) -> list:
        """Take and clear all accumulated follow-up responses."""
        return []

    async def write_no_text_warning(self, has_follow_up_actions: bool) -> None:
        """Write a warning if no text was produced."""
        if not has_follow_up_actions:
            print("[▪ (no text response from agent)]")

    def update_last_entry(self, entry_type, new_text: str) -> None:
        """Update the last output entry (placeholder for now).

        Args:
            entry_type: The type of entry to update.
            new_text: The new text content.
        """
        # Simplified: just print the update
        display_text = new_text[:80] + "..." if len(new_text) > 80 else new_text
        print(f"[Update last entry: {display_text}]", flush=True)

    def request_shutdown(self) -> None:
        """Request application shutdown."""
        print("[Shutdown requested]")

    def replace_session(self, session) -> None:
        """Replace the active session.

        Args:
            session: The new session to use.
        """
        print(f"[Session replaced: {getattr(session, 'id', 'unknown')}]")
