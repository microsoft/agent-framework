// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Base class for console command handlers (e.g., /todos, /mode). Command handlers
/// are checked in order before user input is sent to the agent. The first handler
/// that accepts the input prevents further handlers from being checked.
/// </summary>
public abstract class CommandHandler
{
    /// <summary>
    /// Gets the help text for this command, displayed in the mode-and-help bar.
    /// Returns <see langword="null"/> if the command is not currently available.
    /// </summary>
    /// <returns>Help text like <c>"/todos (show todo list)"</c>, or <see langword="null"/>.</returns>
    public abstract string? GetHelpText();

    /// <summary>
    /// Attempts to handle the given user input.
    /// </summary>
    /// <param name="input">The raw user input string.</param>
    /// <param name="session">The current agent session.</param>
    /// <param name="ux">The UX container for rendering output.</param>
    /// <returns><see langword="true"/> if this handler handled the input; <see langword="false"/> otherwise.</returns>
    public abstract ValueTask<bool> TryHandleAsync(string input, AgentSession session, HarnessUXContainer ux);
}
