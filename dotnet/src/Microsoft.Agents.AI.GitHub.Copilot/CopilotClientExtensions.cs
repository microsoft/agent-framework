// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.GitHub.Copilot;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace GitHub.Copilot.SDK;

/// <summary>
/// Provides extension methods for <see cref="CopilotClient"/>
/// to simplify the creation of GitHub Copilot agents.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between GitHub Copilot SDK client objects
/// and the Microsoft Agent Framework.
/// <para>
/// They allow developers to easily create AI agents that can interact
/// with GitHub Copilot by handling the conversion from Copilot clients to
/// <see cref="GitHubCopilotAgent"/> instances that implement the <see cref="AIAgent"/> interface.
/// </para>
/// </remarks>
public static class CopilotClientExtensions
{
    /// <summary>
    /// Retrieves an instance of <see cref="AIAgent"/> for a GitHub Copilot client.
    /// </summary>
    /// <param name="client">The <see cref="CopilotClient"/> to use for the agent.</param>
    /// <param name="sessionConfig">Optional session configuration for the agent.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the GitHub Copilot client.</returns>
    public static AIAgent AsAIAgent(
        this CopilotClient client,
        SessionConfig? sessionConfig = null,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null)
    {
        Throw.IfNull(client);

        return new GitHubCopilotAgent(client, sessionConfig, ownsClient, id, name, description);
    }

    /// <summary>
    /// Retrieves an instance of <see cref="AIAgent"/> for a GitHub Copilot client.
    /// </summary>
    /// <param name="client">The <see cref="CopilotClient"/> to use for the agent.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="tools">The tools to make available to the agent.</param>
    /// <param name="instructions">Optional instructions to append as a system message.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the GitHub Copilot client.</returns>
    public static AIAgent AsAIAgent(
        this CopilotClient client,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        string? instructions = null)
    {
        Throw.IfNull(client);

        return new GitHubCopilotAgent(client, ownsClient, id, name, description, tools, instructions);
    }
}
