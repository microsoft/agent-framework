# Copyright (c) Microsoft. All rights reserved.

"""Agent mode and help text display widget."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class AgentModeAndHelp(Static):
    """Widget displaying the current agent mode and help text.

    Shows the current agent mode (e.g., "plan", "execute") in a colored label,
    followed by available commands and help text in a dimmed style. Used in
    the fixed bottom area of the console.

    Attributes:
        mode: Current mode name (e.g., "plan", "execute"), or None if no mode.
        mode_color: Rich color string for the mode label (e.g., "yellow", "green").
        help_text: Help text to display (e.g., "/exit to quit, /mode to switch").
    """

    mode: reactive[str | None] = reactive(None)
    mode_color: reactive[str] = reactive("yellow")
    help_text: reactive[str] = reactive("")

    def render(self) -> Text:
        """Render the mode indicator and help text.

        Returns:
            Rich Text object with styled mode and help display.
        """
        result = Text()

        if self.mode:
            result.append(f"[{self.mode}]", style=self.mode_color)

        if self.help_text:
            if self.mode:
                result.append("  ")
            result.append(self.help_text, style="dim")

        if not result.plain:
            result.append(" ")

        return result
