# Copyright (c) Microsoft. All rights reserved.

"""Mode-colored horizontal rule."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class PromptRule(Static):
    """A full-width horizontal rule colored by the current agent mode.

    Renders a line of '─' characters across the terminal width,
    colored to match the current mode (e.g., cyan for plan, green for execute).

    Attributes:
        rule_color: Rich color string for the rule (e.g., "cyan", "green").
    """

    rule_color: reactive[str] = reactive("cyan")

    def render(self) -> str:
        """Render the horizontal rule.

        Returns:
            Formatted string with Rich markup.
        """
        color = self.rule_color
        width = self.size.width or 80
        return f"[{color}]{'─' * width}[/{color}]"
