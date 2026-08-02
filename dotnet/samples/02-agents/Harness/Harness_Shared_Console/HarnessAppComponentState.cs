// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Determines which component is shown in the bottom panel.
/// </summary>
public enum BottomPanelMode
{
    /// <summary>Show the text input component for user input.</summary>
    TextInput,

    /// <summary>Show the list selection component for interactive prompts.</summary>
    ListSelection,

    /// <summary>Show a disabled input indicator during agent streaming.</summary>
    Streaming,
}

/// <summary>
/// Internal state for <see cref="HarnessAppComponent"/>. All UI fields that may
/// change after construction live here; they are mutated exclusively via
/// <see cref="ConsoleReactiveComponent{TProps,TState}.SetState"/> by the
/// owning <see cref="HarnessConsoleUXStateDriver"/>.
/// </summary>
public record HarnessAppComponentState : ConsoleReactiveState
{
    // --- Console dimensions ---

    /// <summary>Gets the current console width in columns.</summary>
    public int ConsoleWidth { get; init; }

    /// <summary>Gets the current console height in rows.</summary>
    public int ConsoleHeight { get; init; }

    // --- Bottom panel mode ---

    /// <summary>Gets the bottom panel mode.</summary>
    public BottomPanelMode Mode { get; init; } = BottomPanelMode.TextInput;

    /// <summary>
    /// Gets the queue of follow-up questions waiting for user answers. The head
    /// (<c>[0]</c>) is the question currently being displayed; subsequent items
    /// are dispatched in order as each is answered. While this queue is non-empty,
    /// the next user submission is treated as the answer to the head question
    /// instead of going to the agent runner's normal input handler.
    /// </summary>
    public IReadOnlyList<FollowUpQuestion> PendingQuestions { get; init; } = [];

    /// <summary>
    /// Gets the accumulated follow-up response messages collected during the
    /// current agent turn — both direct <see cref="FollowUpMessage"/>s emitted
    /// by observers and continuation results from answered questions. Consumed
    /// by the runner via <see cref="IUXStateDriver.TakeFollowUpResponses"/>
    /// before the next agent invocation.
    /// </summary>
    public IReadOnlyList<ChatMessage> AccumulatedFollowUpResponses { get; init; } = [];

    // --- Text input (active in TextInput / Streaming modes) ---

    /// <summary>Gets the prompt string for text input mode.</summary>
    public string Prompt { get; init; } = "> ";

    /// <summary>Gets the placeholder text shown when the input is empty.</summary>
    public string Placeholder { get; init; } = "";

    /// <summary>Gets the current input text being typed.</summary>
    public string InputText { get; init; } = "";

    /// <summary>Gets a value indicating whether input is enabled during streaming.</summary>
    public bool InputEnabled { get; init; }

    /// <summary>Gets the prompt to show during streaming when input is disabled.</summary>
    public string StreamingPrompt { get; init; } = "(agent is running...)";

    // --- List selection (active in ListSelection mode) ---

    /// <summary>Gets the title text displayed above the list selection (for interactive prompts).</summary>
    public string? ListSelectionTitle { get; init; }

    /// <summary>Gets the list selection options.</summary>
    public IReadOnlyList<string> ListSelectionOptions { get; init; } = [];

    /// <summary>Gets the highlighted option index in list selection mode.</summary>
    public int ListSelectionIndex { get; init; }

    /// <summary>Gets the placeholder text for the custom text input option in the list.</summary>
    public string? ListSelectionCustomTextPlaceholder { get; init; }

    /// <summary>Gets the current text being typed into the list's custom text option.</summary>
    public string ListSelectionCustomInputText { get; init; } = "";

    /// <summary>Gets the highlight color for the active list item.</summary>
    public ConsoleColor ListHighlightColor { get; init; } = ConsoleColor.Cyan;

    // --- Scroll / output area ---

    /// <summary>Gets the items rendered in the scroll-area. Each item is a pre-rendered
    /// console string (may include ANSI escape sequences and newlines).</summary>
    public IReadOnlyList<string> ScrollAreaContentItems { get; init; } = [];

    /// <summary>Gets the queued input items to display above the rule. Each item is a
    /// pre-rendered console string (may include ANSI escape sequences and newlines).</summary>
    public IReadOnlyList<string> QueuedItems { get; init; } = [];

    // --- Agent mode + status display ---

    /// <summary>Gets the foreground color for the rule borders and mode label.</summary>
    public ConsoleColor? ModeColor { get; init; }

    /// <summary>Gets the current mode name displayed below the bottom rule (e.g. "plan").</summary>
    public string? ModeText { get; init; }

    /// <summary>Gets the help text displayed below the bottom rule (available commands).</summary>
    public string? HelpText { get; init; }

    /// <summary>Gets a value indicating whether the agent status spinner is visible.</summary>
    public bool ShowSpinner { get; init; }

    /// <summary>Gets the formatted token usage text to display in the status bar.</summary>
    public string? UsageText { get; init; }
}
