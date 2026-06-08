// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Harness.ConsoleReactiveComponents;
using Microsoft.Agents.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Provides a reusable interactive console loop for running an <see cref="AIAgent"/>
/// with streaming output, extensible observers, and mode-aware interaction strategies.
/// </summary>
public static class HarnessConsole
{
    /// <summary>
    /// Runs an interactive console session with the specified agent.
    /// Constructs the reactive UI component and the <see cref="HarnessAgentRunner"/>,
    /// wires them together, and awaits the component's <see cref="HarnessAppComponent.ShutdownTask"/>
    /// (which completes when the user types <c>/exit</c>).
    /// </summary>
    /// <param name="agent">The agent to interact with.</param>
    /// <param name="userPrompt">A short prompt to the user, displayed as a placeholder in the input area.</param>
    /// <param name="options">Optional configuration options for the console session.</param>
    public static async Task RunAgentAsync(AIAgent agent, string userPrompt, HarnessConsoleOptions? options = null)
    {
        options ??= new();

        System.Console.OutputEncoding = Encoding.UTF8;

        // Null means use defaults; an explicit (possibly empty) list means use exactly what was provided.
        var observers = options.Observers
            ?? HarnessConsoleOptions.BuildDefaultObservers();
        var commandHandlers = options.CommandHandlers
            ?? HarnessConsoleOptions.BuildDefaultCommandHandlers(agent, options.ModeColors);

        var modeProvider = agent.GetService<AgentModeProvider>();
        var messageInjector = agent.GetService<MessageInjectingChatClient>();

        AgentSession session = options.SessionFactory is not null
            ? await options.SessionFactory(agent)
            : await agent.CreateSessionAsync();

        using var component = new HarnessAppComponent(
            placeholder: userPrompt,
            initialMode: modeProvider?.GetMode(session),
            inputEnabled: messageInjector is not null,
            runnerFactory: ux => new HarnessAgentRunner(
                agent: agent,
                session: session,
                modeProvider: modeProvider,
                messageInjector: messageInjector,
                commandHandlers: commandHandlers,
                observers: observers,
                ux: ux),
            modeColors: options.ModeColors);

        // Trigger the initial render of the component now that state is seeded.
        component.Render();

        try
        {
            await component.ShutdownTask.ConfigureAwait(false);
        }
        finally
        {
            component.Deactivate();
        }

        System.Console.ResetColor();
        System.Console.Write(AnsiEscapes.ResetScrollRegion);
        System.Console.Write(AnsiEscapes.EraseScrollbackBuffer);
        System.Console.Write(AnsiEscapes.EraseEntireScreen);
        System.Console.Write(AnsiEscapes.MoveCursor(1, 1));
        System.Console.WriteLine("Goodbye!");
    }
}
