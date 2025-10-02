// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides specialized run options for <see cref="ChatClientAgent"/> instances, extending the base agent run options with chat-specific configuration.
/// </summary>
/// <remarks>
/// This class extends <see cref="AgentRunOptions"/> to provide additional configuration options that are specific to
/// chat client agents, in particular <see cref="ChatOptions"/>.
/// </remarks>
public sealed class ChatClientAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentRunOptions"/> class.
    /// </summary>
    /// <param name="chatOptions">
    /// Optional chat options to customize the behavior of the chat client during this specific agent invocation.
    /// These options will be merged with the default chat options configured for the agent.
    /// </param>
    public ChatClientAgentRunOptions(ChatOptions? chatOptions = null)
    {
        this.ChatOptions = chatOptions;
    }

    /// <summary>
    /// Gets or sets the chat options to apply to the agent invocation.
    /// </summary>
    /// <value>
    /// Chat options that control various aspects of the chat client's behavior, such as temperature, max tokens,
    /// tools, instructions, and other model-specific parameters. If <see langword="null"/>, the agent's default
    /// chat options will be used.
    /// </value>
    /// <remarks>
    /// These options are specific to this invocation and will be combined with the agent's default chat options.
    /// If both the agent and this run options specify the same option, the run options value typically takes precedence.
    /// In the case of collections, like <see cref="ChatOptions.Tools"/>, the collections will be unioned.
    /// </remarks>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Gets or sets a factory function that can replace (typically via decorators) the chat client on a per-request basis.
    /// </summary>
    /// <value>
    /// A function that receives the agent's configured chat client and returns a potentially modified or entirely
    /// different chat client to use for this specific invocation. If <see langword="null"/>, the agent's default
    /// chat client will be used without modification.
    /// </value>
    public Func<IChatClient, IChatClient>? ChatClientFactory { get; set; }
}
