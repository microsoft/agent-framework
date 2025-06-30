// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Chat client agent run options.
/// </summary>
internal sealed class ChatClientAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentRunOptions"/> class.
    /// </summary>
    /// <param name="source">Optional source <see cref="AgentRunOptions"/> to clone.</param>
    /// <param name="chatOptions">Optional chat options to pass to the agent's invocation.</param>
    internal ChatClientAgentRunOptions(AgentRunOptions? source = null, ChatOptions? chatOptions = null)
    {
        this.OnIntermediateMessages = source?.OnIntermediateMessages;
        this.ChatOptions = chatOptions;
    }

    /// <summary>
    /// Gets or sets optional chat options to pass to the agent's invocation
    /// </summary>
    internal ChatOptions? ChatOptions { get; }
}
