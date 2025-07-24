// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Chat client agent run options.
/// </summary>
public sealed class ChatClientAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentRunOptions"/> class.
    /// </summary>
    /// <param name="chatOptions">Optional chat options to pass to the agent's invocation.</param>
    public ChatClientAgentRunOptions(ChatOptions? chatOptions = null) :
        this(null, chatOptions)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentRunOptions"/> class.
    /// </summary>
    /// <param name="source">Optional source <see cref="AgentRunOptions"/> to clone.</param>
    /// <param name="chatOptions">Optional chat options to pass to the agent's invocation.</param>
    internal ChatClientAgentRunOptions(AgentRunOptions? source, ChatOptions? chatOptions = null)
    {
        this.ChatOptions = chatOptions;
    }

    /// <summary>
    /// Gets or sets optional chat options to pass to the agent's invocation
    /// </summary>
    public ChatOptions? ChatOptions { get; set; }
}
