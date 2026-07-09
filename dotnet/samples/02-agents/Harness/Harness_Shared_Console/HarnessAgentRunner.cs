// Copyright (c) Microsoft. All rights reserved.

using Harness.Shared.Console.Commands;
using Harness.Shared.Console.Observers;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Orchestrates agent invocations driven by user-input events from the UI.
/// The component invokes the runner's input handlers (<see cref="OnUserInputAsync"/>,
/// <see cref="OnStreamingInputAsync"/>, <see cref="StartAgentTurnAsync"/>) directly;
/// the runner mutates UI state through the supplied <see cref="IUXStateDriver"/>.
/// All per-turn follow-up state (pending questions and accumulated responses) lives
/// in the component's state record — the runner reads/writes it exclusively through
/// the driver and holds no per-turn fields itself.
/// </summary>
public sealed class HarnessAgentRunner : IDisposable
{
    private readonly AIAgent _agent;
    private readonly AgentModeProvider? _modeProvider;
    private readonly MessageInjectingChatClient? _messageInjector;
    private readonly IReadOnlyList<CommandHandler> _commandHandlers;
    private readonly IReadOnlyList<ConsoleObserver> _observers;
    private readonly IUXStateDriver _ux;
    private readonly SemaphoreSlim _inputGate = new(1, 1);

    private AgentSession _session;

    /// <summary>
    /// Initializes a new instance of the <see cref="HarnessAgentRunner"/> class.
    /// </summary>
    public HarnessAgentRunner(
        AIAgent agent,
        AgentSession session,
        AgentModeProvider? modeProvider,
        MessageInjectingChatClient? messageInjector,
        IReadOnlyList<CommandHandler> commandHandlers,
        IReadOnlyList<ConsoleObserver> observers,
        IUXStateDriver ux)
    {
        this._agent = agent;
        this._session = session;
        this._modeProvider = modeProvider;
        this._messageInjector = messageInjector;
        this._commandHandlers = commandHandlers;
        this._observers = observers;
        this._ux = ux;

        this.HelpText = string.Join(
            ", ",
            commandHandlers
                .Select(h => h.GetHelpText())
                .Where(t => t is not null)!);
    }

    /// <summary>
    /// Gets the help text describing all available commands (joined by ", "), suitable
    /// for display in the mode-and-help bar. Computed from the supplied
    /// <c>commandHandlers</c>.
    /// </summary>
    public string HelpText { get; }

    /// <summary>
    /// Replaces the current session with the specified session. Used by the UX driver
    /// when importing a serialized session. This method is always called from within
    /// a command handler (which already holds the input gate), so no additional
    /// synchronization is needed.
    /// </summary>
    /// <param name="newSession">The new session to use.</param>
    internal Task ReplaceSessionAsync(AgentSession newSession)
    {
        this._session = newSession;
        return Task.CompletedTask;
    }

    /// <inheritdoc/>
    public void Dispose() => this._inputGate.Dispose();

    /// <summary>
    /// Handles a top-level user input submission (TextInput mode, no pending question).
    /// Dispatches to command handlers, or starts an agent turn.
    /// </summary>
    internal async Task OnUserInputAsync(string text)
    {
        await this._inputGate.WaitAsync().ConfigureAwait(false);
        try
        {
            this._ux.WriteUserInputEcho(text);

            foreach (var handler in this._commandHandlers)
            {
                if (await handler.TryHandleAsync(text, this._session, this._ux).ConfigureAwait(false))
                {
                    this._ux.CurrentMode = this._modeProvider?.GetMode(this._session);
                    return;
                }
            }

            await this.RunAgentLoopAsync([new ChatMessage(ChatRole.User, text)]).ConfigureAwait(false);
        }
        finally
        {
            this._inputGate.Release();
        }
    }

    /// <summary>
    /// Handles a user input submission while an agent turn is streaming. The text is
    /// enqueued via the <see cref="MessageInjectingChatClient"/> so it can be picked up
    /// by the agent on its next opportunity.
    /// </summary>
    internal Task OnStreamingInputAsync(string text)
    {
        if (this._messageInjector is null)
        {
            return Task.CompletedTask;
        }

        this._messageInjector.EnqueueMessages(this._session, [new ChatMessage(ChatRole.User, text)]);
        this._ux.SetQueuedMessages(this._messageInjector.GetPendingMessages(this._session));
        return Task.CompletedTask;
    }

    /// <summary>
    /// Resumes (or completes) a turn after the user has answered all pending follow-up
    /// questions. The component invokes this with the messages drained from
    /// <see cref="IUXStateDriver.TakeFollowUpResponses"/>; an empty list simply ends
    /// the streaming display state without invoking the agent.
    /// </summary>
    internal async Task StartAgentTurnAsync(IList<ChatMessage> messages)
    {
        await this._inputGate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (messages.Count == 0)
            {
                this.CompleteTurn();
                return;
            }

            await this.RunAgentLoopAsync(messages).ConfigureAwait(false);
        }
        finally
        {
            this._inputGate.Release();
        }
    }

    private async Task RunAgentLoopAsync(IList<ChatMessage> messages)
    {
        IList<ChatMessage>? nextMessages = messages;
        IReadOnlyList<ChatMessage> lastPendingMessages = this._messageInjector?.GetPendingMessages(this._session) ?? [];

        while (nextMessages is not null)
        {
            var runOptions = new AgentRunOptions();
            foreach (var observer in this._observers)
            {
                observer.ConfigureRunOptions(runOptions, this._agent, this._session);
            }

            this._ux.CurrentMode = this._modeProvider?.GetMode(this._session);
            this._ux.BeginStreaming();
            this._ux.BeginStreamingOutput();

            try
            {
                await foreach (var update in this._agent.RunStreamingAsync(nextMessages, this._session, runOptions))
                {
                    if (this._modeProvider is not null)
                    {
                        string currentMode = this._modeProvider.GetMode(this._session);
                        if (currentMode != this._ux.CurrentMode)
                        {
                            this._ux.CurrentMode = currentMode;
                        }
                    }

                    foreach (var content in update.Contents)
                    {
                        foreach (var observer in this._observers)
                        {
                            await observer.OnContentAsync(this._ux, content, this._agent, this._session).ConfigureAwait(false);
                        }
                    }

                    foreach (var observer in this._observers)
                    {
                        await observer.OnResponseUpdateAsync(this._ux, update, this._agent, this._session).ConfigureAwait(false);
                    }

                    if (!string.IsNullOrEmpty(update.Text))
                    {
                        foreach (var observer in this._observers)
                        {
                            await observer.OnTextAsync(this._ux, update.Text, this._agent, this._session).ConfigureAwait(false);
                        }
                    }

                    this.SyncQueuedMessageDisplay(ref lastPendingMessages);
                }
            }
            catch (Exception ex)
            {
                await this._ux.WriteInfoLineAsync($"❌ Stream error: {ex.GetType().Name}:\n{ex}", ConsoleColor.Red).ConfigureAwait(false);
            }

            // Final sync after streaming.
            this.SyncQueuedMessageDisplay(ref lastPendingMessages);

            this._ux.StopSpinner();
            await this._ux.EndStreamingOutputAsync().ConfigureAwait(false);

            // Collect FollowUpActions from each observer.
            var directMessages = new List<ChatMessage>();
            var questions = new List<FollowUpQuestion>();
            foreach (var observer in this._observers)
            {
                var actions = await observer.OnStreamCompleteAsync(this._ux, this._agent, this._session).ConfigureAwait(false);
                if (actions is null)
                {
                    continue;
                }

                foreach (var action in actions)
                {
                    switch (action)
                    {
                        case FollowUpMessage msg:
                            directMessages.Add(msg.Message);
                            break;
                        case FollowUpQuestion q:
                            questions.Add(q);
                            break;
                    }
                }
            }

            bool hasFollowUpActions = directMessages.Count > 0 || questions.Count > 0;
            await this._ux.WriteNoTextWarningAsync(hasFollowUpActions).ConfigureAwait(false);

            // Add any direct messages to the accumulator regardless of whether questions follow —
            // they're sent on the next agent invocation, either by us (if no questions) or by
            // the component (after the user finishes answering, via StartAgentTurnAsync).
            foreach (var msg in directMessages)
            {
                this._ux.AddFollowUpResponse(msg);
            }

            if (questions.Count > 0)
            {
                // Pause: hand control back to the UX to collect answers.
                this._ux.QueueFollowUpQuestions(questions);
                return;
            }

            // No questions to ask — drain anything we just accumulated and loop with it.
            IReadOnlyList<ChatMessage> drained = this._ux.TakeFollowUpResponses();
            nextMessages = drained.Count > 0 ? [.. drained] : null;
        }

        this.CompleteTurn();
    }

    private void CompleteTurn()
    {
        this._ux.EndStreaming();
        this._ux.CurrentMode = this._modeProvider?.GetMode(this._session);
    }

    /// <summary>
    /// Synchronizes the queued items display with the message injector's pending messages.
    /// Messages that have been consumed (drained by the service) are echoed to the output
    /// area as regular user-input entries.
    /// </summary>
    private void SyncQueuedMessageDisplay(ref IReadOnlyList<ChatMessage> lastPendingMessages)
    {
        if (this._messageInjector is null)
        {
            return;
        }

        var pending = this._messageInjector.GetPendingMessages(this._session);

        int consumedCount = lastPendingMessages.Count - pending.Count;
        for (int i = 0; i < consumedCount && i < lastPendingMessages.Count; i++)
        {
            string text = lastPendingMessages[i].Text ?? string.Empty;
            this._ux.WriteUserInputEcho(text);
        }

        lastPendingMessages = pending;
        this._ux.SetQueuedMessages(pending);
    }
}
