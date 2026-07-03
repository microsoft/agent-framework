# Copyright (c) Microsoft. All rights reserved.

"""Text input widget with inline prompt for the harness console."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label


class HarnessTextInput(Widget):
    """Text input widget with a prompt label on the left.

    Displays a prompt (e.g., "> ") followed by a borderless input field.
    Sits between the two mode-colored horizontal rules.

    Attributes:
        prompt: The prompt text displayed on the left (e.g., "> ").
        placeholder: Placeholder text shown when the input is empty.
    """

    prompt: reactive[str] = reactive("> ")
    placeholder: reactive[str] = reactive("")

    class Submitted(Message):
        """Message sent when the input is submitted.

        Attributes:
            value: The submitted text value.
        """

        def __init__(self, value: str) -> None:
            """Initialize the Submitted message.

            Args:
                value: The submitted text value.
            """
            self.value = value
            super().__init__()

    def compose(self) -> ComposeResult:
        """Compose the prompt label and input field.

        Yields:
            A horizontal container with the prompt and input field.
        """
        with Horizontal(classes="prompt-container"):
            yield Label(self.prompt, classes="prompt-label", id="prompt-label")
            yield Input(placeholder=self.placeholder, classes="input-field", id="input-field")

    def watch_prompt(self, new_prompt: str) -> None:
        """Update the prompt label when the prompt attribute changes.

        Args:
            new_prompt: The new prompt text.
        """
        try:
            label = self.query_one("#prompt-label", Label)
            label.update(new_prompt)
        except Exception:
            pass

    def watch_placeholder(self, new_placeholder: str) -> None:
        """Update the input placeholder when the placeholder attribute changes.

        Args:
            new_placeholder: The new placeholder text.
        """
        try:
            input_field = self.query_one("#input-field", Input)
            input_field.placeholder = new_placeholder
        except Exception:
            # Input doesn't exist yet (before compose), ignore
            pass

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission.

        Clears the input field and posts a Submitted message with the value.

        Args:
            event: The Input.Submitted event.
        """
        value = event.value
        event.input.clear()
        self.post_message(self.Submitted(value))

    def focus_input(self) -> None:
        """Focus the input field."""
        input_field = self.query_one(".input-field", Input)
        input_field.focus()

    def clear_input(self) -> None:
        """Clear the input field."""
        input_field = self.query_one(".input-field", Input)
        input_field.clear()
