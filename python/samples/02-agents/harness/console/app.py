# Copyright (c) Microsoft. All rights reserved.

"""Main Textual application for the harness console.

This module provides the HarnessApp - the main Textual application that
composes all UI components and integrates with the agent runner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, Static

from .app_state import (
    BottomPanelMode,
    HarnessAppState,
    OutputEntryType,
)
from .components import (
    AgentModeAndHelp,
    AgentStatus,
    HarnessListSelection,
    HarnessScrollPanel,
    HarnessTextInput,
    PromptRule,
)
from .textual_state_driver import HarnessConsoleUXStateDriver

if TYPE_CHECKING:
    from agent_framework import Agent, AgentSession

    from .agent_runner import HarnessAgentRunner
    from .commands import CommandHandler
    from .observers.base import ConsoleObserver


class HarnessApp(App[None]):
    """Main Textual application for the harness console.

    Composes the scroll panel (conversation history), status bar (spinner, usage),
    mode/help display, and bottom panel (text input, list selection, or streaming
    indicator). Routes user input to the agent runner.
    """

    CSS = """
    Screen {
        background: $background;
    }

    #scroll-panel {
        height: 1fr;
        padding: 0 1;
        background: transparent;
    }

    #bottom-panel {
        height: auto;
    }

    #text-input-container {
        height: 1;
        display: block;
    }

    #list-selection-container {
        height: auto;
        max-height: 12;
        display: none;
    }

    #streaming-indicator {
        height: 1;
        display: none;
    }

    #status-bar {
        height: 1;
    }

    #mode-help {
        height: 1;
    }

    #top-rule {
        height: 1;
    }

    #bottom-rule {
        height: 1;
    }

    #separator-rule {
        height: 1;
    }

    #text-input {
        height: 1;
    }

    .hidden {
        display: none;
    }

    .visible {
        display: block;
    }

    .input-field {
        border: none;
        padding: 0;
        min-height: 1;
        height: 1;
        background: transparent;
    }

    .input-field:focus {
        border: none;
        background: transparent;
    }

    .prompt-container {
        height: 1;
    }

    .prompt-label {
        width: 2;
        min-width: 2;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        agent: Agent,
        observers: list[ConsoleObserver],
        session: AgentSession | None = None,
        mode_colors: dict[str, str] | None = None,
        initial_mode: str | None = None,
        placeholder: str = "Type a message and press Enter...",
        title: str = "Harness Console",
        max_context_window_tokens: int | None = None,
        max_output_tokens: int | None = None,
        command_handlers: list[CommandHandler] | None = None,
    ) -> None:
        """Initialize the harness console application.

        Args:
            agent: The agent to run.
            observers: List of console observers.
            session: Optional agent session.
            mode_colors: Optional mode color mapping.
            initial_mode: Initial agent mode.
            placeholder: Input placeholder text.
            title: Application title.
            max_context_window_tokens: Optional max context window tokens for usage display.
            max_output_tokens: Optional max output tokens for usage display.
            command_handlers: Optional list of command handlers. If None, auto-detected.
        """
        super().__init__()
        self.title = title
        self._agent = agent
        self._observers = observers
        self._session = session
        self._mode_colors = mode_colors
        self._initial_mode = initial_mode
        self._placeholder = placeholder
        self._max_context_window_tokens = max_context_window_tokens
        self._max_output_tokens = max_output_tokens

        # Build command handlers
        if command_handlers is None:
            from .commands import build_default_command_handlers

            self._command_handlers = build_default_command_handlers(agent, mode_colors=mode_colors)
        else:
            self._command_handlers = command_handlers

        # Compute help text from command handlers
        help_parts = [h.get_help_text() for h in self._command_handlers if h.get_help_text() is not None]
        help_text = ", ".join(help_parts) if help_parts else None

        # State and driver
        self._app_state = HarnessAppState(
            placeholder=placeholder,
            mode_text=initial_mode,
            help_text=help_text,
        )
        self._ux_driver = HarnessConsoleUXStateDriver(
            app_state=self._app_state,
            on_state_changed=self._on_state_changed,
            mode_colors=mode_colors,
        )

        # Agent runner (created after init)
        self._runner: HarnessAgentRunner | None = None

    @property
    def ux_driver(self) -> HarnessConsoleUXStateDriver:
        """Get the UX state driver."""
        return self._ux_driver

    @property
    def runner(self) -> HarnessAgentRunner | None:
        """Get the agent runner."""
        return self._runner

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        with Vertical():
            # Main scroll panel for conversation history
            yield HarnessScrollPanel(id="scroll-panel")

            # Blank line separating scroll content from status area
            yield Static(" ", id="separator-rule")

            # Status bar (spinner + usage)
            yield AgentStatus(id="status-bar")

            # Top rule (mode-colored)
            yield PromptRule(id="top-rule")

            # Bottom panel - switches between text input, list selection, streaming
            with Container(id="bottom-panel"):
                # Text input (default)
                with Container(id="text-input-container"):
                    text_input = HarnessTextInput(id="text-input")
                    text_input.placeholder = self._placeholder
                    yield text_input

                # List selection (for follow-up questions)
                with Container(id="list-selection-container"):
                    yield HarnessListSelection(id="list-selection")

            # Bottom rule (mode-colored)
            yield PromptRule(id="bottom-rule")

            # Mode and help
            yield AgentModeAndHelp(id="mode-help")

    def on_mount(self) -> None:
        """Initialize after mount."""
        # Create agent runner now that everything is set up
        from .agent_runner import HarnessAgentRunner

        self._runner = HarnessAgentRunner(
            agent=self._agent,
            observers=self._observers,
            state_driver=self._ux_driver,
            max_context_window_tokens=self._max_context_window_tokens,
            max_output_tokens=self._max_output_tokens,
        )

        # Set initial mode
        if self._initial_mode:
            self._ux_driver.current_mode = self._initial_mode

        # Focus the text input
        try:
            text_input = self.query_one("#text-input", HarnessTextInput)
            text_input.focus_input()
        except NoMatches:
            pass

        # Set initial rule colors and mode display
        self._sync_mode_help()

    # --- Event handlers ---

    @on(HarnessTextInput.Submitted)
    def on_text_submitted(self, event: HarnessTextInput.Submitted) -> None:
        """Handle text input submission."""
        text = event.value.strip()
        if not text:
            return

        if self._app_state.pending_questions:
            # Answer the current follow-up question
            self._handle_follow_up_answer(text)
        elif self._app_state.mode == BottomPanelMode.STREAMING:
            # Input during streaming (message injection placeholder)
            pass
        elif text.startswith("/"):
            # Try command handlers
            self._try_command_handlers(text)
        else:
            # Normal user input - run agent turn
            self._run_agent_turn(text)

    @work(exclusive=True, thread=False)
    async def _try_command_handlers(self, text: str) -> None:
        """Try each command handler; fall through to agent if none match."""
        session = self._session
        if session is None:
            # No session — fall through to agent turn
            self._run_agent_turn(text)
            return

        for handler in self._command_handlers:
            if await handler.try_handle(text, session, self._ux_driver):
                # Command handled — check for shutdown/session swap signals
                self._process_command_signals()
                return

        # No handler matched — treat as normal agent input
        self._run_agent_turn(text)

    def _process_command_signals(self) -> None:
        """Check and process signals set by command handlers."""
        if self._app_state.shutdown_requested:
            self.exit()
            return

        if self._app_state.replaced_session is not None:
            self._session = self._app_state.replaced_session  # type: ignore[assignment]
            self._app_state.replaced_session = None
            self._ux_driver.append_info_line("Session replaced.")

        self._sync_ui_from_state()

    @on(HarnessListSelection.Selected)
    def on_list_selected(self, event: HarnessListSelection.Selected) -> None:
        """Handle list selection."""
        self._handle_follow_up_answer(event.value)

    # --- Agent turn ---

    @work(exclusive=True, thread=False)
    async def _run_agent_turn(self, text: str) -> None:
        """Run an agent turn in a background worker."""
        if self._runner is None:
            return

        await self._runner.run_turn(text, session=self._session)

        # After turn completes, check for follow-up questions
        self._sync_ui_from_state()

    # --- Follow-up question handling ---

    @work(exclusive=True, thread=False)
    async def _handle_follow_up_answer(self, answer: str) -> None:
        """Handle a user's answer to a follow-up question."""
        if not self._app_state.pending_questions:
            return

        question = self._app_state.pending_questions[0]

        # Call the continuation
        result_message = await question.continuation(answer, self._ux_driver)

        # Add result to accumulated responses
        if result_message is not None:
            self._ux_driver.add_follow_up_response(result_message)

        # Advance to next question
        self._ux_driver.advance_follow_up_question()

        # If no more questions, resume the agent with accumulated responses
        if not self._app_state.pending_questions:
            responses = self._ux_driver.take_follow_up_responses()
            if responses and self._runner:
                await self._runner.start_agent_turn(responses, session=self._session)

        self._sync_ui_from_state()

    # --- State synchronization ---

    def _on_state_changed(self) -> None:
        """Called by state driver when state changes - schedule UI sync.

        Since the agent runner uses @work(thread=False), state changes happen
        on the main event loop. We use call_later to batch updates.
        """
        self.call_later(self._sync_ui_from_state)

    def _sync_ui_from_state(self) -> None:
        """Synchronize UI components with current application state."""
        state = self._app_state

        # Update scroll panel with new entries
        self._sync_scroll_panel()

        # Update bottom panel mode
        self._sync_bottom_panel(state.mode)

        # Hide status bar and mode/help during list selection (matching C#)
        is_list_mode = state.mode == BottomPanelMode.LIST_SELECTION
        self._sync_chrome_visibility(not is_list_mode)

        # Update status bar
        self._sync_status_bar()

        # Update mode/help display
        self._sync_mode_help()

    def _sync_scroll_panel(self) -> None:
        """Sync the scroll panel with output entries."""
        try:
            panel = self.query_one("#scroll-panel", HarnessScrollPanel)
        except NoMatches:
            return

        entries = self._app_state.output_entries
        rendered_count = getattr(self, "_rendered_entry_count", 0)

        if rendered_count < len(entries):
            # There are new entries to render
            for entry in entries[rendered_count:]:
                if entry.type == OutputEntryType.STREAMING_TEXT:
                    panel.set_streaming_entry(entry)
                else:
                    # End any active streaming before appending other entry types
                    panel.end_streaming()
                    panel.append_entry(entry)
            self._rendered_entry_count = len(entries)
        elif rendered_count == len(entries) and entries:
            # Same count — check if the last entry is a streaming entry that was mutated
            last_entry = entries[-1]
            if last_entry.type == OutputEntryType.STREAMING_TEXT:
                panel.set_streaming_entry(last_entry)

    def _sync_bottom_panel(self, mode: BottomPanelMode) -> None:
        """Switch the bottom panel between text input, list, and streaming."""
        try:
            text_container = self.query_one("#text-input-container")
            list_container = self.query_one("#list-selection-container")
        except NoMatches:
            return

        if mode == BottomPanelMode.TEXT_INPUT:
            text_container.display = True
            list_container.display = False
            # Restore focus to text input
            try:
                text_input = self.query_one("#text-input", HarnessTextInput)
                text_input.focus_input()
            except NoMatches:
                pass
        elif mode == BottomPanelMode.LIST_SELECTION:
            text_container.display = False
            list_container.display = True
            self._sync_list_selection()
        elif mode == BottomPanelMode.STREAMING:
            text_container.display = True
            list_container.display = False

    def _sync_list_selection(self) -> None:
        """Sync the list selection widget with state."""
        try:
            list_widget = self.query_one("#list-selection", HarnessListSelection)
        except NoMatches:
            return

        state = self._app_state
        list_widget.title = state.list_selection_title or ""
        list_widget.options = list(state.list_selection_options)
        list_widget.allow_custom_text = state.list_selection_custom_text_placeholder is not None

        if state.list_selection_custom_text_placeholder:
            try:
                custom_input = list_widget.query_one("#custom-input", Input)
                custom_input.placeholder = state.list_selection_custom_text_placeholder
            except Exception:
                pass

        # Focus the option list so keyboard navigation works immediately
        list_widget.focus_list()

    def _sync_status_bar(self) -> None:
        """Sync the status bar with state."""
        try:
            status = self.query_one("#status-bar", AgentStatus)
        except NoMatches:
            return

        state = self._app_state
        status.show_spinner = state.show_spinner
        status.usage_text = state.usage_text or ""

    def _sync_mode_help(self) -> None:
        """Sync the mode/help display and rule colors with state."""
        try:
            mode_help = self.query_one("#mode-help", AgentModeAndHelp)
        except NoMatches:
            return

        state = self._app_state
        mode_help.mode = state.mode_text or ""
        mode_help.mode_color = state.mode_color or "blue"
        mode_help.help_text = state.help_text or ""

        # Sync rule colors to match mode
        color = state.mode_color or "cyan"
        try:
            top_rule = self.query_one("#top-rule", PromptRule)
            top_rule.rule_color = color
        except NoMatches:
            pass

        try:
            bottom_rule = self.query_one("#bottom-rule", PromptRule)
            bottom_rule.rule_color = color
        except NoMatches:
            pass

    def _sync_chrome_visibility(self, visible: bool) -> None:
        """Show or hide chrome elements (status bar, mode/help).

        During list selection mode, these are hidden to give more vertical
        space to the scroll panel and list picker.

        Args:
            visible: Whether chrome elements should be visible.
        """
        import contextlib

        with contextlib.suppress(NoMatches):
            self.query_one("#status-bar", AgentStatus).display = visible
        with contextlib.suppress(NoMatches):
            self.query_one("#mode-help", AgentModeAndHelp).display = visible

    # --- Rendering count tracking ---

    _rendered_entry_count: int = 0
