// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents metadata for a chat client agent, including its identifier, name, instructions, and description.
/// </summary>
/// <remarks>
/// This class is used to encapsulate information about a chat client agent, such as its unique
/// identifier, display name, operational instructions, and a descriptive summary. It can be used to store and transfer
/// agent-related metadata within a chat application.
/// </remarks>
public sealed class ChatClientAgentOptions
{
    /// <summary>
    /// Gets or sets the agent id.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the agent name.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the agent description.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the default chatOptions to use.
    /// </summary>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="ChatHistoryProvider"/> instance to use for providing chat history for this agent.
    /// </summary>
    public ChatHistoryProvider? ChatHistoryProvider { get; set; }

    /// <summary>
    /// Gets or sets the list of <see cref="AIContextProvider"/> instances to use for providing additional context for each agent run.
    /// </summary>
    public IEnumerable<AIContextProvider>? AIContextProviders { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to use the provided <see cref="IChatClient"/> instance as is,
    /// without applying any default decorators.
    /// </summary>
    /// <remarks>
    /// By default the <see cref="ChatClientAgent"/> applies decorators to the provided <see cref="IChatClient"/>
    /// for doing for example automatic function invocation. Setting this property to <see langword="true"/>
    /// disables adding these default decorators.
    /// Disabling is recommended if you want to decorate the <see cref="IChatClient"/> with different decorators
    /// than the default ones. The provided <see cref="IChatClient"/> instance should then already be decorated
    /// with the desired decorators.
    /// </remarks>
    public bool UseProvidedChatClientAsIs { get; set; }

    /// <summary>
    /// Creates a new instance of <see cref="ChatClientAgentOptions"/> with the same values as this instance.
    /// </summary>
    public ChatClientAgentOptions Clone()
        => new()
        {
            Id = this.Id,
            Name = this.Name,
            Description = this.Description,
            ChatOptions = this.ChatOptions?.Clone(),
            ChatHistoryProvider = this.ChatHistoryProvider,
            AIContextProviders = this.AIContextProviders is null ? null : new List<AIContextProvider>(this.AIContextProviders),
        };
}
