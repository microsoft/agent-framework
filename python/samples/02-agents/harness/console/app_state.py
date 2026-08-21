# Copyright (c) Microsoft. All rights reserved.

"""Application state and core data types for the harness console.

This module defines enums, dataclasses, follow-up action types, and the
HarnessAppState dataclass which holds all UI state that may change during
application execution. The state driver mutates this state to coordinate
between the agent runner and the Textual UI components.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework import Message

    from .state_driver import IUXStateDriver


# region Enums


class OutputEntryType(Enum):
    """Type of output entry in the console conversation."""

    USER_INPUT = "user_input"
    """User input echo (e.g., 'You: hello')."""

    STREAMING_TEXT = "streaming_text"
    """In-progress streaming text from the agent (accumulated chunk by chunk)."""

    INFO_LINE = "info_line"
    """Informational line (tool calls, errors, usage, approval requests, etc.)."""

    STREAM_FOOTER = "stream_footer"
    """Stream footer (e.g., '(no text response from agent)')."""

    PENDING_MESSAGE = "pending_message"
    """Pending injected message notification."""


class BottomPanelMode(Enum):
    """Mode of the bottom panel UI."""

    TEXT_INPUT = "text_input"
    """Show text input for user messages."""

    LIST_SELECTION = "list_selection"
    """Show choice list for user selection."""

    STREAMING = "streaming"
    """Show 'streaming...' indicator while agent is generating."""


# endregion

# region Output Entry


@dataclass
class OutputEntry:
    """A single output entry in the console conversation history.

    Used internally by the state driver to track conversation output,
    including streaming text, tool calls, errors, and user input echoes.

    Args:
        type: The type of output entry.
        text: The text content of the entry.
        color: Optional Rich color string (e.g., "cyan", "red", "dim").
    """

    type: OutputEntryType
    text: str
    color: str | None = None


# endregion

# region Follow-Up Actions


class FollowUpAction:
    """Base class for follow-up actions returned by observers.

    Follow-up actions describe either a question to ask the user
    (via FollowUpQuestion subclasses) or a message to add directly
    to the next agent input (FollowUpMessage).
    """

    pass


@dataclass
class FollowUpQuestion(FollowUpAction):
    """A question to ask the user with a continuation.

    The continuation delegate is invoked with the user's answer and the
    UX state driver, and returns an optional Message to add to the next
    agent invocation.

    Args:
        prompt: The question text shown to the user.
        continuation: Async function invoked with the user's answer and state driver.
            Returns an optional Message to add to the next agent input.
    """

    prompt: str
    continuation: Callable[[str, IUXStateDriver], Awaitable[Message | None]]


@dataclass
class TextFollowUpQuestion(FollowUpQuestion):
    """A free-form text question.

    The user may type any response. This is the base FollowUpQuestion type
    with no additional constraints.
    """

    pass


@dataclass
class ChoiceFollowUpQuestion(FollowUpQuestion):
    """A multiple choice question.

    The user picks from the provided choices, with an optional ability to
    enter custom text when allow_custom_text is True.

    Args:
        prompt: The question text shown to the user.
        choices: List of pre-defined choices.
        allow_custom_text: If True, the user may type a custom response in
            addition to the listed choices.
        continuation: Async function invoked with the user's choice/text and
            state driver. Returns an optional Message to add to the next agent input.
    """

    choices: list[str]
    allow_custom_text: bool = False


@dataclass
class FollowUpMessage(FollowUpAction):
    """A message to add directly to the next agent invocation without prompting.

    Used when an observer wants to inject a message into the conversation
    without user interaction (e.g., automatic tool results, system messages).

    Args:
        message: The Message to add to the conversation.
    """

    message: Message


# endregion

# region Application State


@dataclass
class HarnessAppState:
    """All UI state for the harness console application.

    This state is mutated by the UX state driver and read by the Textual
    app to update the UI.
    """

    # --- Bottom panel mode ---

    mode: BottomPanelMode = BottomPanelMode.TEXT_INPUT
    """Which component is shown in the bottom panel."""

    # --- Follow-up question queue ---

    pending_questions: list[FollowUpQuestion] = field(default_factory=list)
    """Queue of follow-up questions waiting for user answers.

    The head ([0]) is the question currently being displayed; subsequent items
    are dispatched in order as each is answered.
    """

    accumulated_follow_up_responses: list[Message] = field(default_factory=list)
    """Accumulated follow-up response messages collected during the current agent turn.

    Both direct FollowUpMessages emitted by observers and continuation results
    from answered questions. Consumed by the runner via take_follow_up_responses().
    """

    # --- Text input (active in TextInput / Streaming modes) ---

    prompt: str = "> "
    """The prompt string for text input mode."""

    placeholder: str = ""
    """Placeholder text shown when the input is empty."""

    input_text: str = ""
    """The current input text being typed."""

    input_enabled: bool = True
    """Whether input is enabled (disabled during streaming without injection)."""

    streaming_prompt: str = "(agent is running...)"
    """The prompt to show during streaming when input is disabled."""

    # --- List selection (active in ListSelection mode) ---

    list_selection_title: str | None = None
    """Title text displayed above the list selection."""

    list_selection_options: list[str] = field(default_factory=list)
    """The list selection options."""

    list_selection_index: int = 0
    """The highlighted option index in list selection mode."""

    list_selection_custom_text_placeholder: str | None = None
    """Placeholder text for the custom text input option in the list."""

    list_selection_custom_input_text: str = ""
    """Current text being typed into the list's custom text option."""

    # --- Scroll / output area ---

    output_entries: list[OutputEntry] = field(default_factory=list)
    """Output entries in the scroll area conversation history."""

    queued_items: list[str] = field(default_factory=list)
    """Queued input items to display (pending injected messages)."""

    # --- Agent mode + status display ---

    mode_color: str | None = None
    """Rich color string for the rule borders and mode label."""

    mode_text: str | None = None
    """Current mode name displayed (e.g., 'plan', 'execute')."""

    help_text: str | None = None
    """Help text displayed below the bottom rule (available commands)."""

    show_spinner: bool = False
    """Whether the agent status spinner is visible."""

    usage_text: str | None = None
    """Formatted token usage text to display in the status bar."""

    # --- Command handler signals ---

    shutdown_requested: bool = False
    """Set to True when /exit is invoked; the app should exit."""

    replaced_session: object | None = None
    """When set, the app should swap its session to this AgentSession."""
