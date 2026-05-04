// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles a console command (e.g., /todos, /mode). Command handlers are checked
/// in order before user input is sent to the agent. The first handler that
/// accepts the input prevents further handlers from being checked.
/// </summary>
public interface ICommandHandler
{
    /// <summary>
    /// Gets the help text for this command, displayed in the console header.
    /// Returns <see langword="null"/> if the command is not currently available.
    /// </summary>
    /// <returns>Help text like <c>"/todos (show todo list)"</c>, or <see langword="null"/>.</returns>
    string? GetHelpText();

    /// <summary>
    /// Attempts to handle the given user input.
    /// </summary>
    /// <param name="input">The raw user input string.</param>
    /// <param name="session">The current agent session.</param>
    /// <returns><see langword="true"/> if this handler handled the input; <see langword="false"/> otherwise.</returns>
    bool TryHandle(string input, AgentSession session);
}
