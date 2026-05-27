// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays reasoning content in dark magenta from the response stream.
/// </summary>
public sealed class ReasoningDisplayObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is TextReasoningContent reasoning && !string.IsNullOrEmpty(reasoning.Text))
        {
            await ux.WriteTextAsync(reasoning.Text, ConsoleColor.DarkMagenta);
        }
    }
}
