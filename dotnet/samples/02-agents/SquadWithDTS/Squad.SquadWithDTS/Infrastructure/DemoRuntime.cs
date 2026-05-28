// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI;

namespace Squad.SquadWithDTS.Infrastructure;

/// <summary>
/// Shared runtime helpers used by AI-powered executors.
/// </summary>
internal static class DemoRuntime
{
    /// <summary>
    /// Runs <paramref name="agent"/> with <paramref name="prompt"/>, collecting
    /// all streamed chunks into a single string.
    /// </summary>
    internal static async Task<string> RunAgentAsync(
        AIAgent agent,
        string prompt,
        CancellationToken cancellationToken = default)
    {
        var sb = new System.Text.StringBuilder();
        await foreach (var chunk in agent.RunAsync(prompt, cancellationToken: cancellationToken))
        {
            sb.Append(chunk);
        }
        return sb.ToString().Trim();
    }
}
