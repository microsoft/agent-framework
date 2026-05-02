// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays reasoning content in dark magenta from the response stream.
/// </summary>
internal sealed class ReasoningDisplayObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnContentAsync(ConsoleWriter writer, AIContent content)
    {
        if (content is TextReasoningContent reasoning && !string.IsNullOrEmpty(reasoning.Text))
        {
            await writer.WriteTextAsync(reasoning.Text, ConsoleColor.DarkMagenta);
        }
    }
}
