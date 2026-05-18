// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Commands;

/// <summary>
/// Handles the <c>/exit</c> command to shut down the console application.
/// </summary>
public sealed class ExitCommandHandler : CommandHandler
{
    /// <inheritdoc/>
    public override string? GetHelpText() => "/exit (quit)";

    /// <inheritdoc/>
    public override ValueTask<bool> TryHandleAsync(string input, AgentSession session, IUXStateDriver ux)
    {
        if (!input.Equals("/exit", StringComparison.OrdinalIgnoreCase))
        {
            return new ValueTask<bool>(false);
        }

        ux.RequestShutdown();
        return new ValueTask<bool>(true);
    }
}
