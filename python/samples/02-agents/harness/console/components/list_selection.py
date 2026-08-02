# Copyright (c) Microsoft. All rights reserved.

"""List selection widget with optional custom text input."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, OptionList
from textual.widgets.option_list import Option


class HarnessListSelection(Widget):
    """List selection widget with numbered choices and optional custom text input.

    Displays a title, a list of numbered choices that can be selected via
    keyboard navigation or number keys (1-9), and an optional custom text
    input field at the bottom.

    All child nodes (title label, option list, custom input) are always
    present in the DOM; visibility is toggled via reactive watchers.

    Navigation:
    - Down arrow on last list item moves focus to the custom text input
    - Up arrow on the custom text input moves focus back to the option list
    - When custom input has focus, the option list highlight is cleared

    Attributes:
        title: The title text displayed above the options.
        options: List of option strings to display.
        allow_custom_text: Whether to show a custom text input field.
    """

    DEFAULT_CSS = """
    HarnessListSelection {
        height: auto;
        max-height: 12;
    }

    HarnessListSelection .list-selection-container {
        height: auto;
    }

    HarnessListSelection #selection-title {
        height: auto;
        color: $text;
        text-style: bold;
        padding: 0 0 0 0;
    }

    HarnessListSelection #option-list {
        height: auto;
        max-height: 8;
        border: none;
        padding: 0;
    }

    HarnessListSelection #custom-input {
        height: auto;
        min-height: 1;
        margin-top: 0;
        border: tall transparent;
    }

    HarnessListSelection #custom-input:focus {
        border: tall $accent;
    }
    """

    BINDINGS = [
        Binding("1", "select_option(0)", "Select option 1", show=False),
        Binding("2", "select_option(1)", "Select option 2", show=False),
        Binding("3", "select_option(2)", "Select option 3", show=False),
        Binding("4", "select_option(3)", "Select option 4", show=False),
        Binding("5", "select_option(4)", "Select option 5", show=False),
        Binding("6", "select_option(5)", "Select option 6", show=False),
        Binding("7", "select_option(6)", "Select option 7", show=False),
        Binding("8", "select_option(7)", "Select option 8", show=False),
        Binding("9", "select_option(8)", "Select option 9", show=False),
    ]

    title: reactive[str] = reactive("")
    options: reactive[list[str]] = reactive(list, always_update=True)
    allow_custom_text: reactive[bool] = reactive(False)

    class Selected(Message):
        """Message sent when an option is selected.

        Attributes:
            value: The selected option text or custom text.
        """

        def __init__(self, value: str) -> None:
            """Initialize the Selected message.

            Args:
                value: The selected option text or custom text.
            """
            self.value = value
            super().__init__()

    def compose(self) -> ComposeResult:
        """Compose the widget — all nodes are always present.

        Yields:
            Title label (hidden if empty), option list, custom input (hidden by default).
        """
        with Container(classes="list-selection-container"):
            yield Label("", id="selection-title")
            yield OptionList(id="option-list")
            yield Input(
                placeholder="Or type a custom response...",
                id="custom-input",
            )

    def on_mount(self) -> None:
        """Configure initial visibility after mount."""
        title_label = self.query_one("#selection-title", Label)
        title_label.display = bool(self.title)

        custom_input = self.query_one("#custom-input", Input)
        custom_input.display = self.allow_custom_text

        self._update_options()

    def on_key(self, event: Key) -> None:
        """Handle key navigation between option list and custom input.

        Args:
            event: The key event.
        """
        if not self.allow_custom_text:
            return

        option_list = self.query_one("#option-list", OptionList)
        custom_input = self.query_one("#custom-input", Input)

        # Down arrow on last item → move to custom input
        if event.key == "down" and option_list.has_focus:
            last_index = option_list.option_count - 1
            if last_index >= 0 and option_list.highlighted == last_index:
                option_list.highlighted = None  # type: ignore[assignment]
                custom_input.focus()
                event.prevent_default()
                event.stop()

        # Up arrow on custom input → move back to option list (last item)
        elif event.key == "up" and custom_input.has_focus:
            last_index = option_list.option_count - 1
            if last_index >= 0:
                option_list.highlighted = last_index
            option_list.focus()
            event.prevent_default()
            event.stop()

    @on(Input.Changed, "#custom-input")
    def on_custom_input_focused_or_changed(self, event: Input.Changed) -> None:
        """Clear option list highlight when user is typing in custom input.

        Args:
            event: The input changed event.
        """
        option_list = self.query_one("#option-list", OptionList)
        option_list.highlighted = None  # type: ignore[assignment]

    def watch_title(self, new_title: str) -> None:
        """Update the title label when the title changes.

        Args:
            new_title: The new title text.
        """
        try:
            label = self.query_one("#selection-title", Label)
            label.update(new_title)
            label.display = bool(new_title)
        except NoMatches:
            pass

    def watch_options(self, new_options: list[str]) -> None:
        """Update the option list when options change.

        Args:
            new_options: The new list of options.
        """
        import contextlib

        with contextlib.suppress(NoMatches):
            self._update_options()

    def watch_allow_custom_text(self, allow: bool) -> None:
        """Show/hide the custom input field.

        Args:
            allow: Whether to show the custom text input.
        """
        try:
            custom_input = self.query_one("#custom-input", Input)
            custom_input.display = allow
        except NoMatches:
            pass

    def _update_options(self) -> None:
        """Update the OptionList with numbered options."""
        try:
            option_list = self.query_one("#option-list", OptionList)
            option_list.clear_options()

            for i, option_text in enumerate(self.options):
                display_text = f"{i + 1}. {option_text}" if i < 9 else f"   {option_text}"
                option_list.add_option(Option(display_text, id=str(i)))
        except NoMatches:
            pass

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection from the list.

        Args:
            event: The OptionList.OptionSelected event.
        """
        option_index = int(event.option.id or "0")
        if 0 <= option_index < len(self.options):
            selected_value = self.options[option_index]
            self.post_message(self.Selected(selected_value))

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle custom text input submission.

        Args:
            event: The Input.Submitted event.
        """
        if self.allow_custom_text and event.value:
            self.post_message(self.Selected(event.value))
            event.input.clear()

    def action_select_option(self, index: int) -> None:
        """Select an option by index (0-based).

        Args:
            index: The option index to select.
        """
        if 0 <= index < len(self.options):
            selected_value = self.options[index]
            self.post_message(self.Selected(selected_value))

    def focus_list(self) -> None:
        """Focus the option list."""
        try:
            option_list = self.query_one("#option-list", OptionList)
            option_list.focus()
        except NoMatches:
            pass

    def focus_custom_input(self) -> None:
        """Focus the custom text input field."""
        if self.allow_custom_text:
            try:
                custom_input = self.query_one("#custom-input", Input)
                custom_input.focus()
            except NoMatches:
                pass
