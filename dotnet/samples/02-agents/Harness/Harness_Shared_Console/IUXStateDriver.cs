// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Abstraction over the harness UI state. All callers (observers, command handlers,
/// the agent runner) interact with the UI exclusively through this interface, which
/// internally translates each operation into a <c>SetState</c> call on the underlying
/// reactive component.
/// </summary>
/// <remarks>
/// This interface is intentionally narrow: it does not expose blocking input methods.
/// The agent runner orchestrates input flow via <see cref="FollowUpQuestion"/>
/// objects returned from observers.
/// </remarks>
public interface IUXStateDriver
{
    /// <summary>
    /// Gets or sets the current agent mode (e.g. "plan", "execute"). Setting also
    /// refreshes the rule colour and bottom-panel prompt to match the new mode.
    /// </summary>
    string? CurrentMode { get; set; }

    /// <summary>
    /// Echoes a submitted user input as a regular user-input entry in the output area.
    /// </summary>
    void WriteUserInputEcho(string text);

    /// <summary>
    /// Writes informational output as an output entry, without a trailing newline.
    /// </summary>
    Task WriteInfoAsync(string text, ConsoleColor? color = null);

    /// <summary>
    /// Writes informational output as an output entry, followed by a newline.
    /// </summary>
    Task WriteInfoLineAsync(string text, ConsoleColor? color = null);

    /// <summary>
    /// Writes streaming text output from the agent. Successive calls accumulate into a
    /// single streaming entry that is re-rendered by the text panel.
    /// </summary>
    Task WriteTextAsync(string text, ConsoleColor? color = null);

    /// <summary>
    /// Writes a blank-line separator to visually close the streaming output section.
    /// </summary>
    Task EndStreamingOutputAsync();

    /// <summary>
    /// Shows a "(no text response from agent)" warning if no text was received
    /// and no observer produced follow-up actions.
    /// </summary>
    Task WriteNoTextWarningAsync(bool hasFollowUpActions);

    /// <summary>
    /// Switches the bottom panel to streaming mode and starts the spinner.
    /// </summary>
    void BeginStreaming();

    /// <summary>
    /// Stops the spinner without leaving streaming mode.
    /// </summary>
    void StopSpinner();

    /// <summary>
    /// Switches the bottom panel back to text-input mode and stops the spinner.
    /// </summary>
    void EndStreaming();

    /// <summary>
    /// Resets per-turn streaming bookkeeping in preparation for a new agent turn.
    /// </summary>
    void BeginStreamingOutput();

    /// <summary>
    /// Sets the formatted usage text shown on the agent status bar.
    /// </summary>
    void SetUsageText(string usageText);

    /// <summary>
    /// Replaces the queued-message display with one entry per pending message.
    /// </summary>
    void SetQueuedMessages(IReadOnlyList<ChatMessage> pending);

    /// <summary>
    /// Appends the supplied questions to the pending follow-up question queue in
    /// component state. If the queue was empty, the bottom-panel display is
    /// reconfigured to present the new head question.
    /// </summary>
    void QueueFollowUpQuestions(IReadOnlyList<FollowUpQuestion> questions);

    /// <summary>
    /// Appends a message to the accumulated follow-up response list in component state.
    /// Called by the runner for direct <see cref="FollowUpMessage"/> outputs and by
    /// the component when a question's continuation produces a response.
    /// </summary>
    void AddFollowUpResponse(ChatMessage response);

    /// <summary>
    /// Pops the head of the pending follow-up question queue. Reconfigures the
    /// bottom-panel display for the new head, or restores the default text-input
    /// mode if the queue is now empty.
    /// </summary>
    void AdvanceFollowUpQuestion();

    /// <summary>
    /// Returns the current accumulated follow-up responses and clears them in state.
    /// Called by the runner immediately before invoking the next agent turn.
    /// </summary>
    IReadOnlyList<ChatMessage> TakeFollowUpResponses();

    /// <summary>
    /// Signals that the application should shut down. Completes the shutdown task
    /// on the owning component.
    /// </summary>
    void RequestShutdown();

    /// <summary>
    /// Replaces the current agent session with the specified session (e.g., after importing
    /// a serialized session from a file).
    /// </summary>
    /// <param name="newSession">The new session to use.</param>
    Task ReplaceSessionAsync(AgentSession newSession);
}
