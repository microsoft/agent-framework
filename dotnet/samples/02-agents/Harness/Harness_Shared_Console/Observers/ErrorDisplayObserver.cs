// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays error content (❌) from the response stream.
/// </summary>
public sealed class ErrorDisplayObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is ErrorContent errorContent)
        {
            string errorText = $"❌ Error: {errorContent.Message}";
            if (!string.IsNullOrWhiteSpace(errorContent.ErrorCode))
            {
                errorText += $" (code: {errorContent.ErrorCode})";
            }

            if (!string.IsNullOrWhiteSpace(errorContent.Details))
            {
                errorText += $" details: {errorContent.Details}";
            }

            await ux.WriteInfoLineAsync(errorText, ConsoleColor.Red);
        }
    }
}
