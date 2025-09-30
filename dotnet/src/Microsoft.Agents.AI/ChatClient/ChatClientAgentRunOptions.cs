// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Chat client agent run options.
/// </summary>
public sealed class ChatClientAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentRunOptions"/> class.
    /// </summary>
    /// <param name="chatOptions">Optional chat options to pass to the agent's invocation.</param>
    public ChatClientAgentRunOptions(ChatOptions? chatOptions = null)
    {
        this.ChatOptions = chatOptions;
    }

    /// <summary>Gets or sets optional chat options to pass to the agent's invocation.</summary>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Gets or sets the factory method used to modify instances of <see cref="IChatClient"/> per-request.
    /// </summary>
    public Func<IChatClient, IChatClient>? ChatClientFactory { get; set; }
}
