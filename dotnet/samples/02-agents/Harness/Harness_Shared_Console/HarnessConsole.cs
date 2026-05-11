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

        System.Console.WriteLine($"=== {title} ===");
        System.Console.WriteLine(userPrompt);

        var todoProvider = agent.GetService<TodoProvider>();
        var modeProvider = agent.GetService<AgentModeProvider>();

        // Build command handlers.
        var commandHandlers = new List<ICommandHandler>
        {
            new TodoCommandHandler(todoProvider),
            new ModeCommandHandler(modeProvider, options.ModeColors),
        };

        var commands = commandHandlers
            .Select(h => h.GetHelpText())
            .Where(t => t is not null)
            .Append("exit (quit)");

        System.Console.WriteLine($"Commands: {string.Join(", ", commands)}");
        System.Console.WriteLine();

        AgentSession session = await agent.CreateSessionAsync();
        using var writer = new ConsoleWriter(options.ModeColors);
        writer.CurrentMode = modeProvider?.GetMode(session);

        string prompt = BuildUserPrompt(modeProvider, session);
        string? userInput = await writer.ReadLineAsync(prompt);

        // Main loop to run a command or agent and get the next user command/input.
        while (!string.IsNullOrWhiteSpace(userInput) && !userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
        {
            // Check command handlers first — first one to handle wins.
            bool handled = false;
            foreach (var handler in commandHandlers)
            {
                if (await handler.TryHandleAsync(userInput, session).ConfigureAwait(false))
                {
                    handled = true;
                    break;
                }
            }

            if (!handled)
            {
                await RunAgentTurnAsync(agent, session, modeProvider, options, writer, userInput);
            }

            writer.CurrentMode = modeProvider?.GetMode(session);
            prompt = BuildUserPrompt(modeProvider, session);
            userInput = await writer.ReadLineAsync(prompt);
        }

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
        HarnessConsoleOptions options,
        ConsoleWriter writer,
        string userInput)
    {
        IList<ChatMessage>? nextMessages = [new ChatMessage(ChatRole.User, userInput)];

        while (nextMessages is not null)
        {
            // Build observers for this invocation (may change between iterations due to mode changes).
            var observers = CreateObservers(options, modeProvider, session);

            // Build run options — observers may inject ResponseFormat, etc.
            var runOptions = new AgentRunOptions();
            foreach (var observer in observers)
            {
                observer.ConfigureRunOptions(runOptions);
            }

            // Stream the response, fanning out to all observers.
            writer.CurrentMode = modeProvider?.GetMode(session);
            writer.WriteResponseHeader();

            try
            {
                await foreach (var update in agent.RunStreamingAsync(nextMessages, session, runOptions))
                {
                    // Update mode color if the mode changed during streaming.
                    if (modeProvider is not null)
                    {
                        string currentMode = modeProvider.GetMode(session);
                        if (currentMode != writer.CurrentMode)
                        {
                            writer.CurrentMode = currentMode;
                        }
                    }

                    foreach (var content in update.Contents)
                    {
                        foreach (var observer in observers)
                        {
                            await observer.OnContentAsync(writer, content);
                        }
                    }

                    if (!string.IsNullOrEmpty(update.Text))
                    {
                        foreach (var observer in observers)
                        {
                            await observer.OnTextAsync(writer, update.Text);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                await writer.WriteInfoLineAsync($"❌ Stream error: {ex.GetType().Name}:\n{ex}", ConsoleColor.Red);
            }

            // Collect messages from all observers.
            var combinedMessages = new List<ChatMessage>();
            bool hasObserverMessages = false;
            foreach (var observer in observers)
            {
                var messages = await observer.OnStreamCompleteAsync(writer, agent, session, options);
                if (messages is { Count: > 0 })
                {
                    combinedMessages.AddRange(messages);
                    hasObserverMessages = true;
                }
            }

            await writer.WriteStreamFooterAsync(hasFollowUpMessages: hasObserverMessages);
            nextMessages = combinedMessages.Count > 0 ? combinedMessages : null;
        }
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

        // Add the appropriate output observer based on the current mode.
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

    private static string BuildUserPrompt(AgentModeProvider? modeProvider, AgentSession session)
    {
        if (modeProvider is not null)
        {
            string mode = modeProvider.GetMode(session);
            return $"[{mode}] You: ";
        }

        return "You: ";
    }
}
