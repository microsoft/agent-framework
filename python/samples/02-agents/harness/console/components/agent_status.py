# Copyright (c) Microsoft. All rights reserved.

"""Agent status widget with spinner animation and usage statistics."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class AgentStatus(Static):
    """Agent status bar with animated spinner and token usage display.

    Displays an animated braille pattern spinner when the agent is active,
    along with token usage statistics. The component automatically updates
    the spinner animation at ~10fps for smooth visual feedback.

    Attributes:
        show_spinner: Whether to display the animated spinner.
        usage_text: Token usage text to display (e.g., "1.2K in / 856 out").
    """

    # Braille pattern spinner frames for smooth animation
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    show_spinner: reactive[bool] = reactive(False)
    usage_text: reactive[str] = reactive("")

    def __init__(self, **kwargs) -> None:
        """Initialize the agent status widget."""
        super().__init__(**kwargs)
        self._spinner_index = 0

    def on_mount(self) -> None:
        """Start the spinner animation timer when the widget is mounted."""
        # Update spinner at ~10fps (every 0.1 seconds)
        self.set_interval(0.1, self._advance_spinner)

    def _advance_spinner(self) -> None:
        """Advance the spinner to the next frame."""
        if self.show_spinner:
            self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
            self.refresh()

    def render(self) -> str:
        """Render the status bar with spinner and usage text.

        Returns:
            Formatted string with Rich markup for spinner and usage display.
        """
        if not self.show_spinner and not self.usage_text:
            return ""

        parts = []

        if self.show_spinner:
            frame = self.SPINNER_FRAMES[self._spinner_index]
            parts.append(f"[cyan]{frame}[/cyan]")
        else:
            # Keep consistent spacing when spinner is off
            parts.append(" ")

        if self.usage_text:
            parts.append(f"[dim]{self.usage_text}[/dim]")

        return " ".join(parts)
