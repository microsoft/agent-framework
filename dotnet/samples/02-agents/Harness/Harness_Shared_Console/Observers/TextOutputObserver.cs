// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Streams agent text output directly to the console.
/// Used in normal (non-planning) mode.
/// </summary>
public sealed class TextOutputObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnTextAsync(IUXStateDriver ux, string text, AIAgent agent, AgentSession session)
    {
        await ux.WriteTextAsync(text);
    }
}
