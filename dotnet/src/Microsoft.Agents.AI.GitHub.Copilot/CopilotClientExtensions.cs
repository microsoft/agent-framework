// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.GitHub.Copilot;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using GitHub.Copilot.Rpc;

namespace GitHub.Copilot;

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
    /// <param name="sessionConfig">Session configuration for the agent. Must include <c>SessionConfig.OnPermissionRequest</c> as required by the GitHub Copilot SDK.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the GitHub Copilot client.</returns>
    public static AIAgent AsAIAgent(
        this CopilotClient client,
        SessionConfig sessionConfig,
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
    /// <param name="onPermissionRequest">Handler called before each tool execution to approve or deny it. Required by the GitHub Copilot SDK.</param>
    /// <param name="ownsClient">Whether the agent owns the client and should dispose it. Default is false.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="tools">The tools to make available to the agent.</param>
    /// <param name="instructions">Optional instructions to append as a system message.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the GitHub Copilot client.</returns>
    public static AIAgent AsAIAgent(
        this CopilotClient client,
        Func<PermissionRequest, PermissionInvocation, Task<PermissionDecision>> onPermissionRequest,
        bool ownsClient = false,
        string? id = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        string? instructions = null)
    {
        Throw.IfNull(client);

        return new GitHubCopilotAgent(client, onPermissionRequest, ownsClient, id, name, description, tools, instructions);
    }
}
