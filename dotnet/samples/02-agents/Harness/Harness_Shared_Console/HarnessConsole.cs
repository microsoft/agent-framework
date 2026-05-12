// Copyright (c) Microsoft. All rights reserved.

using Harness.Shared.Console.Commands;
using Harness.Shared.Console.Observers;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Provides a reusable interactive console loop for running an <see cref="AIAgent"/>
/// with streaming output, extensible observers, and mode-aware interaction strategies.
/// </summary>
public static class HarnessConsole
{
    /// <summary>
    /// Runs an interactive console session with the specified agent.
    /// Supports streaming output, tool call display, spinner animation,
    /// optional planning UX with structured output, and the <c>/todos</c> command.
    /// </summary>
    /// <param name="agent">The agent to interact with.</param>
    /// <param name="title">The title displayed in the console header.</param>
    /// <param name="userPrompt">A short prompt to the user, displayed below the title.</param>
    /// <param name="options">Optional configuration options for the console session.</param>
    public static async Task RunAgentAsync(AIAgent agent, string title, string userPrompt, HarnessConsoleOptions? options = null)
    {
        options ??= new();

        if (options.EnablePlanningUx
            && (string.IsNullOrWhiteSpace(options.PlanningModeName) || string.IsNullOrWhiteSpace(options.ExecutionModeName)))
        {
            throw new ArgumentException(
                "When EnablePlanningUx is true, both PlanningModeName and ExecutionModeName must be configured.",
                nameof(options));
        }

        var todoProvider = agent.GetService<TodoProvider>();
        var modeProvider = agent.GetService<AgentModeProvider>();
        var messageInjector = agent.GetService<MessageInjectingChatClient>();

        var commandHandlers = new List<CommandHandler>
        {
            new TodoCommandHandler(todoProvider),
            new ModeCommandHandler(modeProvider, options.ModeColors),
        };

        AgentSession session = await agent.CreateSessionAsync();

        using var ux = new HarnessUXContainer(
            placeholder: userPrompt,
            initialMode: modeProvider?.GetMode(session),
            inputEnabled: messageInjector is not null,
            modeColors: options.ModeColors);

        // Streaming-mode submissions are enqueued for injection; the queued display
        // is then refreshed from the injector's current pending list.
        ux.StreamingInputReceived += (sender, e) =>
        {
            if (messageInjector is null)
            {
                return;
            }

            messageInjector.EnqueueMessages(session, [new ChatMessage(ChatRole.User, e.Text)]);
            ux.ShowQueuedMessages(messageInjector.GetPendingMessages(session));
        };

        var commandHelp = commandHandlers
            .Select(h => h.GetHelpText())
            .Where(t => t is not null)
            .Append("exit (quit)")!;

        ux.Initialize(title, commandHelp!, messageInjector is not null);

        string userInput = await ux.WaitForInputAsync();

        while (!string.IsNullOrWhiteSpace(userInput) && !userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
        {
            ux.WriteUserInputEcho(userInput);

            // Check command handlers first — first one to handle wins.
            bool handled = false;
            foreach (var handler in commandHandlers)
            {
                if (await handler.TryHandleAsync(userInput, session, ux).ConfigureAwait(false))
                {
                    handled = true;
                    break;
                }
            }

            if (!handled)
            {
                await RunAgentTurnAsync(agent, session, modeProvider, messageInjector, options, ux, userInput);
            }

            ux.CurrentMode = modeProvider?.GetMode(session);
            userInput = await ux.WaitForInputAsync();
        }

        ux.Deactivate();
        System.Console.ResetColor();
        System.Console.WriteLine("Goodbye!");
    }

    /// <summary>
    /// Runs one or more agent invocations for a single user turn, using the current
    /// observers. Re-invokes automatically for tool approvals and mode-driven follow-ups
    /// (e.g., planning clarification loops).
    /// </summary>
    private static async Task RunAgentTurnAsync(
        AIAgent agent,
        AgentSession session,
        AgentModeProvider? modeProvider,
        MessageInjectingChatClient? messageInjector,
        HarnessConsoleOptions options,
        HarnessUXContainer ux,
        string userInput)
    {
        IList<ChatMessage>? nextMessages = [new ChatMessage(ChatRole.User, userInput)];
        IReadOnlyList<ChatMessage> lastPendingMessages = messageInjector?.GetPendingMessages(session) ?? [];

        while (nextMessages is not null)
        {
            var observers = CreateObservers(options, modeProvider, session);

            var runOptions = new AgentRunOptions();
            foreach (var observer in observers)
            {
                observer.ConfigureRunOptions(runOptions);
            }

            ux.CurrentMode = modeProvider?.GetMode(session);
            ux.BeginStreaming();
            ux.BeginStreamingOutput();

            try
            {
                await foreach (var update in agent.RunStreamingAsync(nextMessages, session, runOptions))
                {
                    // Update mode color if the mode changed during streaming.
                    if (modeProvider is not null)
                    {
                        string currentMode = modeProvider.GetMode(session);
                        if (currentMode != ux.CurrentMode)
                        {
                            ux.CurrentMode = currentMode;
                        }
                    }

                    foreach (var content in update.Contents)
                    {
                        foreach (var observer in observers)
                        {
                            await observer.OnContentAsync(ux, content);
                        }
                    }

                    if (!string.IsNullOrEmpty(update.Text))
                    {
                        foreach (var observer in observers)
                        {
                            await observer.OnTextAsync(ux, update.Text);
                        }
                    }

                    SyncQueuedMessageDisplay(messageInjector, session, ux, ref lastPendingMessages);
                }
            }
            catch (Exception ex)
            {
                await ux.WriteInfoLineAsync($"❌ Stream error: {ex.GetType().Name}:\n{ex}", ConsoleColor.Red);
            }

            // Final sync after streaming — messages may have been consumed during the last iteration.
            SyncQueuedMessageDisplay(messageInjector, session, ux, ref lastPendingMessages);

            // Stop spinner before observer completions (which may prompt for input).
            ux.StopSpinner();

            // Close the streaming output to provide visual separation from observer output.
            await ux.EndStreamingOutputAsync();

            var combinedMessages = new List<ChatMessage>();
            bool hasObserverMessages = false;
            foreach (var observer in observers)
            {
                var messages = await observer.OnStreamCompleteAsync(ux, agent, session, options);
                if (messages is { Count: > 0 })
                {
                    combinedMessages.AddRange(messages);
                    hasObserverMessages = true;
                }
            }

            await ux.WriteNoTextWarningAsync(hasFollowUpMessages: hasObserverMessages);

            ux.EndStreaming();

            nextMessages = combinedMessages.Count > 0 ? combinedMessages : null;
        }
    }

    /// <summary>
    /// Synchronizes the queued items display with the message injector's pending messages.
    /// Messages that have been consumed (drained by the service) are echoed to the output
    /// area as regular user-input entries.
    /// </summary>
    private static void SyncQueuedMessageDisplay(
        MessageInjectingChatClient? messageInjector,
        AgentSession session,
        HarnessUXContainer ux,
        ref IReadOnlyList<ChatMessage> lastPendingMessages)
    {
        if (messageInjector is null)
        {
            return;
        }

        var pending = messageInjector.GetPendingMessages(session);

        // If previously pending messages exceed current pending count, some were consumed.
        int consumedCount = lastPendingMessages.Count - pending.Count;
        for (int i = 0; i < consumedCount && i < lastPendingMessages.Count; i++)
        {
            string text = lastPendingMessages[i].Text ?? string.Empty;
            ux.WriteUserInputEcho(text);
        }

        lastPendingMessages = pending;
        ux.ShowQueuedMessages(pending);
    }

    private static List<ConsoleObserver> CreateObservers(HarnessConsoleOptions options, AgentModeProvider? modeProvider, AgentSession session)
    {
        var observers = new List<ConsoleObserver>
        {
            new ToolCallDisplayObserver(),
            new ToolApprovalObserver(),
            new ErrorDisplayObserver(),
            new ReasoningDisplayObserver(),
            new UsageDisplayObserver(options.MaxContextWindowTokens, options.MaxOutputTokens),
        };

        if (options.EnablePlanningUx
            && modeProvider is not null
            && string.Equals(modeProvider.GetMode(session), options.PlanningModeName, StringComparison.OrdinalIgnoreCase))
        {
            observers.Add(new PlanningOutputObserver(modeProvider));
        }
        else
        {
            observers.Add(new TextOutputObserver());
        }

        return observers;
    }
}
