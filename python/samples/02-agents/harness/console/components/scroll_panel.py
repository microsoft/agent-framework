# Copyright (c) Microsoft. All rights reserved.

"""Scrolling panel for conversation history display."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import RichLog

if TYPE_CHECKING:
    from ..app_state import OutputEntry


class HarnessScrollPanel(RichLog):
    """Scrolling panel for displaying conversation history.

    Uses Textual's RichLog widget for efficient append-only rendering with
    Rich text formatting support. Automatically scrolls to the bottom when
    new entries are added.

    For streaming text, the panel uses a truncate-and-rewrite strategy: it
    tracks where streaming began in the RichLog lines list, and on each update
    truncates back to that point and rewrites the full accumulated text as a
    single write. This ensures consistent rendering without line-break artifacts
    between streamed chunks.
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the scroll panel.

        Args:
            **kwargs: Additional arguments passed to RichLog.
        """
        super().__init__(
            **kwargs,
            auto_scroll=True,  # Automatically scroll to bottom
            wrap=True,  # Wrap long lines instead of horizontal scroll
            markup=True,  # Enable Rich markup
            highlight=True,  # Enable syntax highlighting
        )
        self._entries: list[OutputEntry] = []
        self._is_streaming = False
        self._streaming_line_start: int = 0

    def append_entry(self, entry: OutputEntry) -> None:
        """Append a new output entry to the conversation history.

        Args:
            entry: The output entry to append.
        """
        self._entries.append(entry)
        text = self._format_entry(entry)
        self.write(text)

    def set_streaming_entry(self, entry: OutputEntry) -> None:
        """Set or update the current streaming entry.

        On each update, truncates the RichLog back to where streaming
        started, then rewrites the full streaming text as a single block.
        This ensures no spurious line breaks between chunks while avoiding
        a full rewrite of all entries.

        Args:
            entry: The streaming entry (will be mutated externally).
        """
        if not self._is_streaming:
            # First streaming chunk — record where streaming lines begin
            self._is_streaming = True
            self._entries.append(entry)
            self._streaming_line_start = len(self.lines)

        # Truncate lines back to where streaming started
        if len(self.lines) > self._streaming_line_start:
            del self.lines[self._streaming_line_start :]
            from textual.geometry import Size

            self.virtual_size = Size(self._widest_line_width, len(self.lines))

        # Write full streaming text as a single renderable
        formatted = self._format_text(entry.text, entry.color)
        self.write(formatted)

    def end_streaming(self) -> None:
        """End the current streaming mode."""
        if self._is_streaming:
            self._is_streaming = False
            self._streaming_line_start = 0

    def _rewrite_all(self) -> None:
        """Clear and rewrite all entries from scratch."""
        self.clear()
        for entry in self._entries:
            self.write(self._format_entry(entry))

    def _format_entry(self, entry: OutputEntry) -> str:
        """Format an output entry with Rich markup.

        Args:
            entry: The entry to format.

        Returns:
            Formatted string with Rich markup for color and styling.
        """
        return self._format_text(entry.text, entry.color)

    @staticmethod
    def _format_text(text: str, color: str | None) -> str:
        """Format text with optional Rich color markup.

        Args:
            text: The text to format.
            color: Optional Rich color name.

        Returns:
            Formatted string.
        """
        if color:
            return f"[{color}]{text}[/{color}]"
        return text

    def clear_history(self) -> None:
        """Clear all conversation history from the panel."""
        self._entries.clear()
        self._is_streaming = False
        self._streaming_line_start = 0
        self.clear()
