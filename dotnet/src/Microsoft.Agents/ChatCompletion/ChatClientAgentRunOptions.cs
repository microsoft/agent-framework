// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents;

/// <summary>
/// Chat client agent run options.
/// </summary>
public sealed class ChatClientAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Gets or sets optional chat options to pass to the agent's invocation
    /// </summary>
    public ChatOptions? ChatOptions { get; set; }
}
